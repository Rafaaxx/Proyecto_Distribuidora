"""clientes: maestro de clientes

Revision ID: 9c4e1f2a3b4d
Revises: 8b9c0d1e2f3a
Create Date: 2026-09-28 00:00:00.000000

Change 07 (`design.md` Migration Plan punto 1, D1 a D7): crea `cliente`
(`docs/03-modelo-de-datos.md` §10).

- Columnas de `03` §10 MENOS `condicion_iva` (D5: `01` §16 y FAC-04 no
  definen su dominio; la agrega el change de facturación con su catálogo).
- `lista_precio_id` queda `uuid NULL` SIN FK (D2: la tabla `lista_precio` la
  crea el change 13; mismo criterio que `producto.proveedor_id` antes del 13,
  ADR-025). `clientes/models.py` lo declara igual, así que el autogenerate no
  detecta deriva.
- `limite_credito` y `tolerancia_offline_valor` en `numeric(14,2)` (D6: misma
  precisión que `configuracion_organizacion.tolerancia_offline_valor`, para
  que heredar el valor de la organización sea una lectura y no una conversión).
- `CHECK` de los cuatro catálogos cerrados (`estado`, `documento_tipo`,
  `politica_credito`, `tolerancia_offline_tipo`,
  `estado_facturacion_default`), de las dos parejas que van juntas
  (`documento_tipo`/`documento_numero` y `tolerancia_offline_tipo`/
  `tolerancia_offline_valor`, CLI-01, CRE-06) y de los dos importes que no
  pueden ser negativos (`limite_credito` y `tolerancia_offline_valor`; CRE-01
  reserva el NULO para "sin control"/"hereda el de la organización", así que un
  negativo es un dato inválido, INV-03).
- `ux_cliente__codigo` y `ux_cliente__documento`, únicos por organización y
  PARCIALES (`WHERE ... IS NOT NULL`) porque ambos son opcionales (D1: la
  unicidad la garantiza la base, no solo el handler, así que dos altas
  concurrentes con el mismo documento no pueden colarse; `nombre` NO es
  único). Índices de listado por organización+nombre,
  organización+estado+nombre y organización+documento (`02` §11).
- `UNIQUE (organizacion_id, id)`: sin ella, `venta`, `cobranza` y `compra` no
  pueden referenciar al cliente con FK compuesta (INV-21, `CLAUDE.md` §4).
- FKs compuestas a `organizacion` y a `usuario(organizacion_id, id)`.
- `GRANT SELECT, INSERT, UPDATE` y NADA de `DELETE`: un cliente no se borra,
  se inactiva (CLI-04, INV-05, TR-06).

Tabla nueva y vacía: no se usan índices concurrentes (mismo criterio que
`70dcb6dce507`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c4e1f2a3b4d"
down_revision: str | Sequence[str] | None = "8b9c0d1e2f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_ESTADOS_CLIENTE = "'ACTIVO','SUSPENDIDO','INACTIVO'"
_TIPOS_DOCUMENTO = "'CUIT','DNI'"
_POLITICAS_CREDITO = "'ADVERTIR','AUTORIZAR','BLOQUEAR'"
_TIPOS_TOLERANCIA = "'IMPORTE','PORCENTAJE'"
_ESTADOS_FACTURACION = "'NO_REQUIERE','PENDIENTE'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cliente",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=True),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("razon_social", sa.Text(), nullable=True),
        sa.Column("documento_tipo", sa.Text(), nullable=True),
        sa.Column("documento_numero", sa.Text(), nullable=True),
        sa.Column("direccion", sa.Text(), nullable=False),
        sa.Column("contacto", sa.Text(), nullable=False),
        sa.Column("telefono", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        # Sin FK: la tabla `lista_precio` la crea el change 13 (D2).
        sa.Column("lista_precio_id", sa.Uuid(), nullable=True),
        sa.Column("limite_credito", sa.Numeric(14, 2), nullable=True),
        sa.Column("politica_credito", sa.Text(), nullable=True),
        sa.Column("tolerancia_offline_tipo", sa.Text(), nullable=True),
        sa.Column("tolerancia_offline_valor", sa.Numeric(14, 2), nullable=True),
        sa.Column("estado_facturacion_default", sa.Text(), nullable=True),
        sa.Column("es_consumidor_final", sa.Boolean(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_cliente"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cliente__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_cliente__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_cliente__org_id"),
        sa.CheckConstraint(f"estado IN ({_ESTADOS_CLIENTE})", name="ck_cliente__estado"),
        sa.CheckConstraint(
            f"documento_tipo IS NULL OR documento_tipo IN ({_TIPOS_DOCUMENTO})",
            name="ck_cliente__documento_tipo",
        ),
        sa.CheckConstraint(
            "(documento_tipo IS NULL AND documento_numero IS NULL) OR "
            "(documento_tipo IS NOT NULL AND documento_numero IS NOT NULL)",
            name="ck_cliente__documento_pareja",
        ),
        sa.CheckConstraint(
            f"politica_credito IS NULL OR politica_credito IN ({_POLITICAS_CREDITO})",
            name="ck_cliente__politica_credito",
        ),
        sa.CheckConstraint(
            f"tolerancia_offline_tipo IS NULL OR tolerancia_offline_tipo IN ({_TIPOS_TOLERANCIA})",
            name="ck_cliente__tolerancia_tipo",
        ),
        sa.CheckConstraint(
            "(tolerancia_offline_tipo IS NULL AND tolerancia_offline_valor IS NULL) OR "
            "(tolerancia_offline_tipo IS NOT NULL AND tolerancia_offline_valor IS NOT NULL)",
            name="ck_cliente__tolerancia_pareja",
        ),
        sa.CheckConstraint(
            "tolerancia_offline_valor IS NULL OR tolerancia_offline_valor >= 0",
            name="ck_cliente__tolerancia_valor",
        ),
        sa.CheckConstraint(
            "limite_credito IS NULL OR limite_credito >= 0", name="ck_cliente__limite_credito"
        ),
        sa.CheckConstraint(
            f"estado_facturacion_default IS NULL OR "
            f"estado_facturacion_default IN ({_ESTADOS_FACTURACION})",
            name="ck_cliente__estado_facturacion",
        ),
    )
    # D1: unicidad en la base, no solo en el handler. Parciales porque
    # `codigo` y `documento_numero` son opcionales: sin el `WHERE`, PostgreSQL
    # los trataría como duplicados entre sí en las filas que no los tienen.
    op.create_index(
        "ux_cliente__codigo",
        "cliente",
        ["organizacion_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("codigo IS NOT NULL"),
    )
    op.create_index(
        "ux_cliente__documento",
        "cliente",
        ["organizacion_id", "documento_tipo", "documento_numero"],
        unique=True,
        postgresql_where=sa.text("documento_numero IS NOT NULL"),
    )
    # Índices de listado (`02` §11): filtro por texto y por estado, orden
    # estable por `nombre`.
    op.create_index("ix_cliente__org_nombre", "cliente", ["organizacion_id", "nombre"])
    op.create_index(
        "ix_cliente__org_estado_nombre", "cliente", ["organizacion_id", "estado", "nombre"]
    )
    op.create_index("ix_cliente__org_documento", "cliente", ["organizacion_id", "documento_numero"])

    # Permisos de app_runtime (ADR-020). Sin `DELETE`: un cliente se inactiva,
    # no se borra (CLI-04, INV-05).
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON cliente TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON cliente FROM {ROL_RUNTIME}")

    op.drop_index("ix_cliente__org_documento", table_name="cliente")
    op.drop_index("ix_cliente__org_estado_nombre", table_name="cliente")
    op.drop_index("ix_cliente__org_nombre", table_name="cliente")
    op.drop_index("ux_cliente__documento", table_name="cliente")
    op.drop_index("ux_cliente__codigo", table_name="cliente")
    op.drop_table("cliente")
