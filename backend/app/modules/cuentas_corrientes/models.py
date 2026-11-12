"""Modelos SQLAlchemy de `cuentas_corrientes`: `CuentaMovimiento` y
`SaldoCuenta` (`docs/03-modelo-de-datos.md` §12; migración `e6f7a8b9c0d1`).

Mapean exactamente lo que crea la migración: `test_modelos_coinciden_con_
migracion.py` corre `alembic revision --autogenerate` y exige que no detecte
ninguna diferencia.

`id` de un movimiento se genera con UUIDv7 (`core/ids.py`). Los momentos son
`timestamptz`. Ninguna relación declara carga diferida implícita: este módulo no
declara `relationship()` alguna (`CLAUDE.md` §4), igual que `clientes/models.py`.

`cliente_id` y `proveedor_id` son columnas GENERADAS por PostgreSQL (`Computed`,
`design.md` D6-A): SQLAlchemy no las incluye en el `INSERT` y nadie las
escribe. Existen para que la base pueda declarar una FK compuesta a `cliente` y
otra a `proveedor` sobre una columna `entidad_id` que apunta a una u otra según
`cuenta_tipo`. Este módulo tampoco las lee: el código trabaja con `entidad_id`.

`cuenta_movimiento` es un libro de solo inserción (CC-06, INV-05): el usuario de
aplicación no tiene `UPDATE` ni `DELETE`. `saldo_cuenta` se actualiza: es una
materialización verificable del libro (`02` §7.2, ADR-015).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id

_CUENTAS_TIPO = "'CLIENTE','PROVEEDOR'"
_SENTIDOS = "'AUMENTA','REDUCE'"
_TIPOS_CLIENTE = "'SALDO_INICIAL','VENTA','ANULACION_VENTA','COBRANZA','ANULACION_COBRANZA'"
_TIPOS_PROVEEDOR = "'SALDO_INICIAL','COMPRA','ANULACION_COMPRA','PAGO','ANULACION_PAGO'"
_TIPOS = (
    "'SALDO_INICIAL','VENTA','ANULACION_VENTA','COBRANZA','ANULACION_COBRANZA',"
    "'COMPRA','ANULACION_COMPRA','PAGO','ANULACION_PAGO'"
)

_CLIENTE_GENERADO = "CASE WHEN cuenta_tipo = 'CLIENTE' THEN entidad_id END"
_PROVEEDOR_GENERADO = "CASE WHEN cuenta_tipo = 'PROVEEDOR' THEN entidad_id END"


class CuentaMovimiento(Base):
    """Un movimiento del libro único de clientes y proveedores (CC-01).

    NO tiene columna de saldo acumulado (CC-04): el saldo se calcula y se
    materializa en `SaldoCuenta`. `origen_tipo`/`origen_id` dicen qué operación
    lo originó; para un saldo inicial no hay una tabla a la que apuntar, así que
    `origen_id` es el `operation_id` (`design.md` D5). `dispositivo_id` es
    `NOT NULL` con FK compuesta a `dispositivo` (D14).
    """

    __tablename__ = "cuenta_movimiento"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_cuenta_movimiento"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cuenta_movimiento__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_cuenta_movimiento__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_cuenta_movimiento__dispositivo",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "cliente_id"],
            ["cliente.organizacion_id", "cliente.id"],
            name="fk_cuenta_movimiento__cliente",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_cuenta_movimiento__proveedor",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_cuenta_movimiento__org_id"),
        CheckConstraint("importe > 0", name="ck_cuenta_movimiento__importe_positivo"),
        CheckConstraint(f"sentido IN ({_SENTIDOS})", name="ck_cuenta_movimiento__sentido"),
        CheckConstraint(
            f"cuenta_tipo IN ({_CUENTAS_TIPO})", name="ck_cuenta_movimiento__cuenta_tipo"
        ),
        CheckConstraint(f"tipo IN ({_TIPOS})", name="ck_cuenta_movimiento__tipo"),
        CheckConstraint(
            f"(cuenta_tipo = 'CLIENTE' AND tipo IN ({_TIPOS_CLIENTE})) OR "
            f"(cuenta_tipo = 'PROVEEDOR' AND tipo IN ({_TIPOS_PROVEEDOR}))",
            name="ck_cuenta_movimiento__tipo_de_cuenta",
        ),
        Index(
            "ix_cuenta_movimiento__estado_de_cuenta",
            "organizacion_id",
            "cuenta_tipo",
            "entidad_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(default=nuevo_id)
    organizacion_id: Mapped[UUID]
    cuenta_tipo: Mapped[str] = mapped_column(Text)
    entidad_id: Mapped[UUID]
    cliente_id: Mapped[UUID | None] = mapped_column(Computed(_CLIENTE_GENERADO, persisted=True))
    proveedor_id: Mapped[UUID | None] = mapped_column(Computed(_PROVEEDOR_GENERADO, persisted=True))
    tipo: Mapped[str] = mapped_column(Text)
    sentido: Mapped[str] = mapped_column(Text)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    origen_tipo: Mapped[str] = mapped_column(Text)
    origen_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usuario_id: Mapped[UUID]
    dispositivo_id: Mapped[UUID]
    operation_id: Mapped[UUID]


class SaldoCuenta(Base):
    """Saldo materializado de una cuenta (`03` §12, `02` §7.2).

    Clave primaria compuesta `(organizacion_id, cuenta_tipo, entidad_id)` sin
    `id` (`design.md` D11-A). Es la fila que se bloquea al registrar un
    movimiento y al evaluar crédito (`02` §7.3, ADR-015). El libro es la
    verdad: esta fila es verificable contra él (INV-13).
    """

    __tablename__ = "saldo_cuenta"
    __table_args__ = (
        PrimaryKeyConstraint(
            "organizacion_id", "cuenta_tipo", "entidad_id", name="pk_saldo_cuenta"
        ),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_saldo_cuenta__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "cliente_id"],
            ["cliente.organizacion_id", "cliente.id"],
            name="fk_saldo_cuenta__cliente",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_saldo_cuenta__proveedor",
        ),
        CheckConstraint(f"cuenta_tipo IN ({_CUENTAS_TIPO})", name="ck_saldo_cuenta__cuenta_tipo"),
    )

    organizacion_id: Mapped[UUID]
    cuenta_tipo: Mapped[str] = mapped_column(Text)
    entidad_id: Mapped[UUID]
    cliente_id: Mapped[UUID | None] = mapped_column(Computed(_CLIENTE_GENERADO, persisted=True))
    proveedor_id: Mapped[UUID | None] = mapped_column(Computed(_PROVEEDOR_GENERADO, persisted=True))
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default=text("0"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
