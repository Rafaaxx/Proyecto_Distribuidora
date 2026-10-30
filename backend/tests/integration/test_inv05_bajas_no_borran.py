# ruff: noqa: F811
"""Change 20b, tarea 12.1 (INV-05): ninguna baja del change borra filas confirmadas.

Dar de baja a un usuario o a un rol los marca `INACTIVO` / `activo = false`: las filas siguen en la
base con sus datos, la auditoría anterior no desaparece (solo se suma la nueva) y la baja de un rol
conserva sus permisos. Una corrección es siempre una escritura inversa (reactivar), nunca un
borrado. Reglas citadas: INV-05, INV-01, AUD-01, ADR-028 D9.4 y D9.5, ADR-053.
"""

from __future__ import annotations

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
VENDER = frozenset({"VENDER", "REGISTRAR_COBRANZA"})


def test_inv05_la_baja_de_un_usuario_no_borra_su_fila_ni_la_auditoria_anterior(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-05: el usuario dado de baja sigue existiendo y la auditoría solo crece."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Vendedor", VENDER)
    usuario_id, nombre = entorno.crear_usuario(rol)
    auditoria_antes = entorno.total_auditoria()
    filas_antes = entorno.fila(
        "SELECT count(*) AS n FROM usuario WHERE organizacion_id = :o", o=entorno.org
    )[0]["n"]

    respuesta = entorno.enviar(
        cliente_http,
        "POST",
        f"{URL_USUARIOS}/{usuario_id}/baja",
        administrador,
        {"observacion": None},
    )

    assert respuesta.status_code == 200, respuesta.text
    fila = entorno.usuario(usuario_id)
    assert fila["estado"] == "INACTIVO"
    assert fila["usuario"] == nombre
    assert (
        entorno.fila("SELECT count(*) AS n FROM usuario WHERE organizacion_id = :o", o=entorno.org)[
            0
        ]["n"]
        == filas_antes
    )
    assert entorno.total_auditoria() > auditoria_antes


def test_inv05_la_baja_de_un_rol_no_borra_el_rol_ni_sus_permisos(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-05: triangulación con el rol; los permisos se conservan (se pueden seguir editando)."""
    entorno = EntornoUsuarios(sesion_real)
    administrador = entorno.administrador(cliente_http)
    rol = entorno.crear_rol("Repartidor", VENDER)
    permisos_antes = entorno.fila(
        "SELECT count(*) AS n FROM rol_permiso WHERE rol_id = :r", r=rol.id
    )[0]["n"]

    respuesta = entorno.enviar(
        cliente_http, "POST", f"{URL_ROLES}/{rol.id}/baja", administrador, {}
    )

    assert respuesta.status_code == 200, respuesta.text
    (fila,) = entorno.fila("SELECT activo, nombre FROM rol WHERE id = :r", r=rol.id)
    assert fila["activo"] is False
    assert fila["nombre"] == "Repartidor"
    assert permisos_antes == len(VENDER)
    assert (
        entorno.fila("SELECT count(*) AS n FROM rol_permiso WHERE rol_id = :r", r=rol.id)[0]["n"]
        == permisos_antes
    )
