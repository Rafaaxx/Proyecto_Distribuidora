import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, RequestIdFilter
from app.core.request_id_middleware import RequestIdMiddleware


def _build_app(capturados: list[str]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    logger = logging.getLogger("app.test.middleware")
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

    @app.get("/eco")
    def eco() -> dict[str, str]:
        logger.info("procesando")
        return {"ok": "true"}

    return app


def test_cada_peticion_tiene_su_propio_request_id_y_viaja_en_la_respuesta():
    capturados: list[str] = []
    client = TestClient(_build_app(capturados))

    respuesta = client.get("/eco")

    assert respuesta.status_code == 200
    request_id = respuesta.headers["X-Request-Id"]
    assert request_id
    registro = json.loads(capturados[-1])
    assert registro["request_id"] == request_id


def test_dos_peticiones_no_comparten_request_id():
    capturados: list[str] = []
    client = TestClient(_build_app(capturados))

    r1 = client.get("/eco")
    r2 = client.get("/eco")

    assert r1.headers["X-Request-Id"] != r2.headers["X-Request-Id"]


def test_el_backend_respeta_el_encabezado_de_correlacion_entrante():
    capturados: list[str] = []
    client = TestClient(_build_app(capturados))

    respuesta = client.get("/eco", headers={"X-Request-Id": "id-del-cliente"})

    assert respuesta.headers["X-Request-Id"] == "id-del-cliente"
    registro = json.loads(capturados[-1])
    assert registro["request_id"] == "id-del-cliente"
