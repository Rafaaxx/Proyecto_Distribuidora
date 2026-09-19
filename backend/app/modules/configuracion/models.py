"""Modelos SQLAlchemy de `configuracion`: `alicuota_iva`, `medio_pago` y
`motivo` (`docs/03-modelo-de-datos.md` §4; TR-09).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id


class AlicuotaIva(Base):
    __tablename__ = "alicuota_iva"
    __table_args__ = (UniqueConstraint("organizacion_id", "id", name="ux_alicuota_iva__org_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(ForeignKey("organizacion.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class MedioPago(Base):
    __tablename__ = "medio_pago"
    __table_args__ = (UniqueConstraint("organizacion_id", "id", name="ux_medio_pago__org_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(ForeignKey("organizacion.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    requiere_referencia: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class Motivo(Base):
    __tablename__ = "motivo"
    __table_args__ = (UniqueConstraint("organizacion_id", "id", name="ux_motivo__org_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(ForeignKey("organizacion.id"), nullable=False)
    ambito: Mapped[str] = mapped_column(Text, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
