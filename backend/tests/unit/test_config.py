import pytest
from pydantic import ValidationError


def test_config_se_construye_desde_variables_de_entorno(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ENVIRONMENT", "production")

    from app.core.config import Settings

    settings = Settings()

    assert settings.database_url == "postgresql+psycopg://u:p@localhost:5432/db"
    assert settings.app_version == "1.2.3"
    assert settings.log_level == "DEBUG"
    assert settings.environment == "production"


def test_config_falla_si_falta_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_config_usa_valores_por_defecto_si_no_se_configuran(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    from app.core.config import Settings

    settings = Settings(_env_file=None)

    assert settings.app_version == "dev"
    assert settings.log_level == "INFO"
    assert settings.environment == "development"
