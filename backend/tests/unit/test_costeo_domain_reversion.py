"""Tarea 6.1: `calcular_reversion` (CMP-06, CST-13, `design.md` D9).

Los casos numéricos canónicos viven en `cst-11-costo-promedio.json`
(`tests/fixtures_compartidos/test_cst11_reversion_fixtures.py`); acá se prueban
los contratos que ese formato no expresa: validaciones, bordes del recálculo y la
propiedad de ida y vuelta con `calcular_ingreso`.

Reglas citadas: CMP-06, CST-11, CST-13, INV-04.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.costeo.domain.costo_promedio import calcular_ingreso, calcular_reversion
from app.modules.costeo.domain.errores import (
    CantidadInvalidaError,
    CostoInvalidoError,
    PromedioInconsistenteError,
)


def test_con_stock_restante_positivo_recalcula_el_promedio() -> None:
    resultado = calcular_reversion(
        stock_previo=120,
        promedio_previo=Decimal("1050.000000"),
        cantidad=60,
        costo_ingreso="1100.000000",
    )

    assert resultado.recalculado is True
    assert resultado.promedio_nuevo == Decimal("1000.000000")
    assert resultado.stock_nuevo == 60


def test_el_recalculo_redondea_una_sola_vez_half_up_a_seis_decimales() -> None:
    # (100 * 10 - 3 * 20) / 97 = 9.690721649...
    resultado = calcular_reversion(
        stock_previo=100, promedio_previo=Decimal("10"), cantidad=3, costo_ingreso="20"
    )

    assert resultado.promedio_nuevo == Decimal("9.690722")
    assert resultado.recalculado is True


def test_con_stock_restante_cero_mantiene_el_promedio() -> None:
    resultado = calcular_reversion(
        stock_previo=60, promedio_previo=Decimal("1100"), cantidad=60, costo_ingreso="1100"
    )

    assert resultado.recalculado is False
    assert resultado.promedio_nuevo == Decimal("1100.000000")
    assert resultado.stock_nuevo == 0


def test_con_stock_restante_negativo_mantiene_el_promedio() -> None:
    resultado = calcular_reversion(
        stock_previo=48, promedio_previo=Decimal("1050"), cantidad=60, costo_ingreso="1100"
    )

    assert (resultado.recalculado, resultado.stock_nuevo) == (False, -12)
    assert resultado.promedio_nuevo == Decimal("1050.000000")


def test_con_promedio_resultante_cero_mantiene_el_promedio() -> None:
    # (10 * 100 - 5 * 200) / 5 = 0
    resultado = calcular_reversion(
        stock_previo=10, promedio_previo=Decimal("100"), cantidad=5, costo_ingreso="200"
    )

    assert resultado.recalculado is False
    assert resultado.promedio_nuevo == Decimal("100.000000")


def test_con_promedio_resultante_negativo_mantiene_el_promedio() -> None:
    resultado = calcular_reversion(
        stock_previo=65,
        promedio_previo=Decimal("1728.571429"),
        cantidad=60,
        costo_ingreso="2000",
    )

    assert resultado.recalculado is False
    assert resultado.promedio_nuevo == Decimal("1728.571429")


def test_sin_promedio_previo_es_inconsistente() -> None:
    with pytest.raises(PromedioInconsistenteError):
        calcular_reversion(stock_previo=10, promedio_previo=None, cantidad=5, costo_ingreso="100")


@pytest.mark.parametrize("cantidad", [0, -1])
def test_la_cantidad_debe_ser_positiva(cantidad: int) -> None:
    with pytest.raises(CantidadInvalidaError):
        calcular_reversion(
            stock_previo=10, promedio_previo=Decimal("1"), cantidad=cantidad, costo_ingreso="1"
        )


@pytest.mark.parametrize("costo", ["0", "-1", "1.1234567", 1000])
def test_el_costo_de_la_linea_debe_ser_valido(costo: object) -> None:
    with pytest.raises(CostoInvalidoError):
        calcular_reversion(
            stock_previo=10, promedio_previo=Decimal("1"), cantidad=1, costo_ingreso=costo
        )


@given(
    stock=st.integers(min_value=1, max_value=100_000),
    cantidad=st.integers(min_value=1, max_value=100_000),
    promedio=st.decimals(min_value=Decimal("1"), max_value=Decimal("100000"), places=6),
    costo=st.decimals(min_value=Decimal("1"), max_value=Decimal("100000"), places=6),
)
def test_ingreso_seguido_de_reversion_devuelve_el_promedio_previo_cmp_06(
    stock: int, cantidad: int, promedio: Decimal, costo: Decimal
) -> None:
    """CMP-06: ida y vuelta con stock previo > 0, dentro de `0.000001 x (S+q)/S`
    (dos redondeos a 6 decimales, `design.md` Risks)."""
    ingreso = calcular_ingreso(
        stock_previo=stock, promedio_previo=promedio, cantidad=cantidad, costo_ingreso=costo
    )

    reversion = calcular_reversion(
        stock_previo=ingreso.stock_nuevo,
        promedio_previo=ingreso.promedio_nuevo,
        cantidad=cantidad,
        costo_ingreso=costo,
    )

    tolerancia = Decimal("0.000001") * Decimal(stock + cantidad) / Decimal(stock)
    assert reversion.stock_nuevo == stock
    assert reversion.recalculado is True
    assert abs(reversion.promedio_nuevo - promedio) <= tolerancia
