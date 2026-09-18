"""Motor y fábrica de sesiones SQLAlchemy 2.x síncrono (`docs/02` §3.1, §14).

- Modo síncrono con psycopg 3.
- La carga diferida implícita se desactiva a nivel de mapeo declarativo
  (`Base` con `__mapper_args__ = {"eager_defaults": True}` no aplica aquí;
  la desactivación real se hace por relación con `lazy="raise"` cuando se
  declaren modelos de negocio en los changes siguientes). Este módulo solo
  provee el engine y la fábrica de sesiones: no hay `create_all` en ningún
  lado fuera de las pruebas.
"""

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker


def crear_engine(database_url: str) -> Engine:
    """Crea el engine de SQLAlchemy para `database_url`."""
    return create_engine(database_url)


def crear_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Crea la fábrica de sesiones ligada a `engine`."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def verificar_conexion(engine: Engine) -> bool:
    """Verifica que `engine` alcanza la base ejecutando `SELECT 1`.

    Nunca propaga la excepción original: el detalle puede incluir la cadena
    de conexión, y `GET /api/v1/salud` no debe exponerla (`02` §17, §18).
    """
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
