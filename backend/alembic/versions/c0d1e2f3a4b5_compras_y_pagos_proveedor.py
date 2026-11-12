"""compras y pagos a proveedor: compra, compra_linea, pago_proveedor, pago_proveedor_medio

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-10-02 00:00:00.000000

Change 11 (`design.md` Migration Plan, D8, D12): crea las cuatro tablas de
`docs/03-modelo-de-datos.md` §6 con los agregados de D12 y siembra los motivos de
`ANULACION_COMPRA` (D8).

- `compra`: `03` §6 más `total_factura` (D1), `numero_comprobante` y `observacion`
  (D13), y las columnas de operación de `03` §2.3. `CHECK` de `condicion`, `estado`,
  `total_neto >= 0`, `total_factura > 0` y coherencia "anulada si y solo si tiene
  motivo, momento y usuario".
- `compra_linea`: `03` §6 más `orden` (el mismo producto puede repetirse, D5) y
  `alicuota_aplicada` congelada (como `costo_informado`). `CHECK` de rangos; la
  `cantidad` es `numeric(14,3)` (`03` §2.2, solo en compras) y la `cantidad_base` es
  `integer` (INV-04).
- `pago_proveedor`: `03` §6 más `origen` (`COMPRA`, `INDEPENDIENTE`), `compra_id`
  (único si no es nulo, FK compuesta), y la anulación (`anulado_en`,
  `anulado_por_id`, `anulacion_motivo_id` nulable: el change 12 decide su motivo).
  El estado es `CONFIRMADA` o `ANULADA` (`01` §21).
- `pago_proveedor_medio`: `03` §6, con `importe > 0` y `referencia` nulable.
- Todas con `UNIQUE (organizacion_id, id)` y FK compuestas con `organizacion_id`
  (INV-02, INV-21).
- Permisos de `app_runtime` (D12-A, INV-05): `SELECT, INSERT` sobre las cuatro tablas
  y `UPDATE` solo por columna de estado y anulación en `compra` y `pago_proveedor`;
  nunca `DELETE`, y ni `UPDATE` en líneas ni medios.
- Motivos de D8: "Error de carga", "Devolución al proveedor" y "Otro" del ámbito
  `ANULACION_COMPRA` en cada organización que no tenga ningún motivo de ese ámbito
  (idempotente). `downgrade` los borra si nada los referencia.

Tablas nuevas y vacías: no se usan índices concurrentes (mismo criterio que
`a8b9c0d1e2f3`). No toca libros ni saldos existentes.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "c0d1e2f3a4b5"
down_revision: str | Sequence[str] | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

AMBITO = "ANULACION_COMPRA"
MOTIVOS = ("Error de carga", "Devolución al proveedor", "Otro")

_COLUMNAS_MUTABLES_COMPRA = "estado, anulacion_motivo_id, anulada_en, anulada_por_id"
_COLUMNAS_MUTABLES_PAGO = "estado, anulado_en, anulado_por_id, anulacion_motivo_id"


def _columnas_de_operacion() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "compra",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("proveedor_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_id", sa.Uuid(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("condicion", sa.Text(), nullable=False),
        sa.Column("total_neto", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_factura", sa.Numeric(14, 2), nullable=False),
        sa.Column("numero_comprobante", sa.Text(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("anulacion_motivo_id", sa.Uuid(), nullable=True),
        sa.Column("anulada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulada_por_id", sa.Uuid(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_compra"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_compra__organizacion"
        ),
        _fk("compra", "proveedor", "proveedor_id", "proveedor"),
        _fk("compra", "ubicacion", "ubicacion_id", "ubicacion"),
        _fk("compra", "usuario", "usuario_id", "usuario"),
        _fk("compra", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("compra", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        _fk("compra", "anulada_por", "anulada_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_compra__org_id"),
        sa.CheckConstraint("condicion IN ('CONTADO','CREDITO')", name="ck_compra__condicion"),
        sa.CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_compra__estado"),
        sa.CheckConstraint("total_neto >= 0", name="ck_compra__total_neto"),
        sa.CheckConstraint("total_factura > 0", name="ck_compra__total_factura"),
        sa.CheckConstraint(
            "(estado = 'ANULADA') = (anulada_en IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulada_por_id IS NOT NULL)",
            name="ck_compra__anulacion_coherente",
        ),
    )
    op.create_index(
        "ix_compra__fecha",
        "compra",
        ["organizacion_id", sa.text("fecha DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_compra__proveedor_fecha",
        "compra",
        ["organizacion_id", "proveedor_id", sa.text("fecha DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "compra_linea",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("compra_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("presentacion_id", sa.Uuid(), nullable=False),
        sa.Column("unidades_presentacion", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 3), nullable=False),
        sa.Column("cantidad_base", sa.Integer(), nullable=False),
        sa.Column("valor_presentacion", sa.Numeric(14, 2), nullable=False),
        sa.Column("incluye_iva", sa.Boolean(), nullable=False),
        sa.Column("bonificacion", sa.Numeric(9, 6), nullable=False),
        sa.Column("alicuota_aplicada", sa.Numeric(9, 6), nullable=False),
        sa.Column("costo_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("importe_neto", sa.Numeric(14, 2), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_compra_linea"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_compra_linea__organizacion"
        ),
        _fk("compra_linea", "compra", "compra_id", "compra"),
        _fk("compra_linea", "producto", "producto_id", "producto"),
        _fk("compra_linea", "presentacion", "presentacion_id", "presentacion"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_compra_linea__org_id"),
        sa.UniqueConstraint(
            "organizacion_id", "compra_id", "orden", name="ux_compra_linea__compra_orden"
        ),
        sa.CheckConstraint("orden >= 1", name="ck_compra_linea__orden"),
        sa.CheckConstraint("unidades_presentacion > 0", name="ck_compra_linea__unidades"),
        sa.CheckConstraint("cantidad > 0", name="ck_compra_linea__cantidad"),
        sa.CheckConstraint("cantidad_base > 0", name="ck_compra_linea__cantidad_base"),
        sa.CheckConstraint("valor_presentacion > 0", name="ck_compra_linea__valor"),
        sa.CheckConstraint(
            "bonificacion >= 0 AND bonificacion < 1", name="ck_compra_linea__bonificacion"
        ),
        sa.CheckConstraint("alicuota_aplicada >= 0", name="ck_compra_linea__alicuota"),
        sa.CheckConstraint("costo_base > 0", name="ck_compra_linea__costo_base"),
        sa.CheckConstraint("importe_neto >= 0", name="ck_compra_linea__importe_neto"),
    )
    op.create_index(
        "ix_compra_linea__presentacion", "compra_linea", ["organizacion_id", "presentacion_id"]
    )

    op.create_table(
        "pago_proveedor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("proveedor_id", sa.Uuid(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("origen", sa.Text(), nullable=False),
        sa.Column("compra_id", sa.Uuid(), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_por_id", sa.Uuid(), nullable=True),
        sa.Column("anulacion_motivo_id", sa.Uuid(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_pago_proveedor"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_pago_proveedor__organizacion"
        ),
        _fk("pago_proveedor", "proveedor", "proveedor_id", "proveedor"),
        _fk("pago_proveedor", "compra", "compra_id", "compra"),
        _fk("pago_proveedor", "usuario", "usuario_id", "usuario"),
        _fk("pago_proveedor", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("pago_proveedor", "anulado_por", "anulado_por_id", "usuario"),
        _fk("pago_proveedor", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_pago_proveedor__org_id"),
        sa.CheckConstraint("importe > 0", name="ck_pago_proveedor__importe"),
        sa.CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_pago_proveedor__estado"),
        sa.CheckConstraint(
            "origen IN ('COMPRA','INDEPENDIENTE')", name="ck_pago_proveedor__origen"
        ),
        sa.CheckConstraint(
            "(origen = 'COMPRA' AND compra_id IS NOT NULL) "
            "OR (origen = 'INDEPENDIENTE' AND compra_id IS NULL)",
            name="ck_pago_proveedor__origen_compra",
        ),
        sa.CheckConstraint(
            "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL) "
            "AND (anulacion_motivo_id IS NULL OR anulado_en IS NOT NULL)",
            name="ck_pago_proveedor__anulacion_coherente",
        ),
    )
    op.create_index(
        "ux_pago_proveedor__compra",
        "pago_proveedor",
        ["organizacion_id", "compra_id"],
        unique=True,
        postgresql_where=sa.text("compra_id IS NOT NULL"),
    )

    op.create_table(
        "pago_proveedor_medio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("pago_id", sa.Uuid(), nullable=False),
        sa.Column("medio_pago_id", sa.Uuid(), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("referencia", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_pago_proveedor_medio"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_pago_proveedor_medio__organizacion"
        ),
        _fk("pago_proveedor_medio", "pago", "pago_id", "pago_proveedor"),
        _fk("pago_proveedor_medio", "medio_pago", "medio_pago_id", "medio_pago"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_pago_proveedor_medio__org_id"),
        sa.CheckConstraint("importe > 0", name="ck_pago_proveedor_medio__importe"),
    )
    op.create_index(
        "ix_pago_proveedor_medio__pago", "pago_proveedor_medio", ["organizacion_id", "pago_id"]
    )

    # D12-A, INV-05: nunca `DELETE`; `UPDATE` solo, por columna, del estado y la
    # anulación; líneas y medios de solo inserción.
    for tabla in ("compra", "pago_proveedor", "compra_linea", "pago_proveedor_medio"):
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ({_COLUMNAS_MUTABLES_COMPRA}) ON compra TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ({_COLUMNAS_MUTABLES_PAGO}) ON pago_proveedor TO {ROL_RUNTIME}")

    _sembrar_motivos()


def _sembrar_motivos() -> None:
    """D8: tres motivos de `ANULACION_COMPRA` en cada organización que no tenga
    ninguno de ese ámbito. Idempotente: una organización con motivos propios (o ya
    sembrada) no se toca."""
    conexion = op.get_bind()
    organizaciones = (
        conexion.execute(
            sa.text(
                "SELECT o.id FROM organizacion o WHERE NOT EXISTS ("
                "SELECT 1 FROM motivo m WHERE m.organizacion_id = o.id AND m.ambito = :ambito)"
            ),
            {"ambito": AMBITO},
        )
        .scalars()
        .all()
    )
    momento = datetime.now(UTC)
    for organizacion_id in organizaciones:
        for nombre in MOTIVOS:
            conexion.execute(
                sa.text(
                    "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, "
                    "creado_en, actualizado_en) "
                    "VALUES (:id, :org, :ambito, :nombre, true, :momento, :momento)"
                ),
                {
                    "id": nuevo_id(),
                    "org": organizacion_id,
                    "ambito": AMBITO,
                    "nombre": nombre,
                    "momento": momento,
                },
            )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pago_proveedor_medio__pago", table_name="pago_proveedor_medio")
    op.drop_table("pago_proveedor_medio")
    op.drop_index("ux_pago_proveedor__compra", table_name="pago_proveedor")
    op.drop_table("pago_proveedor")
    op.drop_index("ix_compra_linea__presentacion", table_name="compra_linea")
    op.drop_table("compra_linea")
    op.drop_index("ix_compra__proveedor_fecha", table_name="compra")
    op.drop_index("ix_compra__fecha", table_name="compra")
    op.drop_table("compra")

    # Los motivos sembrados se borran solo si nada los referencia (el libro de
    # auditoría y el de stock guardan `motivo_id`).
    op.execute(
        sa.text(
            "DELETE FROM motivo m WHERE m.ambito = :ambito AND m.nombre = ANY(:nombres) "
            "AND NOT EXISTS (SELECT 1 FROM auditoria a "
            "WHERE a.organizacion_id = m.organizacion_id AND a.motivo_id = m.id) "
            "AND NOT EXISTS (SELECT 1 FROM stock_movimiento s "
            "WHERE s.organizacion_id = m.organizacion_id AND s.motivo_id = m.id)"
        ).bindparams(
            sa.bindparam("ambito", AMBITO),
            sa.bindparam("nombres", list(MOTIVOS), type_=sa.ARRAY(sa.Text())),
        )
    )
