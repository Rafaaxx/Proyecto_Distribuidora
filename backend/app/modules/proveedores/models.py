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
    Integer,
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
        CheckConstraint(
            "computa_credito_fiscal OR NOT incluye_iva", name="ck_costo_informado__credito_fiscal"
        ),
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
    computa_credito_fiscal: Mapped[bool] = mapped_column(Boolean, nullable=False)
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


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


class Compra(Base):
    """Compra a un proveedor (CMP-01, `03` §6 + D12). Nace `CONFIRMADA`; solo cambia a
    `ANULADA` (TR-06): `app_runtime` puede actualizar únicamente esas columnas."""

    __tablename__ = "compra"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_compra__organizacion"
        ),
        _fk("compra", "proveedor", "proveedor_id", "proveedor"),
        _fk("compra", "ubicacion", "ubicacion_id", "ubicacion"),
        _fk("compra", "usuario", "usuario_id", "usuario"),
        _fk("compra", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("compra", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        _fk("compra", "anulada_por", "anulada_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_compra__org_id"),
        CheckConstraint("condicion IN ('CONTADO','CREDITO')", name="ck_compra__condicion"),
        CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_compra__estado"),
        CheckConstraint("total_neto >= 0", name="ck_compra__total_neto"),
        CheckConstraint("total_factura > 0", name="ck_compra__total_factura"),
        CheckConstraint(
            "(estado = 'ANULADA') = (anulada_en IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulada_por_id IS NOT NULL)",
            name="ck_compra__anulacion_coherente",
        ),
        Index("ix_compra__fecha", "organizacion_id", text("fecha DESC"), text("id DESC")),
        Index(
            "ix_compra__proveedor_fecha",
            "organizacion_id",
            "proveedor_id",
            text("fecha DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    proveedor_id: Mapped[UUID] = mapped_column(nullable=False)
    ubicacion_id: Mapped[UUID] = mapped_column(nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    condicion: Mapped[str] = mapped_column(Text, nullable=False)
    total_neto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_factura: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    numero_comprobante: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    anulacion_motivo_id: Mapped[UUID | None] = mapped_column(nullable=True)
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulada_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    dispositivo_id: Mapped[UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompraLinea(Base):
    """Línea de una compra (CMP-02): congela unidades de la presentación (INV-18) y
    la alícuota aplicada; `cantidad` es la única cantidad `numeric(14,3)` (`03` §2.2),
    `cantidad_base` es entera (INV-04). De solo inserción."""

    __tablename__ = "compra_linea"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_compra_linea__organizacion"
        ),
        _fk("compra_linea", "compra", "compra_id", "compra"),
        _fk("compra_linea", "producto", "producto_id", "producto"),
        _fk("compra_linea", "presentacion", "presentacion_id", "presentacion"),
        UniqueConstraint("organizacion_id", "id", name="ux_compra_linea__org_id"),
        UniqueConstraint(
            "organizacion_id", "compra_id", "orden", name="ux_compra_linea__compra_orden"
        ),
        CheckConstraint("orden >= 1", name="ck_compra_linea__orden"),
        CheckConstraint("unidades_presentacion > 0", name="ck_compra_linea__unidades"),
        CheckConstraint("cantidad > 0", name="ck_compra_linea__cantidad"),
        CheckConstraint("cantidad_base > 0", name="ck_compra_linea__cantidad_base"),
        CheckConstraint("valor_presentacion > 0", name="ck_compra_linea__valor"),
        CheckConstraint(
            "bonificacion >= 0 AND bonificacion < 1", name="ck_compra_linea__bonificacion"
        ),
        CheckConstraint("alicuota_aplicada >= 0", name="ck_compra_linea__alicuota"),
        CheckConstraint("costo_base > 0", name="ck_compra_linea__costo_base"),
        CheckConstraint("importe_neto >= 0", name="ck_compra_linea__importe_neto"),
        CheckConstraint(
            "computa_credito_fiscal OR NOT incluye_iva", name="ck_compra_linea__credito_fiscal"
        ),
        Index("ix_compra_linea__presentacion", "organizacion_id", "presentacion_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    compra_id: Mapped[UUID] = mapped_column(nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    producto_id: Mapped[UUID] = mapped_column(nullable=False)
    presentacion_id: Mapped[UUID] = mapped_column(nullable=False)
    unidades_presentacion: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    cantidad_base: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_presentacion: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    incluye_iva: Mapped[bool] = mapped_column(Boolean, nullable=False)
    computa_credito_fiscal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bonificacion: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    alicuota_aplicada: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    costo_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    importe_neto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class PagoProveedor(Base):
    """Pago a un proveedor (PAG-01). En el change 11 solo nace del contado de una
    compra (`origen = COMPRA`); el 12 agrega el pago independiente (D2, D12)."""

    __tablename__ = "pago_proveedor"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_pago_proveedor__organizacion"
        ),
        _fk("pago_proveedor", "proveedor", "proveedor_id", "proveedor"),
        _fk("pago_proveedor", "compra", "compra_id", "compra"),
        _fk("pago_proveedor", "usuario", "usuario_id", "usuario"),
        _fk("pago_proveedor", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("pago_proveedor", "anulado_por", "anulado_por_id", "usuario"),
        _fk("pago_proveedor", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        UniqueConstraint("organizacion_id", "id", name="ux_pago_proveedor__org_id"),
        CheckConstraint("importe > 0", name="ck_pago_proveedor__importe"),
        CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_pago_proveedor__estado"),
        CheckConstraint("origen IN ('COMPRA','INDEPENDIENTE')", name="ck_pago_proveedor__origen"),
        CheckConstraint(
            "(origen = 'COMPRA' AND compra_id IS NOT NULL) "
            "OR (origen = 'INDEPENDIENTE' AND compra_id IS NULL)",
            name="ck_pago_proveedor__origen_compra",
        ),
        CheckConstraint(
            "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL) "
            "AND (anulacion_motivo_id IS NULL OR anulado_en IS NOT NULL)",
            name="ck_pago_proveedor__anulacion_coherente",
        ),
        Index(
            "ux_pago_proveedor__compra",
            "organizacion_id",
            "compra_id",
            unique=True,
            postgresql_where=text("compra_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    proveedor_id: Mapped[UUID] = mapped_column(nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    origen: Mapped[str] = mapped_column(Text, nullable=False)
    compra_id: Mapped[UUID | None] = mapped_column(nullable=True)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anulado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    anulacion_motivo_id: Mapped[UUID | None] = mapped_column(nullable=True)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    dispositivo_id: Mapped[UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PagoProveedorMedio(Base):
    """Un medio de un pago (PAG-01, INV-08: la suma de medios es el importe del
    pago, validada en el servicio). De solo inserción."""

    __tablename__ = "pago_proveedor_medio"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_pago_proveedor_medio__organizacion"
        ),
        _fk("pago_proveedor_medio", "pago", "pago_id", "pago_proveedor"),
        _fk("pago_proveedor_medio", "medio_pago", "medio_pago_id", "medio_pago"),
        UniqueConstraint("organizacion_id", "id", name="ux_pago_proveedor_medio__org_id"),
        CheckConstraint("importe > 0", name="ck_pago_proveedor_medio__importe"),
        Index("ix_pago_proveedor_medio__pago", "organizacion_id", "pago_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    pago_id: Mapped[UUID] = mapped_column(nullable=False)
    medio_pago_id: Mapped[UUID] = mapped_column(nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    referencia: Mapped[str | None] = mapped_column(Text, nullable=True)
