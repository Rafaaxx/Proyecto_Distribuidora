"""Dominio puro de compras (CMP-01 a CMP-04, INV-04, INV-07, INV-08;
`design.md` D1, D2, D5, D6, D7, **[ALTA: cálculo de costos y deuda]**).

Funciones puras compartidas con el frontend (`frontend/src/domain/compras/
calculoCompra.ts`, con los casos comunes de `shared/fixtures/calculo/
cmp-02-compra.json`). Reutilizan `calcular_costo_base` (CST-02): no duplican la
fórmula del costo (CST-14).

Por línea (CMP-02):

    cantidad_base = cantidad x unidades de la presentacion   (entero, INV-04)
    costo_base    = calcular_costo_base(...)                 (6 decimales, al final)
    importe_neto  = redondear_importe(cantidad_base x costo_base)

El total neto es la suma de los importes de línea (TR-03). El total de factura
sugerido (D1) suma, por línea, `redondear_importe(importe_neto x (1 + alicuota))`.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.errors import DomainError
from app.core.money import redondear_importe
from app.modules.proveedores.domain.costo_base import calcular_costo_base
from app.modules.proveedores.domain.errores import (
    BonificacionInvalidaError,
    CantidadInvalidaError,
    CompraSinLineasError,
    CondicionInvalidaError,
    CursorInvalidoError,
    FechaInvalidaError,
    ImporteInvalidoError,
    LineasInvalidasError,
    MediosNoSumanImporteError,
    RangoDeFechasInvalidoError,
    ReferenciaObligatoriaError,
    ValorInvalidoError,
)

CONTADO = "CONTADO"
CREDITO = "CREDITO"
CONDICIONES = frozenset({CONTADO, CREDITO})
ESTADOS = frozenset({"CONFIRMADA", "ANULADA"})

LIMITE_MINIMO_DE_PAGINA = 1
LIMITE_MAXIMO_DE_PAGINA = 200
LIMITE_DEFAULT_DE_PAGINA = 50

MINIMO_DE_LINEAS = 1
MAXIMO_DE_LINEAS = 200

_DECIMALES_DE_CANTIDAD = 3
_DECIMALES_DE_IMPORTE = 2
_DECIMALES_DE_BONIFICACION = 6
_CANTIDAD_MAXIMA = Decimal("99999999999.999")
"""Mayor valor de `numeric(14,3)`."""
_IMPORTE_MAXIMO = Decimal("999999999999.99")
"""Mayor valor de `numeric(14,2)`."""
_COSTO_MAXIMO = Decimal("999999999999.999999")
"""Mayor valor de `numeric(18,6)`."""
_CANTIDAD_BASE_MAXIMA = 2_147_483_647
"""Rango de `integer` de PostgreSQL (INV-04)."""
_UNO = Decimal(1)


@dataclass(frozen=True)
class EntradaDeLinea:
    """Lo que el usuario informa de una línea y lo que el catálogo aporta: las
    unidades de la presentación y la alícuota del producto."""

    unidades_presentacion: int
    cantidad: Decimal
    valor: Decimal
    incluye_iva: bool
    alicuota: Decimal
    bonificacion: Decimal


@dataclass(frozen=True)
class LineaCalculada:
    """Lo que se deriva de una línea: cantidad base entera, costo base (CST-02),
    importe neto y el importe con IVA que sugiere el total de factura (D1)."""

    cantidad_base: int
    costo_base: Decimal
    importe_neto: Decimal
    importe_con_iva: Decimal


@dataclass(frozen=True)
class TotalesDeCompra:
    lineas: tuple[LineaCalculada, ...]
    total_neto: Decimal
    total_factura_sugerido: Decimal


def _decimales(valor: Decimal) -> int:
    """Cantidad de decimales significativos (`2.500` tiene 1; `1E+1` tiene 0)."""
    exponente = valor.normalize().as_tuple().exponent
    assert isinstance(exponente, int)
    return max(0, -exponente)


def _cantidad_base(cantidad: Decimal, unidades: int) -> int:
    if not cantidad.is_finite() or cantidad <= 0:
        raise CantidadInvalidaError("La cantidad tiene que ser mayor que cero.")
    if _decimales(cantidad) > _DECIMALES_DE_CANTIDAD or cantidad > _CANTIDAD_MAXIMA:
        raise CantidadInvalidaError(
            f"La cantidad admite hasta {_DECIMALES_DE_CANTIDAD} decimales y no más de "
            f"{_CANTIDAD_MAXIMA}."
        )
    base = cantidad * unidades
    if base != base.to_integral_value():
        raise CantidadInvalidaError(
            f"{cantidad} x {unidades} unidades no da una cantidad entera en unidad base."
        )
    entero = int(base)
    if entero > _CANTIDAD_BASE_MAXIMA:
        raise CantidadInvalidaError("La cantidad no entra en un entero de 32 bits.")
    return entero


def _validar_valor(valor: Decimal) -> None:
    if not valor.is_finite() or valor <= 0:
        raise ValorInvalidoError("El valor por presentación debe ser mayor a cero.")
    if _decimales(valor) > _DECIMALES_DE_IMPORTE or valor > _IMPORTE_MAXIMO:
        raise ValorInvalidoError(
            f"El valor admite hasta {_DECIMALES_DE_IMPORTE} decimales y no más de "
            f"{_IMPORTE_MAXIMO}."
        )


def _validar_bonificacion(bonificacion: Decimal) -> None:
    if (
        not bonificacion.is_finite()
        or bonificacion < 0
        or bonificacion >= 1
        or _decimales(bonificacion) > _DECIMALES_DE_BONIFICACION
    ):
        raise BonificacionInvalidaError(
            "La bonificación debe estar entre 0 (inclusive) y 1 (exclusive), con hasta "
            f"{_DECIMALES_DE_BONIFICACION} decimales."
        )


def calcular_linea(entrada: EntradaDeLinea) -> LineaCalculada:
    """CMP-02, D5: cantidad base, costo base e importe neto de una línea.

    `CANTIDAD_INVALIDA` si la cantidad no es positiva, tiene más de 3 decimales o no
    da unidades enteras; `VALOR_INVALIDO` si el valor no es positivo con 2 decimales
    o el costo base no es positivo; `BONIFICACION_INVALIDA` fuera de `[0, 1)`."""
    cantidad_base = _cantidad_base(entrada.cantidad, entrada.unidades_presentacion)
    _validar_valor(entrada.valor)
    _validar_bonificacion(entrada.bonificacion)

    costo_base = calcular_costo_base(
        valor=entrada.valor,
        incluye_iva=entrada.incluye_iva,
        alicuota=entrada.alicuota,
        bonificacion=entrada.bonificacion,
        unidades=entrada.unidades_presentacion,
    )
    if costo_base <= 0 or costo_base > _COSTO_MAXIMO:
        raise ValorInvalidoError("El costo base resultante no es un costo válido.")

    importe_neto = redondear_importe(Decimal(cantidad_base) * costo_base)
    if importe_neto > _IMPORTE_MAXIMO:
        raise ImporteInvalidoError(f"El importe de la línea supera {_IMPORTE_MAXIMO}.")
    importe_con_iva = redondear_importe(importe_neto * (_UNO + entrada.alicuota))
    return LineaCalculada(
        cantidad_base=cantidad_base,
        costo_base=costo_base,
        importe_neto=importe_neto,
        importe_con_iva=importe_con_iva,
    )


def validar_cantidad_de_lineas(cantidad: int) -> None:
    """INV-07, D5: de 1 a 200 líneas (`COMPRA_SIN_LINEAS` si no hay ninguna,
    `LINEAS_INVALIDAS` si pasa de 200). El servicio lo comprueba antes de resolver
    referencias para no consultar la base por una compra que ya es inválida."""
    if cantidad < MINIMO_DE_LINEAS:
        raise CompraSinLineasError("Una compra necesita al menos una línea.")
    if cantidad > MAXIMO_DE_LINEAS:
        raise LineasInvalidasError(
            f"Una compra admite hasta {MAXIMO_DE_LINEAS} líneas, no {cantidad}."
        )


def calcular_compra(lineas: Sequence[EntradaDeLinea]) -> TotalesDeCompra:
    """CMP-02, INV-07, D1, D5: de 1 a 200 líneas, cada una calculada con `calcular_linea`;
    el total neto es la suma de los importes de línea. El error de una línea lleva su
    índice (0-based) en `extension["linea"]`. `COMPRA_SIN_LINEAS` si la lista es
    vacía (INV-07); `LINEAS_INVALIDAS` si pasa de 200."""
    validar_cantidad_de_lineas(len(lineas))

    calculadas: list[LineaCalculada] = []
    for indice, entrada in enumerate(lineas):
        try:
            calculadas.append(calcular_linea(entrada))
        except DomainError as error:
            error.extension = {**(error.extension or {}), "linea": indice}
            raise

    total_neto = sum((linea.importe_neto for linea in calculadas), Decimal("0.00"))
    sugerido = sum((linea.importe_con_iva for linea in calculadas), Decimal("0.00"))
    if total_neto > _IMPORTE_MAXIMO or sugerido > _IMPORTE_MAXIMO:
        raise ImporteInvalidoError(f"El total de la compra supera {_IMPORTE_MAXIMO}.")
    return TotalesDeCompra(
        lineas=tuple(calculadas),
        total_neto=redondear_importe(total_neto),
        total_factura_sugerido=redondear_importe(sugerido),
    )


# --- total de factura, condición, medios y fecha (D1, D2, D6) ------------------------


@dataclass(frozen=True)
class MedioDeEntrada:
    """Un medio del pago de contado ya resuelto por el servicio: su importe, la
    referencia informada y si el medio de la organización la exige."""

    importe: Decimal
    referencia: str | None
    requiere_referencia: bool


def _validar_importe(valor: Decimal, nombre: str) -> Decimal:
    if (
        not valor.is_finite()
        or valor <= 0
        or _decimales(valor) > _DECIMALES_DE_IMPORTE
        or valor > _IMPORTE_MAXIMO
    ):
        raise ImporteInvalidoError(
            f"{nombre} debe ser mayor que cero, con hasta {_DECIMALES_DE_IMPORTE} decimales "
            f"y no más de {_IMPORTE_MAXIMO}."
        )
    return redondear_importe(valor)


def validar_total_factura(total_factura: Decimal) -> Decimal:
    """D1: el total de factura es positivo con 2 decimales (`IMPORTE_INVALIDO`);
    devuelve el importe con exactamente 2 decimales."""
    return _validar_importe(total_factura, "El total de factura")


def validar_pago(condicion: str, total_factura: Decimal, medios: Sequence[MedioDeEntrada]) -> None:
    """D2, CMP-01, CMP-03, INV-08: una compra a crédito no trae medios
    (`CONDICION_INVALIDA`); una de contado trae medios positivos con 2 decimales cuya
    suma es el total de factura (`MEDIOS_NO_SUMAN_IMPORTE`) y, donde el medio la exige,
    referencia no vacía (`REFERENCIA_OBLIGATORIA`)."""
    if condicion not in CONDICIONES:
        raise CondicionInvalidaError(f"La condición {condicion!r} no es CONTADO ni CREDITO.")

    if condicion == CREDITO:
        if medios:
            raise CondicionInvalidaError("Una compra a crédito no lleva medios de pago.")
        return

    suma = Decimal("0.00")
    for medio in medios:
        suma += _validar_importe(medio.importe, "El importe de cada medio")
        if medio.requiere_referencia and not (medio.referencia and medio.referencia.strip()):
            raise ReferenciaObligatoriaError("El medio de pago exige una referencia.")
    if suma != total_factura:
        raise MediosNoSumanImporteError(
            f"Los medios suman {suma} y el total de factura es {total_factura}."
        )


def validar_fecha(fecha: date, *, hoy: date) -> None:
    """D6, TR-04: la fecha del comprobante no es posterior a la fecha de negocio de
    hoy; no hay límite hacia atrás."""
    if fecha > hoy:
        raise FechaInvalidaError(f"La fecha {fecha} es posterior a hoy ({hoy}).")


# --- comparación con el costo informado vigente (CMP-04, D7) -------------------------


@dataclass(frozen=True)
class CostoDeLinea:
    """El costo base de una línea de la compra, con su posición (0-based)."""

    linea: int
    producto_id: UUID
    costo_base: Decimal


@dataclass(frozen=True)
class DiferenciaDeCosto:
    """Una línea cuyo costo base difiere del vigente, o que no tiene vigente."""

    linea: int
    producto_id: UUID
    costo_base_compra: Decimal
    costo_base_vigente: Decimal | None


def diferencias_de_costo(
    costos: Sequence[CostoDeLinea], vigentes: Mapping[UUID, Decimal | None]
) -> list[DiferenciaDeCosto]:
    """CMP-04, D7: las líneas con costo base distinto del costo informado vigente del
    producto a la fecha de la compra, o sin vigente (`None`, o producto ausente del
    mapa). Una línea igual al vigente no aparece. Conserva el orden de las líneas."""
    diferencias: list[DiferenciaDeCosto] = []
    for costo in costos:
        vigente = vigentes.get(costo.producto_id)
        if vigente is None or vigente != costo.costo_base:
            diferencias.append(
                DiferenciaDeCosto(
                    linea=costo.linea,
                    producto_id=costo.producto_id,
                    costo_base_compra=costo.costo_base,
                    costo_base_vigente=vigente,
                )
            )
    return diferencias


# --- consultas: cursor y rango de fechas (`02` §11) -------------------------------------


def validar_rango_de_fechas(desde: date | None, hasta: date | None) -> None:
    """`desde` no puede ser posterior a `hasta`."""
    if desde is not None and hasta is not None and desde > hasta:
        raise RangoDeFechasInvalidoError(f"El rango {desde} a {hasta} está invertido.")


def codificar_cursor(fecha: date, id_: UUID) -> str:
    """Cursor opaco `(fecha, id)` de la última compra de la página."""
    valor = f"{fecha.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def decodificar_cursor(cursor: str) -> tuple[date, UUID]:
    """Inversa de `codificar_cursor`; un cursor ilegible es `CURSOR_INVALIDO`."""
    try:
        valor = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        fecha_texto, id_texto = valor.rsplit("|", 1)
        return date.fromisoformat(fecha_texto), UUID(id_texto)
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise CursorInvalidoError("El cursor de paginación no es válido.") from error
