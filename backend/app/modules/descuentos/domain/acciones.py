"""Acciones de una regla de descuento (DSC-04, DSC-07, TR-03; `design.md` D10).

Funciones puras sobre `Decimal`. Todo redondeo pasa por `core/money.py` (`ROUND_HALF_UP`)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, localcontext

from app.core.money import EntradaNoEsDineroExactoError, redondear_importe

# Precisión del cociente del reparto antes del único redondeo por parte (mismo criterio que
# `precios/domain/bruto_de_linea.py`).
_PRECISION_INTERMEDIA = 60


def exigir_decimal(valor: object, nombre: str) -> Decimal:
    """Devuelve `valor` si es un `Decimal`; si no (punto flotante, `bool`, cadena...) levanta
    `EntradaNoEsDineroExactoError` (INV-03)."""
    if not isinstance(valor, Decimal):
        raise EntradaNoEsDineroExactoError(
            f"{nombre} debe ser un Decimal exacto, no {type(valor).__name__}: {valor!r} "
            "(INV-03: nunca punto flotante)"
        )
    return valor


def descuento_porcentual(importes: Sequence[Decimal], porcentaje: Decimal) -> list[Decimal]:
    """Descuento de `porcentaje` (fracción) sobre el importe de cada línea, redondeado línea por
    línea a 2 decimales con mitad hacia arriba (DSC-07). Nunca se calcula sobre el total."""
    fraccion = exigir_decimal(porcentaje, "El porcentaje")
    return [
        redondear_importe(exigir_decimal(importe, "El importe") * fraccion) for importe in importes
    ]


def repartir_importe_fijo(importes: Sequence[Decimal], importe_fijo: Decimal) -> list[Decimal]:
    """Reparte `importe_fijo` entre las líneas en proporción a su importe, cada parte redondeada
    a 2 decimales. El remanente de redondeo, positivo o negativo, va a la línea de mayor importe
    (la primera si empatan). Si el importe supera la suma de las líneas se aplica esa suma: ninguna
    línea queda con neto negativo (DSC-04, D10). Las partes suman exactamente lo aplicado."""
    fijo = exigir_decimal(importe_fijo, "El importe fijo")
    base = [exigir_decimal(importe, "El importe") for importe in importes]
    total = sum(base, Decimal(0))
    aplicado = redondear_importe(min(fijo, total))
    if aplicado <= 0 or total <= 0:
        return [redondear_importe(Decimal(0)) for _ in base]

    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA
        partes = [redondear_importe(aplicado * importe / total) for importe in base]

    remanente = aplicado - sum(partes, Decimal(0))
    if remanente != 0:
        # Mayor importe; en empate, la primera del orden de la venta.
        mayor = max(range(len(base)), key=lambda i: (base[i], -i))
        partes[mayor] += remanente
    return partes
