"""Entradas decimales del cálculo de precios (INV-03): ningún importe, costo ni porcentaje
entra como punto flotante binario. Una sola definición del rechazo para todo `domain/`."""

from __future__ import annotations

from app.core.money import EntradaNoEsDineroExactoError


def rechazar_punto_flotante(valor: object, nombre: str) -> None:
    """Levanta `EntradaNoEsDineroExactoError` si `valor` es un `float` o un `bool`
    (INV-03: usar `Decimal` o una cadena numérica exacta). `bool` es subclase de `int`,
    pero no es dinero."""
    if isinstance(valor, bool | float):
        raise EntradaNoEsDineroExactoError(
            f"{nombre} no puede ser un punto flotante binario: {valor!r} "
            "(INV-03: usar Decimal o una cadena numérica exacta)"
        )
