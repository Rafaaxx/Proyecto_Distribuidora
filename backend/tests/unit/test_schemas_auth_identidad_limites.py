"""Límites de los cuerpos de login, refresh y alta de usuarios (auditoría de seguridad)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api_v1.auth import LoginRequest, RefreshRequest
from app.modules.identidad.api import (
    ComposicionRolRequest,
    CrearUsuarioRequest,
    RotarPinRequest,
)

LOGIN = {
    "organizacion_slug": "org",
    "usuario": "ana",
    "contrasena": "una-clave-larga",
    "dispositivo_id": str(uuid4()),
    "nombre_dispositivo": "Chrome en Windows",
}


def test_login_acepta_exactamente_lo_que_envia_el_frontend() -> None:
    assert LoginRequest.model_validate(LOGIN).usuario == "ana"


def test_login_rechaza_un_campo_extra() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({**LOGIN, "organizacion_id": str(uuid4())})


@pytest.mark.parametrize(
    ("campo", "largo"),
    [
        ("organizacion_slug", 101),
        ("usuario", 201),
        ("contrasena", 129),
        ("nombre_dispositivo", 201),
    ],
)
def test_login_rechaza_textos_demasiado_largos(campo: str, largo: int) -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({**LOGIN, campo: "x" * largo})


@pytest.mark.parametrize(
    ("campo", "largo"),
    [
        ("organizacion_slug", 100),
        ("usuario", 200),
        ("contrasena", 128),
        ("nombre_dispositivo", 200),
    ],
)
def test_login_acepta_textos_en_el_limite(campo: str, largo: int) -> None:
    assert LoginRequest.model_validate({**LOGIN, campo: "x" * largo})


def test_refresh_acepta_solo_el_dispositivo() -> None:
    assert RefreshRequest.model_validate({"dispositivo_id": str(uuid4())})
    with pytest.raises(ValidationError):
        RefreshRequest.model_validate({"dispositivo_id": str(uuid4()), "otro": 1})


ALTA = {
    "usuario": "ana",
    "nombre": "Ana",
    "email": None,
    "password": "una-clave-larga",
    "rol_id": str(uuid4()),
}


def test_alta_de_usuario_rechaza_extras_y_largos_excesivos() -> None:
    assert CrearUsuarioRequest.model_validate(ALTA)
    with pytest.raises(ValidationError):
        CrearUsuarioRequest.model_validate({**ALTA, "organizacion_id": str(uuid4())})
    with pytest.raises(ValidationError):
        CrearUsuarioRequest.model_validate({**ALTA, "usuario": "x" * 201})
    with pytest.raises(ValidationError):
        CrearUsuarioRequest.model_validate({**ALTA, "password": "x" * 129})
    with pytest.raises(ValidationError):
        CrearUsuarioRequest.model_validate({**ALTA, "nombre": "x" * 201})
    with pytest.raises(ValidationError):
        CrearUsuarioRequest.model_validate({**ALTA, "email": "x" * 321})


def test_composicion_de_rol_y_pin_rechazan_extras() -> None:
    assert ComposicionRolRequest.model_validate({"permisos": ["VENDER"]})
    with pytest.raises(ValidationError):
        ComposicionRolRequest.model_validate({"permisos": [], "x": 1})
    assert RotarPinRequest.model_validate({"pin": "1234"})
    with pytest.raises(ValidationError):
        RotarPinRequest.model_validate({"pin": "1234", "x": 1})
    with pytest.raises(ValidationError):
        RotarPinRequest.model_validate({"pin": "1" * 65})
