"""Change 06, tarea 6.3: `calcular_costo_base` levanta el error exacto para
cada entrada inválida (los casos compartidos de
`tests/fixtures_compartidos/test_cst02_costo_base_fixtures.py` solo
verifican que levanta *alguna* excepción; acá se fija el tipo, TR-01/TR-02)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.proveedores.domain.costo_base import calcular_costo_base
from app.modules.proveedores.domain.errores import (
    BonificacionInvalidaError,
    ValorInvalidoError,
)


@pytest.mark.parametrize("valor", [Decimal("0.00"), Decimal("-5.00")])
def test_valor_no_positivo_es_valor_invalido(valor: Decimal) -> None:
    with pytest.raises(ValorInvalidoError):
        calcular_costo_base(
            valor=valor,
            incluye_iva=False,
            alicuota=Decimal("0"),
            bonificacion=Decimal("0"),
            unidades=12,
        )


@pytest.mark.parametrize("bonificacion", [Decimal("1.000000"), Decimal("-0.000001")])
def test_bonificacion_fuera_de_rango_es_bonificacion_invalida(bonificacion: Decimal) -> None:
    with pytest.raises(BonificacionInvalidaError):
        calcular_costo_base(
            valor=Decimal("18000.00"),
            incluye_iva=False,
            alicuota=Decimal("0"),
            bonificacion=bonificacion,
            unidades=12,
        )


def test_unidades_menor_a_uno_levanta_value_error() -> None:
    with pytest.raises(ValueError):
        calcular_costo_base(
            valor=Decimal("18000.00"),
            incluye_iva=False,
            alicuota=Decimal("0"),
            bonificacion=Decimal("0"),
            unidades=0,
        )


def test_bonificacion_limite_superior_exclusivo_es_valida() -> None:
    # Triangulación del borde: 0.999999 es válida (el CHECK de la base es
    # `< 1`, no `<= 1`), a diferencia de 1.000000.
    resultado = calcular_costo_base(
        valor=Decimal("100.00"),
        incluye_iva=False,
        alicuota=Decimal("0"),
        bonificacion=Decimal("0.999999"),
        unidades=1,
    )
    assert resultado == Decimal("0.000100")
