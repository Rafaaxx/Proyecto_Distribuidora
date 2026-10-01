"""stock y costeo: ubicaciones, libro de stock, saldos y costo promedio

Revision ID: a8b9c0d1e2f3
Revises: e6f7a8b9c0d1
Create Date: 2026-09-30 00:00:00.000000

Change 09 (`design.md` Migration Plan, D7, D10, D12, D13): crea `ubicacion`,
`costo_producto`, `costo_producto_mov`, `stock_saldo` y `stock_movimiento`
(`docs/03-modelo-de-datos.md` §7 y §9).

`ubicacion` (maestro, STK-02):

- Columnas de `03` §9 MÁS `creado_en`, `actualizado_en` y `actualizado_por_id`
  (D7: `03` §2.3 lo exige a todo maestro; `03` §9 no lo lista), con FK compuesta a
  `usuario` como los demás maestros.
- `ux_ubicacion__nombre`: único por organización SIN distinguir mayúsculas
  (`lower(nombre)`), activas o no (D7). El nombre ya llega recortado del dominio.
- `ck_ubicacion__vehiculo_requiere_toma`: `tipo <> 'VEHICULO' OR requiere_toma`
  (STK-02, D7). `ck_ubicacion__tipo`: catálogo de tipos.
- `UNIQUE (organizacion_id, id)`: sin ella ninguna tabla puede referenciar una
  ubicación con FK compuesta.

`costo_producto` y `stock_saldo` (materializaciones verificables, `02` §7.2):

- Clave primaria compuesta que EMPIEZA por `organizacion_id` y sin `id` (ADR-035
  punto 6, D10): `(organizacion_id, producto_id)` y `(organizacion_id,
  producto_id, ubicacion_id)`.
- `costo_promedio` NULO hasta el primer ingreso con costo; `CHECK (costo_promedio
  IS NULL OR costo_promedio > 0)` (D10). `stock_total` y `cantidad_base` son
  `integer NOT NULL DEFAULT 0` (INV-04).
- `ix_stock_saldo__ubicacion` (`03` §16): stock de una ubicación.
- `GRANT SELECT, INSERT, UPDATE`: el servicio las crea de forma perezosa y las
  actualiza en cada movimiento (D10); sin `DELETE`.

`stock_movimiento` y `costo_producto_mov` (libros, solo inserción, INV-05):

- `stock_movimiento` con `dispositivo_id uuid NOT NULL` y FK compuestas a
  `producto`, `ubicacion`, `usuario`, `dispositivo` y `motivo` (opcional).
  `jornada_id` NULABLE y SIN FK hasta el change 15, porque `jornada` no existe
  todavía (D12, mismo trato que `comando.jornada_id`, D8 del 04). `origen_tipo` +
  `origen_id` genéricos y sin FK (`03` §9).
- `ck_stock_movimiento__cantidad_no_cero` (STK-03) y `ck_stock_movimiento__tipo`
  con los nueve tipos de la etapa 1 (D13-A): 11, 14, 18a, 19 y 24 no migran el
  libro.
- `costo_producto_mov`: columnas de `03` §7 más FK compuesta a `producto`;
  `promedio_anterior` es NULO en el primer ingreso (D10);
  `ck_costo_producto_mov__origen_tipo` con los cuatro orígenes de `03` §7.
- Índices `ix_stock_movimiento__kardex` `(organizacion_id, producto_id,
  ubicacion_id, occurred_at, id)` y `ix_stock_movimiento__origen`
  `(organizacion_id, origen_tipo, origen_id)` (`03` §9 y §16, D12);
  `ix_costo_producto_mov__producto` para reconstruir la historia (CST-13).
- `GRANT SELECT, INSERT`: `app_runtime` no recibe `UPDATE` ni `DELETE` (INV-05,
  ADR-020).

Tablas nuevas y vacías: no se usan índices concurrentes (mismo criterio que
`e6f7a8b9c0d1`). `downgrade` elimina las cinco tablas con los permisos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_TIPOS_DE_UBICACION = "'DEPOSITO','VEHICULO','OTRO'"
_TIPOS_DE_MOVIMIENTO = (
    "'STOCK_INICIAL','COMPRA','ANULACION_COMPRA','VENTA','ANULACION_VENTA',"
    "'TRANSFERENCIA_SALIDA','TRANSFERENCIA_ENTRADA','AJUSTE','DIFERENCIA_RENDICION'"
)
_ORIGENES_DE_COSTO = "'COMPRA','ANULACION_COMPRA','STOCK_INICIAL','ANULACION_VENTA'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ubicacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("requiere_toma", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ubicacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_ubicacion__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_ubicacion__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_ubicacion__org_id"),
        sa.CheckConstraint(f"tipo IN ({_TIPOS_DE_UBICACION})", name="ck_ubicacion__tipo"),
        sa.CheckConstraint(
            "tipo <> 'VEHICULO' OR requiere_toma", name="ck_ubicacion__vehiculo_requiere_toma"
        ),
    )
    op.create_index(
        "ux_ubicacion__nombre",
        "ubicacion",
        ["organizacion_id", sa.text("lower(nombre)")],
        unique=True,
    )

    op.create_table(
        "costo_producto",
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("costo_promedio", sa.Numeric(18, 6), nullable=True),
        sa.Column("stock_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organizacion_id", "producto_id", name="pk_costo_producto"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_costo_producto__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_costo_producto__producto",
        ),
        sa.CheckConstraint(
            "costo_promedio IS NULL OR costo_promedio > 0",
            name="ck_costo_producto__promedio_positivo",
        ),
    )

    op.create_table(
        "costo_producto_mov",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("origen_tipo", sa.Text(), nullable=False),
        sa.Column("origen_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("costo_ingreso", sa.Numeric(18, 6), nullable=False),
        sa.Column("stock_anterior", sa.Integer(), nullable=False),
        sa.Column("promedio_anterior", sa.Numeric(18, 6), nullable=True),
        sa.Column("stock_nuevo", sa.Integer(), nullable=False),
        sa.Column("promedio_nuevo", sa.Numeric(18, 6), nullable=False),
        sa.Column("recalculado", sa.Boolean(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_costo_producto_mov"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_costo_producto_mov__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_costo_producto_mov__producto",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_costo_producto_mov__org_id"),
        sa.CheckConstraint(
            f"origen_tipo IN ({_ORIGENES_DE_COSTO})", name="ck_costo_producto_mov__origen_tipo"
        ),
    )
    op.create_index(
        "ix_costo_producto_mov__producto",
        "costo_producto_mov",
        ["organizacion_id", "producto_id", "registered_at", "id"],
    )

    op.create_table(
        "stock_saldo",
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad_base", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "organizacion_id", "producto_id", "ubicacion_id", name="pk_stock_saldo"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_stock_saldo__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_stock_saldo__producto",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "ubicacion_id"],
            ["ubicacion.organizacion_id", "ubicacion.id"],
            name="fk_stock_saldo__ubicacion",
        ),
    )
    op.create_index("ix_stock_saldo__ubicacion", "stock_saldo", ["organizacion_id", "ubicacion_id"])

    op.create_table(
        "stock_movimiento",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad_base", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("origen_tipo", sa.Text(), nullable=False),
        sa.Column("origen_id", sa.Uuid(), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(18, 6), nullable=True),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("motivo_id", sa.Uuid(), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movimiento"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_stock_movimiento__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_stock_movimiento__producto",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "ubicacion_id"],
            ["ubicacion.organizacion_id", "ubicacion.id"],
            name="fk_stock_movimiento__ubicacion",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_stock_movimiento__usuario",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "dispositivo_id"],
            ["dispositivo.organizacion_id", "dispositivo.id"],
            name="fk_stock_movimiento__dispositivo",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "motivo_id"],
            ["motivo.organizacion_id", "motivo.id"],
            name="fk_stock_movimiento__motivo",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_stock_movimiento__org_id"),
        sa.CheckConstraint("cantidad_base <> 0", name="ck_stock_movimiento__cantidad_no_cero"),
        sa.CheckConstraint(f"tipo IN ({_TIPOS_DE_MOVIMIENTO})", name="ck_stock_movimiento__tipo"),
    )
    # `03` §9 y §16: kardex por `(occurred_at, id)`; verificación de consistencia.
    op.create_index(
        "ix_stock_movimiento__kardex",
        "stock_movimiento",
        ["organizacion_id", "producto_id", "ubicacion_id", "occurred_at", "id"],
    )
    # `03` §9: reversiones por documento de origen.
    op.create_index(
        "ix_stock_movimiento__origen",
        "stock_movimiento",
        ["organizacion_id", "origen_tipo", "origen_id"],
    )

    # Permisos de app_runtime (ADR-020): los libros son de solo inserción
    # (INV-05); los saldos y la ubicación se actualizan (`02` §7.2).
    op.execute(f"GRANT SELECT, INSERT ON stock_movimiento TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT ON costo_producto_mov TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON stock_saldo TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON costo_producto TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ubicacion TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON ubicacion FROM {ROL_RUNTIME}")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON costo_producto FROM {ROL_RUNTIME}")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON stock_saldo FROM {ROL_RUNTIME}")
    op.execute(f"REVOKE SELECT, INSERT ON costo_producto_mov FROM {ROL_RUNTIME}")
    op.execute(f"REVOKE SELECT, INSERT ON stock_movimiento FROM {ROL_RUNTIME}")

    op.drop_index("ix_stock_movimiento__origen", table_name="stock_movimiento")
    op.drop_index("ix_stock_movimiento__kardex", table_name="stock_movimiento")
    op.drop_table("stock_movimiento")
    op.drop_index("ix_stock_saldo__ubicacion", table_name="stock_saldo")
    op.drop_table("stock_saldo")
    op.drop_index("ix_costo_producto_mov__producto", table_name="costo_producto_mov")
    op.drop_table("costo_producto_mov")
    op.drop_table("costo_producto")
    op.drop_index("ux_ubicacion__nombre", table_name="ubicacion")
    op.drop_table("ubicacion")
