"""usuarios, roles y cartera: nombre de rol unico por organizacion y cliente.vendedor_id

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-10-28 18:00:00.000000

Change 20b (`design.md` D10, D13), una sola revision, sin cambios de privilegios (`app_runtime` ya
tiene `SELECT, INSERT, UPDATE` sobre `rol` y `cliente`, y nunca `DELETE`):

1. Verifica que no haya nombres de rol repetidos (sin distinguir mayusculas, activos o no) dentro
   de una organizacion. Si los hay, **aborta** con un mensaje que nombra la organizacion y el
   nombre, sin cambiar nada.
2. Crea `ux_rol__nombre`, unico sobre `(organizacion_id, lower(nombre))` (INV-02). Tabla chica y
   ya existente: no se usa un indice concurrente (mismo criterio que `f8a9b0c1d2e3`).
3. Agrega `cliente.vendedor_id uuid NULL` (la cartera, D13), con clave foranea compuesta
   `(organizacion_id, vendedor_id)` a `usuario (organizacion_id, id)` (INV-21) e indice
   `ix_cliente__vendedor`. Los clientes existentes quedan sin vendedor.

`downgrade` quita el indice, la clave foranea y la columna de cliente y el indice de rol; se
pierden solo las asignaciones de cartera hechas despues.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICE_ROL = "ux_rol__nombre"
INDICE_CLIENTE = "ix_cliente__vendedor"
FK_CLIENTE = "fk_cliente__vendedor"


def upgrade() -> None:
    conexion = op.get_bind()

    repetidos = conexion.execute(
        sa.text(
            "SELECT organizacion_id, min(nombre) AS nombre, count(*) AS cantidad "
            "FROM rol GROUP BY organizacion_id, lower(nombre) HAVING count(*) > 1 "
            "ORDER BY organizacion_id, lower(nombre)"
        )
    ).all()
    if repetidos:
        detalle = "; ".join(
            f"organizacion {fila.organizacion_id}: {fila.nombre!r} ({fila.cantidad} veces)"
            for fila in repetidos
        )
        raise RuntimeError(
            f"No se puede crear {INDICE_ROL}: hay roles con el mismo nombre (sin distinguir "
            f"mayusculas) en una misma organizacion. {detalle}. Renombrar esos roles a mano y "
            "volver a correr la migracion."
        )

    op.create_index(
        INDICE_ROL,
        "rol",
        ["organizacion_id", sa.text("lower(nombre)")],
        unique=True,
    )

    op.add_column("cliente", sa.Column("vendedor_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        FK_CLIENTE,
        "cliente",
        "usuario",
        ["organizacion_id", "vendedor_id"],
        ["organizacion_id", "id"],
    )
    op.create_index(INDICE_CLIENTE, "cliente", ["organizacion_id", "vendedor_id"])


def downgrade() -> None:
    op.drop_index(INDICE_CLIENTE, table_name="cliente")
    op.drop_constraint(FK_CLIENTE, "cliente", type_="foreignkey")
    op.drop_column("cliente", "vendedor_id")
    op.drop_index(INDICE_ROL, table_name="rol")
