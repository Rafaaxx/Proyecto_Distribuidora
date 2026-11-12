"""cobranzas: cobranza, cobranza_medio, cobranza_anulacion, motivos de anulacion y
codigos de observacion de medio

Revision ID: d7e8f9a0b1c2
Revises: b5c6d7e8f9a0
Create Date: 2026-10-15 00:00:00.000000

Change 17 (`design.md` D6, D13, D16, `docs/03-modelo-de-datos.md` §12), una sola revision:

- `cobranza`: `03` §12 mas `observacion` (D2) y las columnas de operacion de `03` §2.3.
  `venta_id` nulable y **sin FK** hasta el change 18a (la tabla `venta` no existe; el 18a la
  agrega y aborta si hay filas con venta). `jornada_id` nulable con FK compuesta. `CHECK` de
  `estado`, `origen`, coherencia `origen` <-> `venta_id` e `importe > 0`.
- `cobranza_medio`: `03` §12 mas `orden` (la posicion de la linea, desde 0, que el detalle de
  `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` cita, D13), `importe > 0` y `referencia` nulable.
- `cobranza_anulacion`: `cobranza_id` unico (la base impide anular dos veces, D16), motivo y
  observacion, y las columnas de operacion.
- Todas con `UNIQUE (organizacion_id, id)` y FK compuestas con `organizacion_id` (INV-02,
  INV-21).
- Permisos de `app_runtime` (INV-05, TR-06): `SELECT, INSERT` sobre las tres tablas y `UPDATE`
  **solo** de `cobranza.estado`; nunca `DELETE`.
- Siembra idempotente (D6) de los tres motivos de `ANULACION_COBRANZA`, en cada organizacion
  que no tenga ninguno de ese ambito. El ambito ya esta en `ck_motivo__ambito`.
- `ck_observacion__codigo` suma `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` (D13, SYN-07).

Tablas nuevas y vacias: no se usan indices concurrentes (mismo criterio que `c0d1e2f3a4b5`).

`downgrade` borra las tres tablas y los motivos de `ANULACION_COBRANZA` que nada referencia,
y vuelve el `CHECK` de codigos atras: **pierde las cobranzas, sus medios y anulaciones y los
motivos por diseno** (D16; `04` §2.1 punto 4: "sube y baja limpia" es correr sin errores, no
que los datos de negocio sobrevivan un rollback). Aborta con un mensaje claro si hay
observaciones `MEDIO_INACTIVO` o `REFERENCIA_FALTANTE`, porque dejarian de cumplir el `CHECK`.
La perdida esta escrita como asercion explicita en
`backend/tests/integration/test_cobranzas_migracion.py` (tarea 3.3).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "b5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

AMBITO = "ANULACION_COBRANZA"
MOTIVOS = ("Error de carga", "Pago rechazado o no acreditado", "Otro")

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
)
CODIGOS_NUEVOS = ("MEDIO_INACTIVO", "REFERENCIA_FALTANTE")


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
        "cobranza",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("cliente_id", sa.Uuid(), nullable=False),
        sa.Column("venta_id", sa.Uuid(), nullable=True),
        sa.Column("origen", sa.Text(), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_cobranza"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cobranza__organizacion"
        ),
        _fk("cobranza", "cliente", "cliente_id", "cliente"),
        _fk("cobranza", "jornada", "jornada_id", "jornada"),
        _fk("cobranza", "usuario", "usuario_id", "usuario"),
        _fk("cobranza", "dispositivo", "dispositivo_id", "dispositivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_cobranza__org_id"),
        sa.CheckConstraint("importe > 0", name="ck_cobranza__importe"),
        sa.CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_cobranza__estado"),
        sa.CheckConstraint("origen IN ('VENTA','INDEPENDIENTE')", name="ck_cobranza__origen"),
        sa.CheckConstraint(
            "(origen = 'VENTA' AND venta_id IS NOT NULL) "
            "OR (origen = 'INDEPENDIENTE' AND venta_id IS NULL)",
            name="ck_cobranza__origen_venta",
        ),
    )
    op.create_index(
        "ix_cobranza__occurred_at",
        "cobranza",
        ["organizacion_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_cobranza__cliente",
        "cobranza",
        ["organizacion_id", "cliente_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_cobranza__jornada", "cobranza", ["organizacion_id", "jornada_id"])

    op.create_table(
        "cobranza_medio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("cobranza_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("medio_pago_id", sa.Uuid(), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("referencia", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_cobranza_medio"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cobranza_medio__organizacion"
        ),
        _fk("cobranza_medio", "cobranza", "cobranza_id", "cobranza"),
        _fk("cobranza_medio", "medio_pago", "medio_pago_id", "medio_pago"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_cobranza_medio__org_id"),
        sa.UniqueConstraint(
            "organizacion_id", "cobranza_id", "orden", name="ux_cobranza_medio__cobranza_orden"
        ),
        sa.CheckConstraint("importe > 0", name="ck_cobranza_medio__importe"),
        sa.CheckConstraint("orden >= 0", name="ck_cobranza_medio__orden"),
    )

    op.create_table(
        "cobranza_anulacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("cobranza_id", sa.Uuid(), nullable=False),
        sa.Column("motivo_id", sa.Uuid(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_cobranza_anulacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_cobranza_anulacion__organizacion"
        ),
        _fk("cobranza_anulacion", "cobranza", "cobranza_id", "cobranza"),
        _fk("cobranza_anulacion", "motivo", "motivo_id", "motivo"),
        _fk("cobranza_anulacion", "usuario", "usuario_id", "usuario"),
        _fk("cobranza_anulacion", "dispositivo", "dispositivo_id", "dispositivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_cobranza_anulacion__org_id"),
        sa.UniqueConstraint(
            "organizacion_id", "cobranza_id", name="ux_cobranza_anulacion__cobranza"
        ),
    )

    # INV-05, TR-06, D16: nunca `DELETE`; `UPDATE` solo del estado de la cobranza; medios y
    # anulaciones, de solo insercion.
    for tabla in ("cobranza", "cobranza_medio", "cobranza_anulacion"):
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE (estado) ON cobranza TO {ROL_RUNTIME}")

    _cambiar_ck_observacion_codigo((*CODIGOS_PREVIOS, *CODIGOS_NUEVOS))
    _sembrar_motivos()


def _sembrar_motivos() -> None:
    """D6: tres motivos de `ANULACION_COBRANZA` en cada organizacion que no tenga ninguno de
    ese ambito. Idempotente: una organizacion con motivos propios (o ya sembrada) no se toca."""
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


def _verificar_que_no_hay_observaciones_de_medio() -> None:
    """D13 punto 6: aborta con un mensaje claro si hay observaciones con los codigos nuevos.
    Sin esta comprobacion, `ADD CONSTRAINT` fallaria con un `CheckViolation` opaco."""
    conexion = op.get_bind()
    filas = conexion.execute(
        sa.text(
            "SELECT codigo, count(*) FROM observacion "
            "WHERE codigo IN ('MEDIO_INACTIVO', 'REFERENCIA_FALTANTE') GROUP BY codigo "
            "ORDER BY codigo"
        )
    ).all()
    if filas:
        detalle = ", ".join(f"{codigo}: {cantidad}" for codigo, cantidad in filas)
        raise RuntimeError(
            f"La revisión {revision} no puede bajar (design.md D13 punto 6): hay observaciones "
            f"con codigos que la revision anterior no admite ({detalle}). Resolvelas o "
            "eliminalas antes de volver a intentarlo; la revisión no las modifica."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_no_hay_observaciones_de_medio()

    op.drop_table("cobranza_anulacion")
    op.drop_table("cobranza_medio")
    op.drop_index("ix_cobranza__jornada", table_name="cobranza")
    op.drop_index("ix_cobranza__cliente", table_name="cobranza")
    op.drop_index("ix_cobranza__occurred_at", table_name="cobranza")
    op.drop_table("cobranza")

    _cambiar_ck_observacion_codigo(CODIGOS_PREVIOS)

    # Se borra TODO motivo del ambito que nada referencia (el libro de auditoria y el de
    # stock, de solo insercion, guardan `motivo_id`): el ambito sigue en `ck_motivo__ambito`,
    # asi que un motivo con referencias queda donde esta.
    op.execute(
        sa.text(
            "DELETE FROM motivo m WHERE m.ambito = :ambito "
            "AND NOT EXISTS (SELECT 1 FROM auditoria a "
            "WHERE a.organizacion_id = m.organizacion_id AND a.motivo_id = m.id) "
            "AND NOT EXISTS (SELECT 1 FROM stock_movimiento s "
            "WHERE s.organizacion_id = m.organizacion_id AND s.motivo_id = m.id)"
        ).bindparams(sa.bindparam("ambito", AMBITO))
    )
