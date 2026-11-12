"""Tarea 1.5: Alembic corre con el rol `app_migrations`, leyendo su propia
variable de entorno `DATABASE_URL_MIGRATIONS`, separada de `DATABASE_URL`
(rol `app_runtime`, la única que conoce `app.core.config.Settings`).

`resolver_database_url_migraciones` no es un campo de `Settings`: el
backend en runtime no la conoce ni la referencia (`design.md` D3, decisión
confirmada de la tarea 1.5).
"""

from __future__ import annotations

import pytest

from app.core.alembic_url import (
    DatabaseUrlMigracionesNoDefinidaError,
    resolver_database_url_migraciones,
)


def test_resuelve_la_url_desde_database_url_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL_MIGRATIONS",
        "postgresql+psycopg://app_migrations:secreto@localhost:5432/distribuidora",
    )

    assert (
        resolver_database_url_migraciones()
        == "postgresql+psycopg://app_migrations:secreto@localhost:5432/distribuidora"
    )


def test_falla_explicito_si_no_esta_definida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL_MIGRATIONS", raising=False)

    with pytest.raises(DatabaseUrlMigracionesNoDefinidaError, match="DATABASE_URL_MIGRATIONS"):
        resolver_database_url_migraciones()


def test_no_usa_database_url_como_alternativa(monkeypatch: pytest.MonkeyPatch) -> None:
    """`DATABASE_URL` es del rol `app_runtime`; nunca debe colarse como
    conexión de Alembic aunque esté definida."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://app_runtime:otro@localhost:5432/distribuidora"
    )
    monkeypatch.delenv("DATABASE_URL_MIGRATIONS", raising=False)

    with pytest.raises(DatabaseUrlMigracionesNoDefinidaError):
        resolver_database_url_migraciones()
