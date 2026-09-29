"""Modelos SQLAlchemy de `clientes`: `Cliente` (`docs/03-modelo-de-datos.md`
§10; migración `9c4e1f2a3b4d`).

`id` se genera con UUIDv7 (`core/ids.py`). Los momentos son `timestamptz`.
Ninguna relación declara carga diferida implícita: este módulo no declara
`relationship()` alguna (`CLAUDE.md` §4), igual que `proveedores/models.py`;
toda lectura pasa por consultas explícitas de `clientes/repository.py`.

Dos columnas que `03` §10 declara pero este change NO crea, y por qué:

- `condicion_iva`: `01` §16 y FAC-04 no definen su dominio; la agrega el
  change de facturación junto con su catálogo (`design.md` D5). Guardarla acá
  sería un dato que nadie puede escribir ni leer.
- La FK de `lista_precio_id`: la tabla `lista_precio` la crea el change 13
  (`design.md` D2), igual que `producto.proveedor_id` antes del 13 (ADR-025).
  La columna queda como `uuid` nullable sin validación de existencia.
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
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import nuevo_id

_ESTADOS_CLIENTE = "'ACTIVO','SUSPENDIDO','INACTIVO'"
_TIPOS_DOCUMENTO = "'CUIT','DNI'"
_POLITICAS_CREDITO = "'ADVERTIR','AUTORIZAR','BLOQUEAR'"
_TIPOS_TOLERANCIA = "'IMPORTE','PORCENTAJE'"
_ESTADOS_FACTURACION = "'NO_REQUIERE','PENDIENTE'"


class Cliente(Base):
    """Maestro de clientes de la organización (`03` §10, `design.md` D1 a D7).

    La fila NO guarda saldo: la cuenta corriente llega con el change 08
    (CC-04, `cuenta_movimiento` + `saldo_cuenta`). Los tres campos de crédito
    (`limite_credito`, `politica_credito`, `tolerancia_offline_*`) se guardan
    como datos y NO se resuelven acá: un nulo significa "hereda el de la
    organización" y la herencia se aplica cuando el crédito se evalúa, en el
    change 18b (CRE-01, CRE-03, CRE-06, `design.md` D8).
    """

    __tablename__ = "cliente"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cliente__organizacion"
        ),
        ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_cliente__actualizado_por",
        ),
        UniqueConstraint("organizacion_id", "id", name="ux_cliente__org_id"),
        # Los tres catálogos cerrados y la máquina de estados también están en
        # la base: un valor fuera de ellos no entra ni por un camino que se
        # salte el dominio (`01` §18, CLI-02, CLI-05, CRE-03, CRE-06, VTA-08).
        CheckConstraint(f"estado IN ({_ESTADOS_CLIENTE})", name="ck_cliente__estado"),
        CheckConstraint(
            f"documento_tipo IS NULL OR documento_tipo IN ({_TIPOS_DOCUMENTO})",
            name="ck_cliente__documento_tipo",
        ),
        # El documento es opcional "como pareja" (CLI-01, `design.md` D1): o
        # vienen los dos campos o ninguno.
        CheckConstraint(
            "(documento_tipo IS NULL AND documento_numero IS NULL) OR "
            "(documento_tipo IS NOT NULL AND documento_numero IS NOT NULL)",
            name="ck_cliente__documento_pareja",
        ),
        CheckConstraint(
            f"politica_credito IS NULL OR politica_credito IN ({_POLITICAS_CREDITO})",
            name="ck_cliente__politica_credito",
        ),
        CheckConstraint(
            f"tolerancia_offline_tipo IS NULL OR tolerancia_offline_tipo IN ({_TIPOS_TOLERANCIA})",
            name="ck_cliente__tolerancia_tipo",
        ),
        # Mismo criterio para la tolerancia (CRE-06, D6): tipo y valor van
        # juntos o no van.
        CheckConstraint(
            "(tolerancia_offline_tipo IS NULL AND tolerancia_offline_valor IS NULL) OR "
            "(tolerancia_offline_tipo IS NOT NULL AND tolerancia_offline_valor IS NOT NULL)",
            name="ck_cliente__tolerancia_pareja",
        ),
        CheckConstraint(
            "tolerancia_offline_valor IS NULL OR tolerancia_offline_valor >= 0",
            name="ck_cliente__tolerancia_valor",
        ),
        # Un límite negativo no es "sin control": CRE-01 reserva el nulo para
        # eso, así que el negativo es un dato inválido (INV-03).
        CheckConstraint(
            "limite_credito IS NULL OR limite_credito >= 0", name="ck_cliente__limite_credito"
        ),
        CheckConstraint(
            f"estado_facturacion_default IS NULL OR "
            f"estado_facturacion_default IN ({_ESTADOS_FACTURACION})",
            name="ck_cliente__estado_facturacion",
        ),
        # D1: unicidad en la base, no solo en el handler. `nombre` NO es único
        # (el mismo nombre puede repetir en la organización); código y documento
        # sí, con índice parcial porque ambos son opcionales.
        Index(
            "ux_cliente__codigo",
            "organizacion_id",
            "codigo",
            unique=True,
            postgresql_where=text("codigo IS NOT NULL"),
        ),
        Index(
            "ux_cliente__documento",
            "organizacion_id",
            "documento_tipo",
            "documento_numero",
            unique=True,
            postgresql_where=text("documento_numero IS NOT NULL"),
        ),
        # Índices de listado (`02` §11): el listado filtra por texto y por
        # estado y pagina por `nombre`.
        Index("ix_cliente__org_nombre", "organizacion_id", "nombre"),
        Index("ix_cliente__org_estado_nombre", "organizacion_id", "estado", "nombre"),
        Index("ix_cliente__org_documento", "organizacion_id", "documento_numero"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=nuevo_id)
    organizacion_id: Mapped[UUID] = mapped_column(nullable=False)
    codigo: Mapped[str | None] = mapped_column(Text, nullable=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    razon_social: Mapped[str | None] = mapped_column(Text, nullable=True)
    documento_tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    documento_numero: Mapped[str | None] = mapped_column(Text, nullable=True)
    direccion: Mapped[str] = mapped_column(Text, nullable=False)
    contacto: Mapped[str] = mapped_column(Text, nullable=False)
    telefono: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sin FK hasta el change 13 (D2); la escreve la importación del change 10.
    lista_precio_id: Mapped[UUID | None] = mapped_column(nullable=True)
    limite_credito: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    politica_credito: Mapped[str | None] = mapped_column(Text, nullable=True)
    tolerancia_offline_tipo: Mapped[str | None] = mapped_column(Text, nullable=True)
    tolerancia_offline_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    estado_facturacion_default: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_consumidor_final: Mapped[bool] = mapped_column(Boolean, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por_id: Mapped[UUID | None] = mapped_column(nullable=True)
