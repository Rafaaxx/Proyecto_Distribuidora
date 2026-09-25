"""proveedores_y_costos: proveedor y costo_informado

Revision ID: 70dcb6dce507
Revises: c1d2e3f4a5b6
Create Date: 2026-09-23 00:00:00.000000

Change 06 (`design.md` Migration Plan punto 1, D10): crea `proveedor` y
`costo_informado`, y agrega la FK compuesta `fk_producto__proveedor` a
`producto` (todavía `NULLABLE`: el `NOT NULL` llega en la revisión
`producto_proveedor_obligatorio`, D2).

- `proveedor`: columnas de `03` §6 + `actualizado_en`/`actualizado_por_id`
  (`03` §2.3, igual que `categoria`/`marca`/`producto`); `ux_proveedor__nombre`
  y `ux_proveedor__cuit` (parcial, `WHERE cuit IS NOT NULL`) (D7).
  `GRANT SELECT, INSERT, UPDATE` (sin `DELETE`, D10/D5: un proveedor se
  desactiva, nunca se borra).
- `costo_informado`: FK compuestas a `proveedor`, `producto`, `presentacion`
  y `usuario`; `CHECK` de valor (`> 0`), bonificación (`[0, 1)`), alícuota
  aplicada (`>= 0`) y costo base (`>= 0`); índice de vigencia (D4:
  `organizacion_id, producto_id, vigencia_desde DESC, creado_en DESC, id
  DESC`) para CST-03. `operation_id` sin FK (como `auditoria`). Tabla de
  solo inserción (CST-03): `GRANT SELECT, INSERT` sin `UPDATE` ni `DELETE`.
- `producto.fk_producto__proveedor`: compuesta a `proveedor
  (organizacion_id, id)`, agregada `NOT VALID` y validada en la misma
  transacción de migración (`VALIDATE CONSTRAINT`, D9): las filas con
  `proveedor_id NULL` no la violan, así que valida sin bloquear con datos
  existentes del change 05. `producto.proveedor_id` sigue `NULLABLE` en
  esta revisión (D2, `04` §2.1 punto 4: la migración 2 la completa y recién
  ahí pone `NOT NULL`).

Tablas nuevas y vacías: no se usan índices concurrentes (igual que
`c1d2e3f4a5b6`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "70dcb6dce507"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"


def upgrade() -> None:
    """Upgrade schema."""
    # --- proveedor (CST-01..05, D5, D7) ------------------------------------
    op.create_table(
        "proveedor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("cuit", sa.Text(), nullable=True),
        sa.Column("contacto", sa.Text(), nullable=True),
        sa.Column("telefono", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_proveedor"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_proveedor__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_proveedor__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_proveedor__org_id"),
        sa.UniqueConstraint("organizacion_id", "nombre", name="ux_proveedor__nombre"),
    )
    op.create_index(
        "ux_proveedor__cuit",
        "proveedor",
        ["organizacion_id", "cuit"],
        unique=True,
        postgresql_where=sa.text("cuit IS NOT NULL"),
    )

    # --- costo_informado (CST-01..05, D4, D10) -----------------------------
    op.create_table(
        "costo_informado",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("proveedor_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("presentacion_id", sa.Uuid(), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("incluye_iva", sa.Boolean(), nullable=False),
        sa.Column("bonificacion", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("alicuota_aplicada", sa.Numeric(9, 6), nullable=False),
        sa.Column("costo_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("vigencia_desde", sa.Date(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_costo_informado"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_costo_informado__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "proveedor_id"],
            ["proveedor.organizacion_id", "proveedor.id"],
            name="fk_costo_informado__proveedor",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_costo_informado__producto",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "presentacion_id"],
            ["presentacion.organizacion_id", "presentacion.id"],
            name="fk_costo_informado__presentacion",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "usuario_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_costo_informado__usuario",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_costo_informado__org_id"),
        sa.CheckConstraint("valor > 0", name="ck_costo_informado__valor"),
        sa.CheckConstraint(
            "bonificacion >= 0 AND bonificacion < 1", name="ck_costo_informado__bonificacion"
        ),
        sa.CheckConstraint("alicuota_aplicada >= 0", name="ck_costo_informado__alicuota"),
        sa.CheckConstraint("costo_base >= 0", name="ck_costo_informado__costo_base"),
    )
    op.create_index(
        "ix_costo_informado__producto_vigencia",
        "costo_informado",
        [
            "organizacion_id",
            "producto_id",
            sa.text("vigencia_desde DESC"),
            sa.text("creado_en DESC"),
            sa.text("id DESC"),
        ],
    )

    # --- fk_producto__proveedor (D2, D9): NOT VALID + VALIDATE -------------
    # `proveedor_id` sigue NULLABLE en esta revisión: las filas NULL no
    # violan la FK, así que VALIDATE no requiere datos previos.
    op.execute(
        "ALTER TABLE producto ADD CONSTRAINT fk_producto__proveedor "
        "FOREIGN KEY (organizacion_id, proveedor_id) "
        "REFERENCES proveedor (organizacion_id, id) NOT VALID"
    )
    op.execute("ALTER TABLE producto VALIDATE CONSTRAINT fk_producto__proveedor")

    # --- Permisos de app_runtime (D10; ADR-020) ----------------------------
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON proveedor TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT ON costo_informado TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"REVOKE SELECT, INSERT ON costo_informado FROM {ROL_RUNTIME}")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON proveedor FROM {ROL_RUNTIME}")

    # Un producto puede tener `proveedor_id` apuntando a una fila real de
    # `proveedor` (asignada después del `upgrade`, no solo al provisorio de
    # la migración 2): hay que desasignarlo ANTES de borrar la FK y la
    # tabla, si no la base vuelve al estado del change 05 con un
    # `proveedor_id` colgando hacia una tabla que ya no existe.
    op.execute("UPDATE producto SET proveedor_id = NULL WHERE proveedor_id IS NOT NULL")

    op.drop_constraint("fk_producto__proveedor", "producto", type_="foreignkey")

    op.drop_index("ix_costo_informado__producto_vigencia", table_name="costo_informado")
    op.drop_table("costo_informado")

    op.drop_index("ux_proveedor__cuit", table_name="proveedor")
    op.drop_table("proveedor")
