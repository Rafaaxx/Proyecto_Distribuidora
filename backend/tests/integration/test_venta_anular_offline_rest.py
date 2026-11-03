"""Tarea 1.1 (change 22d; spec `sync/lote-de-comandos`, escenario "Por REST sigue siendo con
conexión"; `design.md` D1): `POST /api/v1/ventas/{venta_id}/anulacion` sigue armando un sobre
`ONLINE` aunque `VENTA_ANULAR` ahora admita también `OFFLINE` por el lote.

Mismo arnés que `test_ventas_anular_api.py`. Reglas citadas: VTA-24, STK-09.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_ventas_anular_api import JWT_SECRET, URL_VENTAS, Sesion, _con_op
from ventas_anular_utiles import PERMISOS_DE_ANULADOR

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.main import crear_app
from app.modules.sync.models import Comando


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente_http(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def test_vta24_por_rest_la_anulacion_sigue_siendo_online(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Por REST sigue siendo con conexión"
    """`02` §6.5, STK-09: el comando de la anulación por REST queda registrado `ONLINE`."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)
    venta_id = s.vender(cliente_http, headers)
    operation_id = uuid4()

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{venta_id}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id)},
        headers=_con_op(headers, operation_id),
    )

    assert respuesta.status_code == 200
    sesion.expire_all()
    comando = sesion.scalars(select(Comando).where(Comando.operation_id == operation_id)).one()
    assert (comando.tipo, comando.modo) == ("VENTA_ANULAR", "ONLINE")


def test_vta24_por_rest_una_venta_ajena_sigue_siendo_404_y_no_venta_inexistente(
    cliente_http: TestClient, sesion: Session
) -> None:
    # Escenario: "Por REST sigue siendo con conexión"
    """Triangulación: con conexión una venta que no existe sigue respondiendo 404 de siempre
    (`VENTA_INEXISTENTE` es solo el rechazo del lote sin conexión)."""
    s = Sesion(sesion, permisos=PERMISOS_DE_ANULADOR)
    headers = s.entrar(cliente_http)

    respuesta = cliente_http.post(
        f"{URL_VENTAS}/{uuid4()}/anulacion",
        json={"motivo_id": str(s.entorno.motivo_anulacion_id)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
