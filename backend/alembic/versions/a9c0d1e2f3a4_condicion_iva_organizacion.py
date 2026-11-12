"""condicion frente al IVA de la organizacion y regla de credito fiscal congelada

Revision ID: a9c0d1e2f3a4
Revises: c0d1e2f3a4b5
Create Date: 2026-10-03 00:00:00.000000

Change 11b (`design.md` D1, D2, D3, D9; CST-06):

- `configuracion_organizacion.condicion_iva text NOT NULL` con `CHECK` de dominio
  (`RESPONSABLE_INSCRIPTO`, `MONOTRIBUTO`, `EXENTO`) y el `CHECK` de D2: una organizacion
  no inscripta es modo `A` y no tiene modalidad de IVA al facturar. Las organizaciones
  existentes quedan `RESPONSABLE_INSCRIPTO` (D9): sus costos y compras ya se calcularon con
  esa regla y nada cambia de comportamiento por migrar (TR-06).
- `costo_informado.computa_credito_fiscal` y `compra_linea.computa_credito_fiscal`
  (`boolean NOT NULL`), la regla vigente al registrar (D3). Las filas existentes quedan en
  `true`. `CHECK (computa_credito_fiscal OR NOT incluye_iva)`: el IVA no se descuenta de un
  valor que no lo computa.

Las columnas nuevas se agregan con `DEFAULT` y luego se quita el `DEFAULT`: es una
operacion de catalogo (sin reescribir filas ni hacer `UPDATE` sobre los libros, INV-05) y la
aplicacion siempre informa el valor. Los permisos de `app_runtime` no cambian:
`configuracion_organizacion` ya tiene `UPDATE` por tabla; `costo_informado` y
`compra_linea` siguen en `SELECT, INSERT`.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c0d1e2f3a4"
down_revision: str | Sequence[str] | None = "c0d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE configuracion_organizacion "
        "ADD COLUMN condicion_iva text NOT NULL DEFAULT 'RESPONSABLE_INSCRIPTO'"
    )
    op.execute("ALTER TABLE configuracion_organizacion ALTER COLUMN condicion_iva DROP DEFAULT")
    op.execute(
        "ALTER TABLE configuracion_organizacion "
        "ADD CONSTRAINT ck_configuracion_organizacion__condicion_iva "
        "CHECK (condicion_iva IN ('RESPONSABLE_INSCRIPTO', 'MONOTRIBUTO', 'EXENTO'))"
    )
    op.execute(
        "ALTER TABLE configuracion_organizacion "
        "ADD CONSTRAINT ck_configuracion_organizacion__no_inscripto_modo_a "
        "CHECK (condicion_iva = 'RESPONSABLE_INSCRIPTO' "
        "OR (modo_impositivo = 'A' AND modalidad_iva_default IS NULL))"
    )

    for tabla in ("costo_informado", "compra_linea"):
        op.execute(
            f"ALTER TABLE {tabla} ADD COLUMN computa_credito_fiscal boolean NOT NULL DEFAULT true"
        )
        op.execute(f"ALTER TABLE {tabla} ALTER COLUMN computa_credito_fiscal DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT ck_{tabla}__credito_fiscal "
            "CHECK (computa_credito_fiscal OR NOT incluye_iva)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for tabla in ("compra_linea", "costo_informado"):
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT ck_{tabla}__credito_fiscal")
        op.execute(f"ALTER TABLE {tabla} DROP COLUMN computa_credito_fiscal")

    op.execute(
        "ALTER TABLE configuracion_organizacion "
        "DROP CONSTRAINT ck_configuracion_organizacion__no_inscripto_modo_a"
    )
    op.execute(
        "ALTER TABLE configuracion_organizacion "
        "DROP CONSTRAINT ck_configuracion_organizacion__condicion_iva"
    )
    op.execute("ALTER TABLE configuracion_organizacion DROP COLUMN condicion_iva")
