"""Modelo SQLAlchemy de `importacion` (`docs/03-modelo-de-datos.md` §13; migración
`b9c0d1e2f3a4`).

Mapea exactamente lo que crea la migración: `test_modelos_coinciden_con_
migracion.py` corre `alembic revision --autogenerate` y exige que no detecte
ninguna diferencia.

Ninguna relación declara carga diferida implícita: este módulo no declara
`relationship()` alguna (`CLAUDE.md` §4). El id se genera con UUIDv7
(`core/ids.py`) y los momentos son `timestamptz`.

`importacion` es un registro de solo inserción (`design.md` D14-A, INV-05): el
usuario de aplicación no tiene `UPDATE` ni `DELETE`. Con el modo todo o nada
(D1) solo se guardan las importaciones exitosas: `estado` es `CONFIRMADA`,
`filas_error` es 0 y `errores` es `[]`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id

_TIPOS = (
    "'PRODUCTOS','CLIENTES','PROVEEDORES','PRECIOS','COSTOS','STOCK_INICIAL','SALDOS_INICIALES'"
)
_ESTADOS = "'CONFIRMADA'"

ESTADO_CONFIRMADA = "CONFIRMADA"


class Importacion(Base):
    """Una importación confirmada: qué tipo, de qué archivo, cuántas filas y quién
    la hizo. Las columnas de operación (`operation_id`, `usuario_id`,
    `dispositivo_id`, `occurred_at`, `registered_at`) son las de `03` §2.3."""

    __tablename__ = "importacion"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_importacion"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_importacion__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_importacion__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_importacion__dispositivo",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_importacion__org_id"),
        CheckConstraint(f"tipo IN ({_TIPOS})", name="ck_importacion__tipo"),
        CheckConstraint(f"estado IN ({_ESTADOS})", name="ck_importacion__estado"),
        CheckConstraint(
            "filas_total >= 0 AND filas_ok >= 0 AND filas_error >= 0",
            name="ck_importacion__filas_no_negativas",
        ),
        Index(
            "ix_importacion__historial",
            "organizacion_id",
            text("registered_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    tipo: Mapped[str] = mapped_column(Text)
    archivo_nombre: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text)
    filas_total: Mapped[int] = mapped_column(Integer)
    filas_ok: Mapped[int] = mapped_column(Integer)
    filas_error: Mapped[int] = mapped_column(Integer)
    errores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    operation_id: Mapped[UUID]
    usuario_id: Mapped[UUID]
    dispositivo_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
