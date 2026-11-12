"""Change 20b, tarea 8.3: concurrencia real de `ROL_BAJA` frente a las operaciones que asignan
usuarios a un rol, contra PostgreSQL real (Testcontainers, `READ COMMITTED`,
`docs/02-arquitectura.md` §7.1 y §7.3). Mismo arnés que `test_identidad_bajas_concurrentes.py`:
cada hilo con su sesión, su transacción confirmada por el bus y arranque junto en una barrera.
Nunca hay rollback externo (`CLAUDE.md` §4).

Escenarios (`design.md` D4, D11, ADR-028 D9.4, INV-01):

- (a) la baja de un rol frente a un cambio de rol hacia él: o la baja se aplica y el cambio responde
  `IDENTIDAD_ROL_INACTIVO`, o el cambio se aplica y la baja responde
  `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`; nunca queda un usuario activo en un rol de baja.
- (b) lo mismo frente a un alta de usuario en ese rol.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text

from app.core.db import crear_engine
from app.modules.identidad.domain.usuarios import RolConUsuariosActivosError, RolInactivoError
from tests.concurrency.identidad_escenario import VENDER, EscenarioDeIdentidad
from tests.concurrency.test_compras_concurrencia import _en_paralelo

RONDAS = 5


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _un_exito_y_un_rechazo_esperado(
    resultados: dict[int, object], errores: dict[int, BaseException]
) -> BaseException:
    assert len(resultados) == 1, (resultados, errores)
    assert len(errores) == 1, (resultados, errores)
    (error,) = errores.values()
    assert isinstance(error, (RolInactivoError, RolConUsuariosActivosError)), repr(error)
    return error


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_a_la_baja_de_un_rol_frente_a_un_cambio_de_rol_hacia_el_nunca_deja_un_activo_en_el_de_baja(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-028 D9.4, D4, INV-01."""
    escenario = EscenarioDeIdentidad(database_url)
    a, _ = escenario.administrador()
    b, _ = escenario.administrador()
    vendedor, _ = escenario.crear_usuario(frozenset({VENDER}))
    _, rol_destino = escenario.crear_usuario(frozenset({VENDER}))
    # El usuario de `rol_destino` se da de baja para que el rol quede sin usuarios activos.
    sesion_aux = escenario.leer("SELECT id FROM usuario WHERE rol_id = :r", r=rol_destino)
    escenario.marcar_inactivo(sesion_aux[0][0])

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: escenario.baja_de_rol(sesion, a, rol_destino),
            lambda sesion: escenario.cambiar_rol(sesion, b, vendedor[0], rol_destino),
        ],
    )

    error = _un_exito_y_un_rechazo_esperado(resultados, errores)
    assert escenario.usuarios_activos_en_roles_de_baja() == 0
    if isinstance(error, RolInactivoError):
        assert escenario.rol_activo(rol_destino) is False
    else:
        assert escenario.rol_activo(rol_destino) is True


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_b_la_baja_de_un_rol_frente_a_un_alta_en_el_nunca_deja_un_activo_en_el_de_baja(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-028 D9.4, D4, INV-01: el alta toma la misma exclusión mutua y ve el rol inactivo."""
    escenario = EscenarioDeIdentidad(database_url)
    a, _ = escenario.administrador()
    b, _ = escenario.administrador()
    _, rol_destino = escenario.crear_usuario(frozenset({VENDER}))
    escenario.marcar_inactivo(
        escenario.leer("SELECT id FROM usuario WHERE rol_id = :r", r=rol_destino)[0][0]
    )

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: escenario.baja_de_rol(sesion, a, rol_destino),
            lambda sesion: escenario.alta_de_usuario(sesion, b, rol_destino),
        ],
    )

    error = _un_exito_y_un_rechazo_esperado(resultados, errores)
    assert escenario.usuarios_activos_en_roles_de_baja() == 0
    assert (escenario.rol_activo(rol_destino) is False) == isinstance(error, RolInactivoError)


def test_el_conteo_del_escenario_ve_a_un_activo_en_un_rol_de_baja(
    database_url: str, _engine_de_sesion
) -> None:
    """Triangulación sin carrera: la consulta de la invariante detecta lo que debe detectar."""
    escenario = EscenarioDeIdentidad(database_url)
    usuario, rol = escenario.crear_usuario(frozenset({VENDER}))
    assert escenario.usuarios_activos_en_roles_de_baja() == 0

    escenario.desactivar_rol(rol)

    assert escenario.usuarios_activos_en_roles_de_baja() == 1
    assert escenario.estado_de(usuario[0]) == "ACTIVO"
