"""Costo de referencia y precio calculado de un producto en una lista (PRC-11, PRC-12,
TR-03; spec `precios/calculo-de-precios`).

Funciones puras sobre `Decimal`: sin acceso a datos ni reloj. Los valores intermedios no se
redondean (TR-03): el costo de referencia es el producto exacto del costo base por las
unidades, y el margen se aplica con precisión ampliada (60 dígitos significativos, como el
bruto de línea y el costo base). La única cuantización de este módulo es la de
`calcular_precio_sin_redondear`, que registra el precio calculado a seis decimales
(`numeric(18,6)`, PRC-16); el redondeo al múltiplo del precio final vive en `redondeo.py` y
parte del valor exacto, no de este.

El cálculo de precios corre solo en el servidor (`design.md` D10): el dispositivo no
genera listas, así que no hay gemela en TypeScript ni casos compartidos de estas fórmulas.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from app.core.money import redondear_costo
from app.modules.precios.domain.decimales import rechazar_punto_flotante
from app.modules.precios.domain.errores import MargenInvalidoError
from app.modules.precios.domain.reglas import MARGEN_BRUTO, MARKUP

_PRECISION_INTERMEDIA = 60
_UNO = Decimal(1)


def calcular_costo_de_referencia(costo_base: Decimal, unidades_referencia: int) -> Decimal:
    """`costo base del costo informado vigente x unidades de la presentación de
    referencia`, sin redondear (PRC-11). El costo base es por unidad base (CST-02) y sale
    del costo informado, no del costo promedio (CST-04); `unidades_referencia` es un
    invariante del llamador (una presentación ya validada por `catalogo`, CAT-02), así que
    se afirma con `ValueError`."""
    rechazar_punto_flotante(costo_base, "El costo base")
    if isinstance(unidades_referencia, bool) or unidades_referencia < 1:
        raise ValueError(
            f"Las unidades de referencia deben ser un entero >= 1 (recibido {unidades_referencia})."
        )
    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA
        return costo_base * unidades_referencia


def aplicar_margen(costo_referencia: Decimal, tipo: str, valor: Decimal) -> Decimal:
    """El precio calculado exacto, sin redondear (PRC-12, TR-03):
    `costo x (1 + m)` para `MARKUP` y `costo / (1 - m)` para `MARGEN_BRUTO`.

    Un margen bruto `>= 1` o un tipo desconocido es un defecto del llamador (la regla ya se
    validó al crearla, PRC-12) y se rechaza con `MARGEN_INVALIDO` en vez de dividir por cero
    o por un negativo."""
    rechazar_punto_flotante(costo_referencia, "El costo de referencia")
    rechazar_punto_flotante(valor, "El valor del margen")
    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA
        if tipo == MARKUP:
            return costo_referencia * (_UNO + valor)
        if tipo == MARGEN_BRUTO:
            if valor >= _UNO:
                raise MargenInvalidoError(
                    f"Un margen bruto debe ser menor que 1 (recibido {valor})."
                )
            return costo_referencia / (_UNO - valor)
    raise MargenInvalidoError(f"El tipo de margen {tipo!r} no existe.")


def calcular_precio_sin_redondear(costo_referencia: Decimal, tipo: str, valor: Decimal) -> Decimal:
    """El precio calculado que se registra (PRC-16): el de `aplicar_margen` a seis
    decimales, medio hacia arriba, una sola vez al final (TR-02, TR-03)."""
    return redondear_costo(aplicar_margen(costo_referencia, tipo, valor))
