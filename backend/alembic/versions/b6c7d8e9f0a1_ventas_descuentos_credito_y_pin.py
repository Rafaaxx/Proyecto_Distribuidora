"""ventas 18b: snapshot de credito en venta, venta_linea_descuento, intento_pin_autorizacion,
observacion AUTORIZACION_OFFLINE y motivos de DESCUENTO_MANUAL

Revision ID: b6c7d8e9f0a1
Revises: a2b3c4d5e6f7
Create Date: 2026-10-22 00:00:00.000000

Change 18b (`design.md` D3, D9, D12, D13, D21; `docs/03-modelo-de-datos.md` §12), una sola
revision:

- `venta` suma `credito_limite`, `credito_saldo_considerado`, `credito_disponible`,
  `credito_exceso` (`numeric(14,2)`), `credito_politica`, `credito_resolucion` (`text`) y
  `credito_autorizador_id` (FK compuesta a `usuario`), todas nulables (las ventas del 18a no
  tienen snapshot, CRE-10). `CHECK` de catalogo de politica y resolucion, `PIN_SUPERVISOR`
  exige autorizador, `credito_exceso >= 0` y limite, disponible y exceso nulos juntos (sin
  control) solo con resolucion `SIN_EXCESO` o sin resolucion (venta del 18a). No hay valor
  `SIN_CONTROL`: el limite nulo lo expresa (D12-A).
- `venta_linea_descuento`: `03` §12 mas `orden`. `UNIQUE (organizacion_id, id)` y
  `UNIQUE (organizacion_id, venta_linea_id, orden)`, FK compuestas a `venta_linea`,
  `regla_descuento`, `motivo` y `usuario` (INV-02). `CHECK` de origen, regla nula si y solo si
  es manual, importe > 0 y porcentaje en (0, 1] o nulo (importe fijo). Indice unico parcial de
  `MANUAL` por linea (DSC-08).
- `intento_pin_autorizacion` (D3 revisada el 2026-10-22): contador de fallos del PIN de
  autorizacion por par (`intentante_id`, `autorizador_id`) y general por autorizador, con
  `organizacion_id` y FK compuestas a `usuario` (a diferencia de `intento_login`, que es
  transversal por IP, aca los sujetos son usuarios de una organizacion). `exito` es `true` solo
  en la fila marcador que reinicia los contadores al definir el PIN (D21, punto 7); el marcador
  admite `intentante_id` nulo y un fallo no (`CHECK (exito OR intentante_id IS NOT NULL)`).
  Indices `(organizacion_id, autorizador_id, creado_en)` (tope general) y
  `(organizacion_id, autorizador_id, intentante_id, creado_en)` (par).
- Permisos de `app_runtime` (INV-05, INV-10, TR-06): `SELECT, INSERT` sobre las dos tablas
  nuevas; `venta` sigue sin `UPDATE`.
- `ck_observacion__codigo` suma `AUTORIZACION_OFFLINE` (D9, SYN-07).
- Siembra idempotente (D13) de los cinco motivos de `DESCUENTO_MANUAL`, en cada organizacion que
  no tenga ninguno de ese ambito. El ambito ya esta en `ck_motivo__ambito`.

Tablas nuevas y vacias: no se usan indices concurrentes (mismo criterio que `a2b3c4d5e6f7`).

`downgrade` **aborta** con un mensaje claro si hay filas en `venta_linea_descuento`, ventas con
snapshot de credito u observaciones `AUTORIZACION_OFFLINE` (perderian historia o dejarian de
cumplir el `CHECK`); sin ellas quita las columnas, las tablas y los motivos sembrados que nada
referencia (un motivo propio de la organizacion no se toca). Lo que se pierde (las tablas, las
columnas y los motivos sin uso) esta escrito como asercion explicita en
`backend/tests/integration/test_ventas_18b_migracion.py` (tarea 3.4). `intento_pin_autorizacion`
se descarta sin comprobar filas: es un contador de ventana corta, no historia de negocio.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: str | Sequence[str] | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_RUNTIME = "app_runtime"

AMBITO = "DESCUENTO_MANUAL"
MOTIVOS = (
    "Cliente frecuente",
    "Negociación por volumen",
    "Producto próximo a vencer",
    "Compensación por reclamo",
    "Otro",
)

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
)
CODIGO_NUEVO = "AUTORIZACION_OFFLINE"

COLUMNAS_CREDITO = (
    "credito_limite",
    "credito_saldo_considerado",
    "credito_disponible",
    "credito_exceso",
    "credito_politica",
    "credito_resolucion",
    "credito_autorizador_id",
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
    op.add_column("venta", sa.Column("credito_limite", sa.Numeric(14, 2), nullable=True))
    op.add_column("venta", sa.Column("credito_saldo_considerado", sa.Numeric(14, 2), nullable=True))
    op.add_column("venta", sa.Column("credito_disponible", sa.Numeric(14, 2), nullable=True))
    op.add_column("venta", sa.Column("credito_exceso", sa.Numeric(14, 2), nullable=True))
    op.add_column("venta", sa.Column("credito_politica", sa.Text(), nullable=True))
    op.add_column("venta", sa.Column("credito_resolucion", sa.Text(), nullable=True))
    op.add_column("venta", sa.Column("credito_autorizador_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_venta__credito_autorizador",
        "venta",
        "usuario",
        ["organizacion_id", "credito_autorizador_id"],
        ["organizacion_id", "id"],
    )
    op.create_check_constraint(
        "ck_venta__credito_politica",
        "venta",
        "credito_politica IN ('ADVERTIR','AUTORIZAR','BLOQUEAR')",
    )
    op.create_check_constraint(
        "ck_venta__credito_resolucion",
        "venta",
        "credito_resolucion IN ('ADVERTENCIA_ACEPTADA','PERMISO_PROPIO','PIN_SUPERVISOR',"
        "'TOLERANCIA_OFFLINE','SIN_EXCESO')",
    )
    op.create_check_constraint(
        "ck_venta__credito_autorizador",
        "venta",
        "credito_resolucion <> 'PIN_SUPERVISOR' OR credito_autorizador_id IS NOT NULL",
    )
    op.create_check_constraint("ck_venta__credito_exceso", "venta", "credito_exceso >= 0")
    op.create_check_constraint(
        "ck_venta__credito_sin_control",
        "venta",
        "(credito_limite IS NULL) = (credito_disponible IS NULL) "
        "AND (credito_limite IS NULL) = (credito_exceso IS NULL) "
        "AND (credito_limite IS NOT NULL OR credito_resolucion IS NULL "
        "OR credito_resolucion = 'SIN_EXCESO')",
    )

    op.create_table(
        "venta_linea_descuento",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("venta_linea_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("origen", sa.Text(), nullable=False),
        sa.Column("regla_id", sa.Uuid(), nullable=True),
        sa.Column("porcentaje", sa.Numeric(9, 6), nullable=True),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("motivo_id", sa.Uuid(), nullable=True),
        sa.Column("autorizador_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_venta_linea_descuento"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"], ["organizacion.id"], name="fk_venta_linea_descuento__organizacion"
        ),
        _fk("venta_linea_descuento", "venta_linea", "venta_linea_id", "venta_linea"),
        _fk("venta_linea_descuento", "regla", "regla_id", "regla_descuento"),
        _fk("venta_linea_descuento", "motivo", "motivo_id", "motivo"),
        _fk("venta_linea_descuento", "autorizador", "autorizador_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_venta_linea_descuento__org_id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "venta_linea_id",
            "orden",
            name="ux_venta_linea_descuento__linea_orden",
        ),
        sa.CheckConstraint("orden >= 0", name="ck_venta_linea_descuento__orden"),
        sa.CheckConstraint(
            "origen IN ('AUTOMATICO','MANUAL')", name="ck_venta_linea_descuento__origen"
        ),
        sa.CheckConstraint(
            "(origen = 'MANUAL') = (regla_id IS NULL)", name="ck_venta_linea_descuento__regla"
        ),
        sa.CheckConstraint("importe > 0", name="ck_venta_linea_descuento__importe"),
        sa.CheckConstraint(
            "porcentaje IS NULL OR (porcentaje > 0 AND porcentaje <= 1)",
            name="ck_venta_linea_descuento__porcentaje",
        ),
    )
    op.create_index(
        "ux_venta_linea_descuento__manual",
        "venta_linea_descuento",
        ["organizacion_id", "venta_linea_id"],
        unique=True,
        postgresql_where=sa.text("origen = 'MANUAL'"),
    )

    op.create_table(
        "intento_pin_autorizacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organizacion_id", sa.Uuid(), nullable=False),
        sa.Column("autorizador_id", sa.Uuid(), nullable=False),
        sa.Column("intentante_id", sa.Uuid(), nullable=True),
        sa.Column("exito", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_intento_pin_autorizacion"),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_intento_pin_autorizacion__organizacion",
        ),
        _fk("intento_pin_autorizacion", "autorizador", "autorizador_id", "usuario"),
        _fk("intento_pin_autorizacion", "intentante", "intentante_id", "usuario"),
        sa.UniqueConstraint("organizacion_id", "id", name="ux_intento_pin_autorizacion__org_id"),
        sa.CheckConstraint(
            "exito OR intentante_id IS NOT NULL",
            name="ck_intento_pin_autorizacion__fallo_con_intentante",
        ),
    )
    op.create_index(
        "ix_intento_pin_autorizacion__autorizador_creado_en",
        "intento_pin_autorizacion",
        ["organizacion_id", "autorizador_id", "creado_en"],
    )
    op.create_index(
        "ix_intento_pin_autorizacion__par_creado_en",
        "intento_pin_autorizacion",
        ["organizacion_id", "autorizador_id", "intentante_id", "creado_en"],
    )

    # INV-05, INV-10, TR-06: solo insercion.
    for tabla in ("venta_linea_descuento", "intento_pin_autorizacion"):
        op.execute(f"GRANT SELECT, INSERT ON {tabla} TO {ROL_RUNTIME}")

    _cambiar_ck_observacion_codigo((*CODIGOS_PREVIOS, CODIGO_NUEVO))
    _sembrar_motivos()


def _sembrar_motivos() -> None:
    """D13: cinco motivos de `DESCUENTO_MANUAL` en cada organizacion que no tenga ninguno de ese
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
    """Aborta con un mensaje claro si hay descuentos de venta (INV-10), snapshots de credito
    (CRE-10) u observaciones `AUTORIZACION_OFFLINE` (dejarian de cumplir el `CHECK`)."""
    conexion = op.get_bind()
    descuentos = conexion.execute(
        sa.text("SELECT count(*) FROM venta_linea_descuento")
    ).scalar_one()
    if descuentos:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: hay {descuentos} fila(s) en "
            "venta_linea_descuento y borrar la tabla perdería la historia (INV-10). "
            "Resolvelas por fuera de la revisión; la revisión no las modifica."
        )
    snapshots = conexion.execute(
        sa.text(
            "SELECT count(*) FROM venta WHERE "
            + " OR ".join(f"{columna} IS NOT NULL" for columna in COLUMNAS_CREDITO)
        )
    ).scalar_one()
    if snapshots:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar: hay {snapshots} venta(s) con snapshot de "
            "crédito (columnas credito_*) y quitarlas perdería lo congelado (CRE-10). "
            "Resolvelas por fuera de la revisión; la revisión no las modifica."
        )
    observaciones = conexion.execute(
        sa.text("SELECT count(*) FROM observacion WHERE codigo = :codigo"),
        {"codigo": CODIGO_NUEVO},
    ).scalar_one()
    if observaciones:
        raise RuntimeError(
            f"La revisión {revision} no puede bajar (design.md D9): hay {observaciones} "
            f"observación(es) {CODIGO_NUEVO} que la revisión anterior no admite. Resolvelas o "
            "eliminalas antes de volver a intentarlo; la revisión no las modifica."
        )


