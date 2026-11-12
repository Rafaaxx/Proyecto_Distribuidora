"""rendicion de jornada: tablas `rendicion` y `rendicion_linea`, datos de la entrega en `jornada`
y observacion `JORNADA_RENDIDA`

Revision ID: d2f4a6c8e0b1
Revises: b7d3f1a9c2e4
Create Date: 2026-11-04 00:00:00.000000

Change 24 (`design.md` D1, D4, D5, D7; `03` §9), una sola revision:

- `rendicion` (una por jornada, `UNIQUE (organizacion_id, jornada_id)`) y `rendicion_linea` (una
  por producto contado, `UNIQUE (organizacion_id, rendicion_id, producto_id)`), con FK compuestas
  que incluyen `organizacion_id` (INV-02). La linea congela el desglose del esperado (al abrir,
  ingresos, ventas, anulaciones, otros), lo contado, la diferencia y el costo unitario con que se
  valorizo (`numeric(18,6)`, nulo si el producto no tenia promedio, D5). `CHECK`s:
  `diferencia = contada - esperada`, `esperada = al abrir + ingresos - ventas + anulaciones +
  otros` y `contada >= 0` (los otros componentes pueden ser cualquier entero: el stock negativo
  esta permitido, STK-06).
- `jornada` suma `entregada_en`, `entrega_occurred_at` y `entrega_secuencia` (nulas juntas,
  `ck_jornada__entrega_coherente`). Se admiten en cualquier estado: una jornada entregada puede
  rendirse, cerrarse o liberarse (RUT-09) sin perder el dato de la entrega. Las jornadas
  anteriores quedan sin entrega (D8): no se modifica ninguna fila.
- `ck_observacion__codigo` suma `JORNADA_RENDIDA` (D7, SYN-07).
- `app_runtime`: `SELECT, INSERT` en las dos tablas nuevas (sin `UPDATE` ni `DELETE`, INV-05) y
  `UPDATE` solo de las tres columnas nuevas de `jornada`.

`downgrade` quita las dos tablas, las tres columnas y vuelve el `CHECK` de observaciones: **pierde
por diseno** las rendiciones y las entregas. Como el libro de la rendicion es de solo insercion y
la entrega es un dato del teléfono que no se reconstruye, ABORTA con un mensaje claro, sin tocar
nada, si hay alguna rendicion, alguna jornada entregada o alguna observacion `JORNADA_RENDIDA`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2f4a6c8e0b1"
down_revision: str | Sequence[str] | None = "b7d3f1a9c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

CODIGOS_PREVIOS = (
    "STOCK_NEGATIVO",
    "EXCESO_CREDITO_ADVERTIDO",
    "EXCESO_CREDITO_AUTORIZADO_OFFLINE",
    "EXCESO_CREDITO_DETECTADO_SYNC",
    "LISTA_NO_VIGENTE",
    "DESCUENTO_DIFIERE",
    "CLIENTE_NO_HABILITADO",
    "PERMISO_REVOCADO",
    "JORNADA_LIBERADA",
    "ANULACION_COMPRA_SIN_RECALCULO",
    "MEDIO_INACTIVO",
    "REFERENCIA_FALTANTE",
    "VENTA_SIN_COSTO",
    "CONSUMIDOR_FINAL_CON_DEUDA",
    "UBICACION_TOMADA_AL_SINCRONIZAR",
    "AUTORIZACION_OFFLINE",
)
CODIGO_NUEVO = "JORNADA_RENDIDA"

COLUMNAS_DE_ENTREGA = ("entregada_en", "entrega_occurred_at", "entrega_secuencia")


def _fk(tabla: str, nombre: str, columna: str, destino: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


def _cambiar_ck_observacion_codigo(codigos: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE observacion DROP CONSTRAINT ck_observacion__codigo")
    op.execute(
        "ALTER TABLE observacion ADD CONSTRAINT ck_observacion__codigo CHECK (codigo IN ("
        + ", ".join(f"'{codigo}'" for codigo in codigos)
        + "))"
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rendicion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rendicion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_rendicion__organizacion"
        ),
        _fk("rendicion", "jornada", "jornada_id", "jornada"),
        _fk("rendicion", "usuario", "usuario_id", "usuario"),
        _fk("rendicion", "dispositivo", "dispositivo_id", "dispositivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_rendicion__org_id"),
        sa.UniqueConstraint("organizacion_id", "jornada_id", name="ux_rendicion__jornada"),
        sa.CheckConstraint(
            "observacion IS NULL OR char_length(observacion) BETWEEN 1 AND 500",
            name="ck_rendicion__observacion",
        ),
    )

    op.create_table(
        "rendicion_linea",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("rendicion_id", sa.Uuid(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("stock_al_abrir", sa.Integer(), nullable=False),
        sa.Column("ingresos", sa.Integer(), nullable=False),
        sa.Column("ventas", sa.Integer(), nullable=False),
        sa.Column("anulaciones", sa.Integer(), nullable=False),
        sa.Column("otros", sa.Integer(), nullable=False),
        sa.Column("cantidad_esperada", sa.Integer(), nullable=False),
        sa.Column("cantidad_contada", sa.Integer(), nullable=False),
        sa.Column("diferencia", sa.Integer(), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(18, 6), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_rendicion_linea"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_rendicion_linea__organizacion"
        ),
        _fk("rendicion_linea", "rendicion", "rendicion_id", "rendicion"),
        _fk("rendicion_linea", "producto", "producto_id", "producto"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_rendicion_linea__org_id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "rendicion_id",
            "producto_id",
            name="ux_rendicion_linea__rendicion_producto",
        ),
        sa.CheckConstraint("cantidad_contada >= 0", name="ck_rendicion_linea__contada"),
        sa.CheckConstraint(
            "diferencia = cantidad_contada - cantidad_esperada",
            name="ck_rendicion_linea__diferencia",
        ),
        sa.CheckConstraint(
            "cantidad_esperada = stock_al_abrir + ingresos - ventas + anulaciones + otros",
            name="ck_rendicion_linea__esperada",
        ),
    )

    op.add_column("jornada", sa.Column("entregada_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jornada", sa.Column("entrega_occurred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("jornada", sa.Column("entrega_secuencia", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_jornada__entrega_coherente",
        "jornada",
        "(entregada_en IS NULL) = (entrega_occurred_at IS NULL) "
        "AND (entregada_en IS NULL) = (entrega_secuencia IS NULL)",
    )

    _cambiar_ck_observacion_codigo((*CODIGOS_PREVIOS, CODIGO_NUEVO))

    # INV-05: las dos tablas son de solo insercion; la jornada solo suma el `UPDATE` de la
    # entrega (las demas columnas mutables no cambian).
    op.execute(f"GRANT SELECT, INSERT ON rendicion, rendicion_linea TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ({', '.join(COLUMNAS_DE_ENTREGA)}) ON jornada TO {ROL_RUNTIME}")


def _verificar_que_no_se_pierde_nada() -> None:
    """Aborta, sin tocar nada, si bajar perderia rendiciones, entregas u observaciones."""
    conexion = op.get_bind()
    rendiciones = conexion.execute(sa.text("SELECT count(*) FROM rendicion")).scalar_one()
    entregas = conexion.execute(
        sa.text("SELECT count(*) FROM jornada WHERE entregada_en IS NOT NULL")
    ).scalar_one()
    observaciones = conexion.execute(
        sa.text("SELECT count(*) FROM observacion WHERE codigo = :codigo"),
        {"codigo": CODIGO_NUEVO},
    ).scalar_one()
    if rendiciones or entregas or observaciones:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: hay {rendiciones} rendicion(es), "
            f"{entregas} jornada(s) con entrega registrada y {observaciones} observación(es) "
            f"{CODIGO_NUEVO}. La rendición es un libro de solo inserción (INV-05) y la entrega "
            "es un dato del teléfono que no se reconstruye: bajar los perdería. No se modificó "
            "nada; resolvelo a mano antes de volver a intentar."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_no_se_pierde_nada()

    _cambiar_ck_observacion_codigo(CODIGOS_PREVIOS)
    op.drop_constraint("ck_jornada__entrega_coherente", "jornada", type_="check")
    for columna in reversed(COLUMNAS_DE_ENTREGA):
        op.drop_column("jornada", columna)
    op.drop_table("rendicion_linea")
    op.drop_table("rendicion")
