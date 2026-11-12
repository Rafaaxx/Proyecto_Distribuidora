"""Tarea 5.1 (change 19, `design.md` D5, D7; spec `stock/libro-de-stock`): el ingreso
`ANULACION_VENTA` en el dominio puro del libro de stock.

Reglas citadas: STK-03, CST-11, CST-12, CAT-05, INV-01, ADR-058.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.stock.domain.errores import TipoDeMovimientoInvalidoError
from app.modules.stock.domain.movimientos import (
    ANULACION_COMPRA,
    ANULACION_VENTA,
    LineaDeMovimiento,
    productos_que_exigen_estar_activos,
    validar_lineas_de_movimiento,
)

VINO = uuid4()
AGUA = uuid4()
DEPOSITO = uuid4()


def _linea(
    tipo: str, cantidad: int, costo: str | None = None, producto: object = VINO
) -> LineaDeMovimiento:
    return LineaDeMovimiento(
        producto,  # type: ignore[arg-type]
        DEPOSITO,
        cantidad,
        tipo,
        None if costo is None else Decimal(costo),
        "VENTA",
        uuid4(),
    )


# --- STK-03, CST-11, CST-12: el ingreso lleva el costo de la línea o ninguno (D5) -------------


@pytest.mark.parametrize(("cantidad", "costo"), [(72, "1050.000000"), (12, "17.500000")])
def test_stk03_un_ingreso_de_anulacion_de_venta_con_costo_es_valido(
    cantidad: int, costo: str
) -> None:
    linea = _linea(ANULACION_VENTA, cantidad, costo)

    assert validar_lineas_de_movimiento([linea]) == [linea]


@pytest.mark.parametrize("cantidad", [12, 1])
def test_cst12_un_ingreso_de_anulacion_de_venta_sin_costo_es_valido(cantidad: int) -> None:
    """Línea vendida sin costo (ADR-054 `VENTA_SIN_COSTO`): se acepta y se revierte sin costo."""
    linea = _linea(ANULACION_VENTA, cantidad, None)

    assert validar_lineas_de_movimiento([linea]) == [linea]


@pytest.mark.parametrize("costo", [None, "1050.000000"])
def test_inv01_una_anulacion_de_venta_con_cantidad_negativa_se_rechaza(costo: str | None) -> None:
    with pytest.raises(TipoDeMovimientoInvalidoError):
        validar_lineas_de_movimiento([_linea(ANULACION_VENTA, -5, costo)])


def test_las_lineas_de_una_anulacion_de_venta_pueden_repetir_producto() -> None:
    """D5: "un mismo producto en dos presentaciones son dos ingresos"."""
    lineas = [_linea(ANULACION_VENTA, 6, "1050.000000"), _linea(ANULACION_VENTA, 12, None)]

    assert validar_lineas_de_movimiento(lineas) == lineas


# --- CAT-05, D7: producto inactivo solo para la anulación --------------------------------------


def test_cat05_la_anulacion_de_venta_no_exige_el_producto_activo() -> None:
    assert productos_que_exigen_estar_activos([_linea(ANULACION_VENTA, 6, "1050")]) == set()


def test_cat05_un_ingreso_de_compra_si_exige_el_producto_activo() -> None:
    assert productos_que_exigen_estar_activos([_linea("COMPRA", 6, "1050")]) == {VINO}


def test_cat05_con_otro_tipo_para_el_mismo_producto_se_exige_activo() -> None:
    """Un producto con una línea de anulación y otra de compra sigue exigiéndose; el otro,
    que solo tiene la anulación, no."""
    lineas = [
        _linea(ANULACION_VENTA, 6, "1050", VINO),
        _linea("COMPRA", 6, "1050", VINO),
        _linea(ANULACION_VENTA, 6, None, AGUA),
    ]

    assert productos_que_exigen_estar_activos(lineas) == {VINO}


def test_cat05_la_exencion_de_la_anulacion_de_compra_sigue_igual() -> None:
    assert productos_que_exigen_estar_activos([_linea(ANULACION_COMPRA, -6, "1050")]) == set()