def downgrade() -> None:
    """Downgrade schema."""
    _verificar_que_se_puede_bajar()

    op.drop_index(
        "ix_intento_pin_autorizacion__par_creado_en", table_name="intento_pin_autorizacion"
    )
    op.drop_index(
        "ix_intento_pin_autorizacion__autorizador_creado_en", table_name="intento_pin_autorizacion"
    )
    op.drop_table("intento_pin_autorizacion")
    op.drop_index("ux_venta_linea_descuento__manual", table_name="venta_linea_descuento")
    op.drop_table("venta_linea_descuento")

    for restriccion in (
        "ck_venta__credito_sin_control",
        "ck_venta__credito_exceso",
        "ck_venta__credito_autorizador",
        "ck_venta__credito_resolucion",
        "ck_venta__credito_politica",
    ):
        op.drop_constraint(restriccion, "venta", type_="check")
    op.drop_constraint("fk_venta__credito_autorizador", "venta", type_="foreignkey")
    for columna in reversed(COLUMNAS_CREDITO):
        op.drop_column("venta", columna)

    _cambiar_ck_observacion_codigo(CODIGOS_PREVIOS)

    # Se borran solo los motivos sembrados (por nombre) que nada referencia: un motivo propio de
    # la organizacion no se toca. El ambito sigue en `ck_motivo__ambito`.
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
