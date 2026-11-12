"""Change 17b, tarea 6.2: ningún cambio de permisos deja la organización sin administrador
(spec `identidad/usuarios-y-roles`, ADR-053), por `PUT /api/v1/identidad/roles/{id}/permisos`
contra PostgreSQL real. La carrera entre dos cambios simultáneos es la tarea 12.1.

Reglas citadas: ADR-053 (D8), TR-10, INV-01, INV-02, INV-06, INV-21, ADR-011.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from roles_utiles import ADMIN, AUTORIZACION, CODIGO, JWT_SECRET, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.main import crear_app
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)


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


def test_quitar_el_permiso_al_unico_rol_que_lo_tiene_responde_409_y_no_cambia_nada(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenarios "Quitar el permiso al único rol que lo tiene" y "El rechazo no toca el PIN"
    (ADR-053, TR-10, ADR-011, INV-01)."""
    completo = frozenset({ADMIN, "VER_REPORTES"}) | AUTORIZACION
    administrador = entorno.crear_rol("Administrador", completo)
    rafa, nombre = entorno.crear_usuario(administrador, con_pin=True)
    headers = entorno.entrar(cliente, nombre)
    auditorias_antes = entorno.filas_de_auditoria()

    respuesta = entorno.cambiar(cliente, headers, administrador, frozenset({"VER_REPORTES"}))

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["codigo"] == CODIGO
    assert entorno.permisos_de(administrador.id) == sorted(completo)
    assert entorno.pin_vigente(rafa) is True
    assert entorno.filas_de_auditoria() == auditorias_antes


def test_el_rechazo_no_deja_rastro_y_el_mismo_pedido_puede_reintentarse(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Un rechazo no queda registrado como comando resuelto: tras darle el permiso a otro rol, el
    reintento con el mismo `Operation-Id` se acepta."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    headers = entorno.entrar(cliente, nombre)
    operation_id = uuid4()

    primero = entorno.cambiar(
        cliente, headers, administrador, frozenset(), operation_id=operation_id
    )
    assert primero.status_code == 409

    otro = entorno.crear_rol("Administración", frozenset({ADMIN}))
    entorno.crear_usuario(otro)
    segundo = entorno.cambiar(
        cliente, headers, administrador, frozenset(), operation_id=operation_id
    )

    assert segundo.status_code == 200, segundo.text
    assert entorno.permisos_de(administrador.id) == []


def test_otro_rol_con_usuario_activo_conserva_el_permiso_y_el_cambio_se_acepta(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenario "Otro usuario activo conserva el permiso" (`01` §19)."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN, "VER_REPORTES"}))
    _, nombre = entorno.crear_usuario(administrador)
    administracion = entorno.crear_rol("Administración", frozenset({ADMIN}))
    entorno.crear_usuario(administracion)
    headers = entorno.entrar(cliente, nombre)

    respuesta = entorno.cambiar(cliente, headers, administrador, frozenset({"VER_REPORTES"}))

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.permisos_de(administrador.id) == ["VER_REPORTES"]
    assert entorno.permisos_de(administracion.id) == [ADMIN]


def test_el_otro_rol_con_solo_usuarios_inactivos_no_cuenta(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenario "El otro rol solo tiene usuarios inactivos" (ADR-028)."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    administracion = entorno.crear_rol("Administración", frozenset({ADMIN}))
    entorno.crear_usuario(administracion, estado="INACTIVO")
    headers = entorno.entrar(cliente, nombre)

    respuesta = entorno.cambiar(cliente, headers, administrador, frozenset())

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == CODIGO
    assert entorno.permisos_de(administrador.id) == [ADMIN]


def test_un_rol_inactivo_con_el_permiso_no_cuenta(cliente: TestClient, entorno: Entorno) -> None:
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    historico = entorno.crear_rol("Histórico", frozenset({ADMIN}), activo=False)
    entorno.crear_usuario(historico)
    headers = entorno.entrar(cliente, nombre)

    respuesta = entorno.cambiar(cliente, headers, administrador, frozenset())

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == CODIGO


def test_otra_organizacion_no_cuenta(
    cliente: TestClient, entorno: Entorno, sesion: Session
) -> None:
    """Escenario "Otra organización no cuenta" (TR-08, INV-02)."""
    ajena = Entorno(sesion)
    rol_ajeno = ajena.crear_rol("Administrador", frozenset({ADMIN}))
    ajena.crear_usuario(rol_ajeno)
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    headers = entorno.entrar(cliente, nombre)

    respuesta = entorno.cambiar(cliente, headers, administrador, frozenset())

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == CODIGO
    assert ajena.permisos_de(rol_ajeno.id) == [ADMIN]


def test_conservar_el_permiso_en_el_unico_rol_se_acepta(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Quitar otros permisos del único administrador no es un caso de rechazo."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN, "VER_REPORTES", "VENDER"}))
    _, nombre = entorno.crear_usuario(administrador)
    headers = entorno.entrar(cliente, nombre)

    respuesta = entorno.cambiar(cliente, headers, administrador, frozenset({ADMIN}))

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.permisos_de(administrador.id) == [ADMIN]


def test_cambiar_un_rol_que_nunca_tuvo_el_permiso_no_se_valida(
    cliente: TestClient, entorno: Entorno
) -> None:
    """La regla solo corre cuando se QUITA `ADMIN_USUARIOS` de un rol que lo tenía."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administrador)
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    headers = entorno.entrar(cliente, nombre)

    respuesta = entorno.cambiar(cliente, headers, vendedor, frozenset({"VER_REPORTES"}))

    assert respuesta.status_code == 200, respuesta.text
    assert entorno.permisos_de(vendedor.id) == ["VER_REPORTES"]


def test_doble_envio_del_cambio_aceptado_devuelve_lo_mismo_sin_otra_auditoria(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Escenario "Doble envío" (INV-06)."""
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN, "VER_REPORTES"}))
    entorno.crear_usuario(administrador)
    administracion = entorno.crear_rol("Administración", frozenset({ADMIN}))
    _, nombre = entorno.crear_usuario(administracion)
    headers = entorno.entrar(cliente, nombre)
    operation_id = uuid4()
    nuevos = frozenset({"VER_REPORTES"})

    primera = entorno.cambiar(cliente, headers, administrador, nuevos, operation_id=operation_id)
    auditorias = entorno.filas_de_auditoria()
    segunda = entorno.cambiar(cliente, headers, administrador, nuevos, operation_id=operation_id)

    assert (primera.status_code, segunda.status_code) == (200, 200)
    assert segunda.json() == primera.json()
    assert entorno.filas_de_auditoria() == auditorias
