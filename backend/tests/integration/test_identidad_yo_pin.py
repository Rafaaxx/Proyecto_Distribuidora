# ruff: noqa: F811
"""Tarea 11.5 (change 18b; `design.md` D21 punto 1; spec `identidad/pin-de-autorizacion`):
`GET /api/v1/yo/pin-autorizacion` dice, para el usuario del token, si puede definir su propio PIN
de autorización (`puede_definir`: su rol confiere algún permiso de autorización) y si ya lo tiene
definido (`tiene_pin_autorizacion`), sin la derivación ni la sal. `GET /api/v1/yo` no cambia.

Reglas citadas: ADR-011, SEG-07, SEG-06.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_identidad_commands_maestros import (
    _crear_organizacion,
    _crear_usuario,
    _limpiar_datos_confirmados,  # noqa: F401  (fixture autouse)
    _login,
    sesion,  # noqa: F401  (fixture)
)

from app.api_v1 import sistema
from app.core.config import Settings
from app.main import crear_app
from app.modules.identidad import service as identidad_service

JWT_SECRET = "secreto-de-prueba-yo-pin"
URL = "/api/v1/yo/pin-autorizacion"
PIN = "482913"


class _Reloj:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


def _entrar(
    cliente: TestClient,
    sesion: Session,
    *,
    permisos: frozenset[str],
    con_pin: bool = False,
) -> dict[str, str]:
    organizacion = _crear_organizacion(sesion, f"org-yopin-{uuid4().hex[:8]}")
    usuario, _ = _crear_usuario(
        sesion, organizacion.id, permisos=permisos, nombre_usuario="persona"
    )
    if con_pin:
        identidad_service.establecer_pin_autorizacion(
            organizacion.id, sesion, _Reloj(), usuario_id=usuario.id, pin=PIN, actor_id=usuario.id
        )
    sesion.commit()
    return {"Authorization": f"Bearer {_login(cliente, organizacion.slug, 'persona')}"}


def test_adr011_un_supervisor_con_pin_puede_definir_y_lo_tiene(
    cliente: TestClient, sesion: Session
) -> None:
    headers = _entrar(cliente, sesion, permisos=frozenset({"AUTORIZAR_DESCUENTO"}), con_pin=True)

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"puede_definir": True, "tiene_pin_autorizacion": True}
    assert PIN not in respuesta.text


def test_adr011_un_supervisor_sin_pin_puede_definir_pero_no_lo_tiene(
    cliente: TestClient, sesion: Session
) -> None:
    """Triangulación: los dos booleanos son independientes."""
    headers = _entrar(cliente, sesion, permisos=frozenset({"SUPERAR_CREDITO"}))

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"puede_definir": True, "tiene_pin_autorizacion": False}


def test_adr011_un_vendedor_sin_permisos_de_autorizacion_recibe_puede_definir_falso(
    cliente: TestClient, sesion: Session
) -> None:
    headers = _entrar(cliente, sesion, permisos=frozenset({"VENDER"}))

    respuesta = cliente.get(URL, headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"puede_definir": False, "tiene_pin_autorizacion": False}


def test_adr011_la_respuesta_no_trae_derivacion_sal_ni_iteraciones(
    cliente: TestClient, sesion: Session
) -> None:
    headers = _entrar(cliente, sesion, permisos=frozenset({"AUTORIZAR_DESCUENTO"}), con_pin=True)

    cuerpo = cliente.get(URL, headers=headers).json()

    assert set(cuerpo) == {"puede_definir", "tiene_pin_autorizacion"}


def test_seg07_cada_usuario_ve_solo_lo_suyo_y_get_yo_no_cambia(
    cliente: TestClient, sesion: Session
) -> None:
    """El estado sale del token: otro usuario de otra organización con PIN no se refleja. Y
    `GET /yo` conserva exactamente su forma (decisión del 2026-10-15)."""
    _entrar(cliente, sesion, permisos=frozenset({"AUTORIZAR_DESCUENTO"}), con_pin=True)
    headers = _entrar(cliente, sesion, permisos=frozenset({"AUTORIZAR_DESCUENTO"}))

    propio = cliente.get(URL, headers=headers)
    yo = cliente.get("/api/v1/yo", headers=headers)

    assert propio.json() == {"puede_definir": True, "tiene_pin_autorizacion": False}
    assert set(yo.json()) == {"usuario", "organizacion", "rol", "permisos"}


def test_seg06_sin_sesion_responde_401(cliente: TestClient) -> None:
    assert cliente.get(URL).status_code == 401
