from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import crear_app


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    monkeypatch.setenv(
        "DATABASE_URL", env.get("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    )
    if "APP_VERSION" in env:
        monkeypatch.setenv("APP_VERSION", env["APP_VERSION"])
    else:
        monkeypatch.delenv("APP_VERSION", raising=False)
    settings = Settings(_env_file=None)
    app = crear_app(settings)
    return TestClient(app)


def test_salud_responde_200_cuando_la_base_conecta(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    with patch("app.api_v1.sistema.verificar_conexion", return_value=True):
        respuesta = client.get("/api/v1/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_salud_responde_503_cuando_la_base_no_conecta(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    with patch("app.api_v1.sistema.verificar_conexion", return_value=False):
        respuesta = client.get("/api/v1/salud")

    assert respuesta.status_code == 503
    assert respuesta.json()["estado"] == "error"
    cuerpo = str(respuesta.json())
    assert "u:p@localhost" not in cuerpo
    assert "postgresql" not in cuerpo


def test_salud_no_requiere_sesion(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    with patch("app.api_v1.sistema.verificar_conexion", return_value=True):
        respuesta = client.get("/api/v1/salud")

    assert respuesta.status_code not in (401, 403)


def test_version_devuelve_la_version_configurada(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, APP_VERSION="1.2.3")

    respuesta = client.get("/api/v1/version")

    assert respuesta.status_code == 200
    assert respuesta.json()["version"] == "1.2.3"


def test_version_devuelve_dev_si_no_esta_configurada(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    respuesta = client.get("/api/v1/version")

    assert respuesta.status_code == 200
    assert respuesta.json()["version"] == "dev"


def test_openapi_incluye_salud_y_version(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    openapi = client.get("/openapi.json").json()

    assert "/api/v1/salud" in openapi["paths"]
    assert "/api/v1/version" in openapi["paths"]
