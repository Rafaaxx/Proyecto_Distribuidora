# ruff: noqa: F811
"""Change 20b, tarea 8.2: `ROL_BAJA` v1 (`POST /api/v1/identidad/roles/{id}/baja`) y
`ROL_REACTIVAR` v1 (`POST /api/v1/identidad/roles/{id}/reactivacion`) (spec
`identidad/administracion-de-roles`).

La baja se rechaza si el rol tiene usuarios ACTIVO (D11-A); con solo inactivos se acepta. Un rol de
baja no se asigna. Reglas citadas: ADR-028 D9.4, ADR-053, AUD-01, INV-01, INV-06, INV-21, SEG-06.
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

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL_ROLES = "/api/v1/identidad/roles"
VENDER = frozenset({"VENDER"})


def _baja(entorno, cliente, quien, rol_id: UUID, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente, "POST", f"{URL_ROLES}/{rol_id}/baja", quien, {}, operation_id=operation_id
    )


def _reactivar(entorno, cliente, quien, rol_id: UUID, operation_id=None):  # type: ignore[no-untyped-def]
    return entorno.enviar(
        cliente, "POST", f"{URL_ROLES}/{rol_id}/reactivacion", quien, {}, operation_id=operation_id
    )


def _activo(entorno: EntornoUsuarios, rol_id: UUID) -> bool:
    (fila,) = entorno.fila("SELECT activo FROM rol WHERE id = :r", r=rol_id)
    return bool(fila["activo"])


def test_la_baja_de_un_rol_sin_usuarios_lo_deja_de_baja_y_auditado(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.4, AUD-01."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Repartidor", VENDER)
    operation_id = uuid4()

    respuesta = _baja(entorno, cliente_http, administrador, rol.id, operation_id)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["activo"] is False
    assert _activo(entorno, rol.id) is False
    (auditoria,) = entorno.auditorias("BAJA_ROL", entidad_id=rol.id)
    assert auditoria["origen"] == "COMANDO"
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"activo": True}
    assert auditoria["despues"] == {"activo": False}
    assert auditoria["usuario_id"] == administrador.usuario_id


def test_la_baja_con_usuarios_activos_responde_409_con_la_cantidad_y_no_toca_nada(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ADR-028 D9.4, INV-01: ninguna sesión se toca."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    uno, nombre_uno = entorno.crear_usuario(rol)
    entorno.crear_usuario(rol)
    entorno.crear_usuario(rol, estado="INACTIVO")
    sesion_del_uno = entorno.abrir_sesion(cliente_http, uno, nombre_uno)

    respuesta = _baja(entorno, cliente_http, administrador, rol.id)

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS"
    assert "2" in cuerpo["title"]
    assert _activo(entorno, rol.id) is True
    assert entorno.auditorias("BAJA_ROL") == []
    assert entorno.familias_vigentes(uno) == {sesion_del_uno.dispositivo_id}


def test_la_baja_con_solo_usuarios_inactivos_se_acepta(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Viejo", VENDER)
    entorno.crear_usuario(rol, estado="INACTIVO")

    respuesta = _baja(entorno, cliente_http, administrador, rol.id)

    assert respuesta.status_code == 200, respuesta.text
    assert _activo(entorno, rol.id) is False


def test_un_rol_de_baja_no_se_asigna_ni_en_el_alta_ni_en_el_cambio_de_rol(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """D7, D9: `IDENTIDAD_ROL_INACTIVO`."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Repartidor", VENDER)
    otro_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDER))
    assert _baja(entorno, cliente_http, administrador, rol.id).status_code == 200

    alta = entorno.enviar(
        cliente_http,
        "POST",
        URL_USUARIOS,
        administrador,
        {
            "usuario": f"u-{uuid4().hex[:6]}",
            "nombre": "Nuevo",
            "email": None,
            "password": "una-contrasena-larga-123",
            "rol_id": str(rol.id),
        },
    )
    cambio = entorno.enviar(
        cliente_http,
        "PUT",
        f"{URL_USUARIOS}/{otro_id}/rol",
        administrador,
        {"rol_id": str(rol.id)},
    )

    assert alta.status_code == cambio.status_code == 409
    assert alta.json()["codigo"] == cambio.json()["codigo"] == "IDENTIDAD_ROL_INACTIVO"


def test_la_baja_de_un_rol_ya_de_baja_se_acepta_sin_auditoria_nueva(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """Como el mismo valor en un renombre o en un tope: sin cambio, sin fila de entidad."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Viejo", VENDER, activo=False)

    respuesta = _baja(entorno, cliente_http, administrador, rol.id)

    assert respuesta.status_code == 200
    assert entorno.auditorias("BAJA_ROL") == []


def test_reactivar_vuelve_a_poder_asignarse_y_audita(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Viejo", VENDER, activo=False)
    usuario_id, _ = entorno.crear_usuario(entorno.crear_rol("Vendedor", VENDER))
    operation_id = uuid4()

    respuesta = _reactivar(entorno, cliente_http, administrador, rol.id, operation_id)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["activo"] is True
    assert _activo(entorno, rol.id) is True
    (auditoria,) = entorno.auditorias("REACTIVAR_ROL", entidad_id=rol.id)
    assert auditoria["operation_id"] == operation_id
    assert auditoria["antes"] == {"activo": False}
    assert auditoria["despues"] == {"activo": True}
    cambio = entorno.enviar(
        cliente_http,
        "PUT",
        f"{URL_USUARIOS}/{usuario_id}/rol",
        administrador,
        {"rol_id": str(rol.id)},
    )
    assert cambio.status_code == 200, cambio.text


def test_reactivar_un_rol_activo_no_cambia_nada_ni_audita(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)

    respuesta = _reactivar(entorno, cliente_http, administrador, rol.id)

    assert respuesta.status_code == 200
    assert entorno.auditorias("REACTIVAR_ROL") == []


def test_el_doble_envio_de_la_baja_no_repite_la_auditoria(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-06."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Repartidor", VENDER)
    operation_id = uuid4()

    primera = _baja(entorno, cliente_http, administrador, rol.id, operation_id)
    segunda = _baja(entorno, cliente_http, administrador, rol.id, operation_id)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno.auditorias("BAJA_ROL")) == 1
    assert entorno.comandos("ROL_BAJA") == 1


def test_baja_y_reactivacion_de_un_rol_de_otra_organizacion_responden_404(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21, SEG-07."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    administrador = propia.administrador(cliente_http)
    rol_ajeno = ajena.crear_rol("Repartidor", VENDER)

    baja = _baja(propia, cliente_http, administrador, rol_ajeno.id)
    reactivacion = _reactivar(propia, cliente_http, administrador, rol_ajeno.id)

    assert baja.status_code == reactivacion.status_code == 404
    assert _activo(ajena, rol_ajeno.id) is True


def test_baja_y_reactivacion_sin_el_permiso_responden_403(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """SEG-06."""
    entorno = EntornoUsuarios(sesion_real)
    rol = entorno.crear_rol("Vendedor", VENDER)
    usuario_id, nombre = entorno.crear_usuario(rol)
    vacio = entorno.crear_rol("Vacio", VENDER)
    sin_permiso = entorno.abrir_sesion(cliente_http, usuario_id, nombre)

    baja = _baja(entorno, cliente_http, sin_permiso, vacio.id)
    reactivacion = _reactivar(entorno, cliente_http, sin_permiso, vacio.id)

    assert baja.status_code == reactivacion.status_code == 403
    assert _activo(entorno, vacio.id) is True
