import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.access_log_middleware import AccessLogMiddleware
from app.core.logging import JsonFormatter, RequestIdFilter
from app.core.request_id_middleware import RequestIdMiddleware


def _build_app(capturados: list[str]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    logger = logging.getLogger("app.access")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            capturados.append(self.format(record))

    handler = _ListHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"ok": "true"}

    @app.post("/login")
    def login(password: str) -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/falla")
    def falla() -> dict[str, str]:
        raise RuntimeError("boom con secreto=super-token-123")

    return app


def test_se_emite_un_registro_de_fin_de_peticion_con_metodo_ruta_estado_y_duracion():
    capturados: list[str] = []
    client = TestClient(_build_app(capturados))

    client.get("/ok")

    registro = json.loads(capturados[-1])
    assert registro["method"] == "GET"
    assert registro["path"] == "/ok"
    assert registro["status_code"] == 200
    assert isinstance(registro["duration_ms"], (int, float))
    assert registro["duration_ms"] >= 0
    assert "request_id" in registro


def test_una_credencial_en_la_peticion_no_aparece_en_ningun_registro():
    capturados: list[str] = []
    client = TestClient(_build_app(capturados))

    client.post(
        "/login",
        params={"password": "hunter2-secreto"},
        headers={"Authorization": "Bearer token-abc"},
    )

    for linea in capturados:
        assert "hunter2-secreto" not in linea
        assert "token-abc" not in linea


def test_un_error_no_filtra_secretos_pero_incluye_request_id_y_tipo_de_error():
    capturados: list[str] = []
    client = TestClient(_build_app(capturados), raise_server_exceptions=False)

    respuesta = client.get("/falla")

    assert respuesta.status_code == 500
    registro = json.loads(capturados[-1])
    assert registro["method"] == "GET"
    assert registro["status_code"] == 500
    assert "request_id" in registro
    assert "super-token-123" not in capturados[-1]
