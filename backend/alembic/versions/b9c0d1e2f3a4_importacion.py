"""importacion: registro de las importaciones de planillas

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-01 00:00:00.000000

Change 10 (`design.md` Migration Plan, D9, D14): crea `importacion`
(`docs/03-modelo-de-datos.md` §13).

- Columnas de `03` §13 (`tipo`, `archivo_nombre`, `estado`, `filas_total`,
  `filas_ok`, `filas_error`, `errores jsonb`) MÁS las columnas de operación de
  `03` §2.3 (`operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`,
  `registered_at`), con FK compuestas a `usuario` y `dispositivo` (D14).
- `ck_importacion__tipo`: catálogo completo de `03` §13 más `COSTOS` (D9). `PRECIOS`
  figura aunque no tenga importador hasta el change 13: es el precedente de
  declarar el catálogo completo de la etapa (ADR-034 punto 7, D13 del change 09).
- `ck_importacion__estado`: solo `CONFIRMADA`. Con el modo todo o nada (D1) solo se
  guardan las importaciones exitosas; `filas_error` = 0 y `errores` = `[]` quedan
  como columnas listas para un modo parcial futuro, que agregaría su estado con
  su propia migración.
- `ck_importacion__filas_no_negativas`: las tres cantidades son `integer >= 0`
  (INV-04).
- `UNIQUE (organizacion_id, id)`: sin ella ninguna tabla puede referenciar una
  importación con FK compuesta (INV-02).
- `ix_importacion__historial` `(organizacion_id, registered_at DESC, id DESC)`: el
  historial de la organización, lo más reciente primero, con `id` de desempate
  para un cursor estable.
- `GRANT SELECT, INSERT`: `app_runtime` no recibe `UPDATE` ni `DELETE` (D14-A,
  INV-05, ADR-020).

Tabla nueva y vacía: no se usan índices concurrentes (mismo criterio que
`a8b9c0d1e2f3`). No toca tablas existentes ni datos. `downgrade` elimina la tabla
con sus permisos.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: str | Sequence[str] | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_TIPOS = (
    "'PRODUCTOS','CLIENTES','PROVEEDORES','PRECIOS','COSTOS','STOCK_INICIAL','SALDOS_INICIALES'"
)
_ESTADOS = "'CONFIRMADA'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "importacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("archivo_nombre", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("filas_total", sa.Integer(), nullable=False),
        sa.Column("filas_ok", sa.Integer(), nullable=False),
        sa.Column("filas_error", sa.Integer(), nullable=False),
        sa.Column(
            "errores",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_importacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_importacion__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_importacion__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_importacion__dispositivo",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_importacion__org_id"),
        sa.CheckConstraint(f"tipo IN ({_TIPOS})", name="ck_importacion__tipo"),
        sa.CheckConstraint(f"estado IN ({_ESTADOS})", name="ck_importacion__estado"),
        sa.CheckConstraint(
            "filas_total >= 0 AND filas_ok >= 0 AND filas_error >= 0",
            name="ck_importacion__filas_no_negativas",
        ),
    )
    op.create_index(
        "ix_importacion__historial",
        "importacion",
        ["organizacion_id", sa.text("registered_at DESC"), sa.text("id DESC")],
    )

    # Registro de solo inserción (D14-A, INV-05, ADR-020).
    op.execute(f"GRANT SELECT, INSERT ON importacion TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"REVOKE SELECT, INSERT ON importacion FROM {ROL_RUNTIME}")
    op.drop_index("ix_importacion__historial", table_name="importacion")
    op.drop_table("importacion")
