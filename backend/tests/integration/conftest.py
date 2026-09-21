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
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from app.core.db import crear_engine, crear_session_factory

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Los dos roles de PostgreSQL que exige INV-05 (`design.md` D3, `ADR-020`).
# En este arnés se crean desde cero en cada corrida (`design.md`, Risks: "el
# arnés de Testcontainers los crea desde cero en cada corrida, así que CI no
# arrastra estado"); en un entorno real los provisiona el paso de
# despliegue, no una migración (tarea 1.5, pendiente de confirmación).
NOMBRE_ROL_MIGRACIONES = "app_migrations"
NOMBRE_ROL_RUNTIME = "app_runtime"
_PASSWORD_ROL_MIGRACIONES = "app-migrations-solo-pruebas"  # noqa: S105 (solo test)
_PASSWORD_ROL_RUNTIME = "app-runtime-solo-pruebas"  # noqa: S105 (solo test)


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


def _url_con_credenciales(url: str, usuario: str, password: str) -> str:
    """Reemplaza usuario y contraseña de `url`, conservando host, puerto y
    base. Usado para derivar la URL de cada rol (`app_migrations`,
    `app_runtime`) a partir de la URL de sesión del arnés."""
    partes = urlsplit(url)
    netloc = f"{usuario}:{password}@{partes.hostname}"
    if partes.port is not None:
        netloc += f":{partes.port}"
    return urlunsplit((partes.scheme, netloc, partes.path, partes.query, partes.fragment))


def _crear_roles_de_base(database_url: str) -> None:
    """Crea (si no existen) `app_migrations` (dueño del esquema) y
    `app_runtime` (aplicación, sin privilegios hasta que cada migración se
    los otorgue tabla por tabla). Idempotente: `IF NOT EXISTS` (tarea 1.4).
    """
    engine = create_engine(database_url)
    try:
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT FROM pg_roles WHERE rolname = '{NOMBRE_ROL_MIGRACIONES}'
                        ) THEN
                            CREATE ROLE {NOMBRE_ROL_MIGRACIONES}
                                LOGIN PASSWORD '{_PASSWORD_ROL_MIGRACIONES}';
                        END IF;
                        IF NOT EXISTS (
                            SELECT FROM pg_roles WHERE rolname = '{NOMBRE_ROL_RUNTIME}'
                        ) THEN
                            CREATE ROLE {NOMBRE_ROL_RUNTIME}
                                LOGIN PASSWORD '{_PASSWORD_ROL_RUNTIME}';
                        END IF;
                    END
                    $$;
                    """
                )
            )
            # `app_migrations` es dueño del esquema (D3): puede crear, alterar
            # y borrar objetos. `app_runtime` solo recibe USAGE acá; el
            # `SELECT`/`INSERT`/`UPDATE`/`DELETE` por tabla lo otorga cada
            # migración que crea o modifica una tabla (ADR-020).
            conexion.execute(text(f"ALTER SCHEMA public OWNER TO {NOMBRE_ROL_MIGRACIONES}"))
            conexion.execute(text(f"GRANT USAGE ON SCHEMA public TO {NOMBRE_ROL_RUNTIME}"))
    finally:
        engine.dispose()


def aplicar_migraciones(database_url: str, *, revision: str = "head") -> None:
    """Aplica migraciones de Alembic sobre `database_url` hasta `revision`.

    Antes de correr Alembic, asegura que existan los dos roles de base
    (tarea 1.4) y corre las migraciones conectado como `app_migrations`
    (dueño del esquema), nunca como el superusuario de la sesión ni como
    `app_runtime` (`design.md` D3, Migration Plan punto 3). Alembic lee esa
    URL de `DATABASE_URL_MIGRATIONS`, no de `DATABASE_URL` (tarea 1.5,
    `app/core/alembic_url.py`): son variables distintas a propósito.
    """
    _crear_roles_de_base(database_url)
    url_migraciones = _url_con_credenciales(
        database_url, NOMBRE_ROL_MIGRACIONES, _PASSWORD_ROL_MIGRACIONES
    )
    entorno = {**os.environ, "DATABASE_URL_MIGRATIONS": url_migraciones}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"No se pudieron aplicar las migraciones: {resultado.stderr}")


@pytest.fixture(scope="session", autouse=True)
def _jwt_secret_de_pruebas() -> None:
    """El arnés de integración fija un secreto de JWT de pruebas si el
    entorno no trae uno propio (`design.md` D4: el backend no levanta sin
    `jwt_secret`, igual que sin `database_url`). No es un valor por defecto
    de producción: solo aplica a la sesión de pytest, igual que el resto del
    arnés de Testcontainers."""
    os.environ.setdefault("JWT_SECRET", "secreto-de-integracion-solo-para-pruebas")


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


@pytest.fixture(scope="session")
def database_url_runtime(database_url: str) -> str:
    """URL de conexión con el rol `app_runtime` (tarea 1.4): expone una
    sesión con el rol de aplicación, distinta de `_engine_de_sesion`
    (que sigue usando la URL de sesión del arnés con privilegios plenos,
    para no tener que reescribir el resto de la suite heredada)."""
    _crear_roles_de_base(database_url)
    return _url_con_credenciales(database_url, NOMBRE_ROL_RUNTIME, _PASSWORD_ROL_RUNTIME)


@pytest.fixture(scope="session")
def app_runtime_engine(database_url_runtime: str) -> Engine:
    return crear_engine(database_url_runtime)


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
