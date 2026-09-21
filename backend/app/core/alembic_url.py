"""Resuelve la URL de conexión que usa Alembic para correr migraciones
(tarea 1.5, `design.md` D3, `ADR-020`).

Alembic corre como el rol dueño del esquema (`app_migrations`), nunca como
`app_runtime` (el que usa la aplicación en runtime a través de
`app.core.config.Settings.database_url`). Por eso lee su propia variable de
entorno, `DATABASE_URL_MIGRATIONS`, y no un campo de `Settings`: el backend
en runtime no conoce ni referencia esta variable en ningún momento.
"""

from __future__ import annotations

import os


class DatabaseUrlMigracionesNoDefinidaError(RuntimeError):
    """`DATABASE_URL_MIGRATIONS` no está definida en el entorno."""


def resolver_database_url_migraciones() -> str:
    url = os.environ.get("DATABASE_URL_MIGRATIONS")
    if not url:
        raise DatabaseUrlMigracionesNoDefinidaError(
            "DATABASE_URL_MIGRATIONS no está definida. Alembic necesita la "
            "conexión del rol app_migrations (dueño del esquema), distinta "
            "de DATABASE_URL (rol app_runtime, que usa la aplicación en "
            "runtime y nunca corre migraciones)."
        )
    return url
