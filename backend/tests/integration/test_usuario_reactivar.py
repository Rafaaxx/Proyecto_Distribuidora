# ruff: noqa: F811
"""Change 20b, tarea 3.3: `USUARIO_REACTIVAR` v1,
`POST /api/v1/identidad/usuarios/{id}/reactivacion` (spec `identidad/administracion-de-usuarios`).

La reactivación solo vuelve el estado a `ACTIVO` (suma un administrador, así que la regla del
último administrador no aplica) y audita `REACTIVAR_USUARIO`. El usuario inicia sesión de nuevo;
su PIN, borrado en la baja, no se recupera.

Reglas citadas: ADR-028 D9.4, ADR-053, AUD-01, INV-01, INV-06, INV-21.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from usuarios_utiles import (
    URL_USUARIOS,
    EntornoUsuarios,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

from app.modules.identidad import service as identidad_service  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")


def _reactivar(entorno, cliente, quien, usuario_id: UUID, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente,
        "POST",
        f"{URL_USUARIOS}/{usuario_id}/reactivacion",
        quien,
        {},
        operation_id=operation_id,
    )


def _login(entorno: EntornoUsuarios, cliente: TestClient, nombre: str):  # type: ignore[no-untyped-def]
    return cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": entorno.slug,
            "usuario": nombre,
            "contrasena": "una-contrasena-larga-123",
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "Equipo",
        },
    )


def test_reactivar_a_un_inactivo_le_devuelve_el_login_y_deja_su_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    supervisor = entorno.crear_rol("Supervisor", frozenset({"VENDER", "AUTORIZAR_DESCUENTO"}))
    usuario_id, nombre = entorno.crear_usuario(supervisor, con_pin=True)
    baja = entorno.enviar(
        cliente_http, "POST", f"{URL_USUARIOS}/{usuario_id}/baja", administrador, {}
    )
    assert baja.status_code == 200
    assert _login(entorno, cliente_http, nombre).status_code == 401
    operation_id = uuid4()

    respuesta = _reactivar(entorno, cliente_http, administrador, usuario_id, operation_id)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "ACTIVO"
    assert _login(entorno, cliente_http, nombre).status_code == 200
    # El PIN que borró la baja no vuelve: hay que definirlo de nuevo (D2-A).
    assert entorno.usuario(usuario_id)["pin_autorizacion_hash"] is None
    (auditoria,) = entorno.auditorias("REACTIVAR_USUARIO", entidad_id=usuario_id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"estado": "INACTIVO"}
    assert auditoria["despues"] == {"estado": "ACTIVO"}
    assert auditoria["usuario_id"] == administrador.usuario_id


def test_reactivar_a_un_activo_responde_409_y_no_audita(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))

    respuesta = _reactivar(entorno, cliente_http, administrador, usuario_id)

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA"
    assert entorno.auditorias("REACTIVAR_USUARIO") == []
    assert entorno.usuario(usuario_id)["estado"] == "ACTIVO"


def test_reactivar_con_el_rol_de_baja_deja_al_usuario_activo_pero_sin_login(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.4: el estado del usuario y el del rol son independientes; con el rol de baja
    el inicio de sesión se rechaza igual."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol_de_baja = entorno.crear_rol("Viejo", frozenset({"VENDER"}), activo=False)
    usuario_id, nombre = entorno.crear_usuario(rol_de_baja, estado="INACTIVO")

    respuesta = _reactivar(entorno, cliente_http, administrador, usuario_id)

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.usuario(usuario_id)["estado"] == "ACTIVO"
    assert _login(entorno, cliente_http, nombre).status_code == 401


def test_el_doble_envio_no_repite_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    usuario_id, _ = entorno.crear_usuario(
        entorno.crear_rol("Vendedor", frozenset({"VENDER"})), estado="INACTIVO"
    )
    operation_id = uuid4()

    primera = _reactivar(entorno, cliente_http, administrador, usuario_id, operation_id)
    segunda = _reactivar(entorno, cliente_http, administrador, usuario_id, operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("REACTIVAR_USUARIO")) == 1
    assert entorno.comandos("USUARIO_REACTIVAR") == 1


def test_un_usuario_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    ajeno_id, _ = ajena.crear_usuario(
        ajena.crear_rol("Vendedor", frozenset({"VENDER"})), estado="INACTIVO"
    )

    respuesta = _reactivar(propia, cliente_http, administrador, ajeno_id)

    assert respuesta.status_code == 404
    assert ajena.usuario(ajeno_id)["estado"] == "INACTIVO"


def test_sin_el_permiso_responde_403_y_no_reactiva(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06."""
    entorno = EntornoUsuarios(sesion_real)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    quien_id, quien = entorno.crear_usuario(vendedor)
    inactivo_id, _ = entorno.crear_usuario(vendedor, estado="INACTIVO")
    sin_permiso = entorno.abrir_sesion(cliente_http, quien_id, quien)

    respuesta = _reactivar(entorno, cliente_http, sin_permiso, inactivo_id)

    assert respuesta.status_code == 403
    assert entorno.usuario(inactivo_id)["estado"] == "INACTIVO"
