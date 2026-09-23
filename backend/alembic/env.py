import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import create_engine

from alembic import context

# Permite `import app...` al ejecutar alembic desde `backend/`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.alembic_url import resolver_database_url_migraciones  # noqa: E402
from app.core.db import Base  # noqa: E402

# Importar los `models.py` de cada módulo registra sus tablas en
# `Base.metadata` (import por efecto secundario, único lugar donde se hace).
from app.modules.catalogo import models as catalogo_models  # noqa: E402,F401
from app.modules.configuracion import models as configuracion_models  # noqa: E402,F401
from app.modules.identidad import models as identidad_models  # noqa: E402,F401
from app.modules.sync import models as sync_models  # noqa: E402,F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `target_metadata` alimenta `alembic revision --autogenerate` (tarea 4.3):
# compara `Base.metadata` (los modelos) contra el esquema real de la base.
target_metadata = Base.metadata


def _database_url() -> str:
    """La URL de la base viene de `DATABASE_URL_MIGRATIONS` (rol
    `app_migrations`, dueño del esquema), nunca de `alembic.ini` (`docs/02`
    §14) ni de `app.core.config.Settings` (esa es `DATABASE_URL`, rol
    `app_runtime`: la aplicación en runtime, no Alembic) -- tarea 1.5,
    `design.md` D3."""
    return resolver_database_url_migraciones()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
