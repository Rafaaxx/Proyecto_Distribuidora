"""Tarea 3.1 (change 14, `design.md` D3, D9): ingreso sin costo en el dominio de `costeo`.

Un ingreso de transferencia o de ajuste sube el stock total y deja el promedio como
está (CST-12): la valorización del movimiento es el promedio vigente, o `None` si el
producto no tiene. Funciones puras, sin infraestructura (`02` §5.2).

Reglas citadas: CST-12, CST-11, INV-04, INV-15.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.costeo.domain.costo_promedio import (
    STOCK_MAXIMO,
    calcular_ingreso_sin_recalculo,
)
from app.modules.costeo.domain.errores import CantidadInvalidaError, StockFueraDeRangoError


def test_el_promedio_no_cambia_y_el_stock_sube() -> None:
    """Escenario "Ingreso sin costo con promedio": 114 + 2 = 116 y el promedio sigue."""
    resultado = calcular_ingreso_sin_recalculo(
        stock_previo=114, promedio_previo=Decimal("1050.000000"), cantidad=2
    )

    assert resultado.stock_nuevo == 116
    assert resultado.promedio == Decimal("1050.000000")
    assert resultado.promedio is not None and str(resultado.promedio) == "1050.000000"


def test_sobre_stock_total_negativo_el_promedio_tampoco_cambia() -> None:
    """Escenario "Ingreso sin costo sobre stock total negativo": −12 + 12 = 0; no se
    recalcula nada (la próxima compra fijará el promedio por CST-11)."""
    resultado = calcular_ingreso_sin_recalculo(
        stock_previo=-12, promedio_previo=Decimal("1050.000000"), cantidad=12
    )

    assert resultado.stock_nuevo == 0
    assert resultado.promedio == Decimal("1050.000000")


def test_sin_promedio_la_valorizacion_es_nula() -> None:
    """Un producto que nunca tuvo un ingreso con costo no tiene promedio (D10): el
    movimiento queda sin valorizar y no se inventa uno."""
    resultado = calcular_ingreso_sin_recalculo(stock_previo=0, promedio_previo=None, cantidad=24)

    assert resultado.stock_nuevo == 24
    assert resultado.promedio is None


@pytest.mark.parametrize("cantidad", [0, -1, -48])
def test_una_cantidad_no_positiva_se_rechaza(cantidad: int) -> None:
    with pytest.raises(CantidadInvalidaError):
        calcular_ingreso_sin_recalculo(
            stock_previo=10, promedio_previo=Decimal("1.000000"), cantidad=cantidad
        )


@pytest.mark.parametrize("cantidad", [1.5, "3", True])
def test_una_cantidad_que_no_es_entero_se_rechaza(cantidad: object) -> None:
    """INV-04: la cantidad es un entero en unidad base (un `bool` no cuenta)."""
    with pytest.raises(CantidadInvalidaError):
        calcular_ingreso_sin_recalculo(
            stock_previo=10,
            promedio_previo=Decimal("1.000000"),
            cantidad=cantidad,  # type: ignore[arg-type]
        )


def test_un_stock_que_no_entra_en_integer_se_rechaza() -> None:
    with pytest.raises(StockFueraDeRangoError):
        calcular_ingreso_sin_recalculo(
            stock_previo=STOCK_MAXIMO, promedio_previo=Decimal("1.000000"), cantidad=1
        )
