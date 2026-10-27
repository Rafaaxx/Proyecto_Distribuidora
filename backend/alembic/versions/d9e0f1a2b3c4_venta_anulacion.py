"""venta_anulacion: registro de anulaciones de venta

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-10-24 00:10:00.000000

Crea tabla venta_anulacion con FK compuestas, UNIQUE (organizacion_id, venta_id) e indice.
Otorga a app_runtime SELECT, INSERT sobre venta_anulacion y UPDATE (estado) sobre venta.
Siembra motivos ANULACION_VENTA para organizaciones sin ninguno.
Downgrade aborta con mensaje claro si hay ventas ANULADA.
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None

ROL_RUNTIME = "app_runtime"
AMBITO = "ANULACION_VENTA"
MOTIVOS = ("Error de carga", "Devolución del cliente", "Otro")


def _columnas_de_operacion():
    return [
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _fk(tabla, nombre, columna, destino):
    return sa.ForeignKeyConstraint(
        ["organizacion_id", columna],
        [f"{destino}.organizacion_id", f"{destino}.id"],
        name=f"fk_{tabla}__{nombre}",
    )


def upgrade():
    op.create_table(
        "venta_anulacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("venta_id", sa.Uuid(), nullable=False),
        sa.Column("motivo_id", sa.Uuid(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("devuelve_dinero", sa.Boolean(), nullable=True),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_venta_anulacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_venta_anulacion__organizacion"
        ),
        _fk("venta_anulacion", "venta", "venta_id", "venta"),
        _fk("venta_anulacion", "motivo", "motivo_id", "motivo"),
        _fk("venta_anulacion", "jornada", "jornada_id", "jornada"),
        _fk("venta_anulacion", "usuario", "usuario_id", "usuario"),
        _fk("venta_anulacion", "dispositivo", "dispositivo_id", "dispositivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_venta_anulacion__org_id"),
        sa.UniqueConstraint("organizacion_id", "venta_id", name="ux_venta_anulacion__venta"),
    )
    op.create_index(
        "ix_venta_anulacion__occurred_at",
        "venta_anulacion",
        ["organizacion_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.execute(f"GRANT SELECT, INSERT ON venta_anulacion TO {ROL_RUNTIME}")
    op.execute(f"GRANT UPDATE (estado) ON venta TO {ROL_RUNTIME}")
    _sembrar_motivos()


def _sembrar_motivos():
    """D12: tres motivos de `ANULACION_VENTA` en cada organizacion que no tenga ninguno de ese
    ambito. Idempotente: una organizacion con motivos propios (o ya sembrada) no se toca."""
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


def downgrade():
    conexion = op.get_bind()
    anuladas = conexion.execute(
        sa.text("SELECT count(*) FROM venta WHERE estado = 'ANULADA'")
    ).scalar_one()
    if anuladas and int(anuladas) > 0:
        raise RuntimeError(
            "No se puede hacer downgrade de la migracion de venta_anulacion porque existen "
            "ventas con estado ANULADA (quedarian sin su anulacion)"
        )
    op.drop_index("ix_venta_anulacion__occurred_at", table_name="venta_anulacion")
    op.drop_table("venta_anulacion")
    op.execute(f"REVOKE UPDATE (estado) ON venta FROM {ROL_RUNTIME}")
    # Se borra todo motivo del ambito que nada referencia (como la migracion de cobranzas).
    op.execute(
        sa.text(
            "DELETE FROM motivo m WHERE m.ambito = :ambito "
            "AND NOT EXISTS (SELECT 1 FROM auditoria a "
            "WHERE a.organizacion_id = m.organizacion_id AND a.motivo_id = m.id) "
            "AND NOT EXISTS (SELECT 1 FROM stock_movimiento s "
            "WHERE s.organizacion_id = m.organizacion_id AND s.motivo_id = m.id)"
        ).bindparams(sa.bindparam("ambito", AMBITO))
    )
