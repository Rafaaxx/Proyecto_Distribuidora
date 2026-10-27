"""Tarea 6.1 (change 19; spec `cobranzas/anulacion-de-cobranzas`; `design.md` D9, D10):
`tomar_cobranza_de_venta` y `anular_cobranza_de_venta` de `cobranzas/service.py`, contra
PostgreSQL real. La cobranza de una venta se anula solo con su venta (con devolución) y lleva el
motivo de la venta; `COBRANZA_ANULAR` sigue rechazándola con `COBRANZA_DE_VENTA`.

Reglas citadas: VTA-22, COB-05, CC-02, INV-05, INV-13, INV-21. La concurrencia con commits reales
es de `tests/concurrency` (tarea 11.1); la secuencia completa de la venta, de la tarea 7.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cobranzas_utiles import MOMENTO, PERMISOS_DE_ANULACION, RELOJ, Entorno
from sqlalchemy import text
from sqlalchemy.orm import Session
from ventas_utiles import sembrar_venta_sql

from app.modules.cobranzas import service as cobranzas_service
from app.modules.cobranzas.domain.errores import CobranzaDeVentaError, CobranzaYaAnuladaError
from app.modules.cobranzas.models import Cobranza

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session, permisos=PERMISOS_DE_ANULACION)


def _venta_y_cobranza(entorno: Entorno, importe: str = "20000.00") -> tuple[UUID, UUID]:
    """Una venta sembrada con su cobranza de origen `VENTA`; devuelve (venta, cobranza)."""
    venta = sembrar_venta_sql(
        entorno.sesion,
        entorno.org,
        cliente_id=entorno.cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )
    cobranza_id = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO cobranza (id, organizacion_id, cliente_id, venta_id, origen, importe, "
            "estado, operation_id, usuario_id, dispositivo_id, occurred_at, registered_at) "
            "VALUES (:id, :org, :cli, :venta, 'VENTA', :imp, 'CONFIRMADA', :op, :usu, :dis, "
            ":m, :m)"
        ),
        {
            "id": cobranza_id,
            "org": entorno.org,
            "cli": entorno.cliente_id,
            "venta": venta.venta_id,
            "imp": importe,
            "op": uuid4(),
            "usu": entorno.usuario_id,
            "dis": entorno.dispositivo_id,
            "m": MOMENTO,
        },
    )
    return venta.venta_id, cobranza_id


def _xmax(entorno: Entorno, cobranza_id: UUID) -> int:
    """`xmax` de la fila: distinto de cero cuando una transacción la tomó con `FOR UPDATE`."""
    return int(
        entorno.sesion.execute(
            text("SELECT xmax::text::bigint FROM cobranza WHERE id = :id"), {"id": cobranza_id}
        ).scalar_one()
    )


def _tomar(
    entorno: Entorno, venta_id: UUID, organizacion_id: UUID | None = None
) -> Cobranza | None:
    return cobranzas_service.tomar_cobranza_de_venta(
        organizacion_id or entorno.org, entorno.sesion, venta_id
    )


def _anular(
    entorno: Entorno,
    cobranza: Cobranza,
    motivo_id: UUID,
    observacion: str | None = None,
) -> cobranzas_service.ResultadoDeAnulacion:
    return cobranzas_service.anular_cobranza_de_venta(
        entorno.org,
        entorno.sesion,
        RELOJ,
        cobranza=cobranza,
        motivo_id=motivo_id,
        observacion=observacion,
        operation_id=uuid4(),
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
    )


# --- tomar_cobranza_de_venta (D9, D10) -------------------------------------------------------


def test_inv13_tomar_devuelve_la_cobranza_de_origen_venta_y_la_toma_for_update(
    entorno: Entorno,
) -> None:
    venta_id, cobranza_id = _venta_y_cobranza(entorno)
    assert _xmax(entorno, cobranza_id) == 0

    cobranza = _tomar(entorno, venta_id)

    assert cobranza is not None
    assert (cobranza.id, cobranza.origen, cobranza.estado) == (cobranza_id, "VENTA", "CONFIRMADA")
    assert _xmax(entorno, cobranza_id) != 0  # `FOR UPDATE`: la fila quedó tomada


def test_tomar_devuelve_none_si_la_venta_no_tiene_cobranza(entorno: Entorno) -> None:
    sin_cobro = sembrar_venta_sql(
        entorno.sesion,
        entorno.org,
        cliente_id=entorno.cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )

    assert _tomar(entorno, sin_cobro.venta_id) is None


def test_inv21_tomar_filtra_por_organizacion(entorno: Entorno) -> None:
    """La cobranza de una venta de otra organización no se toma: responde `None` (INV-21)."""
    venta_id, _ = _venta_y_cobranza(entorno)

    assert _tomar(entorno, venta_id, organizacion_id=uuid4()) is None


def test_tomar_no_confunde_una_cobranza_independiente_del_mismo_cliente(entorno: Entorno) -> None:
    """VTA-22: solo cuenta la de origen `VENTA`; una cobranza suelta del cliente no es de la
    venta."""
    sin_cobro = sembrar_venta_sql(
        entorno.sesion,
        entorno.org,
        cliente_id=entorno.cliente_id,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
    )
    entorno.registrar(
        importe="5000.00", medios=entorno.medios((entorno.efectivo_id, "5000.00", None))
    )

    assert _tomar(entorno, sin_cobro.venta_id) is None


# --- anular_cobranza_de_venta (VTA-22, COB-05, CC-02, D9) -------------------------------------


def test_vta22_la_cobranza_queda_anulada_con_el_motivo_de_la_venta_y_el_importe_completo(
    entorno: Entorno,
) -> None:
    """Escenario "Anulada con la venta": $20.000 de una venta de $80.000. El motivo es del ámbito
    `ANULACION_VENTA` (no se valida contra `ANULACION_COBRANZA`) y la observación es la de la
    venta; el saldo sube $20.000 con un `ANULACION_COBRANZA` `AUMENTA`."""
    venta_id, cobranza_id = _venta_y_cobranza(entorno, "20000.00")
    motivo_de_venta = entorno.crear_motivo("ANULACION_VENTA", "Devolución del cliente")
    cobranza = _tomar(entorno, venta_id)
    assert cobranza is not None
    saldo_previo = entorno.saldo()

    resultado = _anular(entorno, cobranza, motivo_de_venta, "se devolvió la mercadería")

    assert resultado.cobranza.id == cobranza_id
    assert entorno.estado_de(cobranza_id) == "ANULADA"
    (anulacion,) = entorno.anulaciones()
    assert anulacion.cobranza_id == cobranza_id
    assert anulacion.motivo_id == motivo_de_venta
    assert anulacion.observacion == "se devolvió la mercadería"
    assert anulacion.usuario_id == entorno.usuario_id
    (movimiento,) = entorno.movimientos("ANULACION_COBRANZA")
    assert (movimiento.sentido, movimiento.importe) == ("AUMENTA", Decimal("20000.00"))
    assert movimiento.origen_id == cobranza_id
    assert entorno.saldo() == saldo_previo + Decimal("20000.00")
    assert resultado.saldo == entorno.saldo()


def test_vta22_otra_cobranza_de_otro_importe_devuelve_ese_importe(entorno: Entorno) -> None:
    """Triangula: el movimiento lleva el importe completo de ESA cobranza, sin observación."""
    venta_id, cobranza_id = _venta_y_cobranza(entorno, "7500.50")
    motivo = entorno.crear_motivo("ANULACION_VENTA", "Error de carga")
    cobranza = _tomar(entorno, venta_id)
    assert cobranza is not None
    saldo_previo = entorno.saldo()

    _anular(entorno, cobranza, motivo)

    (anulacion,) = entorno.anulaciones()
    assert anulacion.observacion is None
    (movimiento,) = entorno.movimientos("ANULACION_COBRANZA")
    assert movimiento.importe == Decimal("7500.50")
    assert entorno.saldo() == saldo_previo + Decimal("7500.50")


def test_cc02_una_cobranza_ya_anulada_responde_cobranza_ya_anulada_y_no_escribe_nada(
    entorno: Entorno,
) -> None:
    venta_id, cobranza_id = _venta_y_cobranza(entorno)
    motivo = entorno.crear_motivo("ANULACION_VENTA", "Error de carga")
    cobranza = _tomar(entorno, venta_id)
    assert cobranza is not None
    _anular(entorno, cobranza, motivo)
    saldo = entorno.saldo()

    with pytest.raises(CobranzaYaAnuladaError) as error:
        _anular(entorno, cobranza, motivo)

    assert error.value.codigo == "COBRANZA_YA_ANULADA"
    assert len(entorno.anulaciones()) == 1
    assert len(entorno.movimientos("ANULACION_COBRANZA")) == 1
    assert entorno.saldo() == saldo
    assert entorno.estado_de(cobranza_id) == "ANULADA"


# --- COBRANZA_ANULAR sigue rechazándola (COB-05, VTA-22) --------------------------------------


def test_cob05_anular_cobranza_sigue_respondiendo_cobranza_de_venta(entorno: Entorno) -> None:
    """Escenario "Por su propio comando": el camino del comando no cambió y nada se escribe."""
    _, cobranza_id = _venta_y_cobranza(entorno)
    motivo = entorno.crear_motivo("ANULACION_COBRANZA", "Error de carga")

    with pytest.raises(CobranzaDeVentaError) as error:
        cobranzas_service.anular_cobranza(
            entorno.org,
            entorno.sesion,
            RELOJ,
            cobranza_id=cobranza_id,
            motivo_id=motivo,
            observacion=None,
            operation_id=uuid4(),
            usuario_id=entorno.usuario_id,
            dispositivo_id=entorno.dispositivo_id,
            occurred_at=MOMENTO,
        )

    assert error.value.codigo == "COBRANZA_DE_VENTA"
    assert entorno.anulaciones() == []


def test_inv05_la_base_impide_dos_anulaciones_de_la_misma_cobranza(entorno: Entorno) -> None:
    """INV-05, D9: aunque el servicio no revalidara el estado, `ux_cobranza_anulacion__cobranza`
    sigue impidiendo la segunda anulación."""
    venta_id, cobranza_id = _venta_y_cobranza(entorno)
    motivo = entorno.crear_motivo("ANULACION_VENTA", "Error de carga")
    cobranza = _tomar(entorno, venta_id)
    assert cobranza is not None
    _anular(entorno, cobranza, motivo)
    cobranza.estado = "CONFIRMADA"  # salta la revalidación del servicio: lo para la base

    with pytest.raises(CobranzaYaAnuladaError):
        _anular(entorno, cobranza, motivo)

    assert len(entorno.anulaciones()) == 1
