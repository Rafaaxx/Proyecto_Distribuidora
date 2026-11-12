"""catalogos de configuracion: unicidad de motivos y alicuotas, rango del valor y redondeo coherente

Revision ID: a9c1e3f5b7d2
Revises: f1a2b3c4d5e6
Create Date: 2026-10-30 00:00:00.000000

Change 20c (`design.md` D3, D7, D10), una sola revision, sin columnas nuevas ni cambios de
privilegios (`app_runtime` ya tiene `SELECT, INSERT, UPDATE` y nunca `DELETE` sobre `motivo` y
`alicuota_iva`):

1. Verifica que no haya datos que los nuevos indices y `CHECK` rechazarian: motivos repetidos por
   `(organizacion_id, ambito, lower(nombre))`; alicuotas repetidas por `lower(nombre)` o por
   `valor`; alicuotas con `valor` fuera de `[0, 1)`; configuraciones con el redondeo a medias o
   con multiplo no positivo. Si los hay, **aborta** con un mensaje que nombra la organizacion y
   el dato, sin cambiar nada.
2. Crea `ux_motivo__nombre`, `ux_alicuota_iva__nombre` y `ux_alicuota_iva__valor` (INV-02).
3. Agrega `ck_alicuota_iva__valor`, `ck_configuracion_organizacion__redondeo_coherente` y
   `ck_configuracion_organizacion__redondeo_multiplo_positivo`.

`downgrade` borra los `CHECK` y los indices; no hay datos que revertir.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c1e3f5b7d2"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VERIFICACIONES = (
    (
        "motivos con el mismo nombre (sin distinguir mayusculas) en un mismo ambito",
        "SELECT organizacion_id, ambito || ' / ' || min(nombre) AS dato, count(*) AS cantidad "
        "FROM motivo GROUP BY organizacion_id, ambito, lower(nombre) HAVING count(*) > 1 "
        "ORDER BY organizacion_id, ambito, lower(nombre)",
    ),
    (
        "alicuotas con el mismo nombre (sin distinguir mayusculas)",
        "SELECT organizacion_id, min(nombre) AS dato, count(*) AS cantidad "
        "FROM alicuota_iva GROUP BY organizacion_id, lower(nombre) HAVING count(*) > 1 "
        "ORDER BY organizacion_id, lower(nombre)",
    ),
    (
        "alicuotas con el mismo valor",
        "SELECT organizacion_id, valor::text AS dato, count(*) AS cantidad "
        "FROM alicuota_iva GROUP BY organizacion_id, valor HAVING count(*) > 1 "
        "ORDER BY organizacion_id, valor",
    ),
    (
        "alicuotas con valor fuera de [0, 1)",
        "SELECT organizacion_id, nombre || ' = ' || valor::text AS dato, 1 AS cantidad "
        "FROM alicuota_iva WHERE valor < 0 OR valor >= 1 ORDER BY organizacion_id, nombre",
    ),
    (
        "redondeo por defecto a medias (multiplo sin direccion o al reves)",
        "SELECT organizacion_id, 'multiplo=' || coalesce(redondeo_multiplo::text, 'nulo') "
        "|| ', direccion=' || coalesce(redondeo_direccion, 'nula') AS dato, 1 AS cantidad "
        "FROM configuracion_organizacion "
        "WHERE (redondeo_multiplo IS NULL) <> (redondeo_direccion IS NULL) "
        "ORDER BY organizacion_id",
    ),
    (
        "redondeo por defecto con multiplo no positivo",
        "SELECT organizacion_id, 'multiplo=' || redondeo_multiplo::text AS dato, 1 AS cantidad "
        "FROM configuracion_organizacion WHERE redondeo_multiplo <= 0 ORDER BY organizacion_id",
    ),
)


def upgrade() -> None:
    conexion = op.get_bind()

    for descripcion, consulta in _VERIFICACIONES:
        filas = conexion.execute(sa.text(consulta)).all()
        if filas:
            detalle = "; ".join(
                f"organizacion {fila.organizacion_id}: {fila.dato!r} ({fila.cantidad})"
                for fila in filas
            )
            raise RuntimeError(
                f"No se puede aplicar la migracion del change 20c: hay {descripcion}. {detalle}. "
                "Corregir a mano esos datos y volver a correr la migracion."
            )

    op.create_index(
        "ux_motivo__nombre",
        "motivo",
        ["organizacion_id", "ambito", sa.text("lower(nombre)")],
        unique=True,
    )
    op.create_index(
        "ux_alicuota_iva__nombre",
        "alicuota_iva",
        ["organizacion_id", sa.text("lower(nombre)")],
        unique=True,
    )
    op.create_index(
        "ux_alicuota_iva__valor", "alicuota_iva", ["organizacion_id", "valor"], unique=True
    )
    op.create_check_constraint("ck_alicuota_iva__valor", "alicuota_iva", "valor >= 0 AND valor < 1")
    op.create_check_constraint(
        "ck_configuracion_organizacion__redondeo_coherente",
        "configuracion_organizacion",
        "(redondeo_multiplo IS NULL) = (redondeo_direccion IS NULL)",
    )
    op.create_check_constraint(
        "ck_configuracion_organizacion__redondeo_multiplo_positivo",
        "configuracion_organizacion",
        "redondeo_multiplo > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_configuracion_organizacion__redondeo_multiplo_positivo",
        "configuracion_organizacion",
        type_="check",
    )
    op.drop_constraint(
        "ck_configuracion_organizacion__redondeo_coherente",
        "configuracion_organizacion",
        type_="check",
    )
    op.drop_constraint("ck_alicuota_iva__valor", "alicuota_iva", type_="check")
    op.drop_index("ux_alicuota_iva__valor", table_name="alicuota_iva")
    op.drop_index("ux_alicuota_iva__nombre", table_name="alicuota_iva")
    op.drop_index("ux_motivo__nombre", table_name="motivo")
