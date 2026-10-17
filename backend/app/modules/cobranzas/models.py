"""Modelos SQLAlchemy de `cobranzas`: `Cobranza`, `CobranzaMedio` y `CobranzaAnulacion`
(`docs/03-modelo-de-datos.md` §12; migración `d7e8f9a0b1c2`, `design.md` D16).

`id` se genera con UUIDv7 (`core/ids.py`); las cobranzas lo reciben de quien las origina (D2).
Los momentos son `timestamptz`. Ninguna relación declara carga diferida implícita: este módulo
no declara `relationship()` alguna (`CLAUDE.md` §4); toda lectura pasa por consultas explícitas
de `cobranzas/repository.py`.
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


class Cobranza(Base):
    """Cobranza a un cliente (COB-01). Nace `CONFIRMADA` y solo cambia su `estado` a `ANULADA`
    (TR-06, INV-05: `app_runtime` tiene `UPDATE` solo de esa columna). `venta_id` queda nulable
    y sin FK hasta el change 18a (D16)."""

    __tablename__ = "cobranza"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cobranza__organizacion"
        ),
        _fk("cobranza", "cliente", "cliente_id", "cliente"),
        _fk("cobranza", "jornada", "jornada_id", "jornada"),
        _fk("cobranza", "usuario", "usuario_id", "usuario"),
        _fk("cobranza", "dispositivo", "dispositivo_id", "dispositivo"),
        UniqueConstraint("organizacion_id", "id", name="ux_cobranza__org_id"),
        CheckConstraint("importe > 0", name="ck_cobranza__importe"),
        CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_cobranza__estado"),
        CheckConstraint("origen IN ('VENTA','INDEPENDIENTE')", name="ck_cobranza__origen"),
        CheckConstraint(
            "(origen = 'VENTA' AND venta_id IS NOT NULL) "
            "OR (origen = 'INDEPENDIENTE' AND venta_id IS NULL)",
            name="ck_cobranza__origen_venta",
        ),
        Index(
            "ix_cobranza__occurred_at",
            "organizacion_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_cobranza__cliente",
            "organizacion_id",
            "cliente_id",
            text("occurred_at DESC"),
            text("id DESC"),
        ),
        Index("ix_cobranza__jornada", "organizacion_id", "jornada_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(nullable=False)
    venta_id: Mapped[UUID | None] = mapped_column(nullable=True)
    origen: Mapped[str] = mapped_column(Text, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    jornada_id: Mapped[UUID | None] = mapped_column(nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    """D2: opcional e inmutable: no entra en el `GRANT UPDATE` de `app_runtime`."""
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    dispositivo_id: Mapped[UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CobranzaMedio(Base):
    """Un medio de una cobranza (COB-02, INV-08: la suma de medios es el importe de la cobranza,
    validada en el dominio). De solo inserción. `orden` es la posición de la línea desde 0, la que
    citan los detalles de `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` (D13)."""

    __tablename__ = "cobranza_medio"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cobranza_medio__organizacion"
        ),
        _fk("cobranza_medio", "cobranza", "cobranza_id", "cobranza"),
        _fk("cobranza_medio", "medio_pago", "medio_pago_id", "medio_pago"),
        UniqueConstraint("organizacion_id", "id", name="ux_cobranza_medio__org_id"),
        UniqueConstraint(
            "organizacion_id", "cobranza_id", "orden", name="ux_cobranza_medio__cobranza_orden"
        ),
        CheckConstraint("importe > 0", name="ck_cobranza_medio__importe"),
        CheckConstraint("orden >= 0", name="ck_cobranza_medio__orden"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    cobranza_id: Mapped[UUID] = mapped_column(nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    medio_pago_id: Mapped[UUID] = mapped_column(nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    referencia: Mapped[str | None] = mapped_column(Text, nullable=True)


class CobranzaAnulacion(Base):
    """La anulación de una cobranza (COB-05). `cobranza_id` único: la base impide anular dos
    veces (D16). De solo inserción."""

    __tablename__ = "cobranza_anulacion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cobranza_anulacion__organizacion"
        ),
        _fk("cobranza_anulacion", "cobranza", "cobranza_id", "cobranza"),
        _fk("cobranza_anulacion", "motivo", "motivo_id", "motivo"),
        _fk("cobranza_anulacion", "usuario", "usuario_id", "usuario"),
        _fk("cobranza_anulacion", "dispositivo", "dispositivo_id", "dispositivo"),
        UniqueConstraint("organizacion_id", "id", name="ux_cobranza_anulacion__org_id"),
        UniqueConstraint("organizacion_id", "cobranza_id", name="ux_cobranza_anulacion__cobranza"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    cobranza_id: Mapped[UUID] = mapped_column(nullable=False)
    motivo_id: Mapped[UUID] = mapped_column(nullable=False)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    dispositivo_id: Mapped[UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
