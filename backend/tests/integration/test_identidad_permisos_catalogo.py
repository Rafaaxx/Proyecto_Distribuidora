"""Change 17b, tareas 7.1 y 7.2: `GET /api/v1/identidad/permisos` (catálogo global, spec
`identidad/administracion-de-roles`) y la cantidad de usuarios activos por rol en
`GET /api/v1/identidad/roles` (D9), contra PostgreSQL real.

Reglas citadas: `01` §19, `03` §4, TR-08, INV-21, SEG-07, ADR-027.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from roles_utiles import ADMIN, JWT_SECRET, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.main import crear_app
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.identidad.domain.permisos import PERMISOS_DEL_CATALOGO

URL_PERMISOS = "/api/v1/identidad/permisos"
URL_ROLES = "/api/v1/identidad/roles"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


def _administrador(cliente: TestClient, entorno: Entorno) -> dict[str, str]:
    rol = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(rol)
    return entorno.entrar(cliente, nombre)


def test_el_catalogo_trae_codigo_descripcion_y_modulo_en_el_orden_de_01_19(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenario "Catálogo completo" (`01` §19)."""
    administrador = _administrador(cliente, entorno)

    respuesta = cliente.get(URL_PERMISOS, headers=administrador)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [p["codigo"] for p in cuerpo] == [p.codigo for p in PERMISOS_DEL_CATALOGO]
    por_codigo = {p["codigo"]: p for p in cuerpo}
    assert por_codigo["ANULAR_COBRANZA"] == {
        "codigo": "ANULAR_COBRANZA",
        "descripcion": "Anular cobranzas",
        "modulo": "cobranzas",
    }
    assert por_codigo[ADMIN]["modulo"] == "identidad"
    assert all(set(p) == {"codigo", "descripcion", "modulo"} for p in cuerpo)


def test_el_catalogo_sin_admin_usuarios_responde_403(cliente: TestClient, entorno: Entorno) -> None:
    """Escenario "Sin permiso" (ADR-027)."""
    rol = entorno.crear_rol("Consulta", frozenset({"VER_REPORTES"}))
    _, nombre = entorno.crear_usuario(rol)
    headers = entorno.entrar(cliente, nombre)

    respuesta = cliente.get(URL_PERMISOS, headers=headers)

    assert respuesta.status_code == 403
    assert "ANULAR_COBRANZA" not in respuesta.text


def test_el_catalogo_exige_sesion(cliente: TestClient) -> None:
    assert cliente.get(URL_PERMISOS).status_code == 401


def test_get_roles_suma_los_usuarios_activos_de_cada_rol(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Tarea 7.2 (D9): solo cuentan los usuarios ACTIVOS; un rol sin usuarios trae 0."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    ventas = entorno.crear_rol("Ventas", frozenset({"VENDER"}))
    entorno.crear_usuario(ventas)
    entorno.crear_usuario(ventas)
    entorno.crear_usuario(ventas, estado="INACTIVO")
    entorno.crear_rol("Vacío", frozenset())
    headers = entorno.entrar(cliente, nombre)

    respuesta = cliente.get(URL_ROLES, headers=headers)

    assert respuesta.status_code == 200, respuesta.text
    por_nombre = {rol["nombre"]: rol for rol in respuesta.json()}
    assert por_nombre["Administrador"]["usuarios_activos"] == 1
    assert por_nombre["Ventas"]["usuarios_activos"] == 2
    assert por_nombre["Vacío"]["usuarios_activos"] == 0
    assert por_nombre["Ventas"]["permisos"] == ["VENDER"]


def test_get_roles_no_cuenta_los_usuarios_de_otra_organizacion(
    cliente: TestClient, entorno: Entorno, sesion: Session
) -> None:
    """INV-21, TR-08: el conteo se filtra por la organización del token."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    ajena = Entorno(sesion)
    rol_ajeno = ajena.crear_rol("Administrador", frozenset({ADMIN}))
    ajena.crear_usuario(rol_ajeno)
    ajena.crear_usuario(rol_ajeno)
    headers = entorno.entrar(cliente, nombre)

    respuesta = cliente.get(URL_ROLES, headers=headers)

    por_nombre = {rol["nombre"]: rol for rol in respuesta.json()}
    assert por_nombre["Administrador"]["usuarios_activos"] == 1
