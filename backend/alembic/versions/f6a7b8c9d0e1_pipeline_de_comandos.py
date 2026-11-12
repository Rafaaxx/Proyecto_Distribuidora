"""pipeline de comandos: comando, comando_cuarentena, observacion, origen de auditoria

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-21 00:00:00.000000

Change 04 (grupo 2, `design.md`, `03` §13, ADR-012): crea las tres tablas del
bus de comandos y extiende `auditoria` con la columna `origen`.

- `comando`: reserva de idempotencia (INV-06, `UNIQUE (organizacion_id,
  operation_id)`) y registro del estado final de cada operación. `id` y
  `organizacion_id` llevan además `UNIQUE (organizacion_id, id)` (INV-02).
  `jornada_id` se crea nulable y **sin** FK: la tabla `jornada` no existe
  todavía (llega en el change 15, que hereda esta deuda explícita -- tarea
  15.1 de este `tasks.md`, mismo patrón que el change 02 con sus dos FK
  pendientes y el change 03 con las tres escrituras de maestros). La
  obligatoriedad de `jornada_id` para comandos de ruta (`02` §6.2) se valida
  en el esquema Pydantic del tipo de comando, no en la columna: depende del
  tipo, no de la tabla.
- `comando_cuarentena`: SYN-06, comandos de dispositivos revocados. `UNIQUE
  (organizacion_id, operation_id)` para que el reenvío del mismo comando no
  duplique el registro de cuarentena (tarea 8.8).
- `observacion`: SYN-04, SYN-07. `codigo` restringido al catálogo de SYN-07
  (`docs/01-dominio.md` §17). Índice parcial `(organizacion_id, codigo)
  WHERE estado = 'PENDIENTE'` para la consulta de pendientes (tarea 9.6).
- `auditoria.origen` (D2, extensión de ADR-012): `COMANDO` | `SISTEMA`, con
  restricción de verificación `operation_id IS NOT NULL <=> origen =
  'COMANDO'`. Los registros existentes (todos del change 03, ninguno
  originado en un comando porque el bus no existía) se rellenan con
  `SISTEMA` en esta misma revisión, antes de crear la restricción -- si se
  creara la restricción primero, el `UPDATE` de relleno no haría falta
  (`origen` nace con `server_default` y por eso ya cumple), pero se ordena
  así para que el `UPDATE` sea explícito y auditable en el diff, no un
  efecto secundario del `server_default`.

Otorga en la misma revisión (`design.md`, Migration Plan; ADR-020) los
`GRANT` de `app_runtime`: `comando`, `comando_cuarentena` y `observacion`
reciben `SELECT, INSERT, UPDATE` y **ningún** `DELETE` -- las tres son
tablas de libro (INV-05): `comando` pasa de estado intermedio a final con
`UPDATE`, nunca se borra; `comando_cuarentena` y `observacion` tampoco (la
resolución de `observacion` es un `UPDATE` del change 25, nunca un borrado).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

# SYN-07 (`docs/01-dominio.md` §17): catálogo cerrado de códigos de
# observación de la etapa 1. `OBSERVACION_RESOLVER` (change 25) no agrega
# códigos nuevos, solo resuelve los existentes.
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
    "ANULACION_COMPRA_SIN_RECALCULO",
)


def upgrade() -> None:
    """Upgrade schema."""
    # --- comando (INV-06, `02` §6.2, §6.3) --------------------------------
    op.create_table(
        "comando",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("modo", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        # Sin FK todavia: `jornada` no existe hasta el change 15 (ver
        # docstring del modulo; tarea 15.1 anota esta deuda para ese change).
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("secuencia", sa.Integer(), nullable=False),
        sa.Column("huella", sa.Text(), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("resultado", JSONB(), nullable=True),
        sa.Column("error_codigo", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_comando"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_comando__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_comando__dispositivo",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_comando__org_id"),
        sa.UniqueConstraint("organizacion_id", "operation_id", name="ux_comando__org_operation_id"),
        sa.CheckConstraint("modo IN ('ONLINE', 'OFFLINE')", name="ck_comando__modo"),
        sa.CheckConstraint(
            "estado IN ('PROCESANDO', 'ACEPTADO', 'ACEPTADO_CON_OBSERVACIONES', 'RECHAZADO')",
            name="ck_comando__estado",
        ),
    )
    op.create_index(
        "ix_comando__org_dispositivo_secuencia",
        "comando",
        ["organizacion_id", "dispositivo_id", "secuencia"],
    )

    # --- comando_cuarentena (SYN-06) --------------------------------------
    op.create_table(
        "comando_cuarentena",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("contenido", JSONB(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revisado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revisado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_comando_cuarentena"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_comando_cuarentena__organizacion",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_comando_cuarentena__dispositivo",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando_cuarentena__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "revisado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_comando_cuarentena__revisado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_comando_cuarentena__org_id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "operation_id",
            name="ux_comando_cuarentena__org_operation_id",
        ),
    )

    # --- observacion (SYN-04, SYN-07) -------------------------------------
    op.create_table(
        "observacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("comando_id", sa.Uuid(), nullable=False),
        sa.Column("operacion_tipo", sa.Text(), nullable=False),
        sa.Column("operacion_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("detalle", JSONB(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("resuelto_por_id", sa.Uuid(), nullable=True),
        sa.Column("resuelto_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_observacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_observacion__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "comando_id"],
            ["comando.organizacion_id", "comando.id"],
            name="fk_observacion__comando",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "resuelto_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_observacion__resuelto_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_observacion__org_id"),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'RESUELTA')", name="ck_observacion__estado"),
        sa.CheckConstraint(
            "codigo IN (" + ", ".join(f"'{codigo}'" for codigo in CODIGOS_OBSERVACION) + ")",
            name="ck_observacion__codigo",
        ),
    )
    op.create_index(
        "ix_observacion__org_codigo_pendiente",
        "observacion",
        ["organizacion_id", "codigo"],
        unique=False,
        postgresql_where=sa.text("estado = 'PENDIENTE'"),
    )

    # --- auditoria.origen (D2, extensión de ADR-012) ----------------------
    op.add_column(
        "auditoria",
        sa.Column("origen", sa.Text(), nullable=False, server_default=sa.text("'SISTEMA'")),
    )
    # Relleno explícito de los registros existentes (ver docstring: el
    # `server_default` ya los deja en 'SISTEMA', pero se ejecuta el UPDATE
    # para que quede auditable en el diff de la migración, no escondido
    # detrás del default de columna).
    op.execute("UPDATE auditoria SET origen = 'SISTEMA' WHERE origen IS NULL")
    # El `server_default` se deja puesto (a propósito, no es un olvido): el
    # modelo ORM `Auditoria` de `identidad/models.py` todavía no mapea
    # `origen` ni lo escribe `identidad/repository.py::crear_auditoria` --
    # eso es la tarea 10.5 (grupo 10, fuera del alcance de esta sesión, que
    # además hace que el bus declare `origen='COMANDO'` explícitamente). Sin
    # el default, cada INSERT existente de auditoría (el login del change
    # 03) violaría el NOT NULL hasta que 10.5 lo actualice. Con el default,
    # el login sigue auditándose sin cambios de código hasta ese momento, y
    # la restricción de verificación de abajo sigue exigiendo la relación
    # correcta entre `origen` y `operation_id` para todo registro, tenga o
    # no el valor puesto por el default.
    op.create_check_constraint(
        "ck_auditoria__origen",
        "auditoria",
        "origen IN ('COMANDO', 'SISTEMA')",
    )
    op.create_check_constraint(
        "ck_auditoria__operation_id_segun_origen",
        "auditoria",
        "(operation_id IS NOT NULL) = (origen = 'COMANDO')",
    )

    # --- Permisos de app_runtime (design.md, Migration Plan; ADR-020) -----
    for tabla in ("comando", "comando_cuarentena", "observacion"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabla} TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    for tabla in ("comando", "comando_cuarentena", "observacion"):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE ON {tabla} FROM {ROL_RUNTIME}")

    op.drop_constraint("ck_auditoria__operation_id_segun_origen", "auditoria", type_="check")
    op.drop_constraint("ck_auditoria__origen", "auditoria", type_="check")
    op.drop_column("auditoria", "origen")

    op.drop_index("ix_observacion__org_codigo_pendiente", table_name="observacion")
    op.drop_table("observacion")
    op.drop_table("comando_cuarentena")
    op.drop_index("ix_comando__org_dispositivo_secuencia", table_name="comando")
    op.drop_table("comando")
