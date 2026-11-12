"""nota_venta_configuracion: parámetros de la nota de venta

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-10-27 12:00:00.000000

Change 20 (nota-de-venta, D10, VTA-13): `configuracion_organizacion` suma
`nota_venta_muestra_saldo` (boolean no nulo, por defecto falso), `nota_venta_domicilio` y
`nota_venta_telefono` (texto nulable, con CHECK de longitud y de no vacío). Las organizaciones
existentes quedan con falso y nulos. `app_runtime` ya tiene UPDATE sobre la tabla (sin cambio de
privilegios). Downgrade: quita las tres columnas (se pierden solo los textos cargados).
"""

import sqlalchemy as sa

from alembic import op

revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

TABLA = "configuracion_organizacion"


def upgrade():
    op.add_column(
        TABLA,
        sa.Column(
            "nota_venta_muestra_saldo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(TABLA, sa.Column("nota_venta_domicilio", sa.Text(), nullable=True))
    op.add_column(TABLA, sa.Column("nota_venta_telefono", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_configuracion_organizacion__nota_venta_domicilio",
        TABLA,
        "nota_venta_domicilio IS NULL OR (char_length(nota_venta_domicilio) BETWEEN 1 AND 200)",
    )
    op.create_check_constraint(
        "ck_configuracion_organizacion__nota_venta_telefono",
        TABLA,
        "nota_venta_telefono IS NULL OR (char_length(nota_venta_telefono) BETWEEN 1 AND 50)",
    )


def downgrade():
    op.drop_constraint("ck_configuracion_organizacion__nota_venta_telefono", TABLA, type_="check")
    op.drop_constraint("ck_configuracion_organizacion__nota_venta_domicilio", TABLA, type_="check")
    op.drop_column(TABLA, "nota_venta_telefono")
    op.drop_column(TABLA, "nota_venta_domicilio")
    op.drop_column(TABLA, "nota_venta_muestra_saldo")
