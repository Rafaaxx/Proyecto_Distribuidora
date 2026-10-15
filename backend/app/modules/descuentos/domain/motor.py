"""Motor de descuentos de una venta (DSC-05, DSC-06, DSC-07, DSC-08; `design.md` D7 a D11).

Función pura: de las líneas con su bruto ya calculado (PRC-22), las reglas aplicables y el
descuento manual, devuelve por línea los descuentos en el orden en que se aplicaron, su total y
su neto. No calcula IVA ni el total de la venta (VTA-04, change 18a).

Orden de resolución (DSC-05):

1. El bruto de cada línea viene dado.
2. Se evalúan las condiciones de todas las reglas sobre cantidades y brutos (D6).
3. Entre las no acumulables que aplican gana UNA para toda la venta: la de mayor beneficio total
   sobre el bruto; empate por prioridad (número más bajo) y, si persiste, la creada primero
   (D7, D8).
4. Las acumulables, por prioridad y antigüedad, cada una sobre el resultado anterior (D9).
5. El descuento manual: el porcentaje propio de la línea si lo trae, el general si no; uno solo
   por línea, siempre el último (D11).

El resultado no depende del orden en que se entregan las reglas ni sus alcances.

Gemela en TypeScript: `frontend/src/domain/descuentos/motor.ts` (ADR-016, mismos casos de
`shared/fixtures/calculo/dsc-05-descuentos.json`)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.money import redondear_costo, redondear_importe
from app.modules.descuentos.domain.acciones import (
    descuento_porcentual,
    exigir_decimal,
    repartir_importe_fijo,
)
from app.modules.descuentos.domain.condicion import (
    cumple_condicion,
    indices_elegibles,
    lineas_elegibles,
)
from app.modules.descuentos.domain.errores import (
    DescuentoManualInvalidoError,
    LineaDescuentoInvalidaError,
    ReglaDescuentoInvalidaError,
)
from app.modules.descuentos.domain.tipos import (
    ACCIONES,
    MEDIDAS,
    OPERADORES,
    TIPOS_ALCANCE,
    TIPOS_REGLA,
    DescuentoAplicado,
    LineaResultado,
    LineaVenta,
    ReglaDescuento,
    ResultadoDescuentos,
)

_CERO = Decimal("0.00")
_UNO = Decimal(1)
_SEIS_DECIMALES = Decimal("0.000001")


def _es_entero_positivo(valor: object) -> bool:
    # `bool` es subclase de `int` pero no es una cantidad (INV-04).
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 1


def _validar_linea(linea: LineaVenta) -> None:
    bruto = exigir_decimal(linea.bruto, "El bruto de la línea")
    if not bruto.is_finite() or bruto < 0 or bruto != bruto.quantize(_CERO):
        raise LineaDescuentoInvalidaError(
            f"El bruto de la línea {linea.id!r} debe ser un importe no negativo de hasta 2 "
            "decimales "
            f"(recibido {bruto})."
        )
    if not _es_entero_positivo(linea.cantidad_base):
        raise LineaDescuentoInvalidaError(
            f"La cantidad base de la línea {linea.id!r} debe ser un entero positivo "
            f"(recibido {linea.cantidad_base!r})."
        )
    if not _es_entero_positivo(linea.unidades_referencia):
        raise LineaDescuentoInvalidaError(
            f"Las unidades de referencia de la línea {linea.id!r} deben ser un entero >= 1 "
            f"(recibido {linea.unidades_referencia!r})."
        )


def validar_porcentaje_manual(valor: object, nombre: str) -> None:
    """Fracción de hasta 6 decimales, mayor que 0 y hasta 1; un punto flotante no es válido
    (DSC-06, TR-02, INV-03; D11, D11.1)."""
    if (
        not isinstance(valor, Decimal)
        or not valor.is_finite()
        or valor <= 0
        or valor > _UNO
        or valor != valor.quantize(_SEIS_DECIMALES)
    ):
        raise DescuentoManualInvalidoError(
            f"{nombre} debe ser una fracción mayor que 0 y hasta 1 con hasta 6 decimales "
            f"(recibido {valor!r})."
        )


def _validar_regla(regla: ReglaDescuento) -> None:
    if (
        regla.tipo not in TIPOS_REGLA
        or regla.medida not in MEDIDAS
        or regla.operador not in OPERADORES
        or regla.accion_tipo not in ACCIONES
        or any(alcance.tipo not in TIPOS_ALCANCE for alcance in regla.alcances)
    ):
        raise ReglaDescuentoInvalidaError(
            f"La regla {regla.id!r} trae un tipo, medida, operador, acción o alcance desconocido."
        )
    exigir_decimal(regla.umbral, "El umbral de la regla")
    if regla.accion_tipo == "PORCENTAJE":
        porcentaje = exigir_decimal(regla.accion_porcentaje, "El porcentaje de la regla")
        if not 0 < porcentaje <= _UNO:
            raise ReglaDescuentoInvalidaError(
                f"El porcentaje de la regla {regla.id!r} debe ser mayor que 0 y hasta 1."
            )
    else:
        importe = exigir_decimal(regla.accion_importe, "El importe de la regla")
        if importe <= 0:
            raise ReglaDescuentoInvalidaError(
                f"El importe de la regla {regla.id!r} debe ser mayor que 0."
            )


def _descuentos_de_regla(regla: ReglaDescuento, importes: Sequence[Decimal]) -> list[Decimal]:
    if regla.accion_tipo == "PORCENTAJE":
        assert regla.accion_porcentaje is not None  # validado en _validar_regla
        return descuento_porcentual(importes, regla.accion_porcentaje)
    assert regla.accion_importe is not None  # validado en _validar_regla
    return repartir_importe_fijo(importes, regla.accion_importe)


def _clave_de_orden(regla: ReglaDescuento) -> tuple[int, str]:
    """Prioridad (número más bajo primero) y, si empatan, la creada primero (UUIDv7)."""
    return (regla.prioridad, regla.id)


def calcular_descuentos(
    lineas: Sequence[LineaVenta],
    reglas: Sequence[ReglaDescuento],
    descuento_manual_general: Decimal | None,
) -> ResultadoDescuentos:
    """Calcula los descuentos de la venta. Levanta un error de dominio si alguna entrada no es
    válida y, en ese caso, no devuelve nada (tampoco para las demás líneas)."""
    for linea in lineas:
        _validar_linea(linea)
    for regla in reglas:
        _validar_regla(regla)
    if descuento_manual_general is not None:
        validar_porcentaje_manual(descuento_manual_general, "El descuento manual general")
    for linea in lineas:
        if linea.descuento_manual is not None:
            validar_porcentaje_manual(
                linea.descuento_manual, f"El descuento manual propio de la línea {linea.id!r}"
            )

    importes = [linea.bruto for linea in lineas]
    detalle: list[list[DescuentoAplicado]] = [[] for _ in lineas]

    def aplicar(regla: ReglaDescuento) -> None:
        elegibles = indices_elegibles(regla, lineas)
        partes = _descuentos_de_regla(regla, [importes[i] for i in elegibles])
        porcentaje = (
            redondear_costo(regla.accion_porcentaje)
            if regla.accion_tipo == "PORCENTAJE" and regla.accion_porcentaje is not None
            else None
        )
        for posicion, parte in zip(elegibles, partes, strict=True):
            if parte > 0:  # un descuento que redondea a cero no se informa (D9)
                detalle[posicion].append(
                    DescuentoAplicado("AUTOMATICO", regla.id, porcentaje, parte)
                )
                importes[posicion] -= parte

    # Paso 2: las condiciones se evalúan una sola vez, sobre cantidades y brutos (D6).
    aplicables = [regla for regla in reglas if cumple_condicion(regla, lineas)]

    # Paso 3: una sola no acumulable por venta (D7, D8).
    no_acumulables = [regla for regla in aplicables if not regla.acumulable]
    if no_acumulables:

        def clave_de_ganadora(regla: ReglaDescuento) -> tuple[Decimal, int, str]:
            elegibles = lineas_elegibles(regla, lineas)
            beneficio = sum(
                _descuentos_de_regla(regla, [linea.bruto for linea in elegibles]), _CERO
            )
            return (-beneficio, *_clave_de_orden(regla))

        aplicar(min(no_acumulables, key=clave_de_ganadora))

    # Paso 4: las acumulables, en orden, cada una sobre el resultado anterior (D9).
    for regla in sorted((r for r in aplicables if r.acumulable), key=_clave_de_orden):
        aplicar(regla)

    # Paso 5: descuento manual; el propio de la línea reemplaza al general (D11).
    manual_maximo: Decimal | None = None
    for posicion, linea in enumerate(lineas):
        porcentaje_manual = (
            linea.descuento_manual
            if linea.descuento_manual is not None
            else descuento_manual_general
        )
        if porcentaje_manual is None:
            continue
        importe = redondear_importe(importes[posicion] * porcentaje_manual)
        if importe > 0:
            porcentaje = redondear_costo(porcentaje_manual)
            detalle[posicion].append(DescuentoAplicado("MANUAL", None, porcentaje, importe))
            importes[posicion] -= importe
            if manual_maximo is None or porcentaje > manual_maximo:
                manual_maximo = porcentaje

    resultado = tuple(
        LineaResultado(
            id=linea.id,
            descuentos=tuple(detalle[posicion]),
            descuento_total=sum((d.importe for d in detalle[posicion]), _CERO),
            neto=redondear_importe(importes[posicion]),
        )
        for posicion, linea in enumerate(lineas)
    )
    return ResultadoDescuentos(lineas=resultado, porcentaje_manual_maximo=manual_maximo)
