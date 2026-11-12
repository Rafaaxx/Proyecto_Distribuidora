"""Change 20b, tarea 2.1: el conteo SQL general de administradores (`design.md` D3, ADR-053).

Cuenta solo usuarios ACTIVOS de roles ACTIVOS con `ADMIN_USUARIOS` de la organización, con
exclusión de un usuario, de un rol y con un rol sustituto (el estado después del cambio de rol).
Otra organización no cuenta.

Reglas citadas: ADR-053, INV-02 (aislamiento por organización), INV-21.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from roles_utiles import ADMIN, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import crear_engine, crear_session_factory
from app.modules.identidad import repository


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        with crear_session_factory(engine)() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def _contar(entorno: Entorno, **filtros: object) -> int:
    entorno.sesion.rollback()
    return repository.contar_administradores(
        entorno.org,
        entorno.sesion,
        permiso_codigo=ADMIN,
        **filtros,  # type: ignore[arg-type]
    )


def test_cuenta_solo_usuarios_activos_de_roles_activos_con_el_permiso(sesion: Session) -> None:
    entorno = Entorno(sesion)
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    de_baja = entorno.crear_rol("Administrador viejo", frozenset({ADMIN}), activo=False)
    sin_permiso = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    entorno.crear_usuario(administrador)
    entorno.crear_usuario(administrador)
    entorno.crear_usuario(administrador, estado="INACTIVO")
    entorno.crear_usuario(de_baja)
    entorno.crear_usuario(sin_permiso)

    assert _contar(entorno) == 2


def test_una_organizacion_sin_administradores_cuenta_cero(sesion: Session) -> None:
    entorno = Entorno(sesion)
    entorno.crear_usuario(entorno.crear_rol("Vendedor", frozenset({"VENDER"})))

    assert _contar(entorno) == 0


def test_excluir_a_un_usuario_lo_saca_del_conteo(sesion: Session) -> None:
    entorno = Entorno(sesion)
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    uno, _ = entorno.crear_usuario(administrador)
    entorno.crear_usuario(administrador)

    assert _contar(entorno, excluir_usuario_id=uno) == 1
    assert _contar(entorno) == 2


def test_excluir_a_un_rol_saca_a_todos_sus_usuarios(sesion: Session) -> None:
    entorno = Entorno(sesion)
    uno = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    otro = entorno.crear_rol("Gerencia", frozenset({ADMIN}))
    entorno.crear_usuario(uno)
    entorno.crear_usuario(uno)
    entorno.crear_usuario(otro)

    assert _contar(entorno, excluir_rol_id=uno.id) == 1
    assert _contar(entorno, excluir_rol_id=otro.id) == 2


def test_el_rol_sustituto_cuenta_al_usuario_con_el_rol_nuevo(sesion: Session) -> None:
    """Estado posterior al cambio de rol: el usuario deja de contar con su rol actual y cuenta con
    el nuevo solo si éste está activo y tiene el permiso."""
    entorno = Entorno(sesion)
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    gerencia = entorno.crear_rol("Gerencia", frozenset({ADMIN}))
    gerencia_de_baja = entorno.crear_rol("Vieja", frozenset({ADMIN}), activo=False)
    unico, _ = entorno.crear_usuario(administrador)

    assert _contar(entorno, rol_sustituto=(unico, vendedor.id)) == 0
    assert _contar(entorno, rol_sustituto=(unico, gerencia.id)) == 1
    assert _contar(entorno, rol_sustituto=(unico, gerencia_de_baja.id)) == 0


def test_el_rol_sustituto_suma_a_un_usuario_que_hoy_no_es_administrador(sesion: Session) -> None:
    entorno = Entorno(sesion)
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    vendedor = entorno.crear_rol("Vendedor", frozenset({"VENDER"}))
    entorno.crear_usuario(administrador)
    ascendido, _ = entorno.crear_usuario(vendedor)

    assert _contar(entorno) == 1
    assert _contar(entorno, rol_sustituto=(ascendido, administrador.id)) == 2


def test_el_rol_sustituto_de_un_usuario_inactivo_no_cuenta(sesion: Session) -> None:
    entorno = Entorno(sesion)
    administrador = entorno.crear_rol("Administrador", frozenset({ADMIN}))
    inactivo, _ = entorno.crear_usuario(
        entorno.crear_rol("Vendedor", frozenset({"VENDER"})), estado="INACTIVO"
    )

    assert _contar(entorno, rol_sustituto=(inactivo, administrador.id)) == 0


def test_otra_organizacion_no_cuenta(sesion: Session) -> None:
    propia = Entorno(sesion)
    ajena = Entorno(sesion)
    propia.crear_usuario(propia.crear_rol("Administrador", frozenset({ADMIN})))
    ajena.crear_usuario(ajena.crear_rol("Administrador", frozenset({ADMIN})))
    ajena.crear_usuario(ajena.crear_rol("Gerencia", frozenset({ADMIN})))

    assert _contar(propia) == 1
    assert _contar(ajena) == 2
