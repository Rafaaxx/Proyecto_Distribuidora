"""revision de observaciones y rechazos: tabla `comando_rechazado`, resolucion acotada de
`observacion` y `comando_cuarentena`, y observacion `PRODUCTO_DESACTIVADO`

Revision ID: e3a5c7d9f1b2
Revises: d2f4a6c8e0b1
Create Date: 2026-11-05 12:00:00.000000

Change 25 (`design.md` D2, D6, D7, D10; `03` §13), una sola revision:

- `comando_rechazado` (D6): el contenido de cada comando `OFFLINE` rechazado, para que
  administracion vea lo que envio el telefono. `UNIQUE (organizacion_id, operation_id)` (el
  reenvio no lo duplica), FK compuestas con `organizacion_id` a usuario, dispositivo y jornada
  (nulable: nula si la jornada del sobre no existe, INV-02) y a quien resuelve; `CHECK`s de
  estado (`PENDIENTE`, `RESUELTO`), de coherencia de la resolucion y del vinculo (`VENTA` o
  `COBRANZA`, sin FK: es polimorfico) y de largo del comentario; indice parcial de pendientes por
  jornada (cantidad que bloquea la rendicion, D9).
- `observacion` (D2): se le quita el `UPDATE` de tabla a `app_runtime` y se le da solo el de las
  columnas de la resolucion; `CHECK`s `ck_observacion__resolucion_coherente` y
  `ck_observacion__comentario`; `PRODUCTO_DESACTIVADO` en `ck_observacion__codigo` (D10).
- `comando_cuarentena` (D2, D7): columnas `comentario`, `vinculo_tipo` y `vinculo_id`, `UPDATE`
  solo de las columnas de la revision y `CHECK`s de coherencia.
- `app_runtime` (INV-05): en `comando_rechazado` `SELECT, INSERT` y `UPDATE` solo de las seis
  columnas de la resolucion; nunca `DELETE`.

Las observaciones y cuarentenas anteriores (todas pendientes) siguen siendo validas: no se
modifica ninguna fila.

`downgrade` restituye los `GRANT`, quita los `CHECK`, las columnas y la tabla. **Pierde por
diseno** los rechazos, las resoluciones y las observaciones `PRODUCTO_DESACTIVADO`: ABORTA con un
mensaje claro, sin tocar nada, si hay algun rechazo registrado, alguna observacion resuelta,
alguna cuarentena revisada o alguna observacion `PRODUCTO_DESACTIVADO`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a5c7d9f1b2"
down_revision: str | Sequence[str] | None = "d2f4a6c8e0b1"
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
    "JORNADA_RENDIDA",
)
CODIGO_NUEVO = "PRODUCTO_DESACTIVADO"

COLUMNAS_RESOLUCION_OBSERVACION = ("estado", "resuelto_por_id", "resuelto_en", "comentario")
COLUMNAS_REVISION_CUARENTENA = (
    "revisado_en",
    "revisado_por_id",
    "comentario",
    "vinculo_tipo",
    "vinculo_id",
)
COLUMNAS_RESOLUCION_RECHAZO = (
    "estado",
    "resuelto_por_id",
    "resuelto_en",
    "comentario",
    "vinculo_tipo",
    "vinculo_id",
)


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
    # --- comando_rechazado (D6) ---------------------------------------------------------
    op.create_table(
        "comando_rechazado",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("modo", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("secuencia", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=False),
        sa.Column("contenido", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_codigo", sa.Text(), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("resuelto_por_id", sa.Uuid(), nullable=True),
        sa.Column("resuelto_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("vinculo_tipo", sa.Text(), nullable=True),
        sa.Column("vinculo_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_comando_rechazado"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_comando_rechazado__organizacion"
        ),
        _fk("comando_rechazado", "usuario", "usuario_id", "usuario"),
        _fk("comando_rechazado", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("comando_rechazado", "jornada", "jornada_id", "jornada"),
        _fk("comando_rechazado", "resuelto_por", "resuelto_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_comando_rechazado__org_id"),
        sa.UniqueConstraint(
            "organizacion_id", "operation_id", name="ux_comando_rechazado__org_operation_id"
        ),
        sa.CheckConstraint("modo IN ('ONLINE', 'OFFLINE')", name="ck_comando_rechazado__modo"),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'RESUELTO')", name="ck_comando_rechazado__estado"
        ),
        sa.CheckConstraint(
            "(estado = 'PENDIENTE' AND resuelto_por_id IS NULL AND resuelto_en IS NULL "
            "AND comentario IS NULL AND vinculo_tipo IS NULL AND vinculo_id IS NULL) "
            "OR (estado = 'RESUELTO' AND resuelto_por_id IS NOT NULL "
            "AND resuelto_en IS NOT NULL AND comentario IS NOT NULL)",
            name="ck_comando_rechazado__resolucion_coherente",
        ),
        sa.CheckConstraint(
            "comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500",
            name="ck_comando_rechazado__comentario",
        ),
        sa.CheckConstraint(
            "(vinculo_tipo IS NULL) = (vinculo_id IS NULL) "
            "AND (vinculo_tipo IS NULL OR vinculo_tipo IN ('VENTA', 'COBRANZA'))",
            name="ck_comando_rechazado__vinculo",
        ),
    )
    op.create_index(
        "ix_comando_rechazado__org_jornada_pendiente",
        "comando_rechazado",
        ["organizacion_id", "jornada_id"],
        postgresql_where=sa.text("estado = 'PENDIENTE'"),
    )

    # --- observacion: resolucion acotada y codigo nuevo (D2, D10) ------------------------
    _cambiar_ck_observacion_codigo((*CODIGOS_PREVIOS, CODIGO_NUEVO))
    op.create_check_constraint(
        "ck_observacion__resolucion_coherente",
        "observacion",
        "(estado = 'PENDIENTE' AND resuelto_por_id IS NULL AND resuelto_en IS NULL "
        "AND comentario IS NULL) "
        "OR (estado = 'RESUELTA' AND resuelto_por_id IS NOT NULL AND resuelto_en IS NOT NULL "
        "AND comentario IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_observacion__comentario",
        "observacion",
        "comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500",
    )

    # --- comando_cuarentena: revision con comentario y vinculo (D2, D7) -------------------
    op.add_column("comando_cuarentena", sa.Column("comentario", sa.Text(), nullable=True))
    op.add_column("comando_cuarentena", sa.Column("vinculo_tipo", sa.Text(), nullable=True))
    op.add_column("comando_cuarentena", sa.Column("vinculo_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_comando_cuarentena__revision_coherente",
        "comando_cuarentena",
        "(revisado_en IS NULL AND revisado_por_id IS NULL AND comentario IS NULL "
        "AND vinculo_tipo IS NULL AND vinculo_id IS NULL) "
        "OR (revisado_en IS NOT NULL AND revisado_por_id IS NOT NULL "
        "AND comentario IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_comando_cuarentena__comentario",
        "comando_cuarentena",
        "comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500",
    )
    op.create_check_constraint(
        "ck_comando_cuarentena__vinculo",
        "comando_cuarentena",
        "(vinculo_tipo IS NULL) = (vinculo_id IS NULL) "
        "AND (vinculo_tipo IS NULL OR vinculo_tipo IN ('VENTA', 'COBRANZA'))",
    )

    # --- privilegios de app_runtime (INV-05) ---------------------------------------------
    op.execute(f"GRANT SELECT, INSERT ON comando_rechazado TO {ROL_RUNTIME}")
    op.execute(
        f"GRANT UPDATE ({', '.join(COLUMNAS_RESOLUCION_RECHAZO)}) "
        f"ON comando_rechazado TO {ROL_RUNTIME}"
    )
    op.execute(f"REVOKE UPDATE ON observacion FROM {ROL_RUNTIME}")
    op.execute(
        f"GRANT UPDATE ({', '.join(COLUMNAS_RESOLUCION_OBSERVACION)}) "
        f"ON observacion TO {ROL_RUNTIME}"
    )
    op.execute(f"REVOKE UPDATE ON comando_cuarentena FROM {ROL_RUNTIME}")
    op.execute(
        f"GRANT UPDATE ({', '.join(COLUMNAS_REVISION_CUARENTENA)}) "
        f"ON comando_cuarentena TO {ROL_RUNTIME}"
    )


def _verificar_que_no_se_pierde_nada() -> None:
    """Aborta, sin tocar nada, si bajar perderia rechazos, resoluciones o revisiones."""
    conexion = op.get_bind()
    rechazos = conexion.execute(sa.text("SELECT count(*) FROM comando_rechazado")).scalar_one()
    resueltas = conexion.execute(
        sa.text("SELECT count(*) FROM observacion WHERE estado = 'RESUELTA'")
    ).scalar_one()
    revisadas = conexion.execute(
        sa.text("SELECT count(*) FROM comando_cuarentena WHERE revisado_en IS NOT NULL")
    ).scalar_one()
    desactivados = conexion.execute(
        sa.text("SELECT count(*) FROM observacion WHERE codigo = :codigo"),
        {"codigo": CODIGO_NUEVO},
    ).scalar_one()
    if rechazos or resueltas or revisadas or desactivados:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: hay {rechazos} rechazo(s) registrado(s), "
            f"{resueltas} observación(es) resuelta(s), {revisadas} cuarentena(s) revisada(s) y "
            f"{desactivados} observación(es) {CODIGO_NUEVO}. Los rechazos son el único rastro de "
            "lo que envió el teléfono y las resoluciones llevan el comentario de quien revisó: "
            "bajar los perdería. No se modificó nada; resolvelo a mano antes de volver a "
            "intentar."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_no_se_pierde_nada()

    op.execute(f"REVOKE UPDATE ON comando_cuarentena FROM {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ON comando_cuarentena TO {ROL_RUNTIME}")
    op.execute(f"REVOKE UPDATE ON observacion FROM {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE ON observacion TO {ROL_RUNTIME}")

    op.drop_constraint("ck_comando_cuarentena__vinculo", "comando_cuarentena", type_="check")
    op.drop_constraint("ck_comando_cuarentena__comentario", "comando_cuarentena", type_="check")
    op.drop_constraint(
        "ck_comando_cuarentena__revision_coherente", "comando_cuarentena", type_="check"
    )
    op.drop_column("comando_cuarentena", "vinculo_id")
    op.drop_column("comando_cuarentena", "vinculo_tipo")
    op.drop_column("comando_cuarentena", "comentario")

    op.drop_constraint("ck_observacion__comentario", "observacion", type_="check")
    op.drop_constraint("ck_observacion__resolucion_coherente", "observacion", type_="check")
    _cambiar_ck_observacion_codigo(CODIGOS_PREVIOS)

    op.drop_index("ix_comando_rechazado__org_jornada_pendiente", table_name="comando_rechazado")
    op.drop_table("comando_rechazado")
