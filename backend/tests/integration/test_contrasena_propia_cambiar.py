# ruff: noqa: F811
"""Change 20b, tarea 4.5: `CONTRASENA_PROPIA_CAMBIAR` v1 ("Mi contraseña"),
`POST /api/v1/yo/contrasena` (204), spec `identidad/autenticacion-y-sesion` y `design.md` D20.

Cualquier usuario autenticado y activo cambia SU contraseña (el usuario sale del token) enviando la
actual y la nueva como datos efímeros. Una actual incorrecta responde 403
`IDENTIDAD_CONTRASENA_INCORRECTA`, cuenta como intento fallido del inicio de sesión (transacción
aparte) y comparte el bloqueo del login (429). Un cambio aceptado revoca las sesiones de los demás
dispositivos (`CONTRASENA_CAMBIADA`), conserva la del dispositivo actual y respeta la jornada no
cerrada.

Reglas citadas: ADR-018, ADR-056, ADR-057, ADR-028 D9.3-B, AUD-01, AUD-02, SEG-04, SEG-06, INV-01,
INV-06, INV-21.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from usuarios_utiles import (
    PASSWORD,
    EntornoUsuarios,
    SesionAbierta,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

from app.core.clock import SystemClock
from app.core.seguridad import hashear_password
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL = "/api/v1/yo/contrasena"
NUEVA = "clave-nueva-propia-4412"
OTRA = "otra-clave-propia-9035"
EQUIVOCADA = "clave-equivocada-7781"
VENDEDOR = frozenset({"VENDER"})


def _cambiar(
    entorno: EntornoUsuarios,
    cliente: TestClient,
    quien: SesionAbierta,
    *,
    actual: object = PASSWORD,
    nueva: object = NUEVA,
    operation_id: UUID | None = None,
    **extra: object,
) -> Any:
    return entorno.enviar(
        cliente,
        "POST",
        URL,
        quien,
        {"password_actual": actual, "password_nueva": nueva, **extra},
        operation_id=operation_id,
    )


def _login(entorno: EntornoUsuarios, cliente: TestClient, nombre: str, contrasena: str) -> Any:
    return cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": entorno.slug,
            "usuario": nombre,
            "contrasena": contrasena,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "Equipo",
        },
    )


def _intentos_fallidos(entorno: EntornoUsuarios, usuario_id: UUID) -> int:
    (fila,) = entorno.fila(
        "SELECT count(*) AS n FROM intento_login WHERE usuario_id = :u AND exito = false",
        u=usuario_id,
    )
    return int(fila["n"])


def _vendedor(entorno: EntornoUsuarios) -> tuple[UUID, str]:
    return entorno.crear_usuario(entorno.crear_rol(f"Vendedor {uuid4().hex[:6]}", VENDEDOR))


def test_el_cambio_correcto_conserva_la_sesion_actual_y_cierra_las_de_otros_dispositivos(
    cliente_http: TestClient, sesion_real: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """D20, ADR-056, AUD-01, AUD-02, INV-01."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    with caplog.at_level(logging.DEBUG):
        respuesta = _cambiar(entorno, cliente_http, en_la_pc, operation_id=operation_id)

    assert respuesta.status_code == 204, respuesta.text
    assert respuesta.text == ""
    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200
    assert _login(entorno, cliente_http, nombre, PASSWORD).status_code == 401
    assert entorno.renovar(cliente_http, en_la_pc).status_code == 200
    assert entorno.renovar(cliente_http, en_el_telefono).status_code == 401
    del_telefono = [
        f
        for f in entorno.familias(usuario_id)
        if f["dispositivo_id"] == en_el_telefono.dispositivo_id
    ]
    assert {f["motivo_revocacion"] for f in del_telefono} == {"CONTRASENA_CAMBIADA"}
    (cambio,) = entorno.auditorias("CAMBIAR_CONTRASENA_PROPIA", entidad_id=usuario_id)
    assert cambio["origen"] == "COMANDO"
    assert cambio["operation_id"] == operation_id
    assert cambio["usuario_id"] == usuario_id
    assert cambio["despues"] == {"familias_revocadas": 1}
    (revocacion,) = entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO", entidad_id=usuario_id)
    assert revocacion["origen"] == "COMANDO"
    assert revocacion["operation_id"] == operation_id
    for secreto in (PASSWORD, NUEVA):
        assert secreto not in caplog.text
        entorno.sin_rastro(secreto)
    # No toca el PIN de autorización ni el estado.
    assert entorno.usuario(usuario_id)["estado"] == "ACTIVO"


