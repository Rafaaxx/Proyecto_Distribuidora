"""Arnés de integración: PostgreSQL real, nunca SQLite (`docs/02` §15).

Ciclo de vida (`design.md` D2):
- Si `DATABASE_URL` está definida en el entorno, se usa tal cual (flujo de
  desarrollo con `docker compose up -d postgres` ya arriba). No se levanta
  contenedor.
- Si no, se levanta un contenedor de PostgreSQL con Testcontainers, una vez
  por sesión de pytest, y se aplican las migraciones de Alembic antes de la
  primera prueba.
- Si no hay `DATABASE_URL` ni motor de contenedores disponible, la corrida
  falla con un mensaje explícito (spec `integracion-continua`, "No hay motor
  de contenedores disponible"). Nunca cae a un sustituto en memoria.

Aislamiento: `db_session` da a cada prueba una transacción revertida al
final (`docs/02` §15). Las pruebas de concurrencia NO pueden usar esta
fixture: necesitan confirmar transacciones reales desde conexiones
independientes para ejercer condiciones de carrera, y una transacción
externa que se revierte se lo impide. Cuando lleguen (change 04), usan su
propia limpieza explícita contra `database_url` / `_engine_de_sesion`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from app.core.db import crear_engine, crear_session_factory

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _motor_de_contenedores_disponible() -> bool:
    try:
        import docker

        cliente = docker.from_env()
        try:
            cliente.ping()
            return True
        finally:
            cliente.close()
    except Exception:
        return False


def aplicar_migraciones(database_url: str, *, revision: str = "head") -> None:
    """Aplica migraciones de Alembic sobre `database_url` hasta `revision`."""
    entorno = {**os.environ, "DATABASE_URL": database_url}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"No se pudieron aplicar las migraciones: {resultado.stderr}")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url_entorno = os.environ.get("DATABASE_URL")
    if url_entorno:
        yield url_entorno
        return

    if not _motor_de_contenedores_disponible():
        pytest.fail(
            "No hay motor de contenedores disponible y no se definió "
            "DATABASE_URL. Las pruebas de integración requieren PostgreSQL "
            "real (docs/02-arquitectura.md §15): levantá Docker (o Docker "
            "Desktop) para que Testcontainers pueda arrancar un contenedor, "
            "o exportá DATABASE_URL apuntando a una base de desarrollo ya "
            "levantada. Nunca se usa un sustituto en memoria.",
            pytrace=False,
        )

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as contenedor:
        yield contenedor.get_connection_url()


@pytest.fixture(scope="session")
def _engine_de_sesion(database_url: str) -> Engine:
    aplicar_migraciones(database_url)
    return crear_engine(database_url)


@pytest.fixture
def db_session(_engine_de_sesion: Engine) -> Iterator[Session]:
    """Sesión de prueba aislada por transacción revertida al final.

    `join_transaction_mode="create_savepoint"` hace que un `flush()` fallido
    (por ejemplo, un `IntegrityError` esperado en una prueba negativa) solo
    revierta hasta un SAVEPOINT interno, sin desasociar la transacción
    externa (`transaccion`) que este fixture necesita revertir al final.
    Sin esto, la segunda llamada a `rollback()` (la de acá abajo, después de
    que una prueba ya provocó y capturó un `IntegrityError`) emite
    `SAWarning: transaction already deassociated from connection`.
    """
    conexion = _engine_de_sesion.connect()
    transaccion = conexion.begin()
    factory = crear_session_factory(_engine_de_sesion)
    sesion = factory(bind=conexion, join_transaction_mode="create_savepoint")

    try:
        yield sesion
    finally:
        sesion.close()
        transaccion.rollback()
        conexion.close()
