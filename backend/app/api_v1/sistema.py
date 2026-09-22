"""Endpoints del grupo Sistema (`docs/02-arquitectura.md` §11, §17).

`spec: sistema/salud-y-version`.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.db import verificar_conexion

router = APIRouter(tags=["sistema"])


class SaludRespuesta(BaseModel):
    estado: Literal["ok", "error"]


class VersionRespuesta(BaseModel):
    version: str
    # Change 04, grupo 12, tarea 12.4 (`design.md` D9, `02` §6.6): la
    # versión mínima de aplicación que el servidor admite para confirmar
    # OPERACIONES NUEVAS. Un dispositivo por debajo de esta versión puede
    # seguir sincronizando su cola pendiente (esta etapa no bloquea nada
    # todavía -- el bloqueo de operaciones nuevas para una app desactualizada
    # es responsabilidad del frontend, grupo 13, fuera de este grupo). `None`
    # si no hay una mínima configurada.
    app_version_minima: str | None = None


def _get_engine() -> Engine:
    """Se sobreescribe con `app.dependency_overrides` en `crear_app`."""
    raise NotImplementedError


def _get_settings() -> Settings:
    """Se sobreescribe con `app.dependency_overrides` en `crear_app`."""
    raise NotImplementedError


@router.get("/salud", response_model=SaludRespuesta)
def salud(
    response: Response,
    engine: Annotated[Engine, Depends(_get_engine)],
) -> SaludRespuesta:
    """Verifica la conexión con la base antes de responder (`02` §17)."""
    if verificar_conexion(engine):
        return SaludRespuesta(estado="ok")

    response.status_code = 503
    return SaludRespuesta(estado="error")


@router.get("/version", response_model=VersionRespuesta)
def version(settings: Annotated[Settings, Depends(_get_settings)]) -> VersionRespuesta:
    """Devuelve la versión de la aplicación en ejecución y la versión mínima
    admitida (`02` §11, `02` §6.6, tarea 12.4)."""
    return VersionRespuesta(
        version=settings.app_version, app_version_minima=settings.app_version_minima
    )
