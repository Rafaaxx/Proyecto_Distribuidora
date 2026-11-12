"""cuentas corrientes: libro de movimientos y saldo materializado

Revision ID: e6f7a8b9c0d1
Revises: 9c4e1f2a3b4d
Create Date: 2026-09-29 00:00:00.000000

Change 08 (`design.md` Migration Plan, D6, D11, D12, D14): crea
`cuenta_movimiento` y `saldo_cuenta` (`docs/03-modelo-de-datos.md` §12).

`cuenta_movimiento` (libro único de clientes y proveedores, solo inserción):

- Columnas de `03` §12 MÁS `dispositivo_id uuid NOT NULL` (D14: `03` §2.3 lo
  pide a toda tabla de operaciones y `SobreComando` lo trae siempre), con la
  misma FK compuesta que `comando`/`sesion_refresh`.
- `cliente_id` y `proveedor_id` son columnas GENERADAS (D6-A): `entidad_id` si
  `cuenta_tipo` coincide, nulo si no. Cada una tiene su FK compuesta
  `(organizacion_id, cliente_id) -> cliente` y
  `(organizacion_id, proveedor_id) -> proveedor`. Como PostgreSQL no valida una
  FK con alguna columna nula (`MATCH SIMPLE`), solo se valida la que
  corresponde a `cuenta_tipo`: una entidad de otra organización, inexistente o
  del tipo equivocado no entra. Nadie escribe esas columnas. La FK usa el
  comportamiento por defecto (`NO ACTION`), el único que PostgreSQL admite
  sobre una columna generada.
- `UNIQUE (organizacion_id, id)`: sin ella ninguna tabla futura (venta,
  cobranza, compra...) puede referenciar un movimiento con FK compuesta.
- `CHECK` de importe positivo (CC-01), de `sentido`, de `cuenta_tipo`, de
  `tipo` (todos los tipos de CC-02 y CC-03 de la etapa 1, sin los de IVA,
  D12-A) y de la coherencia `cuenta_tipo` x `tipo`.
- Índice `ix_cuenta_movimiento__estado_de_cuenta` de `03` §12 y §16.
- `GRANT SELECT, INSERT`: el libro es de solo inserción (CC-06, INV-05,
  ADR-020). `app_runtime` no recibe `UPDATE` ni `DELETE`.

`saldo_cuenta` (materialización verificable, `02` §7.2):

- Clave primaria compuesta `(organizacion_id, cuenta_tipo, entidad_id)` sin
  `id` (D11-A, `03` §12). `saldo numeric(14,2) NOT NULL DEFAULT 0`.
- Mismas columnas generadas y FK compuestas que el libro (D6-A).
- `GRANT SELECT, INSERT, UPDATE`: el servicio la crea de forma perezosa y la
  actualiza en cada movimiento (D10); sin `DELETE`.

Tablas nuevas y vacías: no se usan índices concurrentes (mismo criterio que
`9c4e1f2a3b4d`). `downgrade` elimina ambas tablas con los permisos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "9c4e1f2a3b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_CUENTAS_TIPO = "'CLIENTE','PROVEEDOR'"
_SENTIDOS = "'AUMENTA','REDUCE'"
_TIPOS_CLIENTE = "'SALDO_INICIAL','VENTA','ANULACION_VENTA','COBRANZA','ANULACION_COBRANZA'"
_TIPOS_PROVEEDOR = "'SALDO_INICIAL','COMPRA','ANULACION_COMPRA','PAGO','ANULACION_PAGO'"
_TIPOS = (
    "'SALDO_INICIAL','VENTA','ANULACION_VENTA','COBRANZA','ANULACION_COBRANZA',"
    "'COMPRA','ANULACION_COMPRA','PAGO','ANULACION_PAGO'"
)

_CLIENTE_GENERADO = "CASE WHEN cuenta_tipo = 'CLIENTE' THEN entidad_id END"
_PROVEEDOR_GENERADO = "CASE WHEN cuenta_tipo = 'PROVEEDOR' THEN entidad_id END"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cuenta_movimiento",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("cuenta_tipo", sa.Text(), nullable=False),
        sa.Column("entidad_id", sa.Uuid(), nullable=False),
        sa.Column(
            "cliente_id", sa.Uuid(), sa.Computed(_CLIENTE_GENERADO, persisted=True), nullable=True
        ),
        sa.Column(
            "proveedor_id",
            sa.Uuid(),
            sa.Computed(_PROVEEDOR_GENERADO, persisted=True),
            nullable=True,
        ),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("sentido", sa.Text(), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("origen_tipo", sa.Text(), nullable=False),
        sa.Column("origen_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cuenta_movimiento"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cuenta_movimiento__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_cuenta_movimiento__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_cuenta_movimiento__dispositivo",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "cliente_id"],
            ["cliente.organizacion_id", "cliente.id"],
            name="fk_cuenta_movimiento__cliente",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_cuenta_movimiento__proveedor",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_cuenta_movimiento__org_id"),
        sa.CheckConstraint("importe > 0", name="ck_cuenta_movimiento__importe_positivo"),
        sa.CheckConstraint(f"sentido IN ({_SENTIDOS})", name="ck_cuenta_movimiento__sentido"),
        sa.CheckConstraint(
            f"cuenta_tipo IN ({_CUENTAS_TIPO})", name="ck_cuenta_movimiento__cuenta_tipo"
        ),
        sa.CheckConstraint(f"tipo IN ({_TIPOS})", name="ck_cuenta_movimiento__tipo"),
        sa.CheckConstraint(
            f"(cuenta_tipo = 'CLIENTE' AND tipo IN ({_TIPOS_CLIENTE})) OR "
            f"(cuenta_tipo = 'PROVEEDOR' AND tipo IN ({_TIPOS_PROVEEDOR}))",
            name="ck_cuenta_movimiento__tipo_de_cuenta",
        ),
    )
    # `03` §12 y §16: estado de cuenta ordenado por `(occurred_at, id)`.
    op.create_index(
        "ix_cuenta_movimiento__estado_de_cuenta",
        "cuenta_movimiento",
        ["organizacion_id", "cuenta_tipo", "entidad_id", "occurred_at", "id"],
    )

    op.create_table(
        "saldo_cuenta",
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("cuenta_tipo", sa.Text(), nullable=False),
        sa.Column("entidad_id", sa.Uuid(), nullable=False),
        sa.Column(
            "cliente_id", sa.Uuid(), sa.Computed(_CLIENTE_GENERADO, persisted=True), nullable=True
        ),
        sa.Column(
            "proveedor_id",
            sa.Uuid(),
            sa.Computed(_PROVEEDOR_GENERADO, persisted=True),
            nullable=True,
        ),
        sa.Column("saldo", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "organizacion_id", "cuenta_tipo", "entidad_id", name="pk_saldo_cuenta"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_saldo_cuenta__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "cliente_id"],
            ["cliente.organizacion_id", "cliente.id"],
            name="fk_saldo_cuenta__cliente",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_saldo_cuenta__proveedor",
        ),
        sa.CheckConstraint(
            f"cuenta_tipo IN ({_CUENTAS_TIPO})", name="ck_saldo_cuenta__cuenta_tipo"
        ),
    )

    # Permisos de app_runtime (ADR-020): el libro es de solo inserción (CC-06,
    # INV-05); el saldo es una materialización que se actualiza (`02` §7.2).
    op.execute(f"GRANT SELECT, INSERT ON cuenta_movimiento TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON saldo_cuenta TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON saldo_cuenta FROM {ROL_RUNTIME}")
    op.execute(f"REVOKE SELECT, INSERT ON cuenta_movimiento FROM {ROL_RUNTIME}")

    op.drop_table("saldo_cuenta")
    op.drop_index("ix_cuenta_movimiento__estado_de_cuenta", table_name="cuenta_movimiento")
    op.drop_table("cuenta_movimiento")
