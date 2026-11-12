"""Modelos SQLAlchemy de `descuentos`: `ReglaDescuento` y `ReglaDescuentoAlcance`
(`docs/03-modelo-de-datos.md` §11; migración `b5c6d7e8f9a0`, `design.md` D17).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`. El umbral, el
porcentaje y el importe fijo son `Numeric` (`Decimal`), nunca `float` (INV-03). Las claves
foráneas entre entidades de negocio son compuestas e incluyen `organizacion_id` (INV-02).

Este módulo no declara `relationship()` alguna (`CLAUDE.md` §4, igual que `precios/models.py`):
toda lectura pasa por consultas explícitas de `descuentos/repository.py`.

`ReglaDescuentoAlcance.producto_id`, `categoria_id` y `marca_id` son columnas GENERADAS por
PostgreSQL a partir de `alcance_id` (ADR-035): nadie las escribe y cada una tiene su clave
foránea compuesta, así la base rechaza un alcance hacia una entidad de otra organización.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id

_TIPOS = "'VOLUMEN_OPERACION','VOLUMEN_ALCANCE'"
_MEDIDAS = "'CAJAS_EQUIVALENTES','UNIDADES_BASE','IMPORTE_BRUTO'"
_OPERADORES = "'GTE','GT'"
_ACCIONES = "'PORCENTAJE','IMPORTE_FIJO'"
_ESTADOS = "'BORRADOR','ACTIVA','PAUSADA'"
_ALCANCES = "'PRODUCTO','CATEGORIA','MARCA'"

_ACCION_EXACTA = (
    "(accion_tipo = 'PORCENTAJE' AND accion_porcentaje IS NOT NULL AND accion_importe IS NULL) "
    "OR (accion_tipo = 'IMPORTE_FIJO' AND accion_importe IS NOT NULL "
    "AND accion_porcentaje IS NULL)"
)


def _generada(alcance: str) -> Computed:
    return Computed(f"CASE WHEN alcance_tipo = '{alcance}' THEN alcance_id END", persisted=True)


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> ForeignKeyConstraint:
    """Clave foránea compuesta que incluye `organizacion_id` (INV-02, `03` §2.4)."""
    return ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


class ReglaDescuento(Base):
    __tablename__ = "regla_descuento"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_regla_descuento__organizacion"
        ),
        _fk("regla_descuento", "actualizado_por", "actualizado_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_regla_descuento__org_id"),
        CheckConstraint(f"tipo IN ({_TIPOS})", name="ck_regla_descuento__tipo"),
        CheckConstraint(f"medida IN ({_MEDIDAS})", name="ck_regla_descuento__medida"),
        CheckConstraint(f"operador IN ({_OPERADORES})", name="ck_regla_descuento__operador"),
        CheckConstraint(f"accion_tipo IN ({_ACCIONES})", name="ck_regla_descuento__accion_tipo"),
        CheckConstraint(f"estado IN ({_ESTADOS})", name="ck_regla_descuento__estado"),
        CheckConstraint(_ACCION_EXACTA, name="ck_regla_descuento__accion"),
        CheckConstraint(
            "accion_porcentaje IS NULL OR (accion_porcentaje > 0 AND accion_porcentaje <= 1)",
            name="ck_regla_descuento__accion_porcentaje",
        ),
        CheckConstraint(
            "accion_importe IS NULL OR accion_importe > 0",
            name="ck_regla_descuento__accion_importe",
        ),
        CheckConstraint("umbral > 0", name="ck_regla_descuento__umbral"),
        CheckConstraint("prioridad >= 1", name="ck_regla_descuento__prioridad"),
        CheckConstraint(
            "vigencia_desde IS NULL OR vigencia_hasta IS NULL OR vigencia_hasta > vigencia_desde",
            name="ck_regla_descuento__vigencia",
        ),
        CheckConstraint(
            "estado = 'BORRADOR' OR vigencia_desde IS NOT NULL",
            name="ck_regla_descuento__vigencia_desde",
        ),
        Index("ix_regla_descuento__listado", "organizacion_id", "estado", text("id DESC")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    medida: Mapped[str] = mapped_column(Text, nullable=False)
    operador: Mapped[str] = mapped_column(Text, nullable=False)
    umbral: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    accion_tipo: Mapped[str] = mapped_column(Text, nullable=False)
    accion_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    accion_importe: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    prioridad: Mapped[int] = mapped_column(Integer, nullable=False)
    acumulable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    vigencia_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vigencia_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ReglaDescuentoAlcance(Base):
    __tablename__ = "regla_descuento_alcance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_regla_descuento_alcance__organizacion",
        ),
        _fk("regla_descuento_alcance", "regla", "regla_id", "regla_descuento"),
        _fk("regla_descuento_alcance", "producto", "producto_id", "producto"),
        _fk("regla_descuento_alcance", "categoria", "categoria_id", "categoria"),
        _fk("regla_descuento_alcance", "marca", "marca_id", "marca"),
        UniqueConstraint("organizacion_id", "id", name="ux_regla_descuento_alcance__org_id"),
        UniqueConstraint(
            "organizacion_id",
            "regla_id",
            "alcance_tipo",
            "alcance_id",
            name="ux_regla_descuento_alcance__regla_entidad",
        ),
        CheckConstraint(
            f"alcance_tipo IN ({_ALCANCES})", name="ck_regla_descuento_alcance__alcance_tipo"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    regla_id: Mapped[UUID] = mapped_column(nullable=False)
    alcance_tipo: Mapped[str] = mapped_column(Text, nullable=False)
    alcance_id: Mapped[UUID] = mapped_column(nullable=False)
    producto_id: Mapped[UUID | None] = mapped_column(_generada("PRODUCTO"))
    categoria_id: Mapped[UUID | None] = mapped_column(_generada("CATEGORIA"))
    marca_id: Mapped[UUID | None] = mapped_column(_generada("MARCA"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
