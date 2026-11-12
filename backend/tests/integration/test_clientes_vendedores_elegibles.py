# ruff: noqa: F811
"""Change 20b, tarea 10.3 (`design.md` D15; spec `clientes/cartera-de-clientes`): `GET
/clientes/vendedores` ofrece los vendedores elegibles a quien administra clientes, sin pedirle
`ADMIN_USUARIOS`.

Elegible = usuario `ACTIVO`, con rol activo y con `VENDER` o `REGISTRAR_COBRANZA`. Se calcula en la
base y se acota a la organización del token.

Reglas citadas: `01` §19, ADR-028, ADR-060, INV-21.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from usuarios_utiles import (
    EntornoUsuarios,
    SesionAbierta,
    cliente_http,  # noqa: F401  (fixture)
    limpiar_datos_confirmados,  # noqa: F401  (fixture)
    sesion_real,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.usefixtures("limpiar_datos_confirmados")

URL = "/api/v1/clientes/vendedores"


def _usuario(
    e: EntornoUsuarios,
    http: TestClient,
    nombre: str,
    permisos: frozenset[str],
    *,
    estado: str = "ACTIVO",
    rol_activo: bool = True,
) -> tuple[UUID, SesionAbierta | None]:
    rol = e.crear_rol(f"Rol {nombre}", permisos, activo=rol_activo)
    usuario_id, usuario = e.crear_usuario(rol, estado=estado)
    e.sesion.execute(
        text("UPDATE usuario SET nombre = :n WHERE id = :u"),
        {"n": nombre, "u": usuario_id},
    )
    e.sesion.commit()
    activo = estado == "ACTIVO" and rol_activo
    return usuario_id, (e.abrir_sesion(http, usuario_id, usuario) if activo else None)


def _ids(respuesta: Any) -> set[str]:
    assert respuesta.status_code == 200, respuesta.text
    return {fila["id"] for fila in respuesta.json()}


def test_quien_solo_gestiona_clientes_recibe_los_vendedores_elegibles(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """ges01: `GESTIONAR_CLIENTES` sin `ADMIN_USUARIOS`; ve vendedores y cobradores, ordenados."""
    e = EntornoUsuarios(sesion_real)
    vende, _ = _usuario(e, cliente_http, "Beto", frozenset({"VENDER"}))
    cobra, _ = _usuario(e, cliente_http, "Ana", frozenset({"REGISTRAR_COBRANZA"}))
    _, gestor = _usuario(e, cliente_http, "Gestor", frozenset({"GESTIONAR_CLIENTES"}))
    assert gestor is not None

    respuesta = e.enviar(cliente_http, "GET", URL, gestor)

    assert _ids(respuesta) == {str(vende), str(cobra)}
    assert [f["nombre"] for f in respuesta.json()] == ["Ana", "Beto"]
    assert set(respuesta.json()[0]) == {"id", "nombre"}


def test_sin_gestionar_clientes_responde_403(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = EntornoUsuarios(sesion_real)
    _, vendedor = _usuario(e, cliente_http, "Vende", frozenset({"VENDER", "ADMIN_USUARIOS"}))
    assert vendedor is not None

    assert e.enviar(cliente_http, "GET", URL, vendedor).status_code == 403


def test_excluye_inactivos_rol_de_baja_y_roles_sin_permiso_de_vendedor(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    e = EntornoUsuarios(sesion_real)
    bueno, _ = _usuario(e, cliente_http, "Bueno", frozenset({"VENDER"}))
    _usuario(e, cliente_http, "Inactivo", frozenset({"VENDER"}), estado="INACTIVO")
    _usuario(e, cliente_http, "RolBaja", frozenset({"VENDER"}), rol_activo=False)
    _usuario(e, cliente_http, "Otro", frozenset({"GESTIONAR_CLIENTES", "VER_REPORTES"}))
    _, gestor = _usuario(e, cliente_http, "Gestor", frozenset({"GESTIONAR_CLIENTES"}))
    assert gestor is not None

    assert _ids(e.enviar(cliente_http, "GET", URL, gestor)) == {str(bueno)}


def test_no_lista_usuarios_de_otra_organizacion(
    cliente_http: TestClient, sesion_real: Session
) -> None:
    """INV-21: la organización sale del token."""
    propia = EntornoUsuarios(sesion_real)
    ajena = EntornoUsuarios(sesion_real)
    mio, _ = _usuario(propia, cliente_http, "Mio", frozenset({"VENDER"}))
    _usuario(ajena, cliente_http, "Ajeno", frozenset({"VENDER"}))
    _, gestor = _usuario(propia, cliente_http, "Gestor", frozenset({"GESTIONAR_CLIENTES"}))
    assert gestor is not None

    assert _ids(propia.enviar(cliente_http, "GET", URL, gestor)) == {str(mio)}
