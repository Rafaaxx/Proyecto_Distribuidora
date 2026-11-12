"""Armado de las filas de un reporte según los permisos (REP-04; `design.md` D5). Puro.

NUNCA suma: las cifras llegan sumadas de la base (REP-01, `02` §14). Acá solo se decide qué se
informa según el permiso de quien consulta y se redondea una sola vez lo que viaja con decimales
(cajas equivalentes, TR-03; valores en pesos, INV-03).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.money import redondear_cantidad, redondear_importe


@dataclass(frozen=True)
class SinCosto:
    """Las líneas vendidas sin costo (ADR-054): cantidad y neto, aparte de costo y utilidad."""

    lineas: int
    importe_neto: Decimal


@dataclass(frozen=True)
class CifrasCrudasDeVentas:
    """Lo que la base devuelve para un nivel (resumen, día o vendedor): sumas exactas."""

    cantidad_ventas: int
    cajas_equivalentes: Decimal
    unidades_base: int
    importe_bruto: Decimal
    importe_descuento: Decimal
    importe_neto: Decimal
    importe_iva: Decimal
    total: Decimal
    costo_vendido: Decimal
    utilidad: Decimal
    lineas_sin_costo: int
    neto_sin_costo: Decimal


@dataclass(frozen=True)
class CifrasDeVentas:
    """Una fila armada del reporte de ventas. Costo, utilidad y `sin_costo` son `None` sin
    `VER_UTILIDAD`."""

    cantidad_ventas: int
    cajas_equivalentes: Decimal
    unidades_base: int
    importe_bruto: Decimal
    importe_descuento: Decimal
    importe_neto: Decimal
    importe_iva: Decimal
    total: Decimal
    costo_vendido: Decimal | None
    utilidad: Decimal | None
    sin_costo: SinCosto | None


def armar_cifras_de_ventas(crudas: CifrasCrudasDeVentas, *, ve_utilidad: bool) -> CifrasDeVentas:
    """Arma la fila: cajas redondeadas una vez sobre la suma exacta; costo vendido, utilidad y
    las líneas sin costo solo con `VER_UTILIDAD` (REP-04, VTA-05)."""
    return CifrasDeVentas(
        cantidad_ventas=crudas.cantidad_ventas,
        cajas_equivalentes=redondear_cantidad(crudas.cajas_equivalentes),
        unidades_base=crudas.unidades_base,
        importe_bruto=crudas.importe_bruto,
        importe_descuento=crudas.importe_descuento,
        importe_neto=crudas.importe_neto,
        importe_iva=crudas.importe_iva,
        total=crudas.total,
        costo_vendido=crudas.costo_vendido if ve_utilidad else None,
        utilidad=crudas.utilidad if ve_utilidad else None,
        sin_costo=(
            SinCosto(lineas=crudas.lineas_sin_costo, importe_neto=crudas.neto_sin_costo)
            if ve_utilidad
            else None
        ),
    )


@dataclass(frozen=True)
class ProductoVendidoCrudo:
    """Un producto del desglose por producto, con las cajas como suma exacta de la base."""

    cajas_equivalentes: Decimal
    unidades_base: int
    importe_neto: Decimal


@dataclass(frozen=True)
class ProductoVendido:
    """El producto armado: cajas equivalentes redondeadas una sola vez. Sin costo ni utilidad
    (REP-06 es de la etapa 2)."""

    cajas_equivalentes: Decimal
    unidades_base: int
    importe_neto: Decimal


def armar_producto_vendido(crudo: ProductoVendidoCrudo) -> ProductoVendido:
    """Redondea las cajas equivalentes una sola vez sobre la suma exacta (TR-03, REP-03)."""
    return ProductoVendido(
        cajas_equivalentes=redondear_cantidad(crudo.cajas_equivalentes),
        unidades_base=crudo.unidades_base,
        importe_neto=crudo.importe_neto,
    )


def armar_valor_con_costos(valor: Decimal | None, *, ve_costos: bool) -> Decimal | None:
    """Un valor en pesos derivado de costos (diferencias de rendición, ajustes de stock): solo
    con `VER_COSTOS` (REP-04) y redondeado una vez sobre la suma exacta."""
    if not ve_costos or valor is None:
        return None
    return redondear_importe(valor)


@dataclass(frozen=True)
class CifrasCrudasDeAjuste:
    """Lo que la base devuelve para un nivel del reporte de ajustes (motivo, producto o
    diferencias de rendición): unidades base que entraron y salieron, el valor exacto de cada
    sentido (`cantidad_base x costo_unitario` sobre las líneas con costo) y las unidades sin
    costo."""

    entradas: int
    salidas: int
    valor_de_entradas: Decimal
    valor_de_salidas: Decimal
    unidades_sin_costo: int


@dataclass(frozen=True)
class CifrasDeAjuste:
    """Las cifras armadas: las unidades siempre; los valores y las unidades sin costo solo con
    `VER_COSTOS` (REP-04, `01` §19)."""

    entradas: int
    salidas: int
    valor_de_entradas: Decimal | None
    valor_de_salidas: Decimal | None
    unidades_sin_costo: int | None


def armar_cifras_de_ajuste(crudas: CifrasCrudasDeAjuste, *, ve_costos: bool) -> CifrasDeAjuste:
    """Redondea cada valor una sola vez sobre la suma exacta (TR-03) y lo informa solo con
    `VER_COSTOS`; las unidades sin costo acompañan a los valores."""
    return CifrasDeAjuste(
        entradas=crudas.entradas,
        salidas=crudas.salidas,
        valor_de_entradas=armar_valor_con_costos(crudas.valor_de_entradas, ve_costos=ve_costos),
        valor_de_salidas=armar_valor_con_costos(crudas.valor_de_salidas, ve_costos=ve_costos),
        unidades_sin_costo=crudas.unidades_sin_costo if ve_costos else None,
    )
