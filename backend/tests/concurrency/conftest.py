"""Reusa el arnés de integración (Postgres real, Testcontainers) para las
pruebas de concurrencia (`docs/02-arquitectura.md` §15): mismas fixtures
(`database_url`, `_engine_de_sesion`, `app_runtime_engine`, ...), ninguna
transacción compartida entre pruebas (`db_session` no se usa acá: las
pruebas de concurrencia necesitan confirmar transacciones reales desde
conexiones independientes)."""

pytest_plugins = ["tests.integration.conftest"]
