"""ventas: venta, venta_linea, clave foranea de cobranza.venta_id, observaciones VENTA_SIN_COSTO,
CONSUMIDOR_FINAL_CON_DEUDA y UBICACION_TOMADA_AL_SINCRONIZAR y motivos de LISTA_ANTERIOR

Revision ID: a2b3c4d5e6f7
Revises: f8a9b0c1d2e3
Create Date: 2026-10-18 00:00:00.000000

Change 18a (`design.md` D6, D10, D12, D16, `docs/03-modelo-de-datos.md` §12), una sola revision:

- `venta`: `03` §12 mas `lista_id`, `motivo_lista_id` y `creado_en` (D16). `ubicacion_id`
  obligatoria (D3: toda venta descuenta de una ubicacion). `jornada_id` nulable con FK compuesta.
  `lista_version_id` y `lista_id` obligatorias (PRC-23). `numero` unico por organizacion
  (VTA-06). `CHECK` de `estado`, `estado_facturacion`, `modo_impositivo` y `modo_confirmacion`,
  `total = total_neto + total_iva` (INV-14), `ck_venta__facturado` (INV-09) y `ck_venta__jornada`.
  Sin las columnas `credito_*` ni `venta_linea_descuento`: son del 18b (D15).
- `venta_linea`: `03` §12 mas `lista_version_id` por linea (VTA-03, PRC-23) y `costo_unitario` /
  `costo_total` nulables juntos (D10). `UNIQUE (organizacion_id, venta_id, orden)`,
  `cantidad > 0`, `cantidad_base = cantidad * unidades_presentacion` (INV-18) y
  `importe_neto = importe_bruto - importe_descuento`.
- Todas con `UNIQUE (organizacion_id, id)` y FK compuestas con `organizacion_id` (INV-02,
  INV-21).
- Permisos de `app_runtime` (INV-05, INV-10, TR-06): `SELECT, INSERT` sobre las dos tablas; sin
  `UPDATE` ni `DELETE` (el change 19 agrega el `UPDATE` de `estado`).
- `cobranza.venta_id` pasa a tener FK compuesta a `venta`. **Aborta** con un mensaje claro si hay
  cobranzas con `venta_id` no nulo (no podian existir: la tabla `venta` no existia; D12).
- `ck_observacion__codigo` suma `VENTA_SIN_COSTO` (D10, SYN-07), `CONSUMIDOR_FINAL_CON_DEUDA`
  (D5, decision del usuario del 2026-10-19) y `UBICACION_TOMADA_AL_SINCRONIZAR` (D1/D3, STK-09,
  decision del usuario del 2026-10-20).
- Siembra idempotente (D6) de los tres motivos de `LISTA_ANTERIOR`, en cada organizacion que no
  tenga ninguno de ese ambito. El ambito ya esta en `ck_motivo__ambito`.

Tablas nuevas y vacias: no se usan indices concurrentes (mismo criterio que `c0d1e2f3a4b5`).

`downgrade` **aborta** con un mensaje claro si hay ventas (borrar las tablas perderia la
historia, INV-10) o observaciones `VENTA_SIN_COSTO`, `CONSUMIDOR_FINAL_CON_DEUDA` o
`UBICACION_TOMADA_AL_SINCRONIZAR` (dejarian de cumplir el `CHECK`); sin ellas quita la FK,
las tablas y los motivos sembrados de `LISTA_ANTERIOR` que nada referencia (un motivo propio
de la organizacion no se toca). La
perdida (las tablas, la FK y los motivos sin uso) esta escrita como asercion explicita en
`backend/tests/integration/test_ventas_migracion.py` (tarea 3.4).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

AMBITO = "LISTA_ANTERIOR"
MOTIVOS = ("Precio acordado con el cliente", "Error en la lista vigente", "Otro")

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
)
CODIGOS_NUEVOS = (
    "VENTA_SIN_COSTO",
    "CONSUMIDOR_FINAL_CON_DEUDA",
    "UBICACION_TOMADA_AL_SINCRONIZAR",
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


def _verificar_que_no_hay_cobranzas_con_venta() -> None:
    """D12: aborta con un mensaje claro si alguna cobranza ya referencia una venta (no podia
    haber: la tabla no existia). Sin esta comprobacion `ADD CONSTRAINT` fallaria con un
    `ForeignKeyViolation` opaco."""
    cantidad = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM cobranza WHERE venta_id IS NOT NULL"))
        .scalar_one()
    )
    if cantidad:
        raise RuntimeError(
            f"La revisión {revision} no puede subir (design.md D12): hay {cantidad} cobranza(s) "
            "con venta_id no nulo en la tabla cobranza y la tabla venta no existía. Resolvelas "
            "o eliminalas antes de volver a intentarlo; la revisión no las modifica."
        )


def upgrade() -> None:
    """Upgrade schema."""
    _verificar_que_no_hay_cobranzas_con_venta()

    op.create_table(
        "venta",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("numero", sa.Text(), nullable=False),
        sa.Column("cliente_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("dispositivo_id", sa.Uuid(), nullable=False),
        sa.Column("ubicacion_id", sa.Uuid(), nullable=False),
        sa.Column("jornada_id", sa.Uuid(), nullable=True),
        sa.Column("lista_id", sa.Uuid(), nullable=False),
        sa.Column("lista_version_id", sa.Uuid(), nullable=False),
        sa.Column("motivo_lista_id", sa.Uuid(), nullable=True),
        sa.Column("modo_impositivo", sa.Text(), nullable=False),
        sa.Column("modo_confirmacion", sa.Text(), nullable=False),
        sa.Column("total_neto", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_iva", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("estado_facturacion", sa.Text(), nullable=False),
        sa.Column("importe_facturado", sa.Numeric(14, 2), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_venta"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_venta__organizacion"
        ),
        _fk("venta", "cliente", "cliente_id", "cliente"),
        _fk("venta", "usuario", "usuario_id", "usuario"),
        _fk("venta", "dispositivo", "dispositivo_id", "dispositivo"),
        _fk("venta", "ubicacion", "ubicacion_id", "ubicacion"),
        _fk("venta", "jornada", "jornada_id", "jornada"),
        _fk("venta", "lista", "lista_id", "lista_precio"),
        _fk("venta", "lista_version", "lista_version_id", "lista_version"),
        _fk("venta", "motivo_lista", "motivo_lista_id", "motivo"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_venta__org_id"),
        sa.UniqueConstraint("organizacion_id", "numero", name="ux_venta__numero"),
        sa.CheckConstraint("estado IN ('CONFIRMADA','ANULADA')", name="ck_venta__estado"),
        sa.CheckConstraint(
            "estado_facturacion IN ('NO_REQUIERE','PENDIENTE','PARCIAL','FACTURADA')",
            name="ck_venta__estado_facturacion",
        ),
        sa.CheckConstraint("modo_impositivo IN ('A','B','C')", name="ck_venta__modo_impositivo"),
        sa.CheckConstraint(
            "modo_confirmacion IN ('ONLINE','OFFLINE')", name="ck_venta__modo_confirmacion"
        ),
        sa.CheckConstraint("total = total_neto + total_iva", name="ck_venta__total"),
        sa.CheckConstraint(
            "importe_facturado >= 0 AND importe_facturado <= total_neto", name="ck_venta__facturado"
        ),
        sa.CheckConstraint(
            "modo_confirmacion = 'ONLINE' OR jornada_id IS NOT NULL", name="ck_venta__jornada"
        ),
    )
    op.create_index(
        "ix_venta__occurred_at",
        "venta",
        ["organizacion_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_venta__cliente",
        "venta",
        ["organizacion_id", "cliente_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_venta__usuario",
        "venta",
        ["organizacion_id", "usuario_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_venta__jornada", "venta", ["organizacion_id", "jornada_id"])
    op.create_index(
        "ix_venta__facturacion_pendiente",
        "venta",
        ["organizacion_id", "cliente_id"],
        postgresql_where=sa.text("estado_facturacion IN ('PENDIENTE','PARCIAL')"),
    )

    op.create_table(
        "venta_linea",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("venta_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("producto_id", sa.Uuid(), nullable=False),
        sa.Column("presentacion_id", sa.Uuid(), nullable=False),
        sa.Column("lista_version_id", sa.Uuid(), nullable=False),
        sa.Column("unidades_presentacion", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("cantidad_base", sa.Integer(), nullable=False),
        sa.Column("precio_referencia", sa.Numeric(14, 2), nullable=False),
        sa.Column("unidades_referencia", sa.Integer(), nullable=False),
        sa.Column("importe_bruto", sa.Numeric(14, 2), nullable=False),
        sa.Column("importe_descuento", sa.Numeric(14, 2), nullable=False),
        sa.Column("importe_neto", sa.Numeric(14, 2), nullable=False),
        sa.Column("alicuota", sa.Numeric(9, 6), nullable=False),
        sa.Column("importe_iva", sa.Numeric(14, 2), nullable=False),
        sa.Column("costo_unitario", sa.Numeric(18, 6), nullable=True),
        sa.Column("costo_total", sa.Numeric(14, 2), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_venta_linea"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_venta_linea__organizacion"
        ),
        _fk("venta_linea", "venta", "venta_id", "venta"),
        _fk("venta_linea", "producto", "producto_id", "producto"),
        _fk("venta_linea", "presentacion", "presentacion_id", "presentacion"),
        _fk("venta_linea", "lista_version", "lista_version_id", "lista_version"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_venta_linea__org_id"),
        sa.UniqueConstraint(
            "organizacion_id", "venta_id", "orden", name="ux_venta_linea__venta_orden"
        ),
        sa.CheckConstraint("orden >= 0", name="ck_venta_linea__orden"),
        sa.CheckConstraint("cantidad > 0", name="ck_venta_linea__cantidad"),
        sa.CheckConstraint(
            "cantidad_base = cantidad * unidades_presentacion", name="ck_venta_linea__cantidad_base"
        ),
        sa.CheckConstraint(
            "unidades_presentacion >= 1", name="ck_venta_linea__unidades_presentacion"
        ),
        sa.CheckConstraint("unidades_referencia >= 1", name="ck_venta_linea__unidades_referencia"),
        sa.CheckConstraint(
            "importe_neto = importe_bruto - importe_descuento", name="ck_venta_linea__neto"
        ),
        sa.CheckConstraint(
            "(costo_total IS NULL) = (costo_unitario IS NULL)", name="ck_venta_linea__costo"
        ),
    )
    op.create_index("ix_venta_linea__producto", "venta_linea", ["organizacion_id", "producto_id"])
    op.create_index(
        "ix_venta_linea__presentacion", "venta_linea", ["organizacion_id", "presentacion_id"]
    )

    # INV-05, INV-10, TR-06, D16: solo insercion; el 19 agrega el `UPDATE` de `estado`.
    for tabla in ("venta", "venta_linea"):
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {ROL_RUNTIME}")

    op.create_foreign_key(
        "fk_cobranza__venta",
        "cobranza",
        "venta",
        ["organizacion_id", "venta_id"],
        ["organizacion_id", "id"],
    )

    _cambiar_ck_observacion_codigo((*CODIGOS_PREVIOS, *CODIGOS_NUEVOS))
    _sembrar_motivos()


def _sembrar_motivos() -> None:
    """D6: tres motivos de `LISTA_ANTERIOR` en cada organizacion que no tenga ninguno de ese
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


