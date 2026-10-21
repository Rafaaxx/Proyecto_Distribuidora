"""Modelos SQLAlchemy de `ventas`: `Venta` y `VentaLinea` (`docs/03-modelo-de-datos.md` §12;
migración `a2b3c4d5e6f7`, `design.md` D16).

`id` se genera con UUIDv7 (`core/ids.py`); las ventas lo reciben de quien las origina (el
dispositivo). Los momentos son `timestamptz`. De solo inserción para `app_runtime` (INV-05,
INV-10, TR-06: sin `UPDATE` ni `DELETE`; el change 19 agrega el `UPDATE` de `estado`). Este
módulo no declara `relationship()` alguna (`CLAUDE.md` §4: carga explícita); toda lectura pasa
por consultas explícitas de `ventas/repository.py`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


class Venta(Base):
    """Cabecera de una venta confirmada (VTA-03, VTA-12). Los totales cumplen INV-14."""

    __tablename__ = "venta"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_venta__organizacion"
        ),
        _fk("venta", "cliente", "cliente_id", "cliente"),
        _fk("venta", "usuario", "usuario_id", "usuario"),
        _fk("venta", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("venta", "ubicacion", "ubicacion_id", "ubicacion"),
        _fk("venta", "jornada", "jornada_id", "jornada"),
        _fk("venta", "lista", "lista_id", "lista_precio"),
        _fk("venta", "lista_version", "lista_version_id", "lista_version"),
        _fk("venta", "motivo_lista", "motivo_lista_id", "motivo"),
        UniqueConstraint("organizacion_id", "id", name="ux_venta__org_id"),
        UniqueConstraint("organizacion_id", "numero", name="ux_venta__numero"),
        CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_venta__estado"),
        CheckConstraint(
            "estado_facturacion IN ('NO_REQUIERE','PENDIENTE','PARCIAL','FACTURADA')",
            name="ck_venta__estado_facturacion",
        ),
        CheckConstraint("modo_impositivo IN ('A','B','C')", name="ck_venta__modo_impositivo"),
        CheckConstraint(
            "modo_confirmacion IN ('ONLINE','OFFLINE')", name="ck_venta__modo_confirmacion"
        ),
        CheckConstraint("total = total_neto + total_iva", name="ck_venta__total"),
        CheckConstraint(
            "importe_facturado >= 0 AND importe_facturado <= total_neto", name="ck_venta__facturado"
        ),
        CheckConstraint(
            "modo_confirmacion = 'ONLINE' OR jornada_id IS NOT NULL", name="ck_venta__jornada"
        ),
        Index(
            "ix_venta__occurred_at", "organizacion_id", text("occurred_at DESC"), text("id DESC")
        ),
        Index(
            "ix_venta__cliente",
            "organizacion_id",
            "cliente_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_venta__usuario",
            "organizacion_id",
            "usuario_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
        Index("ix_venta__jornada", "organizacion_id", "jornada_id"),
        Index(
            "ix_venta__facturacion_pendiente",
            "organizacion_id",
            "cliente_id",
            postgresql_where=text("estado_facturacion IN ('PENDIENTE','PARCIAL')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    numero: Mapped[str] = mapped_column(Text, nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    dispositivo_id: Mapped[UUID] = mapped_column(nullable=False)
    ubicacion_id: Mapped[UUID] = mapped_column(nullable=False)
    jornada_id: Mapped[UUID | None] = mapped_column(nullable=True)
    lista_id: Mapped[UUID] = mapped_column(nullable=False)
    lista_version_id: Mapped[UUID] = mapped_column(nullable=False)
    motivo_lista_id: Mapped[UUID | None] = mapped_column(nullable=True)
    modo_impositivo: Mapped[str] = mapped_column(Text, nullable=False)
    modo_confirmacion: Mapped[str] = mapped_column(Text, nullable=False)
    total_neto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    estado_facturacion: Mapped[str] = mapped_column(Text, nullable=False)
    importe_facturado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VentaLinea(Base):
    """Una línea de venta con todo lo que congela (VTA-03, PRC-23, INV-10, INV-18): presentación
    y sus unidades, versión de lista, precio y unidades de referencia, importes, alícuota, IVA y
    costo (nulo cuando se vendió sin costo, D10)."""

    __tablename__ = "venta_linea"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_venta_linea__organizacion"
        ),
        _fk("venta_linea", "venta", "venta_id", "venta"),
        _fk("venta_linea", "producto", "producto_id", "producto"),
        _fk("venta_linea", "presentacion", "presentacion_id", "presentacion"),
        _fk("venta_linea", "lista_version", "lista_version_id", "lista_version"),
        UniqueConstraint("organizacion_id", "id", name="ux_venta_linea__org_id"),
        UniqueConstraint(
            "organizacion_id", "venta_id", "orden", name="ux_venta_linea__venta_orden"
        ),
        CheckConstraint("orden >= 0", name="ck_venta_linea__orden"),
        CheckConstraint("cantidad > 0", name="ck_venta_linea__cantidad"),
        CheckConstraint(
            "cantidad_base = cantidad * unidades_presentacion", name="ck_venta_linea__cantidad_base"
        ),
        CheckConstraint("unidades_presentacion >= 1", name="ck_venta_linea__unidades_presentacion"),
        CheckConstraint("unidades_referencia >= 1", name="ck_venta_linea__unidades_referencia"),
        CheckConstraint(
            "importe_neto = importe_bruto - importe_descuento", name="ck_venta_linea__neto"
        ),
        CheckConstraint(
            "(costo_total IS NULL) = (costo_unitario IS NULL)", name="ck_venta_linea__costo"
        ),
        Index("ix_venta_linea__producto", "organizacion_id", "producto_id"),
        Index("ix_venta_linea__presentacion", "organizacion_id", "presentacion_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    venta_id: Mapped[UUID] = mapped_column(nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    producto_id: Mapped[UUID] = mapped_column(nullable=False)
    presentacion_id: Mapped[UUID] = mapped_column(nullable=False)
    lista_version_id: Mapped[UUID] = mapped_column(nullable=False)
    unidades_presentacion: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_base: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_referencia: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unidades_referencia: Mapped[int] = mapped_column(Integer, nullable=False)
    importe_bruto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    importe_descuento: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    importe_neto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    alicuota: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    importe_iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    costo_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
