"""Modelos SQLAlchemy de `identidad`: `organizacion` y
`configuracion_organizacion` (`docs/03-modelo-de-datos.md` §4; `03` §3).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`.
La carga de relaciones es explícita (`lazy="raise"`): nada se carga de forma
diferida implícita (`CLAUDE.md` §4).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.ids import nuevo_id


class Organizacion(Base):
    __tablename__ = "organizacion"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    cuit: Mapped[str | None] = mapped_column(Text, nullable=True)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)
    zona_horaria: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)

    configuracion: Mapped[ConfiguracionOrganizacion | None] = relationship(
        back_populates="organizacion", lazy="raise", uselist=False
    )


class ConfiguracionOrganizacion(Base):
    __tablename__ = "configuracion_organizacion"

    organizacion_id: Mapped[UUID] = mapped_column(ForeignKey("organizacion.id"), primary_key=True)
    modo_impositivo: Mapped[str] = mapped_column(Text, nullable=False)
    lista_precio_default_id: Mapped[UUID | None] = mapped_column(nullable=True)
    politica_credito_default: Mapped[str] = mapped_column(Text, nullable=False)
    tolerancia_offline_tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    tolerancia_offline_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    descuento_manual_habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    motivo_obligatorio_descuento: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    motivo_obligatorio_lista: Mapped[bool] = mapped_column(Boolean, nullable=False)
    redondeo_multiplo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    redondeo_direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    permite_consumidor_final: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cliente_consumidor_final_id: Mapped[UUID | None] = mapped_column(nullable=True)
    estado_facturacion_default: Mapped[str] = mapped_column(Text, nullable=False)
    modalidad_iva_default: Mapped[str | None] = mapped_column(Text, nullable=True)
    intentos_pin_max: Mapped[int] = mapped_column(Integer, nullable=False)
    app_version_minima: Mapped[str | None] = mapped_column(Text, nullable=True)
    desvio_reloj_max_segundos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)

    organizacion: Mapped[Organizacion] = relationship(back_populates="configuracion", lazy="raise")
