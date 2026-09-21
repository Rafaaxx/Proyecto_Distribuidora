"""Endpoints de autenticación (`docs/02-arquitectura.md` §11, ADR-017,
ADR-021). Grupo 10.6.

Quedan permanentemente fuera del bus de comandos (`design.md` D6): no son
operaciones de negocio, no tienen `operation_id` (el de login ocurre antes
de que exista un usuario autenticado que lo genere).
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api_v1.dependencias import _get_settings, get_session
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.errors import DomainError
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import RefreshTokenInvalidoError

router = APIRouter(prefix="/auth", tags=["autenticacion"])

# `ADR-017`: cookie HttpOnly, Secure, SameSite=Strict, restringida al camino
# de autenticación. 30 días = vencimiento deslizante del refresh.
_NOMBRE_COOKIE_REFRESH = "refresh_token"
_PATH_COOKIE_REFRESH = "/api/v1/auth"
_MAX_AGE_COOKIE_REFRESH_SEGUNDOS = 30 * 24 * 60 * 60


class LoginRequest(BaseModel):
    organizacion_slug: str
    usuario: str
    contrasena: str
    dispositivo_id: UUID
    nombre_dispositivo: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    dispositivo_id: UUID


def _fijar_cookie_refresh(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=_NOMBRE_COOKIE_REFRESH,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path=_PATH_COOKIE_REFRESH,
        max_age=_MAX_AGE_COOKIE_REFRESH_SEGUNDOS,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    datos: LoginRequest,
    request: Request,
    response: Response,
    sesion: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(_get_settings)],
) -> TokenResponse:
    ip = request.client.host if request.client is not None else "desconocida"
    try:
        resultado = identidad_service.iniciar_sesion(
            sesion,
            SystemClock(),
            organizacion_slug=datos.organizacion_slug,
            nombre_usuario=datos.usuario,
            password=datos.contrasena,
            dispositivo_id=datos.dispositivo_id,
            nombre_dispositivo=datos.nombre_dispositivo,
            jwt_secreto=settings.jwt_secret,
            jwt_kid=settings.jwt_kid,
            ip=ip,
        )
    except DomainError:
        # El rechazo (credenciales inválidas, bloqueo por intentos,
        # dispositivo revocado) igual escribió el intento fallido y, en
        # algunos casos, una auditoría (`identidad/service.py::iniciar_sesion`);
        # sin este `commit`, `get_session` cierra la sesión sin confirmar
        # nada y esos registros se pierden (grupo 11, `ADR-018`).
        sesion.commit()
        raise
    sesion.commit()
    _fijar_cookie_refresh(response, resultado.refresh_token)
    return TokenResponse(access_token=resultado.access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    datos: RefreshRequest,
    response: Response,
    sesion: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(_get_settings)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if refresh_token is None:
        raise RefreshTokenInvalidoError("El refresh token no es válido.")

    try:
        resultado = identidad_service.renovar_sesion(
            sesion,
            SystemClock(),
            refresh_token_claro=refresh_token,
            dispositivo_id=datos.dispositivo_id,
            jwt_secreto=settings.jwt_secret,
            jwt_kid=settings.jwt_kid,
        )
    except DomainError:
        # La detección de reuso (`identidad/service.py::renovar_sesion`)
        # revoca toda la familia de tokens y audita ANTES de rechazar; sin
        # este `commit`, esa revocación se perdía igual que el intento
        # fallido de login (mismo bug, ver `login` más arriba).
        sesion.commit()
        raise
    sesion.commit()
    _fijar_cookie_refresh(response, resultado.refresh_token)
    return TokenResponse(access_token=resultado.access_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    sesion: Annotated[Session, Depends(get_session)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    identidad_service.cerrar_sesion(sesion, SystemClock(), refresh_token_claro=refresh_token)
    sesion.commit()
    response.delete_cookie(key=_NOMBRE_COOKIE_REFRESH, path=_PATH_COOKIE_REFRESH)
