"""Reglas puras del libro de stock (STK-01, STK-03, STK-04, STK-05, INV-04,
INV-12, `design.md` D4, D5, D8, D13).

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

TIPOS_DE_MOVIMIENTO = frozenset(
    {
        STOCK_INICIAL,
        "COMPRA",
        "ANULACION_COMPRA",
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

TIPOS_QUE_INGRESAN_CON_COSTO = frozenset({STOCK_INICIAL, "COMPRA", "ANULACION_VENTA"})
"""Los tipos cuyo ingreso con costo recalcula el promedio (CST-11: compra, stock
inicial y anulación de venta). Un ingreso de otro tipo (ajuste, transferencia,
rendición) todavía no tiene reglas de costo: lo definen los changes 14, 15 y 24
(CST-12) y hoy se rechaza. `ANULACION_COMPRA` es un egreso (lo define el change 11,
CMP-06)."""

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


def _validar_costo_segun_signo(cantidad: int, costo_unitario: object) -> None:
    """D5: el costo es obligatorio si la cantidad es positiva y prohibido si es
    negativa."""
    if cantidad > 0 and costo_unitario is None:
        raise CostoInvalidoError("Una línea que ingresa stock necesita su costo unitario.")
    if cantidad < 0 and costo_unitario is not None:
        raise CostoInvalidoError(
            "Una línea que egresa stock no lleva costo: se valoriza al promedio vigente."
        )


def validar_lineas_de_movimiento(
    lineas: Sequence[LineaDeMovimiento],
) -> list[LineaDeMovimiento]:
    """Al menos una línea; cada una con un tipo del catálogo (STK-03), cantidad
    entera distinta de cero y costo según el signo. El mismo par producto-ubicación
    puede repetirse (a diferencia del stock inicial, D5). Devuelve las líneas en el
    mismo orden."""
    if not lineas:
        raise LineasInvalidasError("El movimiento necesita al menos una línea.")
    for linea in lineas:
        validar_tipo_de_movimiento(linea.tipo)
        cantidad = _validar_cantidad(linea.cantidad_base)
        _validar_costo_segun_signo(cantidad, linea.costo_unitario)
        if cantidad > 0 and linea.tipo not in TIPOS_QUE_INGRESAN_CON_COSTO:
            raise TipoDeMovimientoInvalidoError(
                f"Un ingreso de tipo {linea.tipo} todavía no tiene reglas de costo."
            )
    return list(lineas)


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