def test_con_jornada_abierta_en_otro_dispositivo_esa_familia_sigue(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.3-B, SYN-05, SYN-10: no se vara la cola de un teléfono con jornada."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_otra_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    crear_jornada_sql(
        sesion_real,
        entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=en_el_telefono.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion_real, entorno.org, requiere_toma=True),
    )
    sesion_real.commit()

    assert _cambiar(entorno, cliente_http, en_la_pc).status_code == 204

    assert entorno.familias_vigentes(usuario_id) == {
        en_la_pc.dispositivo_id,
        en_el_telefono.dispositivo_id,
    }
    assert entorno.renovar(cliente_http, en_otra_pc).status_code == 401
    assert entorno.renovar(cliente_http, en_el_telefono).status_code == 200


def test_un_usuario_sin_permisos_de_administracion_puede_cambiar_la_suya(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D20: sin permiso especial; el bus no exige ninguno para este tipo."""
    entorno = EntornoUsuarios(sesion_real)
    sin_permisos, nombre = entorno.crear_usuario(entorno.crear_rol("Sin permisos", frozenset()))
    abierta = entorno.abrir_sesion(cliente_http, sin_permisos, nombre)

    assert _cambiar(entorno, cliente_http, abierta).status_code == 204

    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200


def test_una_actual_incorrecta_responde_403_cuenta_el_intento_y_no_revoca(
    cliente_http: TestClient, sesion_real: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-018, ADR-057: el intento fallido se confirma aunque el comando se rechace."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    hash_antes = entorno.usuario(usuario_id)["password_hash"]

    with caplog.at_level(logging.DEBUG):
        respuesta = _cambiar(entorno, cliente_http, en_la_pc, actual=EQUIVOCADA)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "IDENTIDAD_CONTRASENA_INCORRECTA"
    assert EQUIVOCADA not in respuesta.text
    assert EQUIVOCADA not in caplog.text
    assert _intentos_fallidos(entorno, usuario_id) == 1
    assert entorno.usuario(usuario_id)["password_hash"] == hash_antes
    assert entorno.familias_vigentes(usuario_id) == {
        en_la_pc.dispositivo_id,
        en_el_telefono.dispositivo_id,
    }
    assert entorno.auditorias("CAMBIAR_CONTRASENA_PROPIA") == []
    assert entorno.comandos("CONTRASENA_PROPIA_CAMBIAR") == 0
    entorno.sin_rastro(EQUIVOCADA)


def test_los_fallos_seguidos_bloquean_tambien_con_la_actual_correcta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-018, ADR-057, SEG-04: cinco fallos y el siguiente responde 429 sin verificar ni
    cambiar nada, aunque la contraseña actual sea la correcta."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    hash_antes = entorno.usuario(usuario_id)["password_hash"]
    for _ in range(5):
        assert _cambiar(entorno, cliente_http, abierta, actual=EQUIVOCADA).status_code == 403

    bloqueado = _cambiar(entorno, cliente_http, abierta)

    assert bloqueado.status_code == 429
    assert bloqueado.json()["codigo"] == "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"
    assert entorno.usuario(usuario_id)["password_hash"] == hash_antes
    assert _intentos_fallidos(entorno, usuario_id) == 5  # el intento bloqueado no cuenta
    assert entorno.auditorias("CAMBIAR_CONTRASENA_PROPIA") == []


def test_el_bloqueo_se_comparte_con_el_inicio_de_sesion(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-018 punto 3: cinco fallos en "Mi contraseña" bloquean también el login."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    for _ in range(5):
        _cambiar(entorno, cliente_http, abierta, actual=EQUIVOCADA)

    assert _login(entorno, cliente_http, nombre, PASSWORD).status_code == 429


@pytest.mark.parametrize(
    ("nueva", "codigo"),
    [
        (PASSWORD, "IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL"),
        ("    ", "IDENTIDAD_CONTRASENA_INVALIDA"),
        ("1234567", "IDENTIDAD_CONTRASENA_INVALIDA"),
    ],
)
def test_una_nueva_invalida_o_igual_a_la_actual_responde_422_sin_contar_intento(
    cliente_http: TestClient, sesion_real: Session, nueva: str, codigo: str
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    hash_antes = entorno.usuario(usuario_id)["password_hash"]

    respuesta = _cambiar(entorno, cliente_http, en_la_pc, nueva=nueva)

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == codigo
    assert _intentos_fallidos(entorno, usuario_id) == 0
    assert entorno.usuario(usuario_id)["password_hash"] == hash_antes
    assert len(entorno.familias_vigentes(usuario_id)) == 2
    assert entorno.renovar(cliente_http, en_el_telefono).status_code == 200


def test_una_contrasena_existente_de_menos_de_8_caracteres_sigue_sirviendo_para_entrar(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D9: la regla de 8 caracteres rige solo al definir una contraseña nueva; las existentes no
    se invalidan y el inicio de sesión no cambia."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    sesion_real.execute(
        text("UPDATE usuario SET password_hash = :h WHERE id = :u"),
        {"h": hashear_password("corta"), "u": usuario_id},
    )
    sesion_real.commit()

    assert _login(entorno, cliente_http, nombre, "corta").status_code == 200


def test_un_cuerpo_con_usuario_id_se_rechaza_por_campo_no_admitido(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06, INV-21: solo se puede cambiar la contraseña del usuario del token."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    otro_id, otro_nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    respuesta = _cambiar(entorno, cliente_http, abierta, usuario_id=str(otro_id))

    assert respuesta.status_code == 422
    assert _login(entorno, cliente_http, otro_nombre, PASSWORD).status_code == 200
    assert _login(entorno, cliente_http, nombre, PASSWORD).status_code == 200


def test_un_secreto_que_no_es_texto_no_se_repite_en_el_error(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-056: ningún error de validación devuelve el valor recibido."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    respuesta = _cambiar(entorno, cliente_http, abierta, nueva=917253)

    assert respuesta.status_code == 422
    assert "917253" not in respuesta.text


def test_sin_sesion_o_con_el_usuario_inactivo_responde_401(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    sin_sesion = cliente_http.post(
        URL,
        json={"password_actual": PASSWORD, "password_nueva": NUEVA},
        headers={"Operation-Id": str(uuid4())},
    )
    entorno.sesion.execute(
        text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": usuario_id}
    )
    entorno.sesion.commit()
    inactivo = _cambiar(entorno, cliente_http, abierta)

    assert sin_sesion.status_code == 401
    assert inactivo.status_code == 401
    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 401
    assert entorno.auditorias("CAMBIAR_CONTRASENA_PROPIA") == []


def test_sin_operation_id_responde_400(cliente_http: TestClient, sesion_real: Session) -> None:
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    respuesta = cliente_http.post(
        URL,
        json={"password_actual": PASSWORD, "password_nueva": NUEVA},
        headers=abierta.headers,
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"


def test_el_reintento_con_el_mismo_operation_id_y_datos_corregidos_se_procesa(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D20: todo rechazo lanza una excepción de dominio, sin fila de `comando`."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    primero = _cambiar(entorno, cliente_http, abierta, actual=EQUIVOCADA, operation_id=operation_id)
    segundo = _cambiar(entorno, cliente_http, abierta, operation_id=operation_id)

    assert primero.status_code == 403
    assert segundo.status_code == 204
    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200


def test_el_doble_envio_tras_un_exito_no_revoca_dos_veces(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06: las contraseñas no entran a la huella; el reenvío devuelve el resultado original."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    primero = _cambiar(entorno, cliente_http, abierta, operation_id=operation_id)
    segundo = _cambiar(
        entorno, cliente_http, abierta, actual=NUEVA, nueva=OTRA, operation_id=operation_id
    )

    assert primero.status_code == segundo.status_code == 204
    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200
    assert _login(entorno, cliente_http, nombre, OTRA).status_code == 401
    assert len(entorno.auditorias("CAMBIAR_CONTRASENA_PROPIA")) == 1
    assert len(entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO")) == 1
    assert entorno.comandos("CONTRASENA_PROPIA_CAMBIAR") == 1


@pytest.mark.parametrize("modo", ["ONLINE", "OFFLINE"])
def test_por_el_lote_se_rechaza_en_cualquier_modo_sin_dejar_rastro(
    cliente_http: TestClient, sesion_real: Session, modo: str
) -> None:
    """SYN-06, ADR-056: un tipo con secretos efímeros no entra por el lote ni sin conexión."""
    entorno = EntornoUsuarios(sesion_real)
    usuario_id, nombre = _vendedor(entorno)
    abierta = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    item = ItemLote(
        operation_id=uuid4(),
        tipo="CONTRASENA_PROPIA_CAMBIAR",
        version=1,
        modo=modo,
        usuario_id=usuario_id,
        dispositivo_id=abierta.dispositivo_id,
        occurred_at=SystemClock().now(),
        secuencia=1,
        app_version="1.0.0",
        contenido={"password_actual": PASSWORD, "password_nueva": NUEVA},
        jornada_id=None,
    )

    (resultado,) = sync_service.procesar_lote(
        sesion_real,
        SystemClock(),
        organizacion_id=entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=abierta.dispositivo_id,
        items=[item],
    )

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    assert entorno.comandos("CONTRASENA_PROPIA_CAMBIAR") == 0
    entorno.sin_rastro(NUEVA)
    assert _login(entorno, cliente_http, nombre, PASSWORD).status_code == 200


def test_un_administrador_tambien_cambia_la_suya_sin_tocar_las_de_otros(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21: solo la propia, aunque quien la cambie tenga `ADMIN_USUARIOS`."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    _, otro_nombre = _vendedor(entorno)

    assert _cambiar(entorno, cliente_http, administrador).status_code == 204

    assert _login(entorno, cliente_http, administrador.nombre_usuario, NUEVA).status_code == 200
    assert _login(entorno, cliente_http, otro_nombre, PASSWORD).status_code == 200


def test_inv21_cambiar_la_propia_no_toca_a_los_usuarios_de_otra_organizacion(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07: todo sale del token. Dos organizaciones con un usuario del mismo nombre de
    inicio de sesión: el cambio de una no alcanza a la otra."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    mio, nombre = propia.crear_usuario(propia.crear_rol("Vendedor", VENDEDOR))
    ajeno, _ = ajena.crear_usuario(ajena.crear_rol("Vendedor", VENDEDOR))
    sesion_ajena = ajena.abrir_sesion(cliente_http, ajeno, ajena.usuario(ajeno)["usuario"])
    hash_ajeno = ajena.usuario(ajeno)["password_hash"]
    mi_sesion = propia.abrir_sesion(cliente_http, mio, nombre)

    assert _cambiar(propia, cliente_http, mi_sesion).status_code == 204

    assert ajena.usuario(ajeno)["password_hash"] == hash_ajeno
    assert ajena.renovar(cliente_http, sesion_ajena).status_code == 200
    assert ajena.auditorias("CAMBIAR_CONTRASENA_PROPIA") == []