def _verificar_que_se_puede_bajar() -> None:
    """Aborta con un mensaje claro si hay ventas (se perderia la historia, INV-10) o
    observaciones de un codigo nuevo (`VENTA_SIN_COSTO`, `CONSUMIDOR_FINAL_CON_DEUDA`,
    `UBICACION_TOMADA_AL_SINCRONIZAR`), que dejarian de cumplir el `CHECK`."""
    conexion = op.get_bind()
    ventas = conexion.execute(sa.text("SELECT count(*) FROM venta")).scalar_one()
    if ventas:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: hay {ventas} venta(s) y borrar las tablas "
            "venta y venta_linea perdería la historia (INV-10). Anulalas o resolvelas por fuera "
            "de la revisión; la revisión no las modifica."
        )
    observaciones = conexion.execute(
        sa.text("SELECT count(*) FROM observacion WHERE codigo = ANY(:codigos)"),
        {"codigos": list(CODIGOS_NUEVOS)},
    ).scalar_one()
    if observaciones:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar (design.md D10, D5): hay {observaciones} "
            f"observación(es) {' o '.join(CODIGOS_NUEVOS)} que la revisión anterior no admite. "
            "Resolvelas o eliminalas antes de volver a intentarlo; la revisión no las modifica."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_se_puede_bajar()

    op.drop_constraint("fk_cobranza__venta", "cobranza", type_="foreignkey")
    op.drop_index("ix_venta_linea__presentacion", table_name="venta_linea")
    op.drop_index("ix_venta_linea__producto", table_name="venta_linea")
    op.drop_table("venta_linea")
    op.drop_index("ix_venta__facturacion_pendiente", table_name="venta")
    op.drop_index("ix_venta__jornada", table_name="venta")
    op.drop_index("ix_venta__usuario", table_name="venta")
    op.drop_index("ix_venta__cliente", table_name="venta")
    op.drop_index("ix_venta__occurred_at", table_name="venta")
    op.drop_table("venta")

    _cambiar_ck_observacion_codigo(CODIGOS_PREVIOS)

    # Se borran solo los motivos sembrados (por nombre) que nada referencia (el libro de
    # auditoria y el de stock, de solo insercion, guardan `motivo_id`): un motivo propio de la
    # organizacion no se toca. El ambito sigue en `ck_motivo__ambito`.
    op.execute(
        sa.text(
            "DELETE FROM motivo m WHERE m.ambito = :ambito AND m.nombre IN :nombres "
            "AND NOT EXISTS (SELECT 1 FROM auditoria a "
            "WHERE a.organizacion_id = m.organizacion_id AND a.motivo_id = m.id) "
            "AND NOT EXISTS (SELECT 1 FROM stock_movimiento s "
            "WHERE s.organizacion_id = m.organizacion_id AND s.motivo_id = m.id)"
        ).bindparams(
            sa.bindparam("ambito", AMBITO), sa.bindparam("nombres", list(MOTIVOS), expanding=True)
        )
    )
