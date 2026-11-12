"""reglas de descuento: regla_descuento y regla_descuento_alcance

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-10-14 00:00:00.000000

Change 16 (`design.md` D17 opcion A), una sola revision, solo aditiva:

- `regla_descuento` (`03` §11 mas lo que suma D17): en lugar de `accion_valor`, dos columnas
  `accion_porcentaje numeric(9,6)` y `accion_importe numeric(14,2)` con un `CHECK` que exige
  exactamente la que corresponde a `accion_tipo` (INV-03, `CLAUDE.md` §4) y otros dos que fijan
  el dominio de cada una (porcentaje mayor que 0 y hasta 1; importe mayor que 0); `CHECK` de
  catalogo en `tipo`, `medida`, `operador`, `accion_tipo` y `estado` (`VENCIDA` es derivado y no
  se almacena, D16); `umbral numeric(14,4) > 0`; `prioridad >= 1`;
  `vigencia_hasta > vigencia_desde`; una regla que no es `BORRADOR` tiene `vigencia_desde`;
  `UNIQUE (organizacion_id, id)`; `actualizado_en` y `actualizado_por_id`; indice de listado
  por organizacion y estado.
- `regla_descuento_alcance`: `alcance_tipo` + `alcance_id` con columnas generadas
  `producto_id`, `categoria_id` y `marca_id` y sus claves foraneas compuestas (precedente de
  `regla_margen`, ADR-035, INV-02), clave foranea compuesta a la regla y unico por regla, tipo y
  entidad. "Una regla de operacion no tiene alcances y una de alcance tiene al menos uno" lo
  garantiza el servicio (no es expresable como `CHECK` de fila).
- `app_runtime` (TR-06): `SELECT, INSERT, UPDATE` en `regla_descuento` (nunca `DELETE`);
  `SELECT, INSERT, DELETE` en `regla_descuento_alcance` (sin `UPDATE`): el `DELETE` solo lo usa
  el servicio al reemplazar los alcances de un borrador.

`downgrade` borra las dos tablas: **pierde por diseno las reglas y sus alcances**; como ninguna
venta las referencia todavia (la venta llega en el change 18b) no hay perdida de historia. No
modifica ninguna fila de otras tablas. La perdida esta escrita como asercion explicita en
`backend/tests/integration/test_descuentos_migracion.py` (tarea 5.3).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

_TIPOS = "'VOLUMEN_OPERACION','VOLUMEN_ALCANCE'"
_MEDIDAS = "'CAJAS_EQUIVALENTES','UNIDADES_BASE','IMPORTE_BRUTO'"
_OPERADORES = "'GTE','GT'"
_ACCIONES = "'PORCENTAJE','IMPORTE_FIJO'"
_ESTADOS = "'BORRADOR','ACTIVA','PAUSADA'"
_ALCANCES = "'PRODUCTO','CATEGORIA','MARCA'"

_ACCION_EXACTA = (
    "(accion_tipo = 'PORCENTAJE' AND accion_porcentaje IS NOT NULL AND accion_importe IS NULL) "
    "OR (accion_tipo = 'IMPORTE_FIJO' AND accion_importe IS NOT NULL "
    "AND accion_porcentaje IS NULL)"
)


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> sa.ForeignKeyConstraint:
    """Clave foranea compuesta que incluye `organizacion_id` (INV-02, `03` §2.4)."""
    return sa.ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


def _generada(alcance: str) -> sa.Computed:
    return sa.Computed(f"CASE WHEN alcance_tipo = '{alcance}' THEN alcance_id END", persisted=True)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "regla_descuento",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("medida", sa.Text(), nullable=False),
        sa.Column("operador", sa.Text(), nullable=False),
        sa.Column("umbral", sa.Numeric(14, 4), nullable=False),
        sa.Column("accion_tipo", sa.Text(), nullable=False),
        sa.Column("accion_porcentaje", sa.Numeric(9, 6), nullable=True),
        sa.Column("accion_importe", sa.Numeric(14, 2), nullable=True),
        sa.Column("prioridad", sa.Integer(), nullable=False),
        sa.Column("acumulable", sa.Boolean(), nullable=False),
        sa.Column("vigencia_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vigencia_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_por_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_regla_descuento"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_regla_descuento__organizacion"
        ),
        _fk("regla_descuento", "actualizado_por", "actualizado_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_regla_descuento__org_id"),
        sa.CheckConstraint(f"tipo IN ({_TIPOS})", name="ck_regla_descuento__tipo"),
        sa.CheckConstraint(f"medida IN ({_MEDIDAS})", name="ck_regla_descuento__medida"),
        sa.CheckConstraint(f"operador IN ({_OPERADORES})", name="ck_regla_descuento__operador"),
        sa.CheckConstraint(f"accion_tipo IN ({_ACCIONES})", name="ck_regla_descuento__accion_tipo"),
        sa.CheckConstraint(f"estado IN ({_ESTADOS})", name="ck_regla_descuento__estado"),
        sa.CheckConstraint(_ACCION_EXACTA, name="ck_regla_descuento__accion"),
        sa.CheckConstraint(
            "accion_porcentaje IS NULL OR (accion_porcentaje > 0 AND accion_porcentaje <= 1)",
            name="ck_regla_descuento__accion_porcentaje",
        ),
        sa.CheckConstraint(
            "accion_importe IS NULL OR accion_importe > 0",
            name="ck_regla_descuento__accion_importe",
        ),
        sa.CheckConstraint("umbral > 0", name="ck_regla_descuento__umbral"),
        sa.CheckConstraint("prioridad >= 1", name="ck_regla_descuento__prioridad"),
        sa.CheckConstraint(
            "vigencia_desde IS NULL OR vigencia_hasta IS NULL OR vigencia_hasta > vigencia_desde",
            name="ck_regla_descuento__vigencia",
        ),
        sa.CheckConstraint(
            "estado = 'BORRADOR' OR vigencia_desde IS NOT NULL",
            name="ck_regla_descuento__vigencia_desde",
        ),
    )
    op.create_index(
        "ix_regla_descuento__listado",
        "regla_descuento",
        ["organizacion_id", "estado", sa.text("id DESC")],
    )

    op.create_table(
        "regla_descuento_alcance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("regla_id", sa.Uuid(), nullable=False),
        sa.Column("alcance_tipo", sa.Text(), nullable=False),
        sa.Column("alcance_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), _generada("PRODUCTO"), nullable=True),
        sa.Column("categoria_id", sa.Uuid(), _generada("CATEGORIA"), nullable=True),
        sa.Column("marca_id", sa.Uuid(), _generada("MARCA"), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_regla_descuento_alcance"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_regla_descuento_alcance__organizacion",
        ),
        _fk("regla_descuento_alcance", "regla", "regla_id", "regla_descuento"),
        _fk("regla_descuento_alcance", "producto", "producto_id", "producto"),
        _fk("regla_descuento_alcance", "categoria", "categoria_id", "categoria"),
        _fk("regla_descuento_alcance", "marca", "marca_id", "marca"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_regla_descuento_alcance__org_id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "regla_id",
            "alcance_tipo",
            "alcance_id",
            name="ux_regla_descuento_alcance__regla_entidad",
        ),
        sa.CheckConstraint(
            f"alcance_tipo IN ({_ALCANCES})", name="ck_regla_descuento_alcance__alcance_tipo"
        ),
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON regla_descuento TO {ROL_RUNTIME}")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON regla_descuento_alcance TO {ROL_RUNTIME}")


def downgrade() -> None:
    """Downgrade schema: pierde por diseno las reglas y sus alcances (ver el docstring)."""
    op.drop_table("regla_descuento_alcance")
    op.drop_table("regla_descuento")
