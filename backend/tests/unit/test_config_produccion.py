"""Validación de arranque con ENVIRONMENT=production (change 27a, D6).

Spec `sistema/despliegue`: «El backend de producción valida su configuración
al arrancar». Cita `docs/02-arquitectura.md` §6.6 y §17.
"""

import pytest
from pydantic import ValidationError

SECRETO_VALIDO = "s" * 32
URL = "postgresql+psycopg://u:p@localhost:5432/db"


def _entorno(monkeypatch, **vars_: str) -> None:
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("JWT_SECRET", SECRETO_VALIDO)
    monkeypatch.setenv("APP_VERSION", "1.0.0")
    monkeypatch.setenv("ENVIRONMENT", "production")
    for nombre, valor in vars_.items():
        monkeypatch.setenv(nombre.upper(), valor)


def _construir():
    from app.core.config import Settings

    return Settings(_env_file=None)


def test_produccion_con_secreto_corto_falla_y_nombra_la_variable_sin_el_valor(
    monkeypatch,
):
    corto = "corto-y-secreto-31-caracteres-xx"[:31]
    _entorno(monkeypatch, jwt_secret=corto)

    with pytest.raises(ValidationError) as excinfo:
        _construir()

    mensaje = str(excinfo.value)
    assert "JWT_SECRET" in mensaje
    assert corto not in mensaje


def test_produccion_con_secreto_de_un_caracter_falla(monkeypatch):
    _entorno(monkeypatch, jwt_secret="x")

    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _construir()


def test_produccion_con_secreto_de_32_caracteres_pasa(monkeypatch):
    _entorno(monkeypatch, jwt_secret="a" * 32)

    assert _construir().jwt_secret == "a" * 32


@pytest.mark.parametrize("version", ["dev", "1.0", "v1.0.0", "1.0.0-rc1", "1.a.0", ""])
def test_produccion_con_version_sin_forma_x_y_z_falla_y_no_muestra_el_valor(monkeypatch, version):
    _entorno(monkeypatch, app_version=version)

    with pytest.raises(ValidationError) as excinfo:
        _construir()

    mensaje = str(excinfo.value)
    assert "APP_VERSION" in mensaje
    if version:
        assert f"'{version}'" not in mensaje
        assert f"value={version}" not in mensaje


@pytest.mark.parametrize("version", ["1.0.0", "0.12.345"])
def test_produccion_con_version_x_y_z_pasa(monkeypatch, version):
    _entorno(monkeypatch, app_version=version)

    assert _construir().app_version == version


def test_fuera_de_produccion_no_valida(monkeypatch):
    _entorno(monkeypatch, environment="development", jwt_secret="x", app_version="dev")

    settings = _construir()

    assert settings.jwt_secret == "x"
    assert settings.app_version == "dev"


# --- Documentación interactiva apagada en producción (change 28, Lote 4; D8) --------------------
# Spec `sistema/despliegue`, «Encabezados de seguridad…» (defensa extra). Cita `docs/02` §18.

RUTAS_DE_DOCUMENTACION = ("/docs", "/redoc", "/openapi.json")


def _cliente(monkeypatch, entorno: str):
    from fastapi.testclient import TestClient

    from app.main import crear_app

    _entorno(monkeypatch, environment=entorno)
    return TestClient(crear_app(_construir()))


@pytest.mark.parametrize("ruta", RUTAS_DE_DOCUMENTACION)
def test_en_produccion_la_documentacion_interactiva_no_existe(monkeypatch, ruta):
    respuesta = _cliente(monkeypatch, "production").get(ruta)

    assert respuesta.status_code == 404


@pytest.mark.parametrize("ruta", RUTAS_DE_DOCUMENTACION)
def test_fuera_de_produccion_la_documentacion_sigue_disponible(monkeypatch, ruta):
    # La generación de tipos del cliente (`openapi.json`) y el desarrollo la usan.
    respuesta = _cliente(monkeypatch, "development").get(ruta)

    assert respuesta.status_code == 200
