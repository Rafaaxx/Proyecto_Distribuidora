"""Modelos SQLAlchemy de `precios`: `ListaPrecio`, `ReglaMargen`, `RedondeoCategoria`,
`ListaVersion` y `PrecioItem` (`docs/03-modelo-de-datos.md` §8; migración `e2f3a4b5c6d7`,
`design.md` D13).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`. Importes,
costos y porcentajes son `Numeric` (`Decimal`), nunca `float` (INV-03). Las claves
foráneas entre entidades de negocio son compuestas e incluyen `organizacion_id` (INV-02).

Ninguna relación declara carga diferida implícita: este módulo no declara `relationship()`
alguna (`CLAUDE.md` §4), igual que `catalogo/models.py` y `proveedores/models.py`; toda
lectura pasa por consultas explícitas de `precios/repository.py`.

`ReglaMargen.producto_id`, `marca_id`, `categoria_id` y `proveedor_id` son columnas
GENERADAS por PostgreSQL a partir de `alcance_id` (ADR-035): nadie las escribe y cada una
tiene su clave foránea compuesta, así la base rechaza una regla cuya entidad es de otra
organización o no existe.
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

_DIRECCIONES = "'ARRIBA','CERCANO','ABAJO'"
_TIPOS_MARGEN = "'MARKUP','MARGEN_BRUTO'"
_ALCANCES = "'PRODUCTO','MARCA','CATEGORIA','PROVEEDOR','LISTA'"


def _generada(alcance: str) -> Computed:
    return Computed(f"CASE WHEN alcance_tipo = '{alcance}' THEN alcance_id END", persisted=True)


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> ForeignKeyConstraint:
    """Clave foránea compuesta que incluye `organizacion_id` (INV-02, `03` §2.4)."""
    return ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


class ListaPrecio(Base):
    __tablename__ = "lista_precio"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_lista_precio__organizacion"
        ),
        _fk("lista_precio", "actualizado_por", "actualizado_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_lista_precio__org_id"),
        CheckConstraint("redondeo_multiplo > 0", name="ck_lista_precio__redondeo_multiplo"),
        CheckConstraint(
            f"redondeo_direccion IN ({_DIRECCIONES})", name="ck_lista_precio__redondeo_direccion"
        ),
        # D13 punto 1: el nombre es único por organización sin distinguir mayúsculas.
        Index("ux_lista_precio__nombre", "organizacion_id", text("lower(nombre)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    redondeo_multiplo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    redondeo_direccion: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ReglaMargen(Base):
    __tablename__ = "regla_margen"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_regla_margen__organizacion"
        ),
        _fk("regla_margen", "lista", "lista_id", "lista_precio"),
        _fk("regla_margen", "producto", "producto_id", "producto"),
        _fk("regla_margen", "marca", "marca_id", "marca"),
        _fk("regla_margen", "categoria", "categoria_id", "categoria"),
        _fk("regla_margen", "proveedor", "proveedor_id", "proveedor"),
        _fk("regla_margen", "actualizado_por", "actualizado_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_regla_margen__org_id"),
        CheckConstraint(f"alcance_tipo IN ({_ALCANCES})", name="ck_regla_margen__alcance_tipo"),
        CheckConstraint(f"tipo IN ({_TIPOS_MARGEN})", name="ck_regla_margen__tipo"),
        CheckConstraint(
            "(alcance_tipo = 'LISTA') = (alcance_id IS NULL)", name="ck_regla_margen__alcance"
        ),
        # PRC-12: el valor nunca es negativo y un margen bruto es menor que 1.
        CheckConstraint(
            "valor >= 0 AND (tipo <> 'MARGEN_BRUTO' OR valor < 1)", name="ck_regla_margen__valor"
        ),
        # D8: una sola regla activa por lista y alcance. El alcance `LISTA` no tiene
        # `alcance_id` y NULL no choca consigo mismo en un único, así que son dos índices.
        Index(
            "ux_regla_margen__alcance_activa",
            "organizacion_id",
            "lista_id",
            "alcance_tipo",
            "alcance_id",
            unique=True,
            postgresql_where=text("activo AND alcance_id IS NOT NULL"),
        ),
        Index(
            "ux_regla_margen__lista_activa",
            "organizacion_id",
            "lista_id",
            unique=True,
            postgresql_where=text("activo AND alcance_tipo = 'LISTA'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    lista_id: Mapped[UUID] = mapped_column(nullable=False)
    alcance_tipo: Mapped[str] = mapped_column(Text, nullable=False)
    alcance_id: Mapped[UUID | None] = mapped_column(nullable=True)
    producto_id: Mapped[UUID | None] = mapped_column(_generada("PRODUCTO"))
    marca_id: Mapped[UUID | None] = mapped_column(_generada("MARCA"))
    categoria_id: Mapped[UUID | None] = mapped_column(_generada("CATEGORIA"))
    proveedor_id: Mapped[UUID | None] = mapped_column(_generada("PROVEEDOR"))
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class RedondeoCategoria(Base):
    __tablename__ = "redondeo_categoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_redondeo_categoria__organizacion"
        ),
        _fk("redondeo_categoria", "lista", "lista_id", "lista_precio"),
        _fk("redondeo_categoria", "categoria", "categoria_id", "categoria"),
        _fk("redondeo_categoria", "actualizado_por", "actualizado_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_redondeo_categoria__org_id"),
        UniqueConstraint(
            "organizacion_id",
            "lista_id",
            "categoria_id",
            name="ux_redondeo_categoria__lista_categoria",
        ),
        CheckConstraint("multiplo > 0", name="ck_redondeo_categoria__multiplo"),
        CheckConstraint(f"direccion IN ({_DIRECCIONES})", name="ck_redondeo_categoria__direccion"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    lista_id: Mapped[UUID] = mapped_column(nullable=False)
    categoria_id: Mapped[UUID] = mapped_column(nullable=False)
    multiplo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    direccion: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class ListaVersion(Base):
    __tablename__ = "lista_version"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_lista_version__organizacion"
        ),
        _fk("lista_version", "lista", "lista_id", "lista_precio"),
        _fk("lista_version", "version_base", "version_base_id", "lista_version"),
        _fk("lista_version", "creado_por", "creado_por_id", "usuario"),
        _fk("lista_version", "publicado_por", "publicado_por_id", "usuario"),
        _fk("lista_version", "anulado_por", "anulado_por_id", "usuario"),
        UniqueConstraint("organizacion_id", "id", name="ux_lista_version__org_id"),
        CheckConstraint(
            "estado IN ('BORRADOR','PUBLICADA','ANULADA')", name="ck_lista_version__estado"
        ),
        CheckConstraint("numero >= 1", name="ck_lista_version__numero"),
        # Un borrador no tiene vigencia ni publicación; una versión publicada o anulada
        # tiene usuario, momento y vigencia desde (PRC-02, D6).
        CheckConstraint(
            "(estado = 'BORRADOR') = (publicado_en IS NULL) "
            "AND (publicado_en IS NULL) = (publicado_por_id IS NULL) "
            "AND (publicado_en IS NULL) = (vigencia_desde IS NULL) "
            "AND (vigencia_hasta IS NULL OR vigencia_desde IS NOT NULL)",
            name="ck_lista_version__publicacion_coherente",
        ),
        CheckConstraint(
            "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL)",
            name="ck_lista_version__anulacion_coherente",
        ),
        CheckConstraint(
            "vigencia_hasta IS NULL OR vigencia_hasta > vigencia_desde",
            name="ck_lista_version__vigencia",
        ),
        Index("ux_lista_version__numero", "organizacion_id", "lista_id", "numero", unique=True),
        # D5: un solo borrador por lista.
        Index(
            "ux_lista_version__borrador",
            "organizacion_id",
            "lista_id",
            unique=True,
            postgresql_where=text("estado = 'BORRADOR'"),
        ),
        # D6: dos versiones publicadas de una lista no comparten vigencia desde.
        Index(
            "ux_lista_version__vigencia_desde",
            "organizacion_id",
            "lista_id",
            "vigencia_desde",
            unique=True,
            postgresql_where=text("estado = 'PUBLICADA'"),
        ),
        # PRC-03, PRC-20: la versión vigente se resuelve por la vigencia desde más reciente.
        Index(
            "ix_lista_version__resolucion",
            "organizacion_id",
            "lista_id",
            text("vigencia_desde DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    lista_id: Mapped[UUID] = mapped_column(nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    vigencia_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vigencia_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_base_id: Mapped[UUID | None] = mapped_column(nullable=True)
    generado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_por_id: Mapped[UUID] = mapped_column(nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publicado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operation_id: Mapped[UUID] = mapped_column(nullable=False)


class PrecioItem(Base):
    __tablename__ = "precio_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_precio_item__organizacion"
        ),
        _fk("precio_item", "version", "version_id", "lista_version"),
        _fk("precio_item", "producto", "producto_id", "producto"),
        _fk("precio_item", "costo_informado", "costo_informado_id", "costo_informado"),
        _fk("precio_item", "regla_margen", "regla_margen_id", "regla_margen"),
        UniqueConstraint("organizacion_id", "id", name="ux_precio_item__org_id"),
        CheckConstraint("unidades_referencia >= 1", name="ck_precio_item__unidades_referencia"),
        CheckConstraint("precio_final > 0", name="ck_precio_item__precio_final"),
        CheckConstraint(
            f"tipo_margen IS NULL OR tipo_margen IN ({_TIPOS_MARGEN})",
            name="ck_precio_item__tipo_margen",
        ),
        # PRC-16, D7: un precio calculado guarda todo su cálculo; uno manual puede carecer
        # de costo o de regla (se admite un precio manual sin costo).
        CheckConstraint(
            "manual OR (costo_informado_id IS NOT NULL AND costo_referencia IS NOT NULL "
            "AND regla_margen_id IS NOT NULL AND tipo_margen IS NOT NULL "
            "AND valor_margen IS NOT NULL AND precio_calculado IS NOT NULL)",
            name="ck_precio_item__calculo_coherente",
        ),
        # PRC-10: un único precio por producto en cada versión.
        Index(
            "ux_precio_item__version_producto",
            "organizacion_id",
            "version_id",
            "producto_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    version_id: Mapped[UUID] = mapped_column(nullable=False)
    producto_id: Mapped[UUID] = mapped_column(nullable=False)
    # D1: las unidades de la presentación de referencia al calcular el precio; PRC-22 usa
    # estas, no las actuales del producto.
    unidades_referencia: Mapped[int] = mapped_column(Integer, nullable=False)
    costo_informado_id: Mapped[UUID | None] = mapped_column(nullable=True)
    costo_referencia: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    regla_margen_id: Mapped[UUID | None] = mapped_column(nullable=True)
    tipo_margen: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_margen: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    precio_calculado: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    precio_final: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False)
