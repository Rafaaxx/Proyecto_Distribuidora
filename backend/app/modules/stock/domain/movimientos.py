"""Reglas puras del libro de stock (STK-01, STK-03, STK-04, STK-05, INV-04,
INV-12, `design.md` D4, D5, D8, D13; change 14: D1, D3, D4, D5.2, D9).

`saldo_de` y `aplicar_movimiento` son la definición contra la que se prueba
INV-12; el saldo real se calcula con SQL sobre el libro y se materializa en
`stock_saldo` con la fila bloqueada (`02` §7.2), nunca sumando filas en Python
(`CLAUDE.md` §4).

El formato y el rango del costo de una línea (`design.md` D6) los valida
`costeo`; este dominio solo decide si la línea lleva costo o no según su signo
(D5), porque `stock` no importa el dominio de `costeo` (`02` §5.3).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.stock.domain.errores import (
    CantidadFueraDeRangoError,
    CantidadInvalidaError,
    CostoInvalidoError,
    LineasInvalidasError,
    ProductoConOperacionesError,
    ProductoInactivoError,
    ProductoRepetidoError,
    StockInsuficienteError,
    TipoDeMovimientoInvalidoError,
    UbicacionInactivaError,
)
from app.modules.stock.domain.kardex import DiferenciaDeStock

STOCK_INICIAL = "STOCK_INICIAL"
ANULACION_COMPRA = "ANULACION_COMPRA"

TIPOS_DE_MOVIMIENTO = frozenset(
    {
        STOCK_INICIAL,
        "COMPRA",
        ANULACION_COMPRA,
        "VENTA",
        "ANULACION_VENTA",
        "TRANSFERENCIA_SALIDA",
        "TRANSFERENCIA_ENTRADA",
        "AJUSTE",
        "DIFERENCIA_RENDICION",
    }
)
"""Los nueve tipos de la etapa 1 de STK-03 (DEVOLUCION y RECUENTO son de la
etapa 2). Solo `STOCK_INICIAL` tiene comando en este change (D13)."""

TRANSFERENCIA_SALIDA = "TRANSFERENCIA_SALIDA"
TRANSFERENCIA_ENTRADA = "TRANSFERENCIA_ENTRADA"
AJUSTE = "AJUSTE"

ORIGEN_TRANSFERENCIA = "TRANSFERENCIA"
ORIGEN_AJUSTE = "AJUSTE_STOCK"
ORIGEN_ANULACION_TRANSFERENCIA = "ANULACION_TRANSFERENCIA"
ORIGEN_ANULACION_AJUSTE = "ANULACION_AJUSTE_STOCK"

TIPOS_QUE_INGRESAN_CON_COSTO = frozenset({STOCK_INICIAL, "COMPRA", "ANULACION_VENTA"})
"""Los tipos cuyo ingreso con costo recalcula el promedio (CST-11: compra, stock
inicial y anulación de venta). `ANULACION_COMPRA` es un egreso (lo define el change 11,
CMP-06)."""

TIPOS_QUE_INGRESAN_SIN_COSTO = frozenset({TRANSFERENCIA_ENTRADA, AJUSTE})
"""Change 14, D9 (CST-12): un ingreso de transferencia o de ajuste no recalcula el promedio
y se valoriza al promedio vigente, así que no lleva costo de entrada. Un ingreso de otro
tipo (rendición, venta) sigue sin reglas de costo y se rechaza: lo define el change 24."""

ORIGENES_DE_ANULACION: dict[str, frozenset[str]] = {
    ORIGEN_ANULACION_TRANSFERENCIA: frozenset({TRANSFERENCIA_SALIDA, TRANSFERENCIA_ENTRADA}),
    ORIGEN_ANULACION_AJUSTE: frozenset({AJUSTE}),
}
"""D5.1, D5.2: los inversos de una anulación reutilizan los tipos de STK-03 y cambian el
origen. Cada origen de anulación admite solo los tipos que le corresponden."""

MINIMO_DE_LINEAS = 1
MAXIMO_DE_LINEAS = 200
CANTIDAD_MAXIMA = 2_147_483_647
CANTIDAD_MINIMA = -2_147_483_648
"""Rango de `integer` de PostgreSQL (INV-04)."""


@dataclass(frozen=True)
class LineaDeStockInicial:
    """Una línea de `STOCK_INICIAL_REGISTRAR` (D5): `cantidad_base` con signo y
    `costo_unitario` (cadena decimal, o `None` en una línea negativa)."""

    producto_id: UUID
    cantidad_base: int
    costo_unitario: str | None


@dataclass(frozen=True)
class LineaDeMovimiento:
    """Una línea de `registrar_movimientos`: un cambio de stock de un producto en
    una ubicación. `cantidad_base` lleva signo; `costo_unitario` es obligatorio si
    ingresa (recalcula el promedio, CST-11) y prohibido si egresa (se valoriza al
    promedio vigente, CST-12). `origen_tipo`/`origen_id` dicen qué operación lo
    originó; `motivo_id` y `jornada_id` son opcionales (`03` §9)."""

    producto_id: UUID
    ubicacion_id: UUID
    cantidad_base: int
    tipo: str
    costo_unitario: str | Decimal | None
    origen_tipo: str
    origen_id: UUID
    motivo_id: UUID | None = None
    jornada_id: UUID | None = None


def validar_tipo_de_movimiento(tipo: str) -> str:
    """`tipo` del catálogo de STK-03 o `TIPO_MOVIMIENTO_INVALIDO`."""
    if tipo not in TIPOS_DE_MOVIMIENTO:
        raise TipoDeMovimientoInvalidoError(f"El tipo de movimiento {tipo!r} no es válido.")
    return tipo


def _validar_cantidad(cantidad: object) -> int:
    """Entero distinto de cero dentro de `integer` (INV-04, D5). `bool` es
    subclase de `int` pero no es una cantidad."""
    if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad == 0:
        raise CantidadInvalidaError("La cantidad tiene que ser un entero distinto de cero.")
    if not CANTIDAD_MINIMA <= cantidad <= CANTIDAD_MAXIMA:
        raise CantidadFueraDeRangoError(f"La cantidad {cantidad} no entra en un entero de 32 bits.")
    return cantidad


def _validar_costo_segun_signo(
    cantidad: int, costo_unitario: object, tipo: str | None = None
) -> None:
    """D5: el costo es obligatorio si la cantidad es positiva y prohibido si es
    negativa. Excepción (change 11, D9): el egreso `ANULACION_COMPRA` lleva el
    costo base de la línea que revierte (CMP-06) y sin él es `COSTO_INVALIDO`."""
    if cantidad > 0 and costo_unitario is None:
        raise CostoInvalidoError("Una línea que ingresa stock necesita su costo unitario.")
    if cantidad < 0 and tipo == ANULACION_COMPRA and costo_unitario is None:
        raise CostoInvalidoError(
            "Un egreso de anulación de compra necesita el costo de la línea que revierte."
        )
    if cantidad < 0 and tipo != ANULACION_COMPRA and costo_unitario is not None:
        raise CostoInvalidoError(
            "Una línea que egresa stock no lleva costo: se valoriza al promedio vigente."
        )


def lleva_el_costo_original(linea: LineaDeMovimiento) -> bool:
    """D5.2: una línea de transferencia o de ajuste con origen de anulación lleva el
    `costo_unitario` del movimiento que revierte (puede ser nulo) y la puerta lo guarda
    tal cual, sin valorizarlo al promedio vigente."""
    return linea.tipo in ORIGENES_DE_ANULACION.get(linea.origen_tipo, frozenset())


def validar_lineas_de_movimiento(
    lineas: Sequence[LineaDeMovimiento],
) -> list[LineaDeMovimiento]:
    """Al menos una línea; cada una con un tipo del catálogo (STK-03), cantidad
    entera distinta de cero y costo según el signo. El mismo par producto-ubicación
    puede repetirse (a diferencia del stock inicial, D5). Devuelve las líneas en el
    mismo orden.

    Change 14: un ingreso `TRANSFERENCIA_ENTRADA` o `AJUSTE` no lleva costo (con costo es
    `COSTO_INVALIDO`, D9) salvo que sea el inverso de una anulación (D5.2); un ingreso
    `DIFERENCIA_RENDICION` sigue siendo `TIPO_MOVIMIENTO_INVALIDO`."""
    if not lineas:
        raise LineasInvalidasError("El movimiento necesita al menos una línea.")
    for linea in lineas:
        validar_tipo_de_movimiento(linea.tipo)
        cantidad = _validar_cantidad(linea.cantidad_base)
        if cantidad > 0 and not (
            linea.tipo in TIPOS_QUE_INGRESAN_CON_COSTO or linea.tipo in TIPOS_QUE_INGRESAN_SIN_COSTO
        ):
            raise TipoDeMovimientoInvalidoError(
                f"Un ingreso de tipo {linea.tipo} todavía no tiene reglas de costo."
            )
        if lleva_el_costo_original(linea):
            continue
        if cantidad > 0 and linea.tipo in TIPOS_QUE_INGRESAN_SIN_COSTO:
            if linea.costo_unitario is not None:
                raise CostoInvalidoError(
                    "Un ingreso de transferencia o de ajuste no lleva costo: se valoriza "
                    "al promedio vigente."
                )
            continue
        _validar_costo_segun_signo(cantidad, linea.costo_unitario, linea.tipo)
    return list(lineas)


def puede_quedar_negativo(linea: LineaDeMovimiento, *, permitir_negativo: bool) -> bool:
    """Con `PERMITIR_STOCK_NEGATIVO` pueden dejar el saldo negativo: el egreso
    `ANULACION_COMPRA` (CMP-07, D10), la salida de una transferencia (change 14, D1) --
    también la inversa de una anulación -- y el inverso de la anulación de un ajuste
    (D5 punto 6). Un `AJUSTE` que no es ese inverso NUNCA lo deja (D1 = B), tampoco con
    permiso; cualquier otro egreso exige saldo suficiente (STK-05, STK-10)."""
    if not permitir_negativo:
        return False
    return linea.tipo in {ANULACION_COMPRA, TRANSFERENCIA_SALIDA} or (
        linea.tipo == AJUSTE and linea.origen_tipo == ORIGEN_ANULACION_AJUSTE
    )


def productos_que_exigen_estar_activos(lineas: Iterable[LineaDeMovimiento]) -> set[UUID]:
    """CAT-05, D11: un producto cuyas líneas son todas `ANULACION_COMPRA` puede
    estar inactivo (revertir no es una operación nueva); si tiene alguna línea de
    otro tipo debe estar activo."""
    return {linea.producto_id for linea in lineas if linea.tipo != ANULACION_COMPRA}


def validar_lineas_de_stock_inicial(
    lineas: Sequence[LineaDeStockInicial],
) -> list[LineaDeStockInicial]:
    """D5, D6: de 1 a 200 líneas, ningún producto repetido, cantidad entera
    distinta de cero y costo según el signo (obligatorio si la cantidad es
    positiva, prohibido si es negativa). Devuelve las líneas en el mismo orden."""
    if not MINIMO_DE_LINEAS <= len(lineas) <= MAXIMO_DE_LINEAS:
        raise LineasInvalidasError(
            f"El comando admite de {MINIMO_DE_LINEAS} a {MAXIMO_DE_LINEAS} líneas, "
            f"no {len(lineas)}."
        )

    productos: set[UUID] = set()
    for linea in lineas:
        if linea.producto_id in productos:
            raise ProductoRepetidoError(
                f"El producto {linea.producto_id} está repetido en el comando."
            )
        productos.add(linea.producto_id)

        _validar_costo_segun_signo(_validar_cantidad(linea.cantidad_base), linea.costo_unitario)
    return list(lineas)


def validar_correccion(*, saldo_actual: int, cantidad_a_egresar: int) -> None:
    """STK-05, D4: un egreso no deja negativo el saldo de la ubicación
    (`STOCK_INSUFICIENTE`), sin excepción por `PERMITIR_STOCK_NEGATIVO`.
    `cantidad_a_egresar` es la magnitud (positiva)."""
    if cantidad_a_egresar > saldo_actual:
        raise StockInsuficienteError(
            f"El saldo es {saldo_actual} y se pretende egresar {cantidad_a_egresar}."
        )


def validar_stock_inicial_admitido(*, tiene_movimientos_de_otro_tipo: bool) -> None:
    """D4: el stock inicial se admite solo mientras el producto no tenga en la
    organización movimientos de otro tipo (análogo a CC-08)."""
    if tiene_movimientos_de_otro_tipo:
        raise ProductoConOperacionesError(
            "El producto ya tiene movimientos de otro tipo: no admite más stock inicial."
        )


def validar_ubicacion_activa(*, activo: bool) -> None:
    """D8: sobre una ubicación inactiva no se registran movimientos nuevos."""
    if not activo:
        raise UbicacionInactivaError("La ubicación está inactiva.")


def validar_producto_activo(*, activo: bool) -> None:
    """CAT-05, D8: sobre un producto inactivo no se registran movimientos
    nuevos."""
    if not activo:
        raise ProductoInactivoError("El producto está inactivo.")


def saldo_de(cantidades: Iterable[int]) -> int:
    """Saldo = suma de los movimientos con signo (STK-04, INV-12). Es la
    definición contra la que se prueba INV-12: no depende del orden."""
    return sum(cantidades)


def aplicar_movimiento(saldo: int, cantidad: int) -> int:
    """Saldo después de aplicar un movimiento con signo. Un saldo que no entra en
    `integer` es `CANTIDAD_FUERA_DE_RANGO` (INV-04)."""
    resultado = saldo + cantidad
    if not CANTIDAD_MINIMA <= resultado <= CANTIDAD_MAXIMA:
        raise CantidadFueraDeRangoError(
            f"El saldo resultante {resultado} no entra en un entero de 32 bits."
        )
    return resultado


def diferencias_de_stock_total(
    materializados: Mapping[UUID, int], esperados: Mapping[UUID, int]
) -> list[DiferenciaDeStock]:
    """Productos cuyo `stock_total` materializado no coincide con la suma de sus
    saldos (INV-12, `02` §7.6). Un producto ausente en uno de los dos cuenta como
    cero. La suma la hace la base; acá solo se comparan los dos valores."""
    diferencias = []
    for producto_id in sorted(set(materializados) | set(esperados)):
        materializado = materializados.get(producto_id, 0)
        esperado = esperados.get(producto_id, 0)
        if materializado != esperado:
            diferencias.append(
                DiferenciaDeStock(
                    producto_id=producto_id,
                    ubicacion_id=None,
                    valor_materializado=materializado,
                    valor_esperado=esperado,
                )
            )
    return diferencias
