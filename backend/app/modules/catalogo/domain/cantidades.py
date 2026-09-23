"""Visualización de cantidades: cajas + unidades (CAT-08, `01` §5,
`design.md` D8). Función pura sobre `int`: sin acceso a datos, sin
dependencia del resto del módulo. Idéntica en espíritu a
`frontend/src/domain/catalogo/cantidades.ts` -- ambas se ejercitan contra
los mismos casos de `shared/fixtures/calculo/cat-08-visualizacion.json`.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnidadesDeReferenciaInvalidasError(ValueError):
    """CAT-02: las unidades de la presentación de referencia deben ser un
    entero `>= 1`. Se levanta en vez de devolver un resultado (spec
    visualizacion-de-cantidades, escenario "Unidades de referencia
    inválidas": "la función falla con un error explícito")."""


@dataclass(frozen=True)
class CantidadVisualizada:
    """`cajas` y `unidades` son siempre `>= 0`; `negativo` indica si el
    conjunto representa una cantidad base negativa (CAT-08: "con signo
    negativo aplicado al conjunto si `q < 0`"). `0` nunca es negativo."""

    cajas: int
    unidades: int
    negativo: bool


def visualizar_cantidad(cantidad_base: int, unidades_referencia: int) -> CantidadVisualizada:
    """`floor(|q| / u)` cajas y `|q| mod u` unidades, signo aplicado al
    conjunto si `cantidad_base < 0` (CAT-08). Exacto sobre enteros: `//` y
    `%` de Python ya son división entera y módulo exactos, sin punto
    flotante (INV-04)."""
    if isinstance(unidades_referencia, bool) or not isinstance(unidades_referencia, int):
        raise UnidadesDeReferenciaInvalidasError(
            f"Las unidades de referencia deben ser un entero, no {unidades_referencia!r}."
        )
    if unidades_referencia < 1:
        raise UnidadesDeReferenciaInvalidasError(
            f"Las unidades de referencia deben ser un entero >= 1 (recibido {unidades_referencia})."
        )
    if isinstance(cantidad_base, bool) or not isinstance(cantidad_base, int):
        raise UnidadesDeReferenciaInvalidasError(
            f"La cantidad base debe ser un entero, no {cantidad_base!r}."
        )

    absoluto = abs(cantidad_base)
    cajas, unidades = divmod(absoluto, unidades_referencia)
    return CantidadVisualizada(cajas=cajas, unidades=unidades, negativo=cantidad_base < 0)
