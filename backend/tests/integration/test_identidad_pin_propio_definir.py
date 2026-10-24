# ruff: noqa: F811
"""Tarea 6.5 (change 18b; `design.md` D21 parte B y D24; spec `identidad/pin-de-autorizacion`):
`PIN_AUTORIZACION_PROPIO_DEFINIR` v1, "Mi PIN": cada supervisor define su propio PIN de
autorización reautenticándose con su contraseña.

`POST /api/v1/yo/pin-autorizacion` (204). El usuario sale del token. El cuerpo trae `pin` y
`password_actual`, que la ruta separa antes de armar el contenido y la huella (dato efímero por
clausura, como `PIN_AUTORIZACION_ROTAR`). Una contraseña incorrecta se anota en `intento_login`
en una transacción aparte (comparte el límite del login, ADR-018 y D24); todo rechazo lanza una
excepción, así un reintento con el mismo `Operation-Id` y los datos corregidos se procesa.

Reglas citadas: SEG-05, SEG-06, ADR-011, ADR-018, ADR-019, ADR-022, INV-01, INV-06, `02` §17.
"""

from __future__ import annotations

import logging
import random
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_identidad_commands_maestros import (
    PASSWORD,
    _crear_organizacion,
    _crear_usuario,
    _limpiar_datos_confirmados,  # noqa: F401  (fixture autouse)
    _login,
    sesion,  # noqa: F401  (fixture)
)

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.seguridad import verificar_pin_autorizacion
from app.main import crear_app
from app.modules.identidad import repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import (
    ContrasenaIncorrectaError,
    LoginBloqueadoPorIntentosError,
    PinAutorizacionInvalidoError,
)

JWT_SECRET = "secreto-de-prueba-mi-pin"
URL = "/api/v1/yo/pin-autorizacion"
URL_LOTE = "/api/v1/sync/comandos"
PIN_VIEJO = "735194"
PIN_NUEVO = "482913"
CONTRASENA_MALA = "contrasena-equivocada-999"


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    """Cada prueba entra desde una IP propia: las contraseñas incorrectas de "Mi PIN" y del
    login cuentan por IP (20 en 15 minutos) y `intento_login` no se limpia entre pruebas."""
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    ip = f"10.{random.randint(1, 250)}.{random.randint(1, 250)}.{random.randint(1, 250)}"
    try:
        yield TestClient(app, client=(ip, 50000))
    finally:
        engine.dispose()


class Entorno:
    """Una organización con un supervisor (con PIN viejo) y su sesión."""

    def __init__(
        self,
        cliente: TestClient,
        sesion: Session,
        *,
        permisos: frozenset[str] = frozenset({"AUTORIZAR_DESCUENTO"}),
        con_pin: str | None = PIN_VIEJO,
    ) -> None:
        self.cliente = cliente
        self.sesion = sesion
        self.organizacion = _crear_organizacion(sesion, f"org-mipin-{uuid4().hex[:8]}")
        usuario, _ = _crear_usuario(
            sesion, self.organizacion.id, permisos=permisos, nombre_usuario="marta"
        )
        self.usuario_id: UUID = usuario.id
        if con_pin is not None:
            identidad_service.establecer_pin_autorizacion(
                self.organizacion.id,
                sesion,
                _RelojFijo(),
                usuario_id=usuario.id,
                pin=con_pin,
                actor_id=usuario.id,
            )
        sesion.commit()
        self.token = _login(cliente, self.organizacion.slug, "marta")

    def definir(
        self,
        *,
        pin: object = PIN_NUEVO,
        password_actual: object = PASSWORD,
        operation_id: UUID | None = None,
        **extra: object,
    ):  # type: ignore[no-untyped-def]
        return self.cliente.post(
            URL,
            json={"pin": pin, "password_actual": password_actual, **extra},
            headers={
                "Authorization": f"Bearer {self.token}",
                "Operation-Id": str(operation_id or uuid4()),
            },
        )

    def hash_vigente(self) -> str | None:
        self.sesion.rollback()
        usuario = repository.obtener_usuario_por_id(
            self.organizacion.id, self.usuario_id, self.sesion
        )
        assert usuario is not None
        self.sesion.refresh(usuario)
        return usuario.pin_autorizacion_hash

    def valida(self, pin: str) -> bool:
        self.sesion.rollback()
        usuario = repository.obtener_usuario_por_id(
            self.organizacion.id, self.usuario_id, self.sesion
        )
        assert usuario is not None
        self.sesion.refresh(usuario)
        if usuario.pin_autorizacion_hash is None:
            return False
        return verificar_pin_autorizacion(
            pin,
            hash_almacenado=usuario.pin_autorizacion_hash,
            sal=usuario.pin_autorizacion_sal or "",
            iteraciones=usuario.pin_autorizacion_iteraciones or 0,
        )

    def fallos_de_login(self) -> int:
        self.sesion.rollback()
        return int(
            self.sesion.execute(
                text("SELECT count(*) FROM intento_login WHERE usuario_id = :u AND NOT exito"),
                {"u": self.usuario_id},
            ).scalar_one()
        )

    def volcado(self, tabla: str) -> str:
        self.sesion.rollback()
        return str(
            self.sesion.execute(
                text(f"SELECT coalesce(string_agg(to_json(t)::text, ' '), '') FROM {tabla} t")
            ).scalar_one()
        )

    def sin_rastro(self, *secretos: str) -> None:
        for secreto in secretos:
            for tabla in ("comando", "comando_cuarentena", "auditoria", "observacion"):
                assert secreto not in self.volcado(tabla), (tabla, secreto[:2])


