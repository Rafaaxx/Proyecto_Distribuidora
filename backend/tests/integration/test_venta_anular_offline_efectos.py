"""Tarea 2.2 (change 22d; spec `ventas/anulacion-de-venta`, requisito "La anulación sin conexión
lleva la jornada del sobre"; `design.md` D3, aprobada el 2026-11-03), contra PostgreSQL real y por
`procesar_lote`.

- Con la jornada abierta, la anulación y el reingreso llevan la jornada del sobre.
- Con devolución, el stock y el saldo quedan exactamente como antes de la venta; sin devolución, el
  saldo difiere solo en lo cobrado en el acto.
- Con la jornada liberada o la camioneta tomada, `venta_anulacion.jornada_id` es igual la del sobre
  (la rendición del change 24 cuenta la anulación por esa jornada) y el reingreso queda sin jornada.

Reglas citadas: INV-19, INV-01, INV-12, INV-13, VTA-22, COB-05, RUT-07.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from sqlalchemy.orm import Session
from test_ventas_offline import Ruta
from venta_anular_offline_utiles import anular, vender
from ventas_anular_utiles import EntornoAnulacion

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

SALDO_ANTES = Decimal("150000.00")


@pytest.fixture
def entorno(db_session: Session) -> EntornoAnulacion:
    return EntornoAnulacion(db_session)


def _cobranza_de_la_venta(entorno: EntornoAnulacion) -> UUID:
    (cobranza,) = entorno.cobranzas()
    return cobranza.id


def test_inv19_con_la_jornada_abierta_la_anulacion_y_el_reingreso_llevan_la_jornada_del_sobre(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación con la jornada abierta"
    """RUT-04, STK-09, RUT-07: J1 `ABIERTA` sobre la camioneta 2; la anulación y su reingreso
    llevan J1 y vuelve la mercadería al costo congelado."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta)

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO"
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.jornada_id == ruta.jornada_id
    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert (reingreso.jornada_id, reingreso.ubicacion_id) == (ruta.jornada_id, ruta.camioneta_id)
    (egreso,) = entorno.movimientos_de_stock("VENTA")
    assert reingreso.costo_unitario == egreso.costo_unitario == Decimal("1050.000000")


def test_inv19_con_devolucion_el_stock_y_el_saldo_quedan_como_antes_de_la_venta(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación con devolución"
    """VTA-22, INV-19, COB-05: venta de $31.250 con $20.000 cobrados en el acto; la anulación
    devuelve el dinero: la cobranza queda anulada y el stock y el saldo son los previos."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta, cobranza=entorno.cobranza())
    cobranza_id = _cobranza_de_la_venta(entorno)
    assert entorno.saldo() == Decimal("161250.00")  # 150.000 + 31.250 - 20.000

    _, resultado = anular(entorno, ruta, venta_id, devuelve_dinero=True)

    assert resultado.estado == "ACEPTADO"
    assert resultado.resultado is not None
    assert resultado.resultado["cobranza_anulada"] is True
    assert resultado.resultado["saldo"] == str(SALDO_ANTES)
    assert entorno.estado_de_cobranza(cobranza_id) == "ANULADA"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.devuelve_dinero is True


def test_inv19_sin_devolucion_el_saldo_difiere_solo_en_lo_cobrado_a_favor_del_cliente(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación sin devolución"
    """VTA-22, INV-19: la misma venta anulada sin devolver el dinero: la cobranza sigue
    confirmada y el saldo queda $20.000 por debajo del previo (a favor del cliente)."""
    ruta = Ruta(entorno)
    venta_id = vender(ruta, cobranza=entorno.cobranza())
    cobranza_id = _cobranza_de_la_venta(entorno)

    _, resultado = anular(entorno, ruta, venta_id, devuelve_dinero=False)

    assert resultado.estado == "ACEPTADO"
    assert resultado.resultado is not None
    assert resultado.resultado["cobranza_anulada"] is False
    assert entorno.estado_de_cobranza(cobranza_id) == "CONFIRMADA"
    assert entorno.stock(ubicacion_id=ruta.camioneta_id) == 48
    assert entorno.saldo() == SALDO_ANTES - Decimal("20000.00")
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.devuelve_dinero is False


def test_rut07_con_la_jornada_liberada_la_anulacion_lleva_igual_la_jornada_del_sobre(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación sin conexión con la jornada liberada" (jornada del sobre)
    """RUT-07: J1 fue liberada; el reingreso queda sin jornada (la camioneta es de nadie) pero
    `venta_anulacion.jornada_id` es J1, para que la rendición la cuente."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    venta_id = vender(ruta)

    _, resultado = anular(entorno, ruta, venta_id)

    assert resultado.estado == "ACEPTADO_CON_OBSERVACIONES"
    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.jornada_id == ruta.jornada_id
    (reingreso,) = entorno.movimientos_de_stock("ANULACION_VENTA")
    assert reingreso.jornada_id is None


def test_rut07_con_la_camioneta_tomada_por_otro_la_anulacion_sigue_llevando_la_del_sobre(
    entorno: EntornoAnulacion,
) -> None:
    # Escenario: "Anulación sin conexión con la jornada liberada" (jornada del sobre)
    """Triangulación: Pedro tomó la camioneta; la anulación igual lleva J1 y no la de Pedro."""
    ruta = Ruta(entorno, estado_jornada="LIBERADA")
    venta_id = vender(ruta)
    otro_id, otro_dispositivo_id = crear_usuario_y_dispositivo(
        entorno.sesion, entorno.org, permisos=frozenset({"VENDER"})
    )
    jornada_de_pedro = entorno.crear_jornada(
        usuario_id=otro_id, dispositivo_id=otro_dispositivo_id, ubicacion_id=ruta.camioneta_id
    )

    anular(entorno, ruta, venta_id)

    (anulacion,) = entorno.anulaciones_de_venta()
    assert anulacion.jornada_id == ruta.jornada_id != jornada_de_pedro
