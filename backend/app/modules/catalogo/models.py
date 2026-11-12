"""Modelos SQLAlchemy de `catalogo`: `Categoria`, `Marca`, `Producto`,
`Presentacion` (`docs/03-modelo-de-datos.md` §5; migración `c1d2e3f4a5b6`).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`.
Ninguna relación declara carga diferida implícita: este módulo no declara
`relationship()` alguna (`CLAUDE.md` §4: "la carga diferida implícita está
desactivada" -- sin relaciones ORM, no hay nada que cargar de forma
implícita; toda lectura pasa por consultas explícitas de
`catalogo/repository.py`, igual que el resto del sistema desde `identidad`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id


class Categoria(Base):
    __tablename__ = "categoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_categoria__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_categoria__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_categoria__org_id"),
        UniqueConstraint("organizacion_id", "nombre", name="ux_categoria__nombre"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class Marca(Base):
    __tablename__ = "marca"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_marca__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_marca__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_marca__org_id"),
        UniqueConstraint("organizacion_id", "nombre", name="ux_marca__nombre"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class Producto(Base):
    __tablename__ = "producto"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_producto__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "categoria_id"],
            ["categoria.organizacion_id", "categoria.id"],
            name="fk_producto__categoria",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "marca_id"],
            ["marca.organizacion_id", "marca.id"],
            name="fk_producto__marca",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "alicuota_id"],
            ["alicuota_iva.organizacion_id", "alicuota_iva.id"],
            name="fk_producto__alicuota",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_producto__proveedor",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_producto__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_producto__org_id"),
        UniqueConstraint("organizacion_id", "codigo", name="ux_producto__codigo"),
        Index("ix_producto__categoria", "organizacion_id", "categoria_id"),
        Index("ix_producto__marca", "organizacion_id", "marca_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    codigo: Mapped[str] = mapped_column(Text, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    categoria_id: Mapped[UUID] = mapped_column(nullable=False)
    marca_id: Mapped[UUID | None] = mapped_column(nullable=True)
    # Change 06 (D2, D9, D10): FK compuesta a `proveedor` y `NOT NULL`
    # (migraciones `70dcb6dce507` y `8b9c0d1e2f3a`). Ya no es opcional.
    proveedor_id: Mapped[UUID] = mapped_column(nullable=False)
    unidad_base: Mapped[str] = mapped_column(Text, nullable=False)
    alicuota_id: Mapped[UUID] = mapped_column(nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class Presentacion(Base):
    __tablename__ = "presentacion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_presentacion__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_presentacion__producto",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_presentacion__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_presentacion__org_id"),
        CheckConstraint("unidades_base >= 1", name="ck_presentacion__unidades_base"),
        CheckConstraint(
            "NOT es_referencia OR usar_en_venta", name="ck_presentacion__referencia_venta"
        ),
        Index("ix_presentacion__producto", "organizacion_id", "producto_id"),
        Index(
            "ux_presentacion__referencia",
            "organizacion_id",
            "producto_id",
            unique=True,
            postgresql_where=text("es_referencia"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    producto_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    unidades_base: Mapped[int] = mapped_column(Integer, nullable=False)
    usar_en_venta: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usar_en_compra: Mapped[bool] = mapped_column(Boolean, nullable=False)
    es_referencia: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
