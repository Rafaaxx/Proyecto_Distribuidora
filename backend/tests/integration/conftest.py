"""Fixtures de integración: usan la base de PostgreSQL real levantada por
Docker Compose (`docker compose up -d postgres`), nunca SQLite (`docs/02` §15).

El arnés de Testcontainers llega en el change 01b; mientras tanto, estas
pruebas asumen que la base de desarrollo ya está arriba y usan
`DATABASE_URL` del entorno (por defecto, la del `docker-compose.yml` de
este change corriendo en `localhost`).
"""

import os

import pytest

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://distribuidora:distribuidora@localhost:5432/distribuidora",
)


@pytest.fixture
def database_url() -> str:
    return DATABASE_URL
