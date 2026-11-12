"""Casos de uso de lectura de `importacion` (`design.md` D14, `02` §11).

El historial de la organización, de la más reciente a la más antigua, paginado por
cursor `(registered_at, id)`. El nombre del usuario sale de `identidad.service` (un
módulo no importa modelos ni repositorios ajenos, `CLAUDE.md` §4), por lote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.identidad import service as identidad_service
from app.modules.importacion import repository
from app.modules.importacion.domain.historial import (
    LIMITE_DEFAULT,
    LIMITE_MAXIMO,
    codificar_cursor,
    decodificar_cursor,
)


@dataclass(frozen=True)
class ImportacionDelHistorial:
    """Una fila del historial (la importación y quién la hizo)."""

    id: UUID
    tipo: str
    archivo_nombre: str
    estado: str
    filas_total: int
    filas_ok: int
    filas_error: int
    usuario_id: UUID
    usuario_nombre: str | None
    registered_at: datetime


@dataclass(frozen=True)
class PaginaDelHistorial:
    """Una página del historial. `zona_horaria` es la de la organización (TR-04): la
    pantalla muestra los momentos en esa zona."""

    items: list[ImportacionDelHistorial]
    cursor_siguiente: str | None
    zona_horaria: str


def listar_importaciones(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cursor: str | None,
    limite: int = LIMITE_DEFAULT,
) -> PaginaDelHistorial:
    """Una página del historial. Un cursor ilegible es `CURSOR_INVALIDO`. Pide una
    fila de más para saber si hay otra página."""
    limite_de_pagina = min(max(limite, 1), LIMITE_MAXIMO)
    despues_de = None if cursor is None else decodificar_cursor(cursor)
    filas = repository.listar_importaciones(
        organizacion_id, sesion, despues_de=despues_de, limite=limite_de_pagina + 1
    )
    hay_mas = len(filas) > limite_de_pagina
    pagina = filas[:limite_de_pagina]
    nombres = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, frozenset(i.usuario_id for i in pagina), sesion
    )
    items = [
        ImportacionDelHistorial(
            id=i.id,
            tipo=i.tipo,
            archivo_nombre=i.archivo_nombre,
            estado=i.estado,
            filas_total=i.filas_total,
            filas_ok=i.filas_ok,
            filas_error=i.filas_error,
            usuario_id=i.usuario_id,
            usuario_nombre=nombres.get(i.usuario_id),
            registered_at=i.registered_at,
        )
        for i in pagina
    ]
    cursor_siguiente = (
        codificar_cursor(pagina[-1].registered_at, pagina[-1].id) if hay_mas and pagina else None
    )
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    zona_horaria = "UTC" if organizacion is None else organizacion.zona_horaria
    return PaginaDelHistorial(
        items=items, cursor_siguiente=cursor_siguiente, zona_horaria=zona_horaria
    )
