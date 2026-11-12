"""medios de pago administrables: nombre unico por organizacion y referencia por defecto

Revision ID: f8a9b0c1d2e3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-17 00:00:00.000000

Change 17b (`design.md` D3, D5-A), una sola revision, sin columnas nuevas ni cambios de
privilegios (`app_runtime` ya tiene `SELECT, INSERT, UPDATE` y nunca `DELETE` sobre `medio_pago`):

1. Verifica que no haya nombres repetidos (sin distinguir mayusculas) dentro de una organizacion.
   Si los hay, **aborta** con un mensaje que nombra la organizacion y el nombre, sin cambiar nada
   (la siembra no los tiene; un dato cargado a mano si podria).
2. Crea `ux_medio_pago__nombre`, unico sobre `(organizacion_id, lower(nombre))` (INV-02). Tabla
   chica y ya existente: no se usa un indice concurrente (mismo criterio que `c0d1e2f3a4b5`).
3. Pone `requiere_referencia = true` en los medios llamados "Transferencia", "Cheque" o "Tarjeta"
   (sin distinguir mayusculas) de toda organizacion existente. Idempotente. Es seguro porque hasta
   este change nadie pudo cambiar esa marca (no habia comando).

`downgrade` borra el indice y **no** revierte las marcas de referencia (D5-A): despues del 17b el
valor pudo haberlo elegido una persona. La asercion esta escrita en
`backend/tests/integration/test_medios_pago_migracion.py`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICE = "ux_medio_pago__nombre"
NOMBRES_CON_REFERENCIA = ("transferencia", "cheque", "tarjeta")


def upgrade() -> None:
    conexion = op.get_bind()

    repetidos = conexion.execute(
        sa.text(
            "SELECT organizacion_id, min(nombre) AS nombre, count(*) AS cantidad "
            "FROM medio_pago GROUP BY organizacion_id, lower(nombre) HAVING count(*) > 1 "
            "ORDER BY organizacion_id, lower(nombre)"
        )
    ).all()
    if repetidos:
        detalle = "; ".join(
            f"organizacion {fila.organizacion_id}: {fila.nombre!r} ({fila.cantidad} veces)"
            for fila in repetidos
        )
        raise RuntimeError(
            "No se puede crear ux_medio_pago__nombre: hay medios de pago con el mismo nombre "
            f"(sin distinguir mayusculas) en una misma organizacion. {detalle}. Renombrar o "
            "unificar a mano esos medios y volver a correr la migracion."
        )

    op.create_index(
        INDICE,
        "medio_pago",
        ["organizacion_id", sa.text("lower(nombre)")],
        unique=True,
    )

    conexion.execute(
        sa.text(
            "UPDATE medio_pago SET requiere_referencia = true "
            "WHERE lower(nombre) IN :nombres AND requiere_referencia = false"
        ).bindparams(sa.bindparam("nombres", expanding=True)),
        {"nombres": list(NOMBRES_CON_REFERENCIA)},
    )


def downgrade() -> None:
    # D5-A: las marcas de referencia NO se revierten (pudo elegirlas una persona).
    op.drop_index(INDICE, table_name="medio_pago")
