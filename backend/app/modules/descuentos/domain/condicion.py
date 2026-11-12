"""Condición de volumen de una regla de descuento (DSC-02, DSC-03; `design.md` D5, D6).

La medida se calcula con aritmética racional exacta (`Fraction`: enteros, sin redondear) y se
compara contra el umbral también exacto. Las cajas equivalentes de una línea son su cantidad
base sobre las unidades de referencia con que se calculó su bruto (D5): tres líneas de un tercio
de caja suman exactamente 1, no 0,9999. La condición mira siempre cantidades y brutos de las
líneas, nunca importes ya descontados (D6)."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from app.modules.descuentos.domain.tipos import LineaVenta, Medida, ReglaDescuento


def _es_elegible(regla: ReglaDescuento, linea: LineaVenta) -> bool:
    for alcance in regla.alcances:
        if alcance.tipo == "PRODUCTO" and alcance.entidad_id == linea.producto_id:
            return True
        if alcance.tipo == "CATEGORIA" and alcance.entidad_id == linea.categoria_id:
            return True
        if alcance.tipo == "MARCA" and alcance.entidad_id == linea.marca_id:
            return True
    return False


def indices_elegibles(regla: ReglaDescuento, lineas: Sequence[LineaVenta]) -> list[int]:
    """Posiciones, en el orden de la venta, de las líneas elegibles: todas para una regla de
    operación; para una de alcance, las que coinciden con alguno de sus alcances por producto,
    categoría o marca (unión, D6)."""
    if regla.tipo == "VOLUMEN_OPERACION":
        return list(range(len(lineas)))
    return [i for i, linea in enumerate(lineas) if _es_elegible(regla, linea)]


def lineas_elegibles(regla: ReglaDescuento, lineas: Sequence[LineaVenta]) -> list[LineaVenta]:
    """Las líneas elegibles de `indices_elegibles`, en el orden de la venta."""
    return [lineas[i] for i in indices_elegibles(regla, lineas)]


def medir(medida: Medida, lineas: Sequence[LineaVenta]) -> Fraction:
    """Suma exacta de la medida sobre `lineas`."""
    if medida == "UNIDADES_BASE":
        return Fraction(sum(linea.cantidad_base for linea in lineas))
    if medida == "IMPORTE_BRUTO":
        return sum((Fraction(linea.bruto) for linea in lineas), Fraction(0))
    return sum(
        (Fraction(linea.cantidad_base, linea.unidades_referencia) for linea in lineas),
        Fraction(0),
    )


def cumple_condicion(regla: ReglaDescuento, lineas: Sequence[LineaVenta]) -> bool:
    """`True` si la medida de las líneas elegibles cumple el operador contra el umbral. Una regla
    sin líneas elegibles no aplica."""
    elegibles = lineas_elegibles(regla, lineas)
    if not elegibles:
        return False
    medida = medir(regla.medida, elegibles)
    umbral = Fraction(regla.umbral)
    return medida >= umbral if regla.operador == "GTE" else medida > umbral
