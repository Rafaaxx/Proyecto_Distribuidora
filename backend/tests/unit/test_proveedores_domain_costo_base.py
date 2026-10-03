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
            computa_credito_fiscal=True,
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
            computa_credito_fiscal=True,
            incluye_iva=False,
            alicuota=Decimal("0"),
            bonificacion=bonificacion,
            unidades=12,
        )


def test_unidades_menor_a_uno_levanta_value_error() -> None:
    with pytest.raises(ValueError):
        calcular_costo_base(
            valor=Decimal("18000.00"),
            computa_credito_fiscal=True,
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
        computa_credito_fiscal=True,
        incluye_iva=False,
        alicuota=Decimal("0"),
        bonificacion=Decimal("0.999999"),
        unidades=1,
    )
    assert resultado == Decimal("0.000100")


# --- 11b, CST-06: sin crédito fiscal el IVA es costo --------------------------------------


def test_sin_credito_fiscal_el_valor_pagado_no_se_divide_por_la_alicuota() -> None:
    """CST-02 + CST-06: caja x12 a $21.780 de un monotributista, el IVA es costo."""
    resultado = calcular_costo_base(
        computa_credito_fiscal=False,
        valor=Decimal("21780.00"),
        incluye_iva=False,
        alicuota=Decimal("0.21"),
        bonificacion=Decimal("0"),
        unidades=12,
    )

    assert resultado == Decimal("1815.000000")


def test_con_credito_fiscal_el_mismo_valor_con_iva_incluido_si_se_divide() -> None:
    """Contraste del caso anterior: el responsable inscripto descuenta el IVA."""
    resultado = calcular_costo_base(
        computa_credito_fiscal=True,
        valor=Decimal("21780.00"),
        incluye_iva=True,
        alicuota=Decimal("0.21"),
        bonificacion=Decimal("0"),
        unidades=12,
    )

    assert resultado == Decimal("1500.000000")


@pytest.mark.parametrize("alicuota", [Decimal("0"), Decimal("0.105"), Decimal("0.21")])
def test_sin_credito_fiscal_el_costo_no_depende_de_la_alicuota(alicuota: Decimal) -> None:
    resultado = calcular_costo_base(
        computa_credito_fiscal=False,
        valor=Decimal("21780.00"),
        incluye_iva=False,
        alicuota=alicuota,
        bonificacion=Decimal("0.10"),
        unidades=12,
    )

    assert resultado == Decimal("1633.500000")


def test_sin_credito_fiscal_se_sigue_validando_el_valor() -> None:
    with pytest.raises(ValorInvalidoError):
        calcular_costo_base(
            computa_credito_fiscal=False,
            valor=Decimal("0.00"),
            incluye_iva=False,
            alicuota=Decimal("0.21"),
            bonificacion=Decimal("0"),
            unidades=12,
        )
