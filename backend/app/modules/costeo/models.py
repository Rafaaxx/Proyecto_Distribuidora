"""Modelos SQLAlchemy de `costeo`: `CostoProducto` y `CostoProductoMov`
(`docs/03-modelo-de-datos.md` §7; migración `a8b9c0d1e2f3`).

Mapean exactamente lo que crea la migración: `test_modelos_coinciden_con_
migracion.py` corre `alembic revision --autogenerate` y exige que no detecte
ninguna diferencia.

Ninguna relación declara carga diferida implícita: este módulo no declara
`relationship()` alguna (`CLAUDE.md` §4), igual que `cuentas_corrientes/models.py`.

`costo_producto` es una materialización verificable (`02` §7.2, ADR-015): la fila
que se bloquea al registrar un movimiento del producto. `costo_producto_mov` es
un libro de solo inserción (CST-13, INV-05): el usuario de aplicación no tiene
`UPDATE` ni `DELETE`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id

_ORIGENES_DE_COSTO = "'COMPRA','ANULACION_COMPRA','STOCK_INICIAL','ANULACION_VENTA'"


class CostoProducto(Base):
    """Costo promedio y stock total de un producto en la organización (CST-10).

    Clave primaria compuesta `(organizacion_id, producto_id)` sin `id` (ADR-035
    punto 6, `design.md` D10). `costo_promedio` es NULO hasta el primer ingreso
    con costo ("sin costo" no es "costo cero"). `stock_total` es la suma de los
    saldos del producto en todas las ubicaciones y cambia con todo movimiento.
    """

    __tablename__ = "costo_producto"
    __table_args__ = (
        PrimaryKeyConstraint("organizacion_id", "producto_id", name="pk_costo_producto"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_costo_producto__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_costo_producto__producto",
        ),
        CheckConstraint(
            "costo_promedio IS NULL OR costo_promedio > 0",
            name="ck_costo_producto__promedio_positivo",
        ),
    )

    organizacion_id: Mapped[UUID]
    producto_id: Mapped[UUID]
    costo_promedio: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    stock_total: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CostoProductoMov(Base):
    """Una fila de la historia del promedio (CST-13), de solo inserción.

    Guarda el stock y el promedio anteriores y nuevos de un ingreso con costo,
    de modo que el promedio en cualquier momento pueda reconstruirse.
    `promedio_anterior` es NULO en el primer ingreso (D10). `origen_id` es el
    documento que lo originó; para un stock inicial no hay una tabla a la que
    apuntar, así que es el `operation_id` (`design.md` D5).
    """

    __tablename__ = "costo_producto_mov"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_costo_producto_mov"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_costo_producto_mov__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_costo_producto_mov__producto",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_costo_producto_mov__org_id"),
        CheckConstraint(
            f"origen_tipo IN ({_ORIGENES_DE_COSTO})", name="ck_costo_producto_mov__origen_tipo"
        ),
        Index(
            "ix_costo_producto_mov__producto",
            "organizacion_id",
            "producto_id",
            "registered_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    producto_id: Mapped[UUID]
    origen_tipo: Mapped[str] = mapped_column(Text)
    origen_id: Mapped[UUID]
    cantidad: Mapped[int] = mapped_column(Integer)
    costo_ingreso: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    stock_anterior: Mapped[int] = mapped_column(Integer)
    promedio_anterior: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    stock_nuevo: Mapped[int] = mapped_column(Integer)
    promedio_nuevo: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    recalculado: Mapped[bool] = mapped_column(Boolean)
    operation_id: Mapped[UUID]
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
