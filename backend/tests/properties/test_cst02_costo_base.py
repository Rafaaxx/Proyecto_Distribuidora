"""Propiedad de CST-02 (`design.md` D11, tarea 6.3) con Hypothesis: para
cualquier entrada válida, `calcular_costo_base` nunca devuelve un costo
negativo y es monótono en `valor` (a mayor valor informado, mayor o igual
costo base, con el resto de los parámetros fijos).

ROJO a propósito (tarea 6.3, antes de implementar `costo_base.py`):
`calcular_costo_base` todavía no existe."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.modules.proveedores.domain.costo_base import calcular_costo_base

# NUMERIC(14,2): valores positivos representables por `costo_informado.valor`.
_VALORES = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("999999999999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

# NUMERIC(9,6): alícuotas no negativas, acotadas a un rango de negocio
# razonable (CST-02 no fija un tope, pero 0..2 cubre cualquier alícuota real).
_ALICUOTAS = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("2"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)

# `ck_costo_informado__bonificacion`: `[0, 1)`.
_BONIFICACIONES = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("0.999999"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)

_UNIDADES = st.integers(min_value=1, max_value=100_000)


@given(
    valor=_VALORES,
    incluye_iva=st.booleans(),
    alicuota=_ALICUOTAS,
    bonificacion=_BONIFICACIONES,
    unidades=_UNIDADES,
)
def test_cst02_costo_base_no_negativo_y_monotono_en_valor(
    valor: Decimal,
    incluye_iva: bool,
    alicuota: Decimal,
    bonificacion: Decimal,
    unidades: int,
) -> None:
    resultado = calcular_costo_base(
        valor=valor,
        incluye_iva=incluye_iva,
        alicuota=alicuota,
        bonificacion=bonificacion,
        unidades=unidades,
    )

    assert resultado >= 0

    # Monotonía: informar un valor mayor (mismos IVA/alícuota/bonificación/
    # unidades) nunca produce un costo base menor.
    valor_mayor = valor + Decimal("100.00")
    resultado_con_valor_mayor = calcular_costo_base(
        valor=valor_mayor,
        incluye_iva=incluye_iva,
        alicuota=alicuota,
        bonificacion=bonificacion,
        unidades=unidades,
    )

    assert resultado_con_valor_mayor >= resultado
