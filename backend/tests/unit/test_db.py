from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker


def test_crear_engine_usa_la_url_configurada():
    from app.core.db import crear_engine

    engine = crear_engine("postgresql+psycopg://u:p@localhost:5432/db")

    assert str(engine.url) == "postgresql+psycopg://u:***@localhost:5432/db"


def test_crear_session_factory_devuelve_sessionmaker_sin_autoflush_implicito():
    from app.core.db import crear_engine, crear_session_factory

    engine = crear_engine("postgresql+psycopg://u:p@localhost:5432/db")
    factory = crear_session_factory(engine)

    assert isinstance(factory, sessionmaker)
    assert factory.kw["bind"] is engine


def test_verificar_conexion_devuelve_true_si_select_1_funciona():
    from app.core.db import verificar_conexion

    conexion_cm = MagicMock()
    conexion_cm.__enter__.return_value = MagicMock()
    engine = MagicMock()
    engine.connect.return_value = conexion_cm

    assert verificar_conexion(engine) is True


def test_verificar_conexion_devuelve_false_y_no_propaga_el_error_si_falla():
    from app.core.db import verificar_conexion

    engine = MagicMock()
    engine.connect.side_effect = OperationalError(
        "SELECT 1", {}, Exception("cadena de conexión secreta")
    )

    assert verificar_conexion(engine) is False
