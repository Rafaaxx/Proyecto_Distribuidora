"""Modelos SQLAlchemy de `sync`: `comando`, `comando_cuarentena`, `observacion` y
`comando_rechazado` (`docs/03-modelo-de-datos.md` §13; ADR-012; change 04, grupo 2; change 25).

Mapean exactamente lo que crea `alembic/versions/f6a7b8c9d0e1_...py`: la
prueba `tests/integration/test_modelos_coinciden_con_migracion.py` corre
`alembic revision --autogenerate` y exige que no detecte ninguna diferencia
entre estos modelos y el esquema real.

`comando.jornada_id` tiene FK compuesta a `jornada` desde el change 15 (migración
`a4b5c6d7e8f9`, `design.md` D11). El resto del módulo (`api.py`, `schemas.py`,
`repository.py`, `service.py`) llega en el grupo 8: acá solo se declara la
forma de las tablas para que el esquema y los modelos no diverjan.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# SYN-07 (`docs/01-dominio.md` §17): mismo catálogo que la migración.
CODIGOS_OBSERVACION = (
    "STOCK_NEGATIVO",
    "EXCESO_CREDITO_ADVERTIDO",
    "EXCESO_CREDITO_AUTORIZADO_OFFLINE",
    "EXCESO_CREDITO_DETECTADO_SYNC",
    "LISTA_NO_VIGENTE",
    "DESCUENTO_DIFIERE",
    "CLIENTE_NO_HABILITADO",
    "PERMISO_REVOCADO",
    "JORNADA_LIBERADA",
    "JORNADA_RENDIDA",
    "ANULACION_COMPRA_SIN_RECALCULO",
    "MEDIO_INACTIVO",
    "REFERENCIA_FALTANTE",
    "VENTA_SIN_COSTO",
    "CONSUMIDOR_FINAL_CON_DEUDA",
    "UBICACION_TOMADA_AL_SINCRONIZAR",
    "AUTORIZACION_OFFLINE",
    "PRODUCTO_DESACTIVADO",
)


class Comando(Base):
    """Reserva de idempotencia y estado final de cada operación (INV-06,
    `02` §6.2, §6.3). Tabla de libro (INV-05): `app_runtime` tiene `UPDATE`
    (estado intermedio -> final) pero nunca `DELETE`."""

    __tablename__ = "comando"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_comando"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_comando__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_comando__dispositivo",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "jornada_id"],
            ["jornada.organizacion_id", "jornada.id"],
            name="fk_comando__jornada",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_comando__org_id"),
        UniqueConstraint("organizacion_id", "operation_id", name="ux_comando__org_operation_id"),
        CheckConstraint("modo IN ('ONLINE', 'OFFLINE')", name="ck_comando__modo"),
        CheckConstraint(
            "estado IN ('PROCESANDO', 'ACEPTADO', 'ACEPTADO_CON_OBSERVACIONES', 'RECHAZADO')",
            name="ck_comando__estado",
        ),
        Index(
            "ix_comando__org_dispositivo_secuencia",
            "organizacion_id",
            "dispositivo_id",
            "secuencia",
        ),
    )

    id: Mapped[UUID] = mapped_column()
    organizacion_id: Mapped[UUID] = mapped_column()
    operation_id: Mapped[UUID] = mapped_column()
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    modo: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column()
    dispositivo_id: Mapped[UUID] = mapped_column()
    # FK compuesta `(organizacion_id, jornada_id)` a `jornada` desde el change 15
    # (`design.md` D11); el bus valida antes que la jornada exista (D12).
    jornada_id: Mapped[UUID | None] = mapped_column(nullable=True)
    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    huella: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    resultado: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_codigo: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ComandoCuarentena(Base):
    """SYN-06: comandos de dispositivos revocados. Tabla de libro (INV-05),
    sin `DELETE` para `app_runtime`. `UNIQUE (organizacion_id,
    operation_id)`: el reenvío del mismo comando no duplica el registro."""

    __tablename__ = "comando_cuarentena"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_comando_cuarentena"),
        ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_comando_cuarentena__organizacion",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_comando_cuarentena__dispositivo",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando_cuarentena__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "revisado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando_cuarentena__revisado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_comando_cuarentena__org_id"),
        UniqueConstraint(
            "organizacion_id", "operation_id", name="ux_comando_cuarentena__org_operation_id"
        ),
        CheckConstraint(
            "(revisado_en IS NULL AND revisado_por_id IS NULL AND comentario IS NULL "
            "AND vinculo_tipo IS NULL AND vinculo_id IS NULL) "
            "OR (revisado_en IS NOT NULL AND revisado_por_id IS NOT NULL "
            "AND comentario IS NOT NULL)",
            name="ck_comando_cuarentena__revision_coherente",
        ),
        CheckConstraint(
            "comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500",
            name="ck_comando_cuarentena__comentario",
        ),
        CheckConstraint(
            "(vinculo_tipo IS NULL) = (vinculo_id IS NULL) "
            "AND (vinculo_tipo IS NULL OR vinculo_tipo IN ('VENTA', 'COBRANZA'))",
            name="ck_comando_cuarentena__vinculo",
        ),
    )

    id: Mapped[UUID] = mapped_column()
    organizacion_id: Mapped[UUID] = mapped_column()
    dispositivo_id: Mapped[UUID] = mapped_column()
    usuario_id: Mapped[UUID] = mapped_column()
    operation_id: Mapped[UUID] = mapped_column()
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    contenido: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revisado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    # Change 25 (D7): la revisión lleva comentario y, si la operación ocurrió, su vínculo
    # (`VENTA` o `COBRANZA`; sin FK: es polimórfico).
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    vinculo_tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    vinculo_id: Mapped[UUID | None] = mapped_column(nullable=True)


class Observacion(Base):
    """SYN-04, SYN-07. Tabla de libro (INV-05): `app_runtime` tiene
    `UPDATE` solo de las columnas de la resolución (change 25, D2) y nunca
    `DELETE`. Índice parcial de pendientes por organización y código."""

    __tablename__ = "observacion"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_observacion"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_observacion__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "comando_id"],
            ["comando.organizacion_id", "comando.id"],
            name="fk_observacion__comando",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "resuelto_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_observacion__resuelto_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_observacion__org_id"),
        CheckConstraint("estado IN ('PENDIENTE', 'RESUELTA')", name="ck_observacion__estado"),
        CheckConstraint(
            "codigo IN (" + ", ".join(f"'{codigo}'" for codigo in CODIGOS_OBSERVACION) + ")",
            name="ck_observacion__codigo",
        ),
        CheckConstraint(
            "(estado = 'PENDIENTE' AND resuelto_por_id IS NULL AND resuelto_en IS NULL "
            "AND comentario IS NULL) "
            "OR (estado = 'RESUELTA' AND resuelto_por_id IS NOT NULL "
            "AND resuelto_en IS NOT NULL AND comentario IS NOT NULL)",
            name="ck_observacion__resolucion_coherente",
        ),
        CheckConstraint(
            "comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500",
            name="ck_observacion__comentario",
        ),
        Index(
            "ix_observacion__org_codigo_pendiente",
            "organizacion_id",
            "codigo",
            postgresql_where=text("estado = 'PENDIENTE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column()
    organizacion_id: Mapped[UUID] = mapped_column()
    comando_id: Mapped[UUID] = mapped_column()
    operacion_tipo: Mapped[str] = mapped_column(Text, nullable=False)
    operacion_id: Mapped[UUID] = mapped_column()
    codigo: Mapped[str] = mapped_column(Text, nullable=False)
    detalle: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    resuelto_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)


class ComandoRechazado(Base):
    """SYN-06, SYN-09 (change 25, D6): lo que envió el teléfono en un comando `OFFLINE`
    rechazado, para que administración lo vea. Tabla de libro (INV-05): `app_runtime` tiene
    `SELECT`, `INSERT` y `UPDATE` solo de las columnas de la resolución, nunca `DELETE`.
    `UNIQUE (organizacion_id, operation_id)`: el reenvío no lo duplica. `jornada_id` es nulo si
    la jornada del sobre no existe en la organización. `vinculo_*` no tiene FK (polimórfico)."""

    __tablename__ = "comando_rechazado"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_comando_rechazado"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_comando_rechazado__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando_rechazado__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_comando_rechazado__dispositivo",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "jornada_id"],
            ["jornada.organizacion_id", "jornada.id"],
            name="fk_comando_rechazado__jornada",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "resuelto_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando_rechazado__resuelto_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_comando_rechazado__org_id"),
        UniqueConstraint(
            "organizacion_id", "operation_id", name="ux_comando_rechazado__org_operation_id"
        ),
        CheckConstraint("modo IN ('ONLINE', 'OFFLINE')", name="ck_comando_rechazado__modo"),
        CheckConstraint("estado IN ('PENDIENTE', 'RESUELTO')", name="ck_comando_rechazado__estado"),
        CheckConstraint(
            "(estado = 'PENDIENTE' AND resuelto_por_id IS NULL AND resuelto_en IS NULL "
            "AND comentario IS NULL AND vinculo_tipo IS NULL AND vinculo_id IS NULL) "
            "OR (estado = 'RESUELTO' AND resuelto_por_id IS NOT NULL "
            "AND resuelto_en IS NOT NULL AND comentario IS NOT NULL)",
            name="ck_comando_rechazado__resolucion_coherente",
        ),
        CheckConstraint(
            "comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500",
            name="ck_comando_rechazado__comentario",
        ),
        CheckConstraint(
            "(vinculo_tipo IS NULL) = (vinculo_id IS NULL) "
            "AND (vinculo_tipo IS NULL OR vinculo_tipo IN ('VENTA', 'COBRANZA'))",
            name="ck_comando_rechazado__vinculo",
        ),
        Index(
            "ix_comando_rechazado__org_jornada_pendiente",
            "organizacion_id",
            "jornada_id",
            postgresql_where=text("estado = 'PENDIENTE'"),
        ),
    )

    id: Mapped[UUID] = mapped_column()
    organizacion_id: Mapped[UUID] = mapped_column()
    operation_id: Mapped[UUID] = mapped_column()
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    modo: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_id: Mapped[UUID] = mapped_column()
    dispositivo_id: Mapped[UUID] = mapped_column()
    jornada_id: Mapped[UUID | None] = mapped_column(nullable=True)
    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    app_version: Mapped[str] = mapped_column(Text, nullable=False)
    contenido: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    error_codigo: Mapped[str] = mapped_column(Text, nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    resuelto_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    vinculo_tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    vinculo_id: Mapped[UUID | None] = mapped_column(nullable=True)
