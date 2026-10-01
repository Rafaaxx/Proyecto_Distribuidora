"""Modelos SQLAlchemy de `stock`: `Ubicacion`, `StockSaldo` y `StockMovimiento`
(`docs/03-modelo-de-datos.md` §9; migración `a8b9c0d1e2f3`).

Mapean exactamente lo que crea la migración: `test_modelos_coinciden_con_
migracion.py` corre `alembic revision --autogenerate` y exige que no detecte
ninguna diferencia.

Ninguna relación declara carga diferida implícita: este módulo no declara
`relationship()` alguna (`CLAUDE.md` §4). Los ids se generan con UUIDv7
(`core/ids.py`) y los momentos son `timestamptz`.

`stock_movimiento` es un libro de solo inserción (STK-03, INV-05): el usuario de
aplicación no tiene `UPDATE` ni `DELETE`. `stock_saldo` es una materialización
verificable del libro (`02` §7.2, ADR-015, INV-12): es la fila que se bloquea al
registrar un movimiento. `ubicacion` es un maestro y se actualiza.
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

_TIPOS_DE_UBICACION = "'DEPOSITO','VEHICULO','OTRO'"
_TIPOS_DE_MOVIMIENTO = (
    "'STOCK_INICIAL','COMPRA','ANULACION_COMPRA','VENTA','ANULACION_VENTA',"
    "'TRANSFERENCIA_SALIDA','TRANSFERENCIA_ENTRADA','AJUSTE','DIFERENCIA_RENDICION'"
)


class Ubicacion(Base):
    """Un lugar donde hay stock: depósito, vehículo u otro (STK-02).

    `requiere_toma` es un indicador propio y un vehículo siempre lo tiene en
    `true` (`ck_ubicacion__vehiculo_requiere_toma`, D7). El nombre es único por
    organización sin distinguir mayúsculas, activas o no (`ux_ubicacion__nombre`,
    D7). `actualizado_en` y `actualizado_por_id` como todo maestro (`03` §2.3).
    """

    __tablename__ = "ubicacion"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_ubicacion"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_ubicacion__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_ubicacion__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_ubicacion__org_id"),
        CheckConstraint(f"tipo IN ({_TIPOS_DE_UBICACION})", name="ck_ubicacion__tipo"),
        CheckConstraint(
            "tipo <> 'VEHICULO' OR requiere_toma", name="ck_ubicacion__vehiculo_requiere_toma"
        ),
        Index("ux_ubicacion__nombre", "organizacion_id", text("lower(nombre)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    requiere_toma: Mapped[bool] = mapped_column(Boolean)
    activo: Mapped[bool] = mapped_column(Boolean)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_por_id: Mapped[UUID | None]


class StockSaldo(Base):
    """Saldo materializado de un producto en una ubicación (`03` §9, `02` §7.2).

    Clave primaria compuesta `(organizacion_id, producto_id, ubicacion_id)` sin
    `id` (ADR-035 punto 6). Nace de forma perezosa con el primer movimiento
    (D10). El libro es la verdad: esta fila es verificable contra él (INV-12).
    """

    __tablename__ = "stock_saldo"
    __table_args__ = (
        PrimaryKeyConstraint(
            "organizacion_id", "producto_id", "ubicacion_id", name="pk_stock_saldo"
        ),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_stock_saldo__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_stock_saldo__producto",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "ubicacion_id"],
            ["ubicacion.organizacion_id", "ubicacion.id"],
            name="fk_stock_saldo__ubicacion",
        ),
        Index("ix_stock_saldo__ubicacion", "organizacion_id", "ubicacion_id"),
    )

    organizacion_id: Mapped[UUID]
    producto_id: Mapped[UUID]
    ubicacion_id: Mapped[UUID]
    cantidad_base: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StockMovimiento(Base):
    """Un movimiento del libro de stock (STK-03).

    `cantidad_base` con signo y distinta de cero. `origen_tipo`/`origen_id` dicen
    qué operación lo originó; para un stock inicial no hay una tabla a la que
    apuntar, así que `origen_id` es el `operation_id` (`design.md` D5). No tiene
    FK por tipo de documento (`03` §9). `dispositivo_id` es `NOT NULL` con FK
    compuesta a `dispositivo` (D12). `jornada_id` es nulable y NO tiene FK hasta
    el change 15, porque `jornada` no existe todavía (D12).
    """

    __tablename__ = "stock_movimiento"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_stock_movimiento"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_stock_movimiento__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_stock_movimiento__producto",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "ubicacion_id"],
            ["ubicacion.organizacion_id", "ubicacion.id"],
            name="fk_stock_movimiento__ubicacion",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_stock_movimiento__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_stock_movimiento__dispositivo",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "motivo_id"],
            ["motivo.organizacion_id", "motivo.id"],
            name="fk_stock_movimiento__motivo",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_stock_movimiento__org_id"),
        CheckConstraint("cantidad_base <> 0", name="ck_stock_movimiento__cantidad_no_cero"),
        CheckConstraint(f"tipo IN ({_TIPOS_DE_MOVIMIENTO})", name="ck_stock_movimiento__tipo"),
        Index(
            "ix_stock_movimiento__kardex",
            "organizacion_id",
            "producto_id",
            "ubicacion_id",
            "occurred_at",
            "id",
        ),
        Index("ix_stock_movimiento__origen", "organizacion_id", "origen_tipo", "origen_id"),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    producto_id: Mapped[UUID]
    ubicacion_id: Mapped[UUID]
    cantidad_base: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(Text)
    origen_tipo: Mapped[str] = mapped_column(Text)
    origen_id: Mapped[UUID]
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    jornada_id: Mapped[UUID | None]
    motivo_id: Mapped[UUID | None]
    operation_id: Mapped[UUID]
    usuario_id: Mapped[UUID]
    dispositivo_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
