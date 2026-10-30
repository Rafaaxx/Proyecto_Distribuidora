"""Change 20b, tarea 6.1: concurrencia real de las operaciones de identidad que pueden dejar a la
organización sin administrador, contra PostgreSQL real (Testcontainers, `READ COMMITTED`,
`docs/02-arquitectura.md` §7.1 y §7.3). Mismo arnés que `test_medios_y_roles_concurrencia.py`:
cada hilo tiene su propia conexión/sesión, confirma su propia transacción por el bus y arranca
junto a los otros en una `threading.Barrier`. Nunca hay rollback externo (`CLAUDE.md` §4), y cada
escenario crea su propia organización: ninguna prueba deja sin administrador una base distinta de
la del contenedor.

Escenarios (`design.md` D3, D4, ADR-053, INV-01):

- (a) tres administradores: A da de baja a B y B a A a la vez -> exactamente una baja; la otra,
  `PERMISO_REQUERIDO` (la revalidación de quien ejecuta).
- (b) dos administradores: A da de baja a B y B le cambia el rol a A -> la organización conserva
  uno.
- (c) dos cambios de rol simultáneos que sacan a los dos últimos administradores -> uno se
  rechaza.
- (d) la baja de un usuario frente a `ROL_PERMISOS_CAMBIAR` que quita `ADMIN_USUARIOS` -> siempre
  queda uno.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text

from app.core.db import crear_engine
from app.core.errors import PermisoRequeridoError
from tests.concurrency.identidad_escenario import VENDER, EscenarioDeIdentidad
from tests.concurrency.test_compras_concurrencia import _en_paralelo

RONDAS = 4


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


def _solo_un_exito_y_el_otro_sin_permiso(
    resultados: dict[int, object], errores: dict[int, BaseException]
) -> None:
    assert len(resultados) == 1, (resultados, errores)
    assert len(errores) == 1, (resultados, errores)
    (error,) = errores.values()
    assert isinstance(error, PermisoRequeridoError), repr(error)
    assert error.codigo == "PERMISO_REQUERIDO"


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_a_dos_administradores_que_se_dan_de_baja_mutuamente_dejan_exactamente_una_baja(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-053, D4: con tres administradores la regla del último no alcanza (los dos pasan); la
    revalidación de quien ejecuta rechaza al que ya fue dado de baja. INV-01."""
    escenario = EscenarioDeIdentidad(database_url)
    a, _ = escenario.administrador()
    b, _ = escenario.administrador()
    c, _ = escenario.administrador()

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: escenario.baja(sesion, a, b[0]),
            lambda sesion: escenario.baja(sesion, b, a[0]),
        ],
    )

    _solo_un_exito_y_el_otro_sin_permiso(resultados, errores)
    estados = {escenario.estado_de(u[0]) for u in (a, b)}
    assert estados == {"ACTIVO", "INACTIVO"}
    assert escenario.estado_de(c[0]) == "ACTIVO"
    assert escenario.administradores_activos() == 2


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_b_la_baja_de_uno_frente_al_cambio_de_rol_del_otro_conserva_un_administrador(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-053, INV-01: A da de baja a B mientras B le cambia el rol a A. Sin la exclusión mutua
    ambas validaciones verían al otro como administrador y la organización quedaría vacía."""
    escenario = EscenarioDeIdentidad(database_url)
    a, _ = escenario.administrador()
    b, _ = escenario.administrador()
    vendedor = escenario.rol_de_vendedor()

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: escenario.baja(sesion, a, b[0]),
            lambda sesion: escenario.cambiar_rol(sesion, b, a[0], vendedor),
        ],
    )

    _solo_un_exito_y_el_otro_sin_permiso(resultados, errores)
    assert escenario.administradores_activos() == 1


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_c_dos_cambios_de_rol_que_sacan_a_los_dos_ultimos_administradores_rechazan_uno(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-053: A le cambia el rol a B y B le cambia el rol a A, los dos únicos administradores."""
    escenario = EscenarioDeIdentidad(database_url)
    a, _ = escenario.administrador()
    b, _ = escenario.administrador()
    vendedor = escenario.rol_de_vendedor()

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: escenario.cambiar_rol(sesion, a, b[0], vendedor),
            lambda sesion: escenario.cambiar_rol(sesion, b, a[0], vendedor),
        ],
    )

    _solo_un_exito_y_el_otro_sin_permiso(resultados, errores)
    assert escenario.administradores_activos() == 1


@pytest.mark.parametrize("ronda", range(RONDAS))
def test_d_la_baja_de_un_usuario_frente_a_quitar_admin_usuarios_a_un_rol_deja_siempre_uno(
    database_url: str, _engine_de_sesion, ronda: int
) -> None:
    """ADR-053: A (de su rol) y B (de otro rol) son los dos únicos administradores. B da de baja a
    A mientras A le quita `ADMIN_USUARIOS` al rol de B. Cualquiera sea el orden, queda uno."""
    escenario = EscenarioDeIdentidad(database_url)
    a, _ = escenario.administrador()
    b, rol_de_b = escenario.administrador()

    resultados, errores = _en_paralelo(
        database_url,
        [
            lambda sesion: escenario.baja(sesion, b, a[0]),
            lambda sesion: escenario.cambiar_permisos(sesion, a, rol_de_b, [VENDER]),
        ],
    )

    _solo_un_exito_y_el_otro_sin_permiso(resultados, errores)
    assert escenario.administradores_activos() == 1


def test_el_conteo_del_escenario_distingue_a_un_administrador_de_un_vendedor(
    database_url: str, _engine_de_sesion
) -> None:
    """Sin carrera, triangulación: el conteo del escenario cuenta a quien tiene `ADMIN_USUARIOS` y
    no a un vendedor, así que las aserciones de arriba miden lo que dicen medir."""
    escenario = EscenarioDeIdentidad(database_url)
    escenario.administrador()
    escenario.crear_usuario(frozenset({VENDER}))

    assert escenario.administradores_activos() == 1
