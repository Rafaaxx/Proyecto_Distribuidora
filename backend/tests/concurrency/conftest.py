"""Reusa el arnés de integración (Postgres real, Testcontainers) para las
pruebas de concurrencia (`docs/02-arquitectura.md` §15): mismas fixtures
(`database_url`, `_engine_de_sesion`, `app_runtime_engine`, ...), ninguna
transacción compartida entre pruebas (`db_session` no se usa acá: las
pruebas de concurrencia necesitan confirmar transacciones reales desde
conexiones independientes)."""

import sys
import weakref
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, event

# Los utiles de integración (`ventas_confirmar_utiles`, `cobranzas_utiles`, ...) son módulos
# planos: `tests/integration` no es un paquete y pytest solo lo agrega a `sys.path` al recolectar
# esa carpeta. Las pruebas de ventas los reusan para armar el mismo entorno (change 18a).
_INTEGRACION = str(Path(__file__).resolve().parent.parent / "integration")
if _INTEGRACION not in sys.path:
    sys.path.append(_INTEGRACION)

pytest_plugins = ["tests.integration.conftest"]


# Cada prueba arma sus propios engines (`_sesion_independiente`, `crear_engine(database_url)`
# dentro de hilos, ...) y casi ninguno se descarta: `Session.close()` devuelve la conexión al
# pool del engine, pero el pool la mantiene abierta. Con ~600 pruebas en un solo proceso esas
# conexiones ociosas se acumulan hasta `max_connections` de PostgreSQL ("too many clients").
# En vez de tocar cada archivo, se registran todos los engines que abren una conexión y se
# descartan al terminar cada prueba (`dispose()` cierra las conexiones ociosas del pool).
_ENGINES_ABIERTOS: "weakref.WeakSet[Engine]" = weakref.WeakSet()


def _registrar_engine(conexion: Connection) -> None:
    _ENGINES_ABIERTOS.add(conexion.engine)


@pytest.fixture(scope="session", autouse=True)
def _registro_de_engines() -> Iterator[None]:
    event.listen(Engine, "engine_connect", _registrar_engine)
    yield
    event.remove(Engine, "engine_connect", _registrar_engine)


@pytest.fixture(autouse=True)
def _liberar_conexiones_de_la_prueba(_registro_de_engines: None) -> Iterator[None]:
    yield
    for engine in list(_ENGINES_ABIERTOS):
        engine.dispose()
    _ENGINES_ABIERTOS.clear()
