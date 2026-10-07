"""Importe bruto de una línea de venta (PRC-22, `design.md` D10, `01` §7.3).

    bruto = redondear_importe(precio de referencia x cantidad base / unidades de referencia)

Función pura sobre `Decimal` y enteros: un solo redondeo, al final, con `ROUND_HALF_UP`
desde `core/money.py` (TR-03, ADR-010). El precio unitario por presentación que se
muestra en pantalla se calcula con la misma función (cantidad base igual a las unidades
de la presentación) y NUNCA se usa para armar totales: `$1.433,33 x 3` daría `$4.299,99`,
mientras que el bruto de 3 unidades es `$4.300,00`.

Gemela en TypeScript: `frontend/src/domain/precios/brutoDeLinea.ts`. Ambas se ejercitan
contra los mismos casos de `shared/fixtures/calculo/prc-22-bruto-de-linea.json`
(`"motor": "prc22"`, ADR-016).
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from app.core.money import EntradaNoEsDineroExactoError, redondear_importe
from app.modules.precios.domain.decimales import rechazar_punto_flotante
from app.modules.precios.domain.errores import (
    CantidadBaseInvalidaError,
    UnidadesReferenciaInvalidasError,
)

# Precisión del cociente antes del único redondeo: de sobra para `numeric(14,2)` por una
# cantidad entera de hasta 2^31 sobre unidades de hasta 2^31 (mismo criterio que
# `_PRECISION_INTERMEDIA` de `proveedores/domain/costo_base.py`).
_PRECISION_INTERMEDIA = 60


def _es_entero(valor: object) -> bool:
    # `bool` es subclase de `int` pero no es una cantidad (INV-04).
    return isinstance(valor, int) and not isinstance(valor, bool)


def _a_decimal_exacto(precio_referencia: Decimal | str) -> Decimal:
    rechazar_punto_flotante(precio_referencia, "El precio de referencia")
    if isinstance(precio_referencia, Decimal):
        return precio_referencia
    if isinstance(precio_referencia, str):
        try:
            return Decimal(precio_referencia)
        except ArithmeticError as error:
            raise EntradaNoEsDineroExactoError(
                f"La cadena {precio_referencia!r} no representa un valor decimal exacto"
            ) from error
    raise EntradaNoEsDineroExactoError(
        f"Tipo de precio de referencia no soportado: {type(precio_referencia).__name__}"
    )


def calcular_bruto_de_linea(
    precio_referencia: Decimal | str, unidades_referencia: int, cantidad_base: int
) -> Decimal:
    """`precio de referencia x cantidad base / unidades de referencia`, redondeado a dos
    decimales una sola vez (PRC-22).

    `unidades_referencia` y `cantidad_base` son enteros (INV-04); una cantidad base no
    positiva o unas unidades de referencia menores que uno se rechazan con un error de
    dominio de código estable. Un precio de punto flotante se rechaza (INV-03)."""
    precio = _a_decimal_exacto(precio_referencia)
    if not _es_entero(unidades_referencia) or unidades_referencia < 1:
        raise UnidadesReferenciaInvalidasError(
            "Las unidades de referencia deben ser un entero >= 1 "
            f"(recibido {unidades_referencia!r})."
        )
    if not _es_entero(cantidad_base) or cantidad_base < 1:
        raise CantidadBaseInvalidaError(
            f"La cantidad base debe ser un entero positivo (recibido {cantidad_base!r})."
        )

    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA
        bruto = precio * cantidad_base / unidades_referencia
    return redondear_importe(bruto)
