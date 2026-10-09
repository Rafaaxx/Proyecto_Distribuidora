"""Modelos SQLAlchemy de `stock`: `Ubicacion`, `StockSaldo` y `StockMovimiento`
(`docs/03-modelo-de-datos.md` §9; migración `a8b9c0d1e2f3`) y, del change 14,
`Transferencia`, `TransferenciaLinea`, `AjusteStock` y `AjusteStockLinea` (migración
`f3a4b5c6d7e8`).

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


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


class Transferencia(Base):
    """Cabecera de una transferencia entre dos ubicaciones (STK-07, `design.md` D8). Nace
    `CONFIRMADA`; solo cambia a `ANULADA` (TR-06, D5): `app_runtime` puede actualizar
    únicamente `estado` y las tres columnas de anulación."""

    __tablename__ = "transferencia"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_transferencia"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_transferencia__organizacion"
        ),
        _fk("transferencia", "origen", "ubicacion_origen_id", "ubicacion"),
        _fk("transferencia", "destino", "ubicacion_destino_id", "ubicacion"),
        _fk("transferencia", "usuario", "usuario_id", "usuario"),
        _fk("transferencia", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("transferencia", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        _fk("transferencia", "anulada_por", "anulada_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_transferencia__org_id"),
        CheckConstraint(
            "ubicacion_origen_id <> ubicacion_destino_id",
            name="ck_transferencia__ubicaciones_distintas",
        ),
        CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_transferencia__estado"),
        CheckConstraint(
            "(estado = 'ANULADA') = (anulada_en IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulada_por_id IS NOT NULL)",
            name="ck_transferencia__anulacion_coherente",
        ),
        Index(
            "ix_transferencia__fecha", "organizacion_id", text("occurred_at DESC"), text("id DESC")
        ),
        Index(
            "ix_transferencia__origen_fecha",
            "organizacion_id",
            "ubicacion_origen_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_transferencia__destino_fecha",
            "organizacion_id",
            "ubicacion_destino_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    ubicacion_origen_id: Mapped[UUID]
    ubicacion_destino_id: Mapped[UUID]
    observacion: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text)
    anulacion_motivo_id: Mapped[UUID | None]
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulada_por_id: Mapped[UUID | None]
    operation_id: Mapped[UUID]
    usuario_id: Mapped[UUID]
    dispositivo_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TransferenciaLinea(Base):
    """Línea de una transferencia: un producto y su cantidad en unidad base (INV-04),
    siempre positiva. De solo inserción."""

    __tablename__ = "transferencia_linea"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_transferencia_linea"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_transferencia_linea__organizacion"
        ),
        _fk("transferencia_linea", "transferencia", "transferencia_id", "transferencia"),
        _fk("transferencia_linea", "producto", "producto_id", "producto"),
        UniqueConstraint("organizacion_id", "id", name="ux_transferencia_linea__org_id"),
        UniqueConstraint(
            "organizacion_id",
            "transferencia_id",
            "orden",
            name="ux_transferencia_linea__transferencia_orden",
        ),
        CheckConstraint("orden >= 1", name="ck_transferencia_linea__orden"),
        CheckConstraint("cantidad_base > 0", name="ck_transferencia_linea__cantidad_base"),
        Index("ix_transferencia_linea__producto", "organizacion_id", "producto_id"),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    transferencia_id: Mapped[UUID]
    orden: Mapped[int] = mapped_column(Integer)
    producto_id: Mapped[UUID]
    cantidad_base: Mapped[int] = mapped_column(Integer)


class AjusteStock(Base):
    """Cabecera de un ajuste de stock en una ubicación, con un motivo (STK-08, `design.md`
    D8). Mismo ciclo de estado que `Transferencia`."""

    __tablename__ = "ajuste_stock"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_ajuste_stock"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_ajuste_stock__organizacion"
        ),
        _fk("ajuste_stock", "ubicacion", "ubicacion_id", "ubicacion"),
        _fk("ajuste_stock", "motivo", "motivo_id", "motivo"),
        _fk("ajuste_stock", "usuario", "usuario_id", "usuario"),
        _fk("ajuste_stock", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("ajuste_stock", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        _fk("ajuste_stock", "anulado_por", "anulado_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_ajuste_stock__org_id"),
        CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_ajuste_stock__estado"),
        CheckConstraint(
            "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL)",
            name="ck_ajuste_stock__anulacion_coherente",
        ),
        Index(
            "ix_ajuste_stock__fecha", "organizacion_id", text("occurred_at DESC"), text("id DESC")
        ),
        Index(
            "ix_ajuste_stock__ubicacion_fecha",
            "organizacion_id",
            "ubicacion_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_ajuste_stock__motivo_fecha",
            "organizacion_id",
            "motivo_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    ubicacion_id: Mapped[UUID]
    motivo_id: Mapped[UUID]
    observacion: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text)
    anulacion_motivo_id: Mapped[UUID | None]
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_por_id: Mapped[UUID | None]
    operation_id: Mapped[UUID]
    usuario_id: Mapped[UUID]
    dispositivo_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AjusteStockLinea(Base):
    """Línea de un ajuste: `cantidad_base` con signo y distinta de cero (INV-04) y el
    `costo_unitario` con que se valorizó el movimiento (promedio vigente, nulo si el
    producto no tenía; `design.md` D3). De solo inserción."""

    __tablename__ = "ajuste_stock_linea"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_ajuste_stock_linea"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_ajuste_stock_linea__organizacion"
        ),
        _fk("ajuste_stock_linea", "ajuste", "ajuste_id", "ajuste_stock"),
        _fk("ajuste_stock_linea", "producto", "producto_id", "producto"),
        UniqueConstraint("organizacion_id", "id", name="ux_ajuste_stock_linea__org_id"),
        UniqueConstraint(
            "organizacion_id", "ajuste_id", "orden", name="ux_ajuste_stock_linea__ajuste_orden"
        ),
        CheckConstraint("orden >= 1", name="ck_ajuste_stock_linea__orden"),
        CheckConstraint("cantidad_base <> 0", name="ck_ajuste_stock_linea__cantidad_base"),
        Index("ix_ajuste_stock_linea__producto", "organizacion_id", "producto_id"),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    ajuste_id: Mapped[UUID]
    orden: Mapped[int] = mapped_column(Integer)
    producto_id: Mapped[UUID]
    cantidad_base: Mapped[int] = mapped_column(Integer)
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
