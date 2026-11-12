"""organizacion y configuracion

Revision ID: 568672139155
Revises: 7c9c79f7704e
Create Date: 2026-09-18 20:49:19.981757

Crea la organizacion como raiz de todo dato de negocio (`docs/03` §4):
`organizacion`, `configuracion_organizacion` (1 fila por organizacion) y los
catalogos configurables `alicuota_iva`, `medio_pago` y `motivo` (TR-09).

Deuda anotada (`design.md` D3): `configuracion_organizacion.lista_precio_default_id`
y `configuracion_organizacion.cliente_consumidor_final_id` se crean nulables
y SIN clave foranea porque sus tablas destino (`lista_precio`, change 13; y
`cliente`, change 07) todavia no existen. La migracion que crea cada tabla
destino agrega su FK compuesta `(organizacion_id, <id>)`.

Misma deuda, generalizada (no cubierta explicitamente por `design.md`, se
aplica el mismo patron de D3): `actualizado_por_id` en las tablas maestras
(`docs/03` §2.3) referenciaria `usuario (id)`, que llega recien en el change
03. Se crea como `uuid` nulable sin FK; el change 03 agrega la FK compuesta
`(organizacion_id, actualizado_por_id) REFERENCES usuario (organizacion_id, id)`
a las cinco tablas de este change. Señalado a revision humana junto con D2.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "568672139155"
down_revision: str | Sequence[str] | None = "7c9c79f7704e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organizacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("cuit", sa.Text(), nullable=True),
        sa.Column("moneda", sa.Text(), nullable=False),
        sa.Column("zona_horaria", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_organizacion"),
        sa.CheckConstraint("estado IN ('ACTIVA', 'SUSPENDIDA')", name="ck_organizacion__estado"),
    )

    op.create_table(
        "configuracion_organizacion",
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("modo_impositivo", sa.Text(), nullable=False),
        # `lista_precio_default_id` sin FK: ver docstring del modulo (D3).
        sa.Column("lista_precio_default_id", sa.Uuid(), nullable=True),
        sa.Column("politica_credito_default", sa.Text(), nullable=False),
        sa.Column("tolerancia_offline_tipo", sa.Text(), nullable=True),
        sa.Column("tolerancia_offline_valor", sa.Numeric(14, 2), nullable=True),
        sa.Column("descuento_manual_habilitado", sa.Boolean(), nullable=False),
        sa.Column("motivo_obligatorio_descuento", sa.Boolean(), nullable=True),
        sa.Column("motivo_obligatorio_lista", sa.Boolean(), nullable=False),
        sa.Column("redondeo_multiplo", sa.Numeric(14, 2), nullable=True),
        sa.Column("redondeo_direccion", sa.Text(), nullable=True),
        sa.Column("permite_consumidor_final", sa.Boolean(), nullable=True),
        # `cliente_consumidor_final_id` sin FK: ver docstring del modulo (D3).
        sa.Column("cliente_consumidor_final_id", sa.Uuid(), nullable=True),
        sa.Column("estado_facturacion_default", sa.Text(), nullable=False),
        sa.Column("modalidad_iva_default", sa.Text(), nullable=True),
        sa.Column("intentos_pin_max", sa.Integer(), nullable=False),
        sa.Column("app_version_minima", sa.Text(), nullable=True),
        sa.Column("desvio_reloj_max_segundos", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("organizacion_id", name="pk_configuracion_organizacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_configuracion_organizacion__organizacion",
        ),
        sa.CheckConstraint(
            "modo_impositivo IN ('A', 'B', 'C')",
            name="ck_configuracion_organizacion__modo_impositivo",
        ),
        sa.CheckConstraint(
            "politica_credito_default IN ('ADVERTIR', 'AUTORIZAR', 'BLOQUEAR')",
            name="ck_configuracion_organizacion__politica_credito_default",
        ),
        sa.CheckConstraint(
            "tolerancia_offline_tipo IN ('IMPORTE', 'PORCENTAJE')",
            name="ck_configuracion_organizacion__tolerancia_offline_tipo",
        ),
        sa.CheckConstraint(
            "redondeo_direccion IN ('ARRIBA', 'CERCANO', 'ABAJO')",
            name="ck_configuracion_organizacion__redondeo_direccion",
        ),
        sa.CheckConstraint(
            "estado_facturacion_default IN ('NO_REQUIERE', 'PENDIENTE')",
            name="ck_configuracion_organizacion__estado_facturacion_default",
        ),
        sa.CheckConstraint(
            "modalidad_iva_default IN ('CLIENTE', 'ABSORBIDO')",
            name="ck_configuracion_organizacion__modalidad_iva_default",
        ),
    )

    op.create_table(
        "alicuota_iva",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("valor", sa.Numeric(9, 6), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_alicuota_iva"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_alicuota_iva__organizacion"
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_alicuota_iva__org_id"),
    )

    op.create_table(
        "medio_pago",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("requiere_referencia", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_medio_pago"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_medio_pago__organizacion"
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_medio_pago__org_id"),
    )

    op.create_table(
        "motivo",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("ambito", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_motivo"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_motivo__organizacion"
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_motivo__org_id"),
        sa.CheckConstraint(
            "ambito IN ("
            "'AJUSTE_STOCK', 'ANULACION_VENTA', 'ANULACION_COMPRA', "
            "'ANULACION_COBRANZA', 'DESCUENTO_MANUAL', 'LISTA_ANTERIOR', "
            "'LIBERACION_JORNADA')",
            name="ck_motivo__ambito",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("motivo")
    op.drop_table("medio_pago")
    op.drop_table("alicuota_iva")
    op.drop_table("configuracion_organizacion")
    op.drop_table("organizacion")
