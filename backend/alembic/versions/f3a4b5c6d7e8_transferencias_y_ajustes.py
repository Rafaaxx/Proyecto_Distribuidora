"""transferencias y ajustes de stock: cuatro tablas, ambitos de motivo de anulacion y
permiso ANULAR_TRANSFERENCIA

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-07 00:00:00.000000

Change 14 (`design.md` D5, D5.3, D8), una sola revision:

- `transferencia`, `transferencia_linea`, `ajuste_stock` y `ajuste_stock_linea` (`03`
  §9 mas lo que suma D8): `UNIQUE (organizacion_id, id)`, FK compuestas (INV-02),
  columnas de operacion como `compra`, `orden` por linea con su `UNIQUE`, los `CHECK`
  de ubicaciones distintas y de cantidad, `observacion` nulable y, en AMBAS cabeceras,
  `estado` (`CONFIRMADA`/`ANULADA`) con las tres columnas de anulacion atadas por el
  mismo `CHECK` de coherencia que `compra`. Indices de listado.
- `app_runtime`: `SELECT, INSERT` en las cuatro tablas; `UPDATE` SOLO de `estado` y las
  tres columnas de anulacion de cada cabecera; nunca `DELETE`; las lineas no se
  actualizan (INV-05, TR-06). `stock_movimiento`, `costo_producto_mov` y `auditoria` no
  se tocan.
- `ck_motivo__ambito` suma `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE` (TR-09) y se
  siembran, de forma idempotente, "Error de carga" y "Otro" en cada ambito de cada
  organizacion que no tenga ninguno (D5.3, mismo precedente que `d1e2f3a4b5c6`).
- Permiso `ANULAR_TRANSFERENCIA` (D5 punto 5): se inserta en `permiso` y se asigna, en
  las organizaciones existentes, a los roles de plantilla cuya composicion en
  `PLANTILLAS_DE_ROL` lo incluye. Los roles de plantilla se reconocen por su NOMBRE
  (no hay una marca de plantilla en `rol`): una organizacion que renombro un rol no lo
  recibe y lo asigna a mano. La lista de roles NO vive aca: se deriva de
  `app.modules.identidad.domain.permisos.PLANTILLAS_DE_ROL`, la fuente unica que usa
  tambien la siembra.

`downgrade` borra las cuatro tablas, el permiso con sus asignaciones y los motivos de los
dos ambitos y restaura `ck_motivo__ambito`: **pierde por diseno** transferencias, ajustes,
sus anulaciones, esos motivos y el permiso (los movimientos quedan en el libro, que no se
toca). Si un movimiento de stock o una fila de auditoria referencia un motivo de esos
ambitos, el `downgrade` aborta con un mensaje claro en lugar de tocar un libro de solo
insercion. La perdida esta escrita como asercion explicita en
`backend/tests/integration/test_transferencias_ajustes_migracion.py` (tarea 1.4).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id
from app.modules.identidad.domain.permisos import PERMISOS_DEL_CATALOGO, PLANTILLAS_DE_ROL

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

AMBITOS_MOTIVO = (
    "AJUSTE_STOCK",
    "ANULACION_VENTA",
    "ANULACION_COMPRA",
    "ANULACION_COBRANZA",
    "ANULACION_PAGO",
    "ANULACION_TRANSFERENCIA",
    "ANULACION_AJUSTE",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)
AMBITOS_NUEVOS = ("ANULACION_TRANSFERENCIA", "ANULACION_AJUSTE")
MOTIVOS = ("Error de carga", "Otro")

PERMISO = "ANULAR_TRANSFERENCIA"

_COLUMNAS_MUTABLES_TRANSFERENCIA = "estado, anulacion_motivo_id, anulada_en, anulada_por_id"
_COLUMNAS_MUTABLES_AJUSTE = "estado, anulacion_motivo_id, anulado_en, anulado_por_id"


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


def _cambiar_ck_motivo_ambito(ambitos: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE motivo DROP CONSTRAINT ck_motivo__ambito")
    op.execute(
        "ALTER TABLE motivo ADD CONSTRAINT ck_motivo__ambito CHECK (ambito IN ("
        + ", ".join(f"'{ambito}'" for ambito in ambitos)
        + "))"
    )


def upgrade() -> None:
    """Upgrade schema."""
    _cambiar_ck_motivo_ambito(AMBITOS_MOTIVO)

    op.create_table(
        "transferencia",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_origen_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_destino_id", sa.Uuid(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("anulacion_motivo_id", sa.Uuid(), nullable=True),
        sa.Column("anulada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulada_por_id", sa.Uuid(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_transferencia"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_transferencia__organizacion"
        ),
        _fk("transferencia", "origen", "ubicacion_origen_id", "ubicacion"),
        _fk("transferencia", "destino", "ubicacion_destino_id", "ubicacion"),
        _fk("transferencia", "usuario", "usuario_id", "usuario"),
        _fk("transferencia", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("transferencia", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        _fk("transferencia", "anulada_por", "anulada_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_transferencia__org_id"),
        sa.CheckConstraint(
            "ubicacion_origen_id <> ubicacion_destino_id",
            name="ck_transferencia__ubicaciones_distintas",
        ),
        sa.CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_transferencia__estado"),
        sa.CheckConstraint(
            "(estado = 'ANULADA') = (anulada_en IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
            "AND (anulada_en IS NOT NULL) = (anulada_por_id IS NOT NULL)",
            name="ck_transferencia__anulacion_coherente",
        ),
    )
    op.create_index(
        "ix_transferencia__fecha",
        "transferencia",
        ["organizacion_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_transferencia__origen_fecha",
        "transferencia",
        ["organizacion_id", "ubicacion_origen_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_transferencia__destino_fecha",
        "transferencia",
        [
            "organizacion_id",
            "ubicacion_destino_id",
            sa.text("occurred_at DESC"),
            sa.text("id DESC"),
        ],
    )

    op.create_table(
        "transferencia_linea",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("transferencia_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad_base", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_transferencia_linea"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_transferencia_linea__organizacion"
        ),
        _fk("transferencia_linea", "transferencia", "transferencia_id", "transferencia"),
        _fk("transferencia_linea", "producto", "producto_id", "producto"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_transferencia_linea__org_id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "transferencia_id",
            "orden",
            name="ux_transferencia_linea__transferencia_orden",
        ),
        sa.CheckConstraint("orden >= 1", name="ck_transferencia_linea__orden"),
        sa.CheckConstraint("cantidad_base > 0", name="ck_transferencia_linea__cantidad_base"),
    )
    op.create_index(
        "ix_transferencia_linea__producto",
        "transferencia_linea",
        ["organizacion_id", "producto_id"],
    )

    op.create_table(
        "ajuste_stock",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_id", sa.Uuid(), nullable=False),
        sa.Column("motivo_id", sa.Uuid(), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("anulacion_motivo_id", sa.Uuid(), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_por_id", sa.Uuid(), nullable=True),
        *_columnas_de_operacion(),
        sa.PrimaryKeyConstraint("id", name="pk_ajuste_stock"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_ajuste_stock__organizacion"
        ),
        _fk("ajuste_stock", "ubicacion", "ubicacion_id", "ubicacion"),
        _fk("ajuste_stock", "motivo", "motivo_id", "motivo"),
        _fk("ajuste_stock", "usuario", "usuario_id", "usuario"),
        _fk("ajuste_stock", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("ajuste_stock", "anulacion_motivo", "anulacion_motivo_id", "motivo"),
        _fk("ajuste_stock", "anulado_por", "anulado_por_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_ajuste_stock__org_id"),
        sa.CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_ajuste_stock__estado"),
        sa.CheckConstraint(
            "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
            "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL)",
            name="ck_ajuste_stock__anulacion_coherente",
        ),
    )
    op.create_index(
        "ix_ajuste_stock__fecha",
        "ajuste_stock",
        ["organizacion_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_ajuste_stock__ubicacion_fecha",
        "ajuste_stock",
        ["organizacion_id", "ubicacion_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_ajuste_stock__motivo_fecha",
        "ajuste_stock",
        ["organizacion_id", "motivo_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "ajuste_stock_linea",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("ajuste_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad_base", sa.Integer(), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(18, 6), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ajuste_stock_linea"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_ajuste_stock_linea__organizacion"
        ),
        _fk("ajuste_stock_linea", "ajuste", "ajuste_id", "ajuste_stock"),
        _fk("ajuste_stock_linea", "producto", "producto_id", "producto"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_ajuste_stock_linea__org_id"),
        sa.UniqueConstraint(
            "organizacion_id", "ajuste_id", "orden", name="ux_ajuste_stock_linea__ajuste_orden"
        ),
        sa.CheckConstraint("orden >= 1", name="ck_ajuste_stock_linea__orden"),
        sa.CheckConstraint("cantidad_base <> 0", name="ck_ajuste_stock_linea__cantidad_base"),
    )
    op.create_index(
        "ix_ajuste_stock_linea__producto",
        "ajuste_stock_linea",
        ["organizacion_id", "producto_id"],
    )

    # INV-05, TR-06: nunca `DELETE`; `UPDATE` solo, por columna, del estado y la anulacion
    # de las cabeceras; las lineas son de solo insercion.
    for tabla in ("transferencia", "transferencia_linea", "ajuste_stock", "ajuste_stock_linea"):
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {ROL_RUNTIME}")
    op.execute(
        f"GRANT UPDATE ({_COLUMNAS_MUTABLES_TRANSFERENCIA}) ON transferencia TO {ROL_RUNTIME}"
    )
    op.execute(f"GRANT UPDATE ({_COLUMNAS_MUTABLES_AJUSTE}) ON ajuste_stock TO {ROL_RUNTIME}")

    _sembrar_motivos()
    _crear_permiso_y_asignarlo()


def _sembrar_motivos() -> None:
    """D5.3: "Error de carga" y "Otro" en cada ambito nuevo de cada organizacion que no
    tenga ninguno de ESE ambito. Idempotente, como la siembra de `ANULACION_PAGO`."""
    conexion = op.get_bind()
    momento = datetime.now(UTC)
    for ambito in AMBITOS_NUEVOS:
        organizaciones = (
            conexion.execute(
                sa.text(
                    "SELECT o.id FROM organizacion o WHERE NOT EXISTS ("
                    "SELECT 1 FROM motivo m WHERE m.organizacion_id = o.id AND m.ambito = :ambito)"
                ),
                {"ambito": ambito},
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
                        "ambito": ambito,
                        "nombre": nombre,
                        "momento": momento,
                    },
                )


def _roles_de_plantilla_con_el_permiso() -> list[str]:
    """Nombres de las plantillas que incluyen `ANULAR_TRANSFERENCIA`, derivados de la
    fuente unica `PLANTILLAS_DE_ROL` (Administrador y Administracion al aprobarse D5)."""
    return [nombre for nombre, permisos in PLANTILLAS_DE_ROL.items() if PERMISO in permisos]


def _crear_permiso_y_asignarlo() -> None:
    conexion = op.get_bind()
    permiso = next(p for p in PERMISOS_DEL_CATALOGO if p.codigo == PERMISO)
    conexion.execute(
        sa.text(
            "INSERT INTO permiso (codigo, descripcion, modulo) "
            "VALUES (:codigo, :descripcion, :modulo) ON CONFLICT (codigo) DO NOTHING"
        ),
        {"codigo": permiso.codigo, "descripcion": permiso.descripcion, "modulo": permiso.modulo},
    )
    for nombre_rol in _roles_de_plantilla_con_el_permiso():
        conexion.execute(
            sa.text(
                "INSERT INTO rol_permiso (organizacion_id, rol_id, permiso_codigo) "
                "SELECT r.organizacion_id, r.id, :permiso FROM rol r WHERE r.nombre = :rol "
                "ON CONFLICT DO NOTHING"
            ),
            {"permiso": PERMISO, "rol": nombre_rol},
        )


def _verificar_que_ningun_libro_referencia_los_motivos() -> None:
    conexion = op.get_bind()
    referencias = conexion.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM stock_movimiento s JOIN motivo m "
            "ON m.organizacion_id = s.organizacion_id AND m.id = s.motivo_id "
            "WHERE m.ambito = ANY(:ambitos)) + "
            "(SELECT count(*) FROM auditoria a JOIN motivo m "
            "ON m.organizacion_id = a.organizacion_id AND m.id = a.motivo_id "
            "WHERE m.ambito = ANY(:ambitos))"
        ),
        {"ambitos": list(AMBITOS_NUEVOS)},
    ).scalar_one()
    if referencias:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: {referencias} fila(s) de "
            "stock_movimiento o de auditoria referencian motivos de ANULACION_TRANSFERENCIA o "
            "ANULACION_AJUSTE, y los libros son de solo inserción (INV-05). Bajar el esquema "
            "dejaría esas referencias sin motivo; resolvelo a mano antes de volver a intentar."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_ningun_libro_referencia_los_motivos()
    conexion = op.get_bind()

    for tabla in ("ajuste_stock_linea", "ajuste_stock", "transferencia_linea", "transferencia"):
        op.drop_table(tabla)

    conexion.execute(
        sa.text("DELETE FROM rol_permiso WHERE permiso_codigo = :permiso"), {"permiso": PERMISO}
    )
    conexion.execute(sa.text("DELETE FROM permiso WHERE codigo = :permiso"), {"permiso": PERMISO})

    conexion.execute(
        sa.text("DELETE FROM motivo WHERE ambito = ANY(:ambitos)"),
        {"ambitos": list(AMBITOS_NUEVOS)},
    )
    _cambiar_ck_motivo_ambito(tuple(a for a in AMBITOS_MOTIVO if a not in AMBITOS_NUEVOS))
