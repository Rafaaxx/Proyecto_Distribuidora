"""Esquemas HTTP de `importacion` (change 10, grupo 4; `design.md` D1, D14).

`organizacion_id` no existe acá: sale del token (INV-21). La subida del archivo es
multipart, así que no hay esquema de entrada; el informe de errores viaja en el
Problem Details de `IMPORTACION_CON_ERRORES` (`errores`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.importacion.queries import ImportacionDelHistorial


class ImportacionResponse(BaseModel):
    """Resultado de una importación aceptada. Con el modo todo o nada (D1),
    `filas_ok` es siempre `filas_total`."""

    importacion_id: UUID
    filas_total: int
    filas_ok: int


class ImportacionItem(BaseModel):
    """Una fila del historial. El momento viaja en UTC con su desfase: la zona de
    la organización la aplica la pantalla (TR-04)."""

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


class PaginaImportaciones(BaseModel):
    """`zona_horaria` (IANA) es la de la organización: la pantalla muestra
    `registered_at` en esa zona (TR-04)."""

    items: list[ImportacionItem]
    cursor_siguiente: str | None
    zona_horaria: str


def item_de(importacion: ImportacionDelHistorial) -> ImportacionItem:
    return ImportacionItem(
        id=importacion.id,
        tipo=importacion.tipo,
        archivo_nombre=importacion.archivo_nombre,
        estado=importacion.estado,
        filas_total=importacion.filas_total,
        filas_ok=importacion.filas_ok,
        filas_error=importacion.filas_error,
        usuario_id=importacion.usuario_id,
        usuario_nombre=importacion.usuario_nombre,
        registered_at=importacion.registered_at,
    )
