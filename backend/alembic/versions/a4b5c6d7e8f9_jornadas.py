"""jornadas: tabla `jornada`, sus privilegios, las dos FK heredadas y los motivos de
liberacion

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-10-09 00:00:00.000000

Change 15 (`design.md` D3, D10, D11, D13), una sola revision:

- `jornada` (`03` §9 mas lo que suma D10): `UNIQUE (organizacion_id, id)`, FK compuestas a
  `usuario`, `dispositivo`, `ubicacion` y `motivo` (INV-02), `estado` con `CHECK` de los
  cuatro valores de `01` §18, columnas de operacion de la apertura `NOT NULL`, los datos de
  la rendicion, el cierre y la liberacion nulables y un `CHECK` de coherencia por estado.
  Tres indices unicos parciales sobre `estado IN ('ABIERTA','EN_RENDICION')`: por ubicacion
  (INV-16), por dispositivo y por usuario (D3). Indice de listado.
- `app_runtime`: `SELECT, INSERT`; `UPDATE` SOLO del estado y de las columnas de transicion;
  nunca `DELETE` (INV-05, TR-06).
- Las dos FK heredadas (deudas del 04 y del 09): `stock_movimiento.jornada_id` y
  `comando.jornada_id` pasan a FK compuesta `(organizacion_id, jornada_id)` a `jornada`,
  con `NOT VALID` mas `VALIDATE` (D11). Antes se cuentan las filas con `jornada_id` no nulo:
  como `jornada` es nueva no puede haber ninguna valida, asi que si hay alguna la migracion
  ABORTA diciendo la tabla y la cantidad, sin modificar nada (TR-06).
- Se siembran, de forma idempotente, "Dispositivo perdido o averiado", "Vendedor ausente" y
  "Otro" en el ambito `LIBERACION_JORNADA` de cada organizacion que no tenga ninguno (D13,
  mismo precedente que `f3a4b5c6d7e8`). `ck_motivo__ambito` no cambia: el ambito ya existe.

`downgrade` quita las dos FK, borra la tabla y los motivos sembrados: **pierde por diseno**
las jornadas, las dos FK y esos motivos. NO modifica ninguna fila de `stock_movimiento` ni de
`comando` (TR-06, D11): los movimientos y comandos que tenian `jornada_id` lo conservan, sin
referencia; por eso, subir de nuevo con esas filas presentes aborta por el conteo de D11 sin
tocar nada. Si un movimiento de stock o una fila de auditoria referencia uno de los motivos
sembrados, el `downgrade` aborta con un mensaje claro en lugar de tocar un libro de solo
insercion. La perdida esta escrita como asercion explicita en
`backend/tests/integration/test_jornadas_migracion.py` (tarea 1.5).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

AMBITO = "LIBERACION_JORNADA"
MOTIVOS = ("Dispositivo perdido o averiado", "Vendedor ausente", "Otro")

TABLAS_CON_JORNADA = ("stock_movimiento", "comando")

_COLUMNAS_MUTABLES = (
    "estado, rendida_en, rendida_por_id, cerrada_en, cerrada_por_id, liberada_en, "
    "liberada_por_id, motivo_liberacion_id, observacion_liberacion"
)

_ESTADOS_NO_CERRADOS = "estado IN ('ABIERTA','EN_RENDICION')"


def _fk(nombre: str, columna: str, destino: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_jornada__{nombre}",
    )


def _verificar_que_ninguna_fila_tiene_jornada() -> None:
    """D11: `jornada` nace vacia, asi que toda fila con `jornada_id` no nulo seria huerfana.
    Si hay alguna se aborta ANTES de crear nada, sin modificar ninguna fila."""
    conexion = op.get_bind()
    huerfanas = {
        tabla: conexion.execute(
            sa.text(f"SELECT count(*) FROM {tabla} WHERE jornada_id IS NOT NULL")
        ).scalar_one()
        for tabla in TABLAS_CON_JORNADA
    }
    detalle = ", ".join(
        f"{tabla}: {cantidad} fila(s)" for tabla, cantidad in huerfanas.items() if cantidad
    )
    if detalle:
        raise RuntimeError(
            f"La revisión {revision} no puede subir: hay filas con jornada_id no nulo ({detalle}) "
            "y la tabla jornada todavía no existe, así que serían huérfanas. No se modificó "
            "ninguna fila: revisalas a mano (stock_movimiento es un libro de solo inserción, "
            "INV-05) y volvé a intentar."
        )


def upgrade() -> None:
    """Upgrade schema."""
    _verificar_que_ninguna_fila_tiene_jornada()

    op.create_table(
        "jornada",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_id", sa.Uuid(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("abierta_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rendida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rendida_por_id", sa.Uuid(), nullable=True),
        sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cerrada_por_id", sa.Uuid(), nullable=True),
        sa.Column("liberada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("liberada_por_id", sa.Uuid(), nullable=True),
        sa.Column("motivo_liberacion_id", sa.Uuid(), nullable=True),
        sa.Column("observacion_liberacion", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_jornada"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_jornada__organizacion"
        ),
        _fk("usuario", "usuario_id", "usuario"),
        _fk("dispositivo", "dispositivo_id", "dispositivo"),
        _fk("ubicacion", "ubicacion_id", "ubicacion"),
        _fk("rendida_por", "rendida_por_id", "usuario"),
        _fk("cerrada_por", "cerrada_por_id", "usuario"),
        _fk("liberada_por", "liberada_por_id", "usuario"),
        _fk("motivo_liberacion", "motivo_liberacion_id", "motivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_jornada__org_id"),
        sa.CheckConstraint(
            "estado IN ('ABIERTA','EN_RENDICION','CERRADA','LIBERADA')",
            name="ck_jornada__estado",
        ),
        # D10: los datos de rendicion, cierre y liberacion estan presentes si y solo si el
        # estado los implica. Una `LIBERADA` puede venir de una `ABIERTA` (sin rendicion) o
        # de una `EN_RENDICION` (con ella); una `CERRADA` siempre paso por la rendicion.
        sa.CheckConstraint(
            "(rendida_en IS NULL) = (rendida_por_id IS NULL) "
            "AND (cerrada_en IS NULL) = (cerrada_por_id IS NULL) "
            "AND (liberada_en IS NULL) = (liberada_por_id IS NULL) "
            "AND (liberada_en IS NULL) = (motivo_liberacion_id IS NULL) "
            "AND (estado = 'CERRADA') = (cerrada_en IS NOT NULL) "
            "AND (estado = 'LIBERADA') = (liberada_en IS NOT NULL) "
            "AND (estado NOT IN ('EN_RENDICION','CERRADA') OR rendida_en IS NOT NULL) "
            "AND (estado <> 'ABIERTA' OR rendida_en IS NULL) "
            "AND (observacion_liberacion IS NULL OR estado = 'LIBERADA')",
            name="ck_jornada__estado_coherente",
        ),
        sa.CheckConstraint(
            "observacion_liberacion IS NULL "
            "OR char_length(observacion_liberacion) BETWEEN 1 AND 500",
            name="ck_jornada__observacion_liberacion",
        ),
    )
    # INV-16 y D3: a lo sumo una jornada no cerrada por ubicacion, por usuario y por
    # dispositivo. Las decide la base: una segunda apertura falla por el indice. El ORDEN de
    # creacion importa: si una apertura viola varios a la vez, PostgreSQL informa el primero
    # (orden de OID del indice), y el servicio prefiere decir la ubicacion tomada, despues el
    # usuario y por ultimo el dispositivo.
    for nombre, columna in (
        ("ux_jornada__ubicacion_abierta", "ubicacion_id"),
        ("ux_jornada__usuario_abierta", "usuario_id"),
        ("ux_jornada__dispositivo_abierta", "dispositivo_id"),
    ):
        op.create_index(
            nombre,
            "jornada",
            ["organizacion_id", columna],
            unique=True,
            postgresql_where=sa.text(_ESTADOS_NO_CERRADOS),
        )
    op.create_index(
        "ix_jornada__abierta_en",
        "jornada",
        ["organizacion_id", sa.text("abierta_en DESC"), sa.text("id DESC")],
    )

    # INV-05, TR-06: nunca `DELETE`; `UPDATE` solo, por columna, del estado y la transicion.
    op.execute(f"GRANT SELECT, INSERT ON jornada TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ({_COLUMNAS_MUTABLES}) ON jornada TO {ROL_RUNTIME}")

    # D11: `NOT VALID` y despues `VALIDATE` (el conteo previo ya garantiza que valida).
    for tabla in TABLAS_CON_JORNADA:
        op.execute(
            f"ALTER TABLE {tabla} ADD CONSTRAINT fk_{tabla}__jornada "
            "FOREIGN KEY (organizacion_id, jornada_id) "
            "REFERENCES jornada (organizacion_id, id) NOT VALID"
        )
        op.execute(f"ALTER TABLE {tabla} VALIDATE CONSTRAINT fk_{tabla}__jornada")

    _sembrar_motivos()


def _sembrar_motivos() -> None:
    """D13: los tres motivos en cada organizacion que no tenga ninguno del ambito
    `LIBERACION_JORNADA`. Idempotente, como la siembra de `ANULACION_TRANSFERENCIA`."""
    conexion = op.get_bind()
    momento = datetime.now(UTC)
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


def _verificar_que_ningun_libro_referencia_los_motivos() -> None:
    conexion = op.get_bind()
    referencias = conexion.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM stock_movimiento s JOIN motivo m "
            "ON m.organizacion_id = s.organizacion_id AND m.id = s.motivo_id "
            "WHERE m.ambito = :ambito AND m.nombre = ANY(:nombres)) + "
            "(SELECT count(*) FROM auditoria a JOIN motivo m "
            "ON m.organizacion_id = a.organizacion_id AND m.id = a.motivo_id "
            "WHERE m.ambito = :ambito AND m.nombre = ANY(:nombres))"
        ),
        {"ambito": AMBITO, "nombres": list(MOTIVOS)},
    ).scalar_one()
    if referencias:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: {referencias} fila(s) de "
            "stock_movimiento o de auditoria referencian motivos de LIBERACION_JORNADA, y los "
            "libros son de solo inserción (INV-05). Bajar el esquema dejaría esas referencias "
            "sin motivo; resolvelo a mano antes de volver a intentar."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_ningun_libro_referencia_los_motivos()
    conexion = op.get_bind()

    for tabla in TABLAS_CON_JORNADA:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT fk_{tabla}__jornada")

    op.drop_table("jornada")

    conexion.execute(
        sa.text("DELETE FROM motivo WHERE ambito = :ambito AND nombre = ANY(:nombres)"),
        {"ambito": AMBITO, "nombres": list(MOTIVOS)},
    )
