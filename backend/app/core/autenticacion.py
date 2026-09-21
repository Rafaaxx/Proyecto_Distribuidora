"""Dependencia de autenticación y permisos (`design.md` D5, tareas 10.1 y
10.2).

Único camino por el que un endpoint obtiene `organizacion_id`, `usuario_id`
y `dispositivo_id`: los toma del access token, nunca del cuerpo, la
consulta ni un encabezado de la petición (`CLAUDE.md` §4, tarea 10.4). Los
permisos se cargan sin caché en cada petición (`design.md` D5): una
revocación tiene efecto inmediato en la petición siguiente con el mismo
access token (tarea 10.5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.api_v1.dependencias import _get_settings, get_session
from app.core.config import Settings
from app.core.errors import DomainError
from app.core.seguridad import verificar_access_token
from app.modules.identidad import service as identidad_service


class AccessTokenAusenteError(DomainError):
    """Tarea 10.1: "Una petición sin token no llega al negocio"."""

    codigo = "IDENTIDAD_ACCESS_TOKEN_AUSENTE"
    status_http = 401


class PermisoRequeridoError(DomainError):
    """Tarea 10.2 (`docs/02-arquitectura.md` §11): código estable listado
    explícitamente en la documentación de la API."""

    codigo = "PERMISO_REQUERIDO"
    status_http = 403


@dataclass(frozen=True)
class ContextoAutenticado:
    usuario_id: UUID
    organizacion_id: UUID
    dispositivo_id: UUID


def obtener_contexto_autenticado(
    settings: Annotated[Settings, Depends(_get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> ContextoAutenticado:
    """Extrae y verifica el access token del encabezado `Authorization:
    Bearer <token>` (tarea 10.1). `verificar_access_token` ya distingue
    firma alterada de vencimiento (`AccessTokenInvalidoError`/
    `AccessTokenExpiradoError`, ambas `DomainError` 401): esta función no
    los atrapa, los deja propagar tal cual."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise AccessTokenAusenteError("Falta el access token.")

    token = authorization.removeprefix("Bearer ").strip()
    claims = verificar_access_token(token, claves_por_kid={settings.jwt_kid: settings.jwt_secret})

    return ContextoAutenticado(
        usuario_id=claims.usuario_id,
        organizacion_id=claims.organizacion_id,
        dispositivo_id=claims.dispositivo_id,
    )


def requiere_permiso(codigo_permiso: str) -> Callable[..., ContextoAutenticado]:
    """Fábrica de dependencia (tarea 10.2): `Depends(requiere_permiso("X"))`
    en la firma de una ruta. Cada ruta de negocio DEBE declarar la suya
    (tarea 10.3, ratchet).

    `_dependencia.permiso_requerido` es el marcador que el ratchet de la
    tarea 10.3 (`tests/integration/test_ratchet_permiso_por_ruta.py`) usa
    para reconocer, recorriendo el árbol de `Dependant` de cada `APIRoute`,
    que esa ruta sí declaró un permiso -- sin depender de un nombre de
    función ni de introspección de clausura.
    """

    def _dependencia(
        contexto: Annotated[ContextoAutenticado, Depends(obtener_contexto_autenticado)],
        sesion: Annotated[Session, Depends(get_session)],
    ) -> ContextoAutenticado:
        permisos_del_usuario = identidad_service.listar_permisos_del_usuario(
            contexto.organizacion_id, contexto.usuario_id, sesion
        )
        if codigo_permiso not in permisos_del_usuario:
            raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")
        return contexto

    _dependencia.permiso_requerido = codigo_permiso  # type: ignore[attr-defined]
    return _dependencia
