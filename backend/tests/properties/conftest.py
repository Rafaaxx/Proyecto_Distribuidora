"""Reusa las fixtures del arnés de integración (PostgreSQL real, Testcontainers)
para las propiedades que necesitan la base (INV-13 contra PostgreSQL, change 08,
tarea 8.2). Se importan por nombre y no con `pytest_plugins`: pytest no admite
declarar plugins en un `conftest.py` que no es de la raíz.

Las propiedades de dominio puro (`test_cat08_*`, `test_money_*`, ...) no piden
estas fixtures, así que no arrancan ningún contenedor."""

import sys
from pathlib import Path

# Los utiles de integración (`ventas_confirmar_utiles`, ...) son módulos planos: ver
# `tests/concurrency/conftest.py`.
_INTEGRACION = str(Path(__file__).resolve().parent.parent / "integration")
if _INTEGRACION not in sys.path:
    sys.path.append(_INTEGRACION)

from tests.integration.conftest import (  # noqa: E402, F401
    _engine_de_sesion,
    _jwt_secret_de_pruebas,
    database_url,
    db_session,
)
