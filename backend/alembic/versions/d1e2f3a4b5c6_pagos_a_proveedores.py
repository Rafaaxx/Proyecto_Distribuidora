"""pagos a proveedores: ambito de motivo ANULACION_PAGO, observacion, CHECK estricto de
anulacion e indices de listado

Revision ID: d1e2f3a4b5c6
Revises: a9c0d1e2f3a4
Create Date: 2026-10-03 00:00:00.000000

Change 12 (`design.md` D1, D6, D9 opcion A), una sola revision, sin mover datos
de negocio existentes:

- `ck_motivo__ambito` suma `ANULACION_PAGO` a la lista cerrada (`03` §4, TR-09) y
  siembra, de forma idempotente, sus tres motivos -- "Error de carga", "Pago
  rechazado o devuelto" y "Otro" -- en cada organizacion que no tenga ninguno de
  ese ambito (D1).
- `pago_proveedor.observacion text` nulable (D6): donde se anota a que facturas se
  imputa el pago, porque no hay imputacion (PAG-02). NO entra en el `GRANT
  UPDATE`: es inmutable (INV-05, igual que `compra.observacion`).
- `ck_pago_proveedor__anulacion_coherente` pasa a exigir "anulada <=> momento,
  usuario **y motivo**", con el mismo texto que `ck_compra__anulacion_coherente`
  (PAG-03, D9 punto 3). Antes de crearlo, la revision verifica que ningun pago
  `ANULADA` tenga `anulacion_motivo_id` nulo y aborta con un mensaje claro si
  encuentra uno: el change 11 siempre escribio el motivo, asi que un NULL deleria
  un defecto previo y el error de PostgreSQL al agregar el CHECK seria opaco.
- Indices de listado `(organizacion_id, fecha DESC, id DESC)` y
  `(organizacion_id, proveedor_id, fecha DESC, id DESC)`, los mismos que usa el
  listado de compras (D9 punto 4).

Los permisos de `app_runtime` no cambian: `pago_proveedor` sigue en
`SELECT, INSERT` mas `UPDATE` solo de `estado`, `anulado_en`, `anulado_por_id` y
`anulacion_motivo_id`; nunca `DELETE` (INV-05).

`downgrade` quita los indices, la columna y el `CHECK` estricto, pone en nulo el
motivo de los pagos anulados con un motivo `ANULACION_PAGO`, borra esos motivos y
restaura el `CHECK` de ambitos: **pierde motivos y observaciones por diseno**
(D9; `04` §2.1 punto 4 lo tolera: "sube y baja limpia" es correr sin errores y
respetando la integridad referencial en cada paso, no que los datos de negocio
sobrevivan un rollback; mismo criterio que `docs/04` §7 en el change 06). Por eso
volver a aplicar `upgrade` sobre una base ya bajada exige restituir antes los
motivos: el guard de D9 punto 3 aborta si queda un pago `ANULADA` sin motivo, que
es exactamente lo que el propio `downgrade` deja. La perdida esta escrita como
asercion explicita en `backend/tests/integration/test_pagos_proveedor_migracion.py`
(tarea 1.2).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from app.core.ids import nuevo_id

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "a9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AMBITOS_MOTIVO = (
    "AJUSTE_STOCK",
    "ANULACION_VENTA",
    "ANULACION_COMPRA",
    "ANULACION_COBRANZA",
    "ANULACION_PAGO",
    "DESCUENTO_MANUAL",
    "LISTA_ANTERIOR",
    "LIBERACION_JORNADA",
)

AMBITO = "ANULACION_PAGO"
MOTIVOS = ("Error de carga", "Pago rechazado o devuelto", "Otro")

_CHECK_ANULACION_COHERENTE = (
    "(estado = 'ANULADA') = (anulado_en IS NOT NULL) "
    "AND (anulado_en IS NOT NULL) = (anulacion_motivo_id IS NOT NULL) "
    "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL)"
)
"""La forma estricta de "anulada <=> momento, usuario y motivo", con los nombres de
columna del pago (`anulado_en`, `anulado_por_id`; `compra` usa `anulada_*`): es la
misma regla que `ck_compra__anulacion_coherente`, byte a byte salvo por esos dos
nombres, y la prueba `test_el_check_de_anulacion_del_pago_es_el_mismo_que_el_de_la_
compra` lo compara normalizándolos."""


def _cambiar_ck_motivo_ambito(ambitos: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE motivo DROP CONSTRAINT ck_motivo__ambito")
    op.execute(
        "ALTER TABLE motivo ADD CONSTRAINT ck_motivo__ambito CHECK (ambito IN ("
        + ", ".join(f"'{ambito}'" for ambito in ambitos)
        + "))"
    )


def upgrade() -> None:
    """Upgrade schema."""
    _verificar_que_todo_pago_anulado_tiene_motivo()

    _cambiar_ck_motivo_ambito(AMBITOS_MOTIVO)

    op.execute("ALTER TABLE pago_proveedor ADD COLUMN observacion text")
    op.execute("ALTER TABLE pago_proveedor DROP CONSTRAINT ck_pago_proveedor__anulacion_coherente")
    op.execute(
        "ALTER TABLE pago_proveedor ADD CONSTRAINT ck_pago_proveedor__anulacion_coherente "
        f"CHECK ({_CHECK_ANULACION_COHERENTE})"
    )

    op.create_index(
        "ix_pago_proveedor__fecha",
        "pago_proveedor",
        ["organizacion_id", sa.text("fecha DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_pago_proveedor__proveedor_fecha",
        "pago_proveedor",
        ["organizacion_id", "proveedor_id", sa.text("fecha DESC"), sa.text("id DESC")],
    )

    _sembrar_motivos()


def _verificar_que_todo_pago_anulado_tiene_motivo() -> None:
    """D9 punto 3: aborta con un mensaje claro si hay un pago `ANULADA` con
    `anulacion_motivo_id` nulo. Sin esta comprobacion, `ADD CONSTRAINT` fallaria con
    un `CheckViolation` que no dice que pago ni por que; el mensaje de arriba si."""
    conexion = op.get_bind()
    sin_motivo = conexion.execute(
        sa.text(
            "SELECT count(*) FROM pago_proveedor "
            "WHERE estado = 'ANULADA' AND anulacion_motivo_id IS NULL"
        )
    ).scalar_one()
    if sin_motivo:
        raise RuntimeError(
            f"La revisión {revision} no puede aplicar "
            "ck_pago_proveedor__anulacion_coherente (PAG-03, design.md D9 punto 3): hay "
            f"{sin_motivo} pago(s) en estado ANULADA con anulacion_motivo_id nulo. "
            "Todo pago anulado debe tener motivo, usuario y momento. Revisá esas filas "
            "(SELECT id, proveedor_id FROM pago_proveedor WHERE estado = 'ANULADA' AND "
            "anulacion_motivo_id IS NULL) y corregilas antes de volver a aplicar la "
            "migración; la revisión no las modifica."
        )


def _sembrar_motivos() -> None:
    """D1: tres motivos de `ANULACION_PAGO` en cada organización que no tenga
    ninguno de ese ámbito. Idempotente, igual que la siembra de `ANULACION_COMPRA`
    del change 11: una organización con motivos propios (o ya sembrada) no se toca."""
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
    op.drop_index("ix_pago_proveedor__proveedor_fecha", table_name="pago_proveedor")
    op.drop_index("ix_pago_proveedor__fecha", table_name="pago_proveedor")

    # El `CHECK` estricto se afloja ANTES de poner motivos en nulo: el estricto
    # rechaza justamente ese estado.
    op.execute("ALTER TABLE pago_proveedor DROP CONSTRAINT ck_pago_proveedor__anulacion_coherente")
    op.execute(
        "ALTER TABLE pago_proveedor ADD CONSTRAINT ck_pago_proveedor__anulacion_coherente "
        "CHECK ((estado = 'ANULADA') = (anulado_en IS NOT NULL) "
        "AND (anulado_en IS NOT NULL) = (anulado_por_id IS NOT NULL) "
        "AND (anulacion_motivo_id IS NULL OR anulado_en IS NOT NULL))"
    )

    # Los motivos de `ANULACION_PAGO` se van con el `CHECK` de ambitos, asi que el
    # pago que los tiene deja de poder referenciarlos (D9: se pierde por diseno).
    op.execute(
        sa.text(
            "UPDATE pago_proveedor p SET anulacion_motivo_id = NULL "
            "WHERE p.estado = 'ANULADA' AND EXISTS ("
            "SELECT 1 FROM motivo m WHERE m.id = p.anulacion_motivo_id "
            "AND m.organizacion_id = p.organizacion_id AND m.ambito = :ambito)"
        ).bindparams(sa.bindparam("ambito", AMBITO))
    )

    op.execute("ALTER TABLE pago_proveedor DROP COLUMN observacion")

    # Se borra TODO motivo del ámbito `ANULACION_PAGO`, no solo los tres sembrados: el
    # `CHECK` de ámbitos vuelve a una lista sin ese ámbito, así que un motivo propio de
    # la organización que quedara haría fallar el `downgrade`. Primero quedan en nulo
    # las referencias de los pagos (arriba); los libros, que son de solo inserción
    # (INV-05), se respetan como en el change 11.
    op.execute(
        sa.text(
            "DELETE FROM motivo m WHERE m.ambito = :ambito "
            "AND NOT EXISTS (SELECT 1 FROM auditoria a "
            "WHERE a.organizacion_id = m.organizacion_id AND a.motivo_id = m.id) "
            "AND NOT EXISTS (SELECT 1 FROM stock_movimiento s "
            "WHERE s.organizacion_id = m.organizacion_id AND s.motivo_id = m.id) "
            "AND NOT EXISTS (SELECT 1 FROM compra c "
            "WHERE c.organizacion_id = m.organizacion_id AND c.anulacion_motivo_id = m.id)"
        ).bindparams(sa.bindparam("ambito", AMBITO))
    )

    _cambiar_ck_motivo_ambito(tuple(a for a in AMBITOS_MOTIVO if a != AMBITO))
