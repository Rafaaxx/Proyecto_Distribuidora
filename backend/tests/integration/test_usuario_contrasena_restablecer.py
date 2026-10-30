# ruff: noqa: F811
"""Change 20b, tarea 4.3: `USUARIO_CONTRASENA_RESTABLECER` v1,
`POST /api/v1/identidad/usuarios/{id}/contrasena` (spec `identidad/administracion-de-usuarios`).

El administrador fija una contraseña nueva. La contraseña viaja fuera del contenido (dato efímero
por clausura) y no queda en la huella, el comando, la cuarentena, la auditoría, la respuesta ni el
registro. En la misma transacción revoca las sesiones del usuario salvo las de una jornada no
cerrada (`CONTRASENA_RESTABLECIDA`) y neutraliza el bloqueo por intentos.

Reglas citadas: ADR-018, ADR-056, ADR-057, ADR-028 D9.3-B, AUD-01, INV-01, INV-06, INV-21,
SEG-06.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql
from usuarios_utiles import (
    PASSWORD,
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

from app.core.clock import SystemClock
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

NUEVA = "clave-nueva-del-administrador-5521"
OTRA = "otra-clave-del-administrador-8817"
VENDEDOR = frozenset({"VENDER"})


def _restablecer(entorno, cliente, quien, usuario_id, contrasena=NUEVA, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente,
        "POST",
        f"{URL_USUARIOS}/{usuario_id}/contrasena",
        quien,
        {"contrasena": contrasena},
        operation_id=operation_id,
    )


def _login(entorno, cliente, nombre, contrasena):  # type: ignore[no-untyped-def]
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


def test_restablecer_cambia_la_contrasena_corta_las_sesiones_y_no_deja_rastro(
    cliente_http: TestClient, sesion_real: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-018, ADR-056, ADR-057, INV-01: efectos y ausencia de la contraseña en todo registro."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    with caplog.at_level(logging.DEBUG):
        respuesta = _restablecer(
            entorno, cliente_http, administrador, usuario_id, operation_id=operation_id
        )

    assert respuesta.status_code == 204, respuesta.text
    assert NUEVA not in respuesta.text
    assert NUEVA not in caplog.text
    entorno.sin_rastro(NUEVA)
    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200
    assert _login(entorno, cliente_http, nombre, PASSWORD).status_code == 401
    familias = [
        f
        for f in entorno.familias(usuario_id)
        if f["dispositivo_id"] in {en_la_pc.dispositivo_id, en_el_telefono.dispositivo_id}
    ]
    assert len(familias) == 2
    assert {f["motivo_revocacion"] for f in familias} == {"CONTRASENA_RESTABLECIDA"}
    assert entorno.renovar(cliente_http, en_la_pc).status_code == 401
    assert entorno.renovar(cliente_http, en_el_telefono).status_code == 401
    (restablecimiento,) = entorno.auditorias("RESTABLECER_CONTRASENA", entidad_id=usuario_id)
    assert restablecimiento["origen"] == "COMANDO"
    assert restablecimiento["operation_id"] == operation_id
    assert restablecimiento["usuario_id"] == administrador.usuario_id
    (revocacion,) = entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO", entidad_id=usuario_id)
    assert revocacion["origen"] == "COMANDO"
    assert revocacion["operation_id"] == operation_id


def test_el_pin_de_autorizacion_no_se_toca(cliente_http: TestClient, sesion_real: Session) -> None:
    """D8-A: restablecer la contraseña no toca el PIN."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    supervisor = entorno.crear_rol("Supervisor", frozenset({"AUTORIZAR_DESCUENTO"}))
    usuario_id, _ = entorno.crear_usuario(supervisor, con_pin=True)

    assert _restablecer(entorno, cliente_http, administrador, usuario_id).status_code == 204

    assert entorno.usuario(usuario_id)["pin_autorizacion_hash"] is not None


def test_con_jornada_abierta_en_un_dispositivo_esa_familia_sigue(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.3-B: la excepción de la jornada no cerrada vale también acá."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    en_la_pc = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    en_el_telefono = entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    crear_jornada_sql(
        sesion_real,
        entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=en_el_telefono.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(sesion_real, entorno.org, requiere_toma=True),
    )
    sesion_real.commit()

    assert _restablecer(entorno, cliente_http, administrador, usuario_id).status_code == 204

    assert entorno.familias_vigentes(usuario_id) == {en_el_telefono.dispositivo_id}
    assert entorno.renovar(cliente_http, en_la_pc).status_code == 401
    assert entorno.renovar(cliente_http, en_el_telefono).status_code == 200


def test_restablecer_neutraliza_el_bloqueo_por_intentos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-057: quien restablece la contraseña para que el usuario pueda entrar no debería
    encontrarlo bloqueado."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    for _ in range(5):
        assert _login(entorno, cliente_http, nombre, "equivocada").status_code == 401
    bloqueado = _login(entorno, cliente_http, nombre, PASSWORD)
    assert bloqueado.status_code == 429

    assert _restablecer(entorno, cliente_http, administrador, usuario_id).status_code == 204

    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200


