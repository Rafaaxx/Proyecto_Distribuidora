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
    """Devuelve la versión de la aplicación en ejecución (`02` §11)."""
    return VersionRespuesta(version=settings.app_version)
