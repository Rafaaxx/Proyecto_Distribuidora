"""Pruebas de integración de `sistema/salud-y-version` contra PostgreSQL
real (`docs/02` §15: nunca SQLite). Requieren `docker compose up -d postgres`
(o el entorno de desarrollo completo) corriendo antes de ejecutarlas.
"""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import crear_app


def test_salud_responde_200_con_la_base_de_desarrollo_disponible(database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=database_url)
    client = TestClient(crear_app(settings))

    respuesta = client.get("/api/v1/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_salud_responde_503_si_la_base_no_esta_accesible() -> None:
    url_invalida = "postgresql+psycopg://u:p@host-inexistente-01a:5432/db"
    settings = Settings(_env_file=None, database_url=url_invalida)
    client = TestClient(crear_app(settings))

    respuesta = client.get("/api/v1/salud")

    assert respuesta.status_code == 503
    assert "host-inexistente-01a" not in str(respuesta.json())


def test_version_responde_200_con_el_entorno_de_desarrollo(database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=database_url, app_version="dev")
    client = TestClient(crear_app(settings))

    respuesta = client.get("/api/v1/version")

    assert respuesta.status_code == 200
    assert respuesta.json()["version"] == "dev"
