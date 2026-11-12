"""Change 13, tarea 4.2: costo de referencia y precio calculado
(`precios/domain/calculo.py`; spec `precios/calculo-de-precios`; PRC-11, PRC-12, TR-03).

Los primeros casos son los ejemplos de `01` §7.2: Vino A, costo base `1000.000000` por
botella, referencia `Caja x6` (costo de referencia `6000.000000`), markup 30% (`7800`) y
margen bruto 30% (`8571.428571`).

Reglas citadas: PRC-11, PRC-12, TR-01, TR-02, TR-03, INV-03.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.money import EntradaNoEsDineroExactoError
from app.modules.precios.domain.calculo import (
    calcular_costo_de_referencia,
    calcular_precio_sin_redondear,
)
from app.modules.precios.domain.errores import MargenInvalidoError

# --- PRC-11: el costo de referencia ---------------------------------------------------


@pytest.mark.parametrize(
    ("costo_base", "unidades", "esperado"),
    [
        ("1000.000000", 6, "6000.000000"),  # Vino A: informado por botella, referencia x6
        ("1500.000000", 12, "18000.000000"),  # Cerveza B: informado en la caja de referencia
        ("1815.000000", 12, "21780.000000"),  # monotributo: el IVA es costo
        ("1239.669421", 6, "7438.016526"),
        ("0.333333", 3, "0.999999"),  # sin redondeo intermedio: no sube a 1
        ("1000.000000", 1, "1000.000000"),
    ],
)
def test_el_costo_de_referencia_es_el_costo_base_por_las_unidades_de_la_referencia(
    costo_base: str, unidades: int, esperado: str
) -> None:
    resultado = calcular_costo_de_referencia(Decimal(costo_base), unidades)

    assert str(resultado) == esperado


@pytest.mark.parametrize("unidades", [0, -6])
def test_las_unidades_de_referencia_deben_ser_al_menos_una(unidades: int) -> None:
    with pytest.raises(ValueError, match="unidades de referencia"):
        calcular_costo_de_referencia(Decimal("1000.000000"), unidades)


def test_el_costo_base_no_puede_ser_un_punto_flotante() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_costo_de_referencia(1000.5, 6)  # type: ignore[arg-type]


# --- PRC-12: markup y margen bruto -------------------------------------------------------


@pytest.mark.parametrize(
    ("costo", "tipo", "valor", "esperado"),
    [
        ("6000.000000", "MARKUP", "0.300000", "7800.000000"),  # `01` §7.2
        ("6000.000000", "MARGEN_BRUTO", "0.300000", "8571.428571"),  # `01` §7.2
        ("6000.000000", "MARKUP", "0.000000", "6000.000000"),  # margen cero
        ("6000.000000", "MARGEN_BRUTO", "0.000000", "6000.000000"),
        ("21780.000000", "MARKUP", "0.300000", "28314.000000"),
        ("21780.000000", "MARGEN_BRUTO", "0.350000", "33507.692308"),
        ("5700.000000", "MARKUP", "0.300000", "7410.000000"),
        ("6600.000000", "MARGEN_BRUTO", "0.300000", "9428.571429"),
        ("6000.000000", "MARKUP", "1.500000", "15000.000000"),  # markup mayor al 100%
        ("6000.000000", "MARGEN_BRUTO", "0.999999", "6000000000.000000"),
    ],
)
def test_el_precio_calculado_aplica_el_margen_con_decimales_exactos(
    costo: str, tipo: str, valor: str, esperado: str
) -> None:
    resultado = calcular_precio_sin_redondear(Decimal(costo), tipo, Decimal(valor))

    assert str(resultado) == esperado


def test_el_precio_calculado_tiene_seis_decimales_con_medio_hacia_arriba() -> None:
    """TR-02, TR-03: se registra con seis decimales, medio hacia arriba, una sola vez al
    final: `1 / (1 - 0.666667) = 3.000003000003...` queda en `3.000003`."""
    assert (
        str(calcular_precio_sin_redondear(Decimal("1.000000"), "MARGEN_BRUTO", Decimal("0.500000")))
        == "2.000000"
    )
    assert (
        str(calcular_precio_sin_redondear(Decimal("1.000000"), "MARGEN_BRUTO", Decimal("0.666667")))
        == "3.000003"
    )
    # El séptimo decimal es 5 exacto: `0.0000005 x 1.5` no aplica; el medio sube.
    assert (
        str(calcular_precio_sin_redondear(Decimal("0.000001"), "MARKUP", Decimal("0.500000")))
        == "0.000002"
    )


def test_inv03_el_costo_y_el_valor_no_pueden_ser_punto_flotante() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_precio_sin_redondear(6000.0, "MARKUP", Decimal("0.3"))  # type: ignore[arg-type]
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_precio_sin_redondear(Decimal("6000"), "MARKUP", 0.3)  # type: ignore[arg-type]


def test_un_margen_bruto_de_uno_o_mas_no_se_puede_calcular() -> None:
    """La división por cero o por un negativo es un defecto del llamador: la regla ya se
    validó al crearla (PRC-12), pero la función no depende de eso."""
    with pytest.raises(MargenInvalidoError):
        calcular_precio_sin_redondear(Decimal("6000"), "MARGEN_BRUTO", Decimal("1"))
    with pytest.raises(MargenInvalidoError):
        calcular_precio_sin_redondear(Decimal("6000"), "MARGEN_BRUTO", Decimal("1.2"))
    with pytest.raises(MargenInvalidoError):
        calcular_precio_sin_redondear(Decimal("6000"), "DESCUENTO", Decimal("0.1"))


# --- propiedades --------------------------------------------------------------------------

_COSTOS = st.decimals(min_value=Decimal("0.000001"), max_value=Decimal("99999999.999999"), places=6)
_VALORES = st.decimals(min_value=Decimal("0"), max_value=Decimal("0.999999"), places=6)


@given(costo=_COSTOS, valor=_VALORES)
def test_el_margen_bruto_es_siempre_mayor_o_igual_que_el_costo(
    costo: Decimal, valor: Decimal
) -> None:
    """`costo / (1 - m) >= costo` para todo `0 <= m < 1`: el margen nunca baja el precio."""
    assert calcular_precio_sin_redondear(costo, "MARGEN_BRUTO", valor) >= costo


@given(costo=_COSTOS, valor=_VALORES)
def test_un_margen_bruto_y_su_markup_equivalente_dan_el_mismo_precio(
    costo: Decimal, valor: Decimal
) -> None:
    """`m / (1 - m)` como markup equivale al margen bruto `m` (con tolerancia de un
    microcosto por los seis decimales del markup equivalente)."""
    markup = valor / (1 - valor)
    if markup > Decimal("999.999999"):
        return
    como_bruto = calcular_precio_sin_redondear(costo, "MARGEN_BRUTO", valor)
    como_markup = calcular_precio_sin_redondear(costo, "MARKUP", markup.quantize(Decimal("1e-6")))

    assert abs(como_bruto - como_markup) <= costo * Decimal("0.000001") + Decimal("0.000001")
