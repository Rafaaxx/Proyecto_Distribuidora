"""Acceso a datos de `importacion` (`design.md` D14).

Toda función recibe `organizacion_id` como primer parámetro y filtra por él
(`CLAUDE.md` §4). El registro es de solo inserción (INV-05): no hay `update` ni
`delete`. La transacción la gestiona el bus: el repositorio hace `flush`, nunca
`commit`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.modules.importacion.models import ESTADO_CONFIRMADA, Importacion

FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Ninguna: todo dato de importación es de una organización."""


def crear_importacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    importacion_id: UUID,
    tipo: str,
    archivo_nombre: str,
    filas_total: int,
    filas_ok: int,
    operation_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
) -> Importacion:
    """Registra una importación confirmada. Con el modo todo o nada (D1) solo se
    guardan las exitosas: `filas_error` = 0 y `errores` = `[]` (D14-A)."""
    importacion = Importacion(
        id=importacion_id,
        organizacion_id=organizacion_id,
        tipo=tipo,
        archivo_nombre=archivo_nombre,
        estado=ESTADO_CONFIRMADA,
        filas_total=filas_total,
        filas_ok=filas_ok,
        filas_error=0,
        errores=[],
        operation_id=operation_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
    )
    sesion.add(importacion)
    sesion.flush()
    return importacion


def listar_importaciones(
    organizacion_id: UUID,
    sesion: Session,
    *,
    despues_de: tuple[datetime, UUID] | None,
    limite: int,
) -> list[Importacion]:
    """Importaciones de la organización, la más reciente primero (`registered_at`
    descendente, `id` de desempate), después del cursor `(registered_at, id)`. Pide
    `limite` filas: quien pagina pide una de más para saber si hay otra página."""
    consulta = select(Importacion).where(Importacion.organizacion_id == organizacion_id)
    if despues_de is not None:
        consulta = consulta.where(tuple_(Importacion.registered_at, Importacion.id) < despues_de)
    consulta = consulta.order_by(Importacion.registered_at.desc(), Importacion.id.desc()).limit(
        limite
    )
    return list(sesion.scalars(consulta).all())
