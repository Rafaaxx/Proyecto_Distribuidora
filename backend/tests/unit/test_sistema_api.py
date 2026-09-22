from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import crear_app


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    monkeypatch.setenv(
        "DATABASE_URL", env.get("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    )
    monkeypatch.setenv(
        "JWT_SECRET", env.get("JWT_SECRET", "un-secreto-de-prueba-suficientemente-largo")
    )
    if "APP_VERSION" in env:
        monkeypatch.setenv("APP_VERSION", env["APP_VERSION"])
    else:
        monkeypatch.delenv("APP_VERSION", raising=False)
    if "APP_VERSION_MINIMA" in env:
        monkeypatch.setenv("APP_VERSION_MINIMA", env["APP_VERSION_MINIMA"])
    else:
        monkeypatch.delenv("APP_VERSION_MINIMA", raising=False)
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


class TestVersionMinimaDeAplicacion:
    """Change 04, grupo 12, tarea 12.4 (`design.md` D9): el servidor publica
    la versión mínima de aplicación admitida junto con la versión desplegada
    -- configuración de despliegue (`Settings.app_version_minima`), no por
    organización (columna huérfana eliminada en la migración de este grupo).

    Spec `sistema/salud-y-version`, escenarios "La versión mínima se
    consulta sin sesión" y "La versión mínima aparece en el contrato
    publicado"."""

    def test_version_incluye_la_version_minima_configurada_sin_sesion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(monkeypatch, APP_VERSION_MINIMA="2.0.0")

        respuesta = client.get("/api/v1/version")

        assert respuesta.status_code == 200
        assert respuesta.json()["app_version_minima"] == "2.0.0"

    def test_version_sin_minima_configurada_la_devuelve_nula(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Triangulación: sin `APP_VERSION_MINIMA` en el entorno, el campo
        viaja como `null` -- no restringe nada por defecto (`design.md` D9)."""
        client = _client(monkeypatch)

        respuesta = client.get("/api/v1/version")

        assert respuesta.status_code == 200
        assert respuesta.json()["app_version_minima"] is None

    def test_openapi_incluye_el_campo_de_version_minima_en_el_esquema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(monkeypatch)

        openapi = client.get("/openapi.json").json()

        esquema_version = openapi["components"]["schemas"]["VersionRespuesta"]
        assert "app_version_minima" in esquema_version["properties"]
