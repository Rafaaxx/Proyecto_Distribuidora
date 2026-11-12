"""Propiedad de `core/money.py` con Hypothesis (`docs/02-arquitectura.md` §10.1).

Para cualquier `Decimal` de entrada dentro del rango representable por sus
columnas, `redondear_importe` siempre devuelve exactamente 2 decimales y
`redondear_costo` siempre devuelve exactamente 6 -- son funciones puras de
dominio, el tipo de prueba que Hypothesis está pensado para ejercitar
(`docs/02-arquitectura.md` §5.2).
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.core.money import redondear_costo, redondear_importe

# NUMERIC(14,2): hasta 12 dígitos enteros + 2 decimales.
_IMPORTES = st.decimals(
    min_value=Decimal("-999999999999.99"),
    max_value=Decimal("999999999999.99"),
    allow_nan=False,
    allow_infinity=False,
    places=None,
)

# NUMERIC(18,6): hasta 12 dígitos enteros + 6 decimales.
_COSTOS = st.decimals(
    min_value=Decimal("-999999999999.999999"),
    max_value=Decimal("999999999999.999999"),
    allow_nan=False,
    allow_infinity=False,
    places=None,
)


def _cantidad_de_decimales(valor: Decimal) -> int:
    signo, digitos, exponente = valor.as_tuple()
    assert isinstance(exponente, int)
    return max(0, -exponente)


@given(_IMPORTES)
def test_redondear_importe_siempre_devuelve_exactamente_dos_decimales(
    entrada: Decimal,
) -> None:
    resultado = redondear_importe(entrada)

    assert _cantidad_de_decimales(resultado) == 2


@given(_COSTOS)
def test_redondear_costo_siempre_devuelve_exactamente_seis_decimales(
    entrada: Decimal,
) -> None:
    resultado = redondear_costo(entrada)

    assert _cantidad_de_decimales(resultado) == 6


@given(_IMPORTES)
def test_redondear_importe_es_idempotente(entrada: Decimal) -> None:
    # Redondear un importe ya redondeado no debe moverlo (propiedad de
    # cuantización: aplicar la misma escala dos veces es un no-op).
    una_vez = redondear_importe(entrada)
    dos_veces = redondear_importe(una_vez)

    assert una_vez == dos_veces
