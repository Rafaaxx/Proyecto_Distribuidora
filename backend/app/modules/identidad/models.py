"""Modelos SQLAlchemy de `identidad`: `organizacion` y
`configuracion_organizacion` (`docs/03-modelo-de-datos.md` §4; `03` §3).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`.
La carga de relaciones es explícita (`lazy="raise"`): nada se carga de forma
diferida implícita (`CLAUDE.md` §4).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.ids import nuevo_id


class Organizacion(Base):
    __tablename__ = "organizacion"
    __table_args__ = (UniqueConstraint("slug", name="ux_organizacion__slug"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    cuit: Mapped[str | None] = mapped_column(Text, nullable=True)
    moneda: Mapped[str] = mapped_column(Text, nullable=False)
    zona_horaria: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)

    configuracion: Mapped[ConfiguracionOrganizacion | None] = relationship(
        back_populates="organizacion", lazy="raise", uselist=False
    )


class ConfiguracionOrganizacion(Base):
    __tablename__ = "configuracion_organizacion"

    organizacion_id: Mapped[UUID] = mapped_column(ForeignKey("organizacion.id"), primary_key=True)
    modo_impositivo: Mapped[str] = mapped_column(Text, nullable=False)
    lista_precio_default_id: Mapped[UUID | None] = mapped_column(nullable=True)
    politica_credito_default: Mapped[str] = mapped_column(Text, nullable=False)
    tolerancia_offline_tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    tolerancia_offline_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    descuento_manual_habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    motivo_obligatorio_descuento: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    motivo_obligatorio_lista: Mapped[bool] = mapped_column(Boolean, nullable=False)
    redondeo_multiplo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    redondeo_direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    permite_consumidor_final: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cliente_consumidor_final_id: Mapped[UUID | None] = mapped_column(nullable=True)
    estado_facturacion_default: Mapped[str] = mapped_column(Text, nullable=False)
    modalidad_iva_default: Mapped[str | None] = mapped_column(Text, nullable=True)
    intentos_pin_max: Mapped[int] = mapped_column(Integer, nullable=False)
    app_version_minima: Mapped[str | None] = mapped_column(Text, nullable=True)
    desvio_reloj_max_segundos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)

    organizacion: Mapped[Organizacion] = relationship(back_populates="configuracion", lazy="raise")


class Permiso(Base):
    """Catálogo global de permisos (`03` §4, `03` §17, D7): sin
    `organizacion_id`, sincronizado por migración, no editable desde la
    aplicación."""

    __tablename__ = "permiso"

    codigo: Mapped[str] = mapped_column(Text, primary_key=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    modulo: Mapped[str] = mapped_column(Text, nullable=False)


class Rol(Base):
    __tablename__ = "rol"
    __table_args__ = (
        ForeignKeyConstraint(["organizacion_id"], ["organizacion.id"], name="fk_rol__organizacion"),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_rol__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_rol__org_id"),
        CheckConstraint(
            "tope_descuento >= 0 AND tope_descuento <= 1", name="ck_rol__tope_descuento"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    tope_descuento: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_usuario__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "rol_id"],
            ["rol.organizacion_id", "rol.id"],
            name="fk_usuario__rol",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_usuario__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_usuario__org_id"),
        UniqueConstraint("organizacion_id", "usuario", name="ux_usuario__org_usuario"),
        CheckConstraint("estado IN ('ACTIVO', 'INACTIVO')", name="ck_usuario__estado"),
        CheckConstraint(
            "tope_descuento_override IS NULL "
            "OR (tope_descuento_override >= 0 AND tope_descuento_override <= 1)",
            name="ck_usuario__tope_descuento_override",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario: Mapped[str] = mapped_column(Text, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rol_id: Mapped[UUID] = mapped_column(nullable=False)
    tope_descuento_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    pin_autorizacion_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    pin_autorizacion_sal: Mapped[str | None] = mapped_column(Text, nullable=True)
    pin_autorizacion_iteraciones: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class RolPermiso(Base):
    """Relación entre `rol` y `permiso` (`03` §4). La FK a `permiso` es
    simple a propósito: el catálogo es global (D7)."""

    __tablename__ = "rol_permiso"
    __table_args__ = (
        PrimaryKeyConstraint("organizacion_id", "rol_id", "permiso_codigo", name="pk_rol_permiso"),
        ForeignKeyConstraint(
            ["organizacion_id", "rol_id"],
            ["rol.organizacion_id", "rol.id"],
            name="fk_rol_permiso__rol",
        ),
        ForeignKeyConstraint(
            ["permiso_codigo"], ["permiso.codigo"], name="fk_rol_permiso__permiso"
        ),
    )

    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    rol_id: Mapped[UUID] = mapped_column(nullable=False)
    permiso_codigo: Mapped[str] = mapped_column(Text, nullable=False)


class Dispositivo(Base):
    """`id` lo genera el DISPOSITIVO, no el servidor (`03` §4, `02` §12.2):
    el cliente lo crea en su primer arranque y lo guarda en IndexedDB antes
    de que exista ninguna sesión. Por eso la clave primaria es compuesta
    (`organizacion_id`, `id`) en vez de `id` solo: el mismo identificador
    puede repetirse entre organizaciones (spec `dispositivos`, "Un
    identificador de dispositivo de otra organización no se reutiliza" — se
    registra un dispositivo NUEVO con el mismo `id` en la otra
    organización, lo que una PK de una sola columna no permitiría)."""

    __tablename__ = "dispositivo"
    __table_args__ = (
        PrimaryKeyConstraint("organizacion_id", "id", name="pk_dispositivo"),
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_dispositivo__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "revocado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_dispositivo__revocado_por",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_dispositivo__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_dispositivo__org_id"),
        UniqueConstraint("organizacion_id", "prefijo", name="ux_dispositivo__org_prefijo"),
        CheckConstraint("estado IN ('ACTIVO', 'REVOCADO')", name="ck_dispositivo__estado"),
    )

    id: Mapped[UUID] = mapped_column()
    organizacion_id: Mapped[UUID] = mapped_column()
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    prefijo: Mapped[str] = mapped_column(Text, nullable=False)
    ultimo_correlativo: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)


class SesionRefresh(Base):
    __tablename__ = "sesion_refresh"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_sesion_refresh__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_sesion_refresh__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_sesion_refresh__dispositivo",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_sesion_refresh__org_id"),
        Index("ix_sesion_refresh__token_hash", "token_hash", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(nullable=False)
    dispositivo_id: Mapped[UUID] = mapped_column(nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    familia_id: Mapped[UUID] = mapped_column(nullable=False)
    emitido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_revocacion: Mapped[str | None] = mapped_column(Text, nullable=True)


class Auditoria(Base):
    """Tabla de libro (`03` §2.5, INV-05): solo inserción, `app_runtime`
    sin `UPDATE`/`DELETE` (`ADR-020`, otorgado en la migración)."""

    __tablename__ = "auditoria"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_auditoria__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_auditoria__usuario",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_auditoria__dispositivo",
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "autorizador_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_auditoria__autorizador",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_auditoria__org_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    usuario_id: Mapped[UUID | None] = mapped_column(nullable=True)
    dispositivo_id: Mapped[UUID | None] = mapped_column(nullable=True)
    accion: Mapped[str] = mapped_column(Text, nullable=False)
    entidad: Mapped[str] = mapped_column(Text, nullable=False)
    entidad_id: Mapped[UUID | None] = mapped_column(nullable=True)
    antes: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    despues: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    motivo_id: Mapped[UUID | None] = mapped_column(nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    autorizador_id: Mapped[UUID | None] = mapped_column(nullable=True)
    # Nulable hasta el change 04 (tarea 2.6): nada lo genera todavia.
    operation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntentoLogin(Base):
    """Rate limit de login (`ADR-018`, grupo 11): tabla de solo inserción,
    sin `organizacion_id` a propósito (ver el docstring de la migración
    `e5f6a7b8c9d0` -- el límite por IP es transversal a organizaciones; el
    límite por usuario ya identifica una fila de `usuario`, que sí la
    tiene). `usuario_id` queda `NULL` cuando el nombre de usuario informado
    no corresponde a ningún usuario real."""

    __tablename__ = "intento_login"
    __table_args__ = (
        ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name="fk_intento_login__usuario"),
        Index("ix_intento_login__usuario_id_creado_en", "usuario_id", "creado_en"),
        Index("ix_intento_login__ip_creado_en", "ip", "creado_en"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    usuario_id: Mapped[UUID | None] = mapped_column(nullable=True)
    ip: Mapped[str] = mapped_column(Text, nullable=False)
    exito: Mapped[bool] = mapped_column(Boolean, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