@pytest.mark.parametrize("contrasena", ["   ", "1234567"])
def test_una_contrasena_invalida_responde_422_y_no_revoca_nada(
    cliente_http: TestClient, sesion_real: Session, contrasena: str
) -> None:
    """INV-01: la validación va antes de escribir y de revocar."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    hash_antes = entorno.usuario(usuario_id)["password_hash"]

    respuesta = _restablecer(
        entorno, cliente_http, administrador, usuario_id, contrasena=contrasena
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "IDENTIDAD_CONTRASENA_INVALIDA"
    assert entorno.usuario(usuario_id)["password_hash"] == hash_antes
    assert len(entorno.familias_vigentes(usuario_id)) == 1
    assert entorno.auditorias("RESTABLECER_CONTRASENA") == []


def test_una_contrasena_que_no_es_texto_no_se_repite_en_el_error(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-056: ningún error de validación devuelve el valor recibido."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))

    respuesta = entorno.enviar(
        cliente_http,
        "POST",
        f"{URL_USUARIOS}/{usuario_id}/contrasena",
        administrador,
        {"contrasena": 917253},
    )

    assert respuesta.status_code == 422
    assert "917253" not in respuesta.text


def test_se_puede_restablecer_la_de_un_inactivo_y_la_propia(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D8-A: queda listo para reactivar; sobre uno mismo está permitido."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    inactivo_id, nombre = entorno.crear_usuario(
        entorno.crear_rol("Vendedor", VENDEDOR), estado="INACTIVO"
    )

    assert _restablecer(entorno, cliente_http, administrador, inactivo_id).status_code == 204
    assert (
        _restablecer(
            entorno, cliente_http, administrador, administrador.usuario_id, contrasena=OTRA
        ).status_code
        == 204
    )

    assert entorno.usuario(inactivo_id)["estado"] == "INACTIVO"
    assert _login(entorno, cliente_http, administrador.nombre_usuario, OTRA).status_code == 200


def test_el_doble_envio_con_otra_contrasena_devuelve_el_resultado_original(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06: la contraseña no entra a la huella, así que un reenvío con el mismo `Operation-Id`
    no la vuelve a aplicar ni vuelve a revocar."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    entorno.abrir_sesion(cliente_http, usuario_id, nombre)
    operation_id = uuid4()

    primera = _restablecer(
        entorno, cliente_http, administrador, usuario_id, NUEVA, operation_id=operation_id
    )
    segunda = _restablecer(
        entorno, cliente_http, administrador, usuario_id, OTRA, operation_id=operation_id
    )

    assert primera.status_code == segunda.status_code == 204
    assert _login(entorno, cliente_http, nombre, NUEVA).status_code == 200
    assert _login(entorno, cliente_http, nombre, OTRA).status_code == 401
    assert len(entorno.auditorias("RESTABLECER_CONTRASENA")) == 1
    assert len(entorno.auditorias("REVOCAR_SESIONES_REFRESH_USUARIO")) == 1


def test_un_usuario_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, nombre = ajena.crear_usuario(ajena.crear_rol("Vendedor", VENDEDOR))

    respuesta = _restablecer(propia, cliente_http, administrador, ajeno_id)

    assert respuesta.status_code == 404
    assert _login(ajena, cliente_http, nombre, PASSWORD).status_code == 200


def test_sin_el_permiso_responde_403(cliente_http: TestClient, sesion_real: Session) -> None:
    """SEG-06: ni el propio usuario puede cambiarse la contraseña por esta vía sin
    `ADMIN_USUARIOS` (para eso existe "Mi contraseña")."""
    entorno = EntornoUsuarios(sesion_real)
    yo, nombre = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    mi_sesion = entorno.abrir_sesion(cliente_http, yo, nombre)

    respuesta = _restablecer(entorno, cliente_http, mi_sesion, yo)

    assert respuesta.status_code == 403
    assert _login(entorno, cliente_http, nombre, PASSWORD).status_code == 200


def test_por_el_lote_se_rechaza_por_credenciales_efimeras_sin_dejar_rastro(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SYN-06, ADR-056: el lote no admite un tipo que recibe un secreto fuera del contenido."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    objetivo_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDEDOR))
    item = ItemLote(
        operation_id=uuid4(),
        tipo="USUARIO_CONTRASENA_RESTABLECER",
        version=1,
        modo="ONLINE",
        usuario_id=administrador.usuario_id,
        dispositivo_id=administrador.dispositivo_id,
        occurred_at=SystemClock().now(),
        secuencia=1,
        app_version="1.0.0",
        contenido={"usuario_id": str(objetivo_id), "contrasena": NUEVA},
        jornada_id=None,
    )

    (resultado,) = sync_service.procesar_lote(
        sesion_real,
        SystemClock(),
        organizacion_id=entorno.org,
        usuario_id=administrador.usuario_id,
        dispositivo_id=administrador.dispositivo_id,
        items=[item],
    )

    assert (resultado.estado, resultado.error_codigo) == (
        "RECHAZADO",
        "MODO_NO_ADMITIDO_PARA_TIPO",
    )
    entorno.sin_rastro(NUEVA)
    assert entorno.comandos("USUARIO_CONTRASENA_RESTABLECER") == 0