class _RelojFijo:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


# --- contraseña correcta: define el PIN y el anterior deja de validar ----------------------


def test_seg05_con_la_contrasena_correcta_define_el_pin_propio_y_el_anterior_deja_de_validar(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    assert e.valida(PIN_VIEJO)

    respuesta = e.definir()

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert e.valida(PIN_NUEVO)
    assert not e.valida(PIN_VIEJO)


@pytest.mark.parametrize(
    "permiso", ["AUTORIZAR_DESCUENTO", "SUPERAR_CREDITO", "VENDER_CLIENTE_SUSPENDIDO"]
)
def test_seg05_triangulacion_dos_usuarios_de_roles_distintos_definen_su_pin(
    cliente: TestClient,
    sesion: Session,
    permiso: str,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion, permisos=frozenset({permiso}), con_pin=None)

    assert e.definir().status_code == 204
    assert e.valida(PIN_NUEVO)


# --- contraseña incorrecta (D21 punto 4 y 5) ------------------------------------------------


def test_seg05_una_contrasena_incorrecta_responde_403_deja_vigente_el_pin_y_anota_el_intento(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    antes = e.fallos_de_login()

    respuesta = e.definir(password_actual=CONTRASENA_MALA)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "IDENTIDAD_CONTRASENA_INCORRECTA"
    assert CONTRASENA_MALA not in respuesta.text
    assert e.valida(PIN_VIEJO)
    assert e.fallos_de_login() == antes + 1  # la fila sobrevive al rechazo del comando
    assert e.volcado("comando") == ""


def test_seg05_un_reintento_con_el_mismo_operation_id_y_la_contrasena_correcta_se_procesa(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    operacion = uuid4()

    primero = e.definir(password_actual=CONTRASENA_MALA, operation_id=operacion)
    segundo = e.definir(operation_id=operacion)

    assert primero.status_code == 403
    assert segundo.status_code == 204
    assert e.valida(PIN_NUEVO)


def test_adr018_cinco_contrasenas_incorrectas_bloquean_tambien_con_la_correcta_y_el_login(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    for _ in range(5):
        assert e.definir(password_actual=CONTRASENA_MALA).status_code == 403
    assert e.fallos_de_login() >= 5

    respuesta = e.definir()  # la contraseña correcta, ya bloqueado

    assert respuesta.status_code == 429
    assert respuesta.json()["codigo"] == "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"
    assert re.fullmatch(
        r"Demasiados intentos\. Probá de nuevo a las \d{2}:\d{2}\.", respuesta.json()["title"]
    )
    assert e.valida(PIN_VIEJO)
    login = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": e.organizacion.slug,
            "usuario": "marta",
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "PC",
        },
    )
    assert login.status_code == 429  # el login queda bloqueado igual


def test_adr018_los_intentos_bloqueados_no_cuentan_ni_escriben_fila(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    for _ in range(5):
        e.definir(password_actual=CONTRASENA_MALA)
    antes = e.fallos_de_login()

    for password in (PASSWORD, CONTRASENA_MALA, PASSWORD):
        assert e.definir(password_actual=password).status_code == 429

    assert e.fallos_de_login() == antes


def test_adr018_un_usuario_ya_bloqueado_por_el_login_responde_429_en_mi_pin(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    for _ in range(5):
        cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": e.organizacion.slug,
                "usuario": "marta",
                "contrasena": CONTRASENA_MALA,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )

    respuesta = e.definir()

    assert respuesta.status_code == 429
    assert respuesta.json()["codigo"] == "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"
    assert e.valida(PIN_VIEJO)


# --- permiso (D21 punto 2) ------------------------------------------------------------------


def test_seg06_un_usuario_sin_permisos_de_autorizacion_recibe_403_sin_efectos(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion, permisos=frozenset({"VENDER"}), con_pin=None)

    respuesta = e.definir()

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert e.hash_vigente() is None
    assert e.fallos_de_login() == 0
    assert e.volcado("comando") == ""


# --- formato del PIN (D21 punto 6) ----------------------------------------------------------


@pytest.mark.parametrize("pin", ["48291", "48291a", "123456", "000000", "987654", "abcdef"])
def test_adr019_un_pin_corto_con_letras_o_trivial_se_rechaza_y_deja_vigente_el_anterior(
    cliente: TestClient,
    sesion: Session,
    pin: str,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    vigente = e.hash_vigente()

    respuesta = e.definir(pin=pin)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "IDENTIDAD_PIN_AUTORIZACION_INVALIDO"
    assert pin not in respuesta.text
    assert e.hash_vigente() == vigente
    assert e.fallos_de_login() == 0  # la contraseña era correcta: no es un intento fallido


def test_inv21_definir_el_pin_propio_no_toca_a_los_usuarios_de_otra_organizacion(
    cliente: TestClient, sesion: Session
) -> None:
    """Dos organizaciones con login real: el PIN que define el usuario de B no cambia el de A,
    aunque el cuerpo informe identificadores ajenos (se rechazan, `extra="forbid"`)."""
    a = Entorno(cliente, sesion)
    b = Entorno(cliente, sesion)

    assert b.definir().status_code == 204
    ajena = b.definir(usuario_id=str(a.usuario_id), organizacion_id=str(a.organizacion.id))

    assert ajena.status_code == 422
    assert a.valida(PIN_VIEJO)
    assert not a.valida(PIN_NUEVO)
    assert b.valida(PIN_NUEVO)


# --- forma del comando ----------------------------------------------------------------------


def test_seg06_el_cuerpo_no_acepta_usuario_id_el_usuario_sale_del_token(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    otro, _ = _crear_usuario(
        sesion, e.organizacion.id, permisos=frozenset({"AUTORIZAR_DESCUENTO"}), nombre_usuario="lu"
    )
    sesion.commit()

    respuesta = e.definir(usuario_id=str(otro.id))

    assert respuesta.status_code == 422
    assert all("input" not in error for error in respuesta.json()["detail"])
    assert e.valida(PIN_VIEJO)


def test_syn06_el_lote_no_admite_el_comando_en_ningun_modo(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    dispositivo = sesion.execute(
        text("SELECT id FROM dispositivo WHERE organizacion_id = :o"), {"o": e.organizacion.id}
    ).scalar_one()
    sesion.rollback()
    for modo in ("ONLINE", "OFFLINE"):
        item = {
            "operation_id": str(uuid4()),
            "tipo": "PIN_AUTORIZACION_PROPIO_DEFINIR",
            "version": 1,
            "modo": modo,
            "usuario_id": str(e.usuario_id),
            "dispositivo_id": str(dispositivo),
            "occurred_at": "2026-10-22T12:00:00Z",
            "secuencia": 1,
            "app_version": "1.0.0",
            "contenido": {},
        }

        respuesta = cliente.post(
            URL_LOTE, json={"items": [item]}, headers={"Authorization": f"Bearer {e.token}"}
        )

        (resultado,) = respuesta.json()["resultados"]
        assert resultado["error_codigo"] == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert e.valida(PIN_VIEJO)


def test_aud01_la_fila_de_auditoria_del_bus_no_lleva_secretos(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    operacion = uuid4()

    assert e.definir(operation_id=operacion).status_code == 204

    filas = sesion.execute(
        text(
            "SELECT accion, origen, operation_id, usuario_id FROM auditoria "
            "WHERE accion = 'PIN_AUTORIZACION_PROPIO_DEFINIR'"
        )
    ).all()
    sesion.rollback()
    assert len(filas) == 1
    assert filas[0].origen == "COMANDO"
    assert filas[0].operation_id == operacion
    assert filas[0].usuario_id == e.usuario_id
    e.sin_rastro(PIN_NUEVO, PASSWORD)


# --- idempotencia y huella (INV-06, `02` §17) -----------------------------------------------


def test_inv06_el_doble_envio_no_vuelve_a_derivar_ni_depende_de_los_secretos(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    operacion = uuid4()

    primera = e.definir(operation_id=operacion)
    derivacion = e.hash_vigente()
    segunda = e.definir(pin="918273", operation_id=operacion)  # otro PIN, misma operación

    assert (primera.status_code, segunda.status_code) == (204, 204)
    assert e.hash_vigente() == derivacion
    assert e.valida(PIN_NUEVO)


@pytest.mark.parametrize(
    ("password", "pin", "estado"),
    [
        (PASSWORD, PIN_NUEVO, 204),
        (CONTRASENA_MALA, PIN_NUEVO, 403),
        (PASSWORD, "123456", 400),
    ],
    ids=["correcta", "contrasena_incorrecta", "pin_invalido"],
)
def test_sec17_ni_el_pin_ni_la_contrasena_quedan_en_ningun_registro(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    password: str,
    pin: str,
    estado: int,
) -> None:
    e = Entorno(cliente, sesion)

    with caplog.at_level(logging.DEBUG):
        respuesta = e.definir(pin=pin, password_actual=password)

    assert respuesta.status_code == estado
    for secreto in (pin, password):
        assert secreto not in respuesta.text
        assert secreto not in caplog.text
    e.sin_rastro(pin, password)


def test_sec17_un_cuerpo_invalido_responde_422_sin_los_valores(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)

    respuesta = e.definir(pin=482913, password_actual=PASSWORD)  # el PIN no es un texto

    assert respuesta.status_code == 422
    assert "482913" not in respuesta.text
    assert PASSWORD not in respuesta.text
    assert all("input" not in error for error in respuesta.json()["detail"])


# --- servicio con reloj inyectable: bloqueo de 15 minutos desde el último fallo (D24) -------


class _RelojAjustable:
    def __init__(self) -> None:
        self.ahora = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)

    def en(self, hora: str) -> None:
        horas, minutos = (int(parte) for parte in hora.split(":"))
        self.ahora = self.ahora.replace(hour=horas, minute=minutos)

    def now(self) -> datetime:
        return self.ahora


def _definir_en_servicio(e: Entorno, reloj: _RelojAjustable, hora: str, password: str) -> None:
    reloj.en(hora)
    identidad_service.definir_pin_propio(
        e.organizacion.id,
        e.sesion,
        reloj,
        usuario_id=e.usuario_id,
        password_actual=password,
        pin=PIN_NUEVO,
        ip="10.0.0.9",
        dispositivo_id=None,
    )


def test_d24_el_bloqueo_dura_15_minutos_desde_el_ultimo_fallo_y_los_intentos_bloqueados_no_cuentan(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    reloj = _RelojAjustable()
    for hora in ("10:02", "10:05", "10:07", "10:09", "10:10"):
        with pytest.raises(ContrasenaIncorrectaError):
            _definir_en_servicio(e, reloj, hora, CONTRASENA_MALA)
    antes = e.fallos_de_login()

    with pytest.raises(LoginBloqueadoPorIntentosError) as error:
        _definir_en_servicio(e, reloj, "10:20", PASSWORD)  # correcta, pero bloqueado

    assert (
        str(error.value) == "Demasiados intentos. Probá de nuevo a las 07:25."
    )  # 10:25 UTC, Mendoza
    assert e.fallos_de_login() == antes  # el intento bloqueado no inserta fila
    _definir_en_servicio(e, reloj, "10:25", PASSWORD)  # a las 10:25 entra
    e.sesion.commit()
    assert e.valida(PIN_NUEVO)


def test_d24_pasado_el_bloqueo_un_fallo_es_el_primero_de_su_ventana(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    reloj = _RelojAjustable()
    for hora in ("10:02", "10:05", "10:07", "10:09", "10:10"):
        with pytest.raises(ContrasenaIncorrectaError):
            _definir_en_servicio(e, reloj, hora, CONTRASENA_MALA)

    with pytest.raises(ContrasenaIncorrectaError):
        _definir_en_servicio(e, reloj, "10:26", CONTRASENA_MALA)  # primero de la ventana nueva

    for hora in ("10:27", "10:28", "10:29"):
        with pytest.raises(ContrasenaIncorrectaError):
            _definir_en_servicio(e, reloj, hora, CONTRASENA_MALA)
    _definir_en_servicio(e, reloj, "10:30", PASSWORD)  # cuatro fallos: todavía entra


def test_formato_invalido_en_el_servicio_no_cuenta_como_fallo_de_contrasena(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    reloj = _RelojAjustable()
    reloj.en("10:00")

    with pytest.raises(PinAutorizacionInvalidoError):
        identidad_service.definir_pin_propio(
            e.organizacion.id,
            e.sesion,
            reloj,
            usuario_id=e.usuario_id,
            password_actual=PASSWORD,
            pin="123456",
            ip="10.0.0.9",
            dispositivo_id=None,
        )

    assert e.fallos_de_login() == 0


# --- ADR-057 (tarea 24.5, D21 punto 5): "Mi PIN" cuenta con el par escrito del usuario ----------


def test_adr057_las_contrasenas_incorrectas_se_anotan_con_la_clave_del_par_del_usuario(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    from app.modules.identidad.domain.clave_intento import clave_de_intento_login

    e = Entorno(cliente, sesion)
    for _ in range(2):
        assert e.definir(password_actual=CONTRASENA_MALA).status_code == 403

    sesion.rollback()
    claves = (
        sesion.execute(
            text("SELECT clave_intento FROM intento_login WHERE usuario_id = :u AND NOT exito"),
            {"u": e.usuario_id},
        )
        .scalars()
        .all()
    )
    assert claves == [clave_de_intento_login(e.organizacion.slug, "marta")] * 2


def test_adr057_el_login_con_otro_texto_no_consume_el_cupo_de_mi_pin(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    """ "Marta" no es el par de "marta": sus cinco fallos de login no bloquean "Mi PIN" ni el
    login de "marta" (la clave distingue mayúsculas, igual que la búsqueda del login)."""
    e = Entorno(cliente, sesion)
    for _ in range(5):
        respuesta = cliente.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": e.organizacion.slug,
                "usuario": "Marta",
                "contrasena": CONTRASENA_MALA,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 401

    assert e.definir().status_code == 204


def test_adr057_el_429_de_mi_pin_usa_la_zona_de_la_organizacion(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    """Decisión del 2026-10-24: solo el 429 del login va siempre en zona argentina; "Mi PIN"
    (usuario ya autenticado) sigue con la zona de la organización."""
    e = Entorno(cliente, sesion)
    e.organizacion.zona_horaria = "Asia/Tokyo"  # UTC+9: 10:25 UTC -> 19:25
    sesion.commit()
    reloj = _RelojAjustable()
    for hora in ("10:02", "10:05", "10:07", "10:09", "10:10"):
        with pytest.raises(ContrasenaIncorrectaError):
            _definir_en_servicio(e, reloj, hora, CONTRASENA_MALA)

    with pytest.raises(LoginBloqueadoPorIntentosError) as error:
        _definir_en_servicio(e, reloj, "10:20", PASSWORD)

    assert str(error.value) == "Demasiados intentos. Probá de nuevo a las 19:25."
