import pytest
from pydantic import ValidationError


def test_config_se_construye_desde_variables_de_entorno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "un-secreto-de-prueba-suficientemente-largo")

    from app.core.config import Settings

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://u:p@localhost:5432/db"
    assert settings.app_version == "1.2.3"
    assert settings.log_level == "DEBUG"
    assert settings.environment == "production"
    assert settings.jwt_secret == "un-secreto-de-prueba-suficientemente-largo"


def test_config_falla_si_falta_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "un-secreto-de-prueba-suficientemente-largo")

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_config_usa_valores_por_defecto_si_no_se_configuran(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "un-secreto-de-prueba-suficientemente-largo")
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("JWT_KID", raising=False)

    from app.core.config import Settings

    settings = Settings(_env_file=None)

    assert settings.app_version == "dev"
    assert settings.log_level == "INFO"
    assert settings.environment == "development"
    assert settings.jwt_kid == "1"


def test_config_falla_si_falta_jwt_secret(monkeypatch):
    """Tarea 7.3: el secreto de firma del JWT es obligatorio, sin valor por
    defecto (`design.md` D4)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
