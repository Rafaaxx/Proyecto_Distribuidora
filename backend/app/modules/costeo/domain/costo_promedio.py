"""CST-11 y CST-12: costo promedio ponderado móvil (`docs/01-dominio.md` §6.2,
`design.md` D4, D6, D10, D14, **[ALTA: cálculo de costos]**).

Funciones puras compartidas con el frontend
(`frontend/src/domain/costeo/costoPromedio.ts`), con los casos comunes de
`shared/fixtures/calculo/cst-11-costo-promedio.json`.

Fórmula de un ingreso con costo (CST-11):

    stock previo > 0:   (stock x promedio + cantidad x costo) / (stock + cantidad)
    stock previo <= 0:  costo del ingreso

El cociente se calcula con `Decimal` de precisión ampliada (50 dígitos
significativos, mismo criterio que `proveedores/domain/costo_base.py`) para que la
única cuantización sea la de `redondear_costo` (`ROUND_HALF_UP`, 6 decimales) al
final -- nunca antes (TR-02, TR-03). Un egreso no cambia el promedio y se
valoriza a ese promedio (CST-12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.core.money import redondear_costo
from app.modules.costeo.domain.errores import (
    CantidadInvalidaError,
    CostoInvalidoError,
    OrigenDeCostoInvalidoError,
    PromedioInconsistenteError,
    StockFueraDeRangoError,
)

_PRECISION_INTERMEDIA = 50

COSTO_MAXIMO = Decimal("999999999999.999999")
"""Mayor valor de `numeric(18,6)`: 12 dígitos enteros y 6 decimales."""

STOCK_MAXIMO = 2_147_483_647
STOCK_MINIMO = -2_147_483_648
"""Rango de `integer` de PostgreSQL (INV-04)."""

ORIGENES_DE_COSTO = frozenset({"COMPRA", "ANULACION_COMPRA", "STOCK_INICIAL", "ANULACION_VENTA"})
"""Los cuatro orígenes que dejan historia del promedio (`03` §7, D13)."""

_FORMATO = re.compile(r"[0-9]+(\.[0-9]{1,6})?")


@dataclass(frozen=True)
class ResultadoDeIngreso:
    """Promedio y stock total del producto después de un ingreso con costo."""

    promedio_nuevo: Decimal
    stock_nuevo: int


@dataclass(frozen=True)
class ResultadoDeEgreso:
    """Promedio (sin cambios), valorización del egreso y stock total después de
    un egreso. `promedio_nuevo` y `costo_valorizacion` son `None` mientras el
    producto no tuvo ingresos con costo (`design.md` D10)."""

    promedio_nuevo: Decimal | None
    costo_valorizacion: Decimal | None
    stock_nuevo: int


@dataclass(frozen=True)
class ResultadoDeReversion:
    """Promedio y stock total del producto después de revertir un ingreso.
    `recalculado` es `False` cuando el promedio se mantiene (CMP-06)."""

    promedio_nuevo: Decimal
    stock_nuevo: int
    recalculado: bool


def validar_costo(valor: object) -> Decimal:
    """Devuelve el costo por unidad base con exactamente 6 decimales o levanta
    `COSTO_INVALIDO` (`design.md` D6-A).

    Solo acepta `str` (`"1000"`, `"1000.5"`, `"0.833333"`) y `Decimal`. Debe ser
    finito, mayor que cero, con a lo sumo 6 decimales y dentro de
    `numeric(18,6)`. NO se redondea: más decimales se rechazan (TR-02). Un
    `float`, un `int` o un `bool` no es dinero exacto y se rechaza aunque el valor
    sea entero, porque un número JSON es justamente lo que INV-03 no admite. La
    cuantización final solo fija el exponente y la hace `core/money.py`.
    """
    if isinstance(valor, str):
        if _FORMATO.fullmatch(valor) is None:
            raise CostoInvalidoError(
                f"El costo {valor!r} no es un decimal positivo con hasta seis decimales."
            )
        decimal = Decimal(valor)
    elif isinstance(valor, Decimal):
        decimal = valor
    else:
        raise CostoInvalidoError(
            f"El costo debe ser un string decimal exacto, no {type(valor).__name__}."
        )

    if not decimal.is_finite():
        raise CostoInvalidoError(f"El costo {valor!r} no es un número finito.")
    exponente = decimal.as_tuple().exponent
    assert isinstance(exponente, int)
    if exponente < -6:
        raise CostoInvalidoError(f"El costo {valor!r} tiene más de seis decimales.")
    if decimal <= 0:
        raise CostoInvalidoError(f"El costo {valor!r} tiene que ser mayor que cero.")
    if decimal > COSTO_MAXIMO:
        raise CostoInvalidoError(f"El costo {valor!r} supera el máximo de {COSTO_MAXIMO}.")
    return redondear_costo(decimal)


def validar_origen_de_costo(origen_tipo: str) -> str:
    """`origen_tipo` del catálogo de `03` §7 o `ORIGEN_COSTO_INVALIDO`."""
    if origen_tipo not in ORIGENES_DE_COSTO:
        raise OrigenDeCostoInvalidoError(f"El origen {origen_tipo!r} no deja historia de costo.")
    return origen_tipo


def _validar_cantidad(cantidad: object) -> int:
    """Entero positivo (INV-04). `bool` es subclase de `int` pero no es una
    cantidad."""
    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        raise CantidadInvalidaError(
            f"La cantidad debe ser un entero, no {type(cantidad).__name__}."
        )
    if cantidad <= 0:
        raise CantidadInvalidaError(f"La cantidad {cantidad} tiene que ser mayor que cero.")
    return cantidad


def _validar_stock(stock: int) -> int:
    if not STOCK_MINIMO <= stock <= STOCK_MAXIMO:
        raise StockFueraDeRangoError(f"El stock total {stock} no entra en un entero de 32 bits.")
    return stock


def calcular_ingreso(
    *,
    stock_previo: int,
    promedio_previo: Decimal | None,
    cantidad: int,
    costo_ingreso: str | Decimal,
) -> ResultadoDeIngreso:
    """CST-11: recalcula el promedio por un ingreso con costo.

    - `stock_previo`: stock total del producto en la organización (todas las
      ubicaciones) ANTES del ingreso; puede ser cero o negativo.
    - `promedio_previo`: promedio vigente, `None` si el producto nunca tuvo un
      ingreso con costo (D10).
    - `cantidad`: unidades base que ingresan, entero `> 0`.
    - `costo_ingreso`: costo por unidad base (`COSTO_INVALIDO` si no cumple D6).

    Con stock previo `> 0` el promedio previo es obligatorio
    (`PROMEDIO_INCONSISTENTE` si falta). Con stock previo `<= 0` el promedio pasa
    a ser el costo del ingreso y el previo no interviene.
    """
    costo = validar_costo(costo_ingreso)
    cantidad_validada = _validar_cantidad(cantidad)
    stock_nuevo = _validar_stock(stock_previo + cantidad_validada)

    if stock_previo <= 0:
        return ResultadoDeIngreso(promedio_nuevo=costo, stock_nuevo=stock_nuevo)

    if promedio_previo is None:
        raise PromedioInconsistenteError(
            f"El producto tiene {stock_previo} unidades y ningún costo promedio."
        )

    with localcontext() as contexto:
        contexto.prec = _PRECISION_INTERMEDIA
        ponderado = (
            Decimal(stock_previo) * promedio_previo + Decimal(cantidad_validada) * costo
        ) / Decimal(stock_nuevo)

    return ResultadoDeIngreso(promedio_nuevo=redondear_costo(ponderado), stock_nuevo=stock_nuevo)


def calcular_egreso(
    *, stock_previo: int, promedio_previo: Decimal | None, cantidad: int
) -> ResultadoDeEgreso:
    """CST-12: un egreso no modifica el promedio y se valoriza al promedio
    vigente. `cantidad` es la magnitud (`> 0`); el stock resultante puede ser
    negativo: la condición de saldo suficiente es de `stock` (STK-05, `02` §7.4)."""
    cantidad_validada = _validar_cantidad(cantidad)
    stock_nuevo = _validar_stock(stock_previo - cantidad_validada)
    return ResultadoDeEgreso(
        promedio_nuevo=promedio_previo,
        costo_valorizacion=promedio_previo,
        stock_nuevo=stock_nuevo,
    )


def calcular_reversion(
    *,
    stock_previo: int,
    promedio_previo: Decimal | None,
    cantidad: int,
    costo_ingreso: str | Decimal,
) -> ResultadoDeReversion:
    """CMP-06: revierte un ingreso con costo (anulación de una compra).

    El stock restante es el stock total de la organización después de quitar
    `cantidad` (CST-10). Con stock restante `> 0` se recalcula el promedio como
    inverso exacto de CST-11:

        (stock x promedio - cantidad x costo) / (stock - cantidad)

    y se acepta solo si es `> 0`; con stock restante `<= 0` o promedio resultante
    `<= 0` el promedio se mantiene y `recalculado` es `False` (`design.md` D9). El
    promedio previo es obligatorio (`PROMEDIO_INCONSISTENTE` si falta).
    """
    costo = validar_costo(costo_ingreso)
    cantidad_validada = _validar_cantidad(cantidad)
    stock_nuevo = _validar_stock(stock_previo - cantidad_validada)
    if promedio_previo is None:
        raise PromedioInconsistenteError(
            "No se puede revertir un ingreso de un producto sin costo promedio."
        )

    if stock_nuevo > 0:
        with localcontext() as contexto:
            contexto.prec = _PRECISION_INTERMEDIA
            restante = (
                Decimal(stock_previo) * promedio_previo - Decimal(cantidad_validada) * costo
            ) / Decimal(stock_nuevo)
        if restante > 0:
            promedio = redondear_costo(restante)
            if promedio > 0:
                return ResultadoDeReversion(
                    promedio_nuevo=promedio, stock_nuevo=stock_nuevo, recalculado=True
                )

    return ResultadoDeReversion(
        promedio_nuevo=promedio_previo, stock_nuevo=stock_nuevo, recalculado=False
    )
