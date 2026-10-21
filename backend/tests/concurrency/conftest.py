"""Reusa el arnés de integración (Postgres real, Testcontainers) para las
pruebas de concurrencia (`docs/02-arquitectura.md` §15): mismas fixtures
(`database_url`, `_engine_de_sesion`, `app_runtime_engine`, ...), ninguna
transacción compartida entre pruebas (`db_session` no se usa acá: las
pruebas de concurrencia necesitan confirmar transacciones reales desde
conexiones independientes)."""

import sys
from pathlib import Path

# Los utiles de integración (`ventas_confirmar_utiles`, `cobranzas_utiles`, ...) son módulos
# planos: `tests/integration` no es un paquete y pytest solo lo agrega a `sys.path` al recolectar
# esa carpeta. Las pruebas de ventas los reusan para armar el mismo entorno (change 18a).
_INTEGRACION = str(Path(__file__).resolve().parent.parent / "integration")
if _INTEGRACION not in sys.path:
    sys.path.append(_INTEGRACION)

pytest_plugins = ["tests.integration.conftest"]
