"""catalogo: categoria, marca, producto, presentacion

Revision ID: c1d2e3f4a5b6
Revises: a7b8c9d0e1f2
Create Date: 2026-09-22 00:00:00.000000

Change 05 (`design.md` Migration Plan, `03` §5): crea las cuatro tablas del
catálogo, todas maestras (`03` §2.3: `actualizado_en`/`actualizado_por_id`
además de `id`/`organizacion_id`/`creado_en`).

- `categoria`, `marca`: `UNIQUE (organizacion_id, nombre)` (CAT-01).
- `producto`: `UNIQUE (organizacion_id, codigo)` (CAT-01); FK compuestas a
  `categoria`, `marca` (opcional) y `alicuota_iva` (`configuracion`, change
  02); índices `ix_producto__categoria`, `ix_producto__marca` para los
  filtros de listado (`02` §11) y el chequeo de D11 ("categoría con
  productos activos"). `proveedor_id` es `uuid` NULABLE y SIN FK (D1
  opción A, aprobada 2026-09-22): `proveedor` no existe hasta el change 06,
  que agrega la FK compuesta y el `NOT NULL` (deuda nominada, tarea 12.1).
- `presentacion`: FK compuesta a `producto`; `ux_presentacion__referencia`
  parcial (`WHERE es_referencia`, CAT-03: a lo sumo una referencia por
  producto); `ck_presentacion__referencia_venta` (una referencia siempre se
  usa en venta); `ck_presentacion__unidades_base` (entero `>= 1`, CAT-02,
  INV-04); `ix_presentacion__producto` para el detalle de un producto.

`GRANT SELECT, INSERT, UPDATE` a `app_runtime` sobre las cuatro tablas, sin
`DELETE` (ADR-020, CAT-05: se desactiva, nunca se borra). Tablas nuevas y
vacías: no se usan índices concurrentes (`design.md` Migration Plan).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"
_TABLAS = ("categoria", "marca", "producto", "presentacion")


def upgrade() -> None:
    """Upgrade schema."""
    # --- categoria (CAT-01, CAT-05) ---------------------------------------
    op.create_table(
        "categoria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_categoria"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_categoria__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_categoria__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_categoria__org_id"),
        sa.UniqueConstraint("organizacion_id", "nombre", name="ux_categoria__nombre"),
    )

    # --- marca (CAT-01, CAT-05) --------------------------------------------
    op.create_table(
        "marca",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_marca"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_marca__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_marca__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_marca__org_id"),
        sa.UniqueConstraint("organizacion_id", "nombre", name="ux_marca__nombre"),
    )

    # --- producto (CAT-01 a CAT-06) ----------------------------------------
    op.create_table(
        "producto",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("categoria_id", sa.Uuid(), nullable=False),
        sa.Column("marca_id", sa.Uuid(), nullable=True),
        # D1 opcion A (aprobada 2026-09-22): nulable, SIN FK. El change 06
        # agrega la FK compuesta a `proveedor` y el `NOT NULL` (deuda
        # nominada, tasks.md 12.1: `NOT VALID` + `VALIDATE` + `SET NOT NULL`).
        sa.Column("proveedor_id", sa.Uuid(), nullable=True),
        sa.Column("unidad_base", sa.Text(), nullable=False),
        sa.Column("alicuota_id", sa.Uuid(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_producto"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_producto__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "categoria_id"],
            ["categoria.organizacion_id", "categoria.id"],
            name="fk_producto__categoria",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "marca_id"],
            ["marca.organizacion_id", "marca.id"],
            name="fk_producto__marca",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "alicuota_id"],
            ["alicuota_iva.organizacion_id", "alicuota_iva.id"],
            name="fk_producto__alicuota",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_producto__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_producto__org_id"),
        sa.UniqueConstraint("organizacion_id", "codigo", name="ux_producto__codigo"),
    )
    op.create_index("ix_producto__categoria", "producto", ["organizacion_id", "categoria_id"])
    op.create_index("ix_producto__marca", "producto", ["organizacion_id", "marca_id"])

    # --- presentacion (CAT-02, CAT-03, CAT-04) -----------------------------
    op.create_table(
        "presentacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("unidades_base", sa.Integer(), nullable=False),
        sa.Column("usar_en_venta", sa.Boolean(), nullable=False),
        sa.Column("usar_en_compra", sa.Boolean(), nullable=False),
        sa.Column("es_referencia", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_presentacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_presentacion__organizacion"
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "producto_id"],
            ["producto.organizacion_id", "producto.id"],
            name="fk_presentacion__producto",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id", "actualizado_por_id"],
            ["usuario.organizacion_id", "usuario.id"],
            name="fk_presentacion__actualizado_por",
        ),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_presentacion__org_id"),
        sa.CheckConstraint("unidades_base >= 1", name="ck_presentacion__unidades_base"),
        sa.CheckConstraint(
            "NOT es_referencia OR usar_en_venta", name="ck_presentacion__referencia_venta"
        ),
    )
    op.create_index("ix_presentacion__producto", "presentacion", ["organizacion_id", "producto_id"])
    op.create_index(
        "ux_presentacion__referencia",
        "presentacion",
        ["organizacion_id", "producto_id"],
        unique=True,
        postgresql_where=sa.text("es_referencia"),
    )

    # --- Permisos de app_runtime (design.md, Migration Plan; ADR-020) -----
    for tabla in _TABLAS:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {tabla} TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema."""
    for tabla in _TABLAS:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE ON {tabla} FROM {ROL_RUNTIME}")

    op.drop_index("ux_presentacion__referencia", table_name="presentacion")
    op.drop_index("ix_presentacion__producto", table_name="presentacion")
    op.drop_table("presentacion")

    op.drop_index("ix_producto__marca", table_name="producto")
    op.drop_index("ix_producto__categoria", table_name="producto")
    op.drop_table("producto")

    op.drop_table("marca")
    op.drop_table("categoria")
