"""Modelos SQLAlchemy de `proveedores`: `Proveedor`, `CostoInformado`
(`docs/03-modelo-de-datos.md` §6; migración `70dcb6dce507`, D10).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`.
Ninguna relación declara carga diferida implícita: este módulo no declara
`relationship()` alguna (`CLAUDE.md` §4), igual que `catalogo/models.py`;
toda lectura pasa por consultas explícitas de `proveedores/repository.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id


class Proveedor(Base):
    __tablename__ = "proveedor"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_proveedor__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_proveedor__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_proveedor__org_id"),
        UniqueConstraint("organizacion_id", "nombre", name="ux_proveedor__nombre"),
        Index(
            "ux_proveedor__cuit",
            "organizacion_id",
            "cuit",
            unique=True,
            postgresql_where=text("cuit IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    cuit: Mapped[str | None] = mapped_column(Text, nullable=True)
    contacto: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefono: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class CostoInformado(Base):
    __tablename__ = "costo_informado"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_costo_informado__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_costo_informado__proveedor",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_costo_informado__producto",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "presentacion_id"],
            ["presentacion.organizacion_id", "presentacion.id"],
            name="fk_costo_informado__presentacion",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_costo_informado__usuario",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_costo_informado__org_id"),
        CheckConstraint("valor > 0", name="ck_costo_informado__valor"),
        CheckConstraint(
            "bonificacion >= 0 AND bonificacion < 1", name="ck_costo_informado__bonificacion"
        ),
        CheckConstraint("alicuota_aplicada >= 0", name="ck_costo_informado__alicuota"),
        CheckConstraint("costo_base >= 0", name="ck_costo_informado__costo_base"),
        Index(
            "ix_costo_informado__producto_vigencia",
            "organizacion_id",
            "producto_id",
            text("vigencia_desde DESC"),
            text("creado_en DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    proveedor_id: Mapped[UUID] = mapped_column(nullable=False)
    producto_id: Mapped[UUID] = mapped_column(nullable=False)
    presentacion_id: Mapped[UUID] = mapped_column(nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    incluye_iva: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bonificacion: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, server_default=text("0")
    )
    alicuota_aplicada: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    costo_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
