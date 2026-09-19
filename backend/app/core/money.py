"""Redondeo de dinero (`docs/02-arquitectura.md` §10.1, INV-03).

Único módulo del backend que cuantiza importes, costos y porcentajes. Usa
`Decimal.quantize` con `ROUND_HALF_UP` pasado explícitamente en cada llamada
-- el contexto decimal por defecto de Python redondea al par (`ROUND_HALF_EVEN`)
y nunca debe usarse para cuantizar dinero.

Ninguna otra parte del sistema redondea un importe, costo o porcentaje por su
cuenta: siempre pasa por `redondear_importe` o `redondear_costo`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.errors import DomainError

_DOS_DECIMALES = Decimal("0.01")
_SEIS_DECIMALES = Decimal("0.000001")


class EntradaNoEsDineroExactoError(DomainError):
    """La entrada no es un valor decimal exacto (INV-03).

    Se levanta tanto para `float`/`bool` del lenguaje (punto flotante
    binario) como para cadenas que no representan un número.
    """

    codigo = "ENTRADA_NO_ES_DINERO_EXACTO"


def _a_decimal_exacto(valor: Decimal | str) -> Decimal:
    # `bool` es subclase de `int`, no de `float`, pero tampoco es dinero
    # exacto: se rechaza explícitamente para no colar `True`/`False`.
    if isinstance(valor, bool | float):
        raise EntradaNoEsDineroExactoError(
            f"No se puede redondear un punto flotante binario del lenguaje: {valor!r} "
            "(INV-03: usar Decimal o una cadena numérica exacta)"
        )

    if isinstance(valor, Decimal):
        return valor

    if isinstance(valor, str):
        try:
            return Decimal(valor)
        except InvalidOperation as error:
            raise EntradaNoEsDineroExactoError(
                f"La cadena {valor!r} no representa un valor decimal exacto"
            ) from error

    raise EntradaNoEsDineroExactoError(
        f"Tipo de entrada no soportado para redondeo de dinero: {type(valor).__name__}"
    )


def redondear_importe(valor: Decimal | str) -> Decimal:
    """Cuantiza un importe a 2 decimales con `ROUND_HALF_UP` (`NUMERIC(14,2)`).

    El medio se desempata siempre alejándose de cero: `0.125 -> 0.13`,
    `-0.125 -> -0.13`.
    """
    decimal_exacto = _a_decimal_exacto(valor)
    return decimal_exacto.quantize(_DOS_DECIMALES, rounding=ROUND_HALF_UP)


def redondear_costo(valor: Decimal | str) -> Decimal:
    """Cuantiza un costo por unidad base o un porcentaje a 6 decimales con
    `ROUND_HALF_UP` (`NUMERIC(18,6)` / `NUMERIC(9,6)`).

    La misma función cubre costos y porcentajes: ambos cuantizan a 6
    decimales (`design.md` D4); la diferencia de precisión total entre
    `numeric(18,6)` y `numeric(9,6)` se resuelve en la definición de columna,
    no en el redondeo.
    """
    decimal_exacto = _a_decimal_exacto(valor)
    return decimal_exacto.quantize(_SEIS_DECIMALES, rounding=ROUND_HALF_UP)
