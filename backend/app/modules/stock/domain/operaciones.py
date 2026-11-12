"""Reglas puras de transferencias y ajustes de stock (STK-07, STK-08, INV-04, INV-15,
CST-12, `design.md` D3, D6, D9; change 14).

Valida el contenido de los comandos `STOCK_TRANSFERIR` y `STOCK_AJUSTAR` y lo expande en
las líneas que `registrar_movimientos` recibe (la única puerta del libro). No importa
infraestructura (`02` §5.2): el servicio resuelve ubicaciones, productos y motivo contra
la base y le pasa a estas funciones solo los datos que necesitan.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.stock.domain.errores import (
    CantidadFueraDeRangoError,
    CantidadInvalidaError,
    LineasInvalidasError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    ProductoRepetidoError,
    ProductoSinCostoError,
    UbicacionesIgualesError,
)
from app.modules.stock.domain.movimientos import (
    AJUSTE,
    CANTIDAD_MAXIMA,
    CANTIDAD_MINIMA,
    MAXIMO_DE_LINEAS,
    MINIMO_DE_LINEAS,
    ORIGEN_AJUSTE,
    ORIGEN_TRANSFERENCIA,
    TRANSFERENCIA_ENTRADA,
    TRANSFERENCIA_SALIDA,
    LineaDeMovimiento,
)

MAXIMO_OBSERVACION = 500
AMBITO_MOTIVO_DE_AJUSTE = "AJUSTE_STOCK"


@dataclass(frozen=True)
class LineaDeOperacion:
    """Una línea de transferencia o de ajuste: un producto y su `cantidad_base` (positiva
    en la transferencia; con signo y distinta de cero en el ajuste)."""

    producto_id: UUID
    cantidad_base: int


@dataclass(frozen=True)
class TransferenciaValidada:
    ubicacion_origen_id: UUID
    ubicacion_destino_id: UUID
    lineas: list[LineaDeOperacion]
    observacion: str | None


@dataclass(frozen=True)
class AjusteValidado:
    ubicacion_id: UUID
    motivo_id: UUID
    lineas: list[LineaDeOperacion]
    observacion: str | None


def _validar_observacion(observacion: str | None) -> str | None:
    """D6: recortada, vacía equivale a `None`, hasta 500 caracteres."""
    if observacion is None:
        return None
    recortada = observacion.strip()
    if len(recortada) > MAXIMO_OBSERVACION:
        raise ObservacionInvalidaError(
            f"La observación admite hasta {MAXIMO_OBSERVACION} caracteres, no {len(recortada)}."
        )
    return recortada or None


def _validar_cantidad(cantidad: object, *, con_signo: bool) -> int:
    """Entero dentro de `integer` (INV-04): mayor que cero en la transferencia, distinto
    de cero en el ajuste. `bool` es subclase de `int` pero no es una cantidad."""
    if isinstance(cantidad, bool) or not isinstance(cantidad, int):
        raise CantidadInvalidaError("La cantidad tiene que ser un entero.")
    if cantidad == 0:
        raise CantidadInvalidaError("La cantidad tiene que ser distinta de cero.")
    if not con_signo and cantidad < 0:
        raise CantidadInvalidaError("La cantidad de una transferencia tiene que ser positiva.")
    if not CANTIDAD_MINIMA <= cantidad <= CANTIDAD_MAXIMA:
        raise CantidadFueraDeRangoError(f"La cantidad {cantidad} no entra en un entero de 32 bits.")
    return cantidad


def _validar_lineas(
    lineas: Sequence[LineaDeOperacion], *, con_signo: bool
) -> list[LineaDeOperacion]:
    """D6: de 1 a 200 líneas, ningún producto repetido, cantidades válidas."""
    if not MINIMO_DE_LINEAS <= len(lineas) <= MAXIMO_DE_LINEAS:
        raise LineasInvalidasError(
            f"El comando admite de {MINIMO_DE_LINEAS} a {MAXIMO_DE_LINEAS} líneas, "
            f"no {len(lineas)}."
        )
    productos: set[UUID] = set()
    for indice, linea in enumerate(lineas):
        # Contrato de la API (P9): el error de una línea lleva su índice 0-based.
        if linea.producto_id in productos:
            raise ProductoRepetidoError(
                f"El producto {linea.producto_id} está repetido en el comando.",
                extension={"linea": indice},
            )
        productos.add(linea.producto_id)
        try:
            _validar_cantidad(linea.cantidad_base, con_signo=con_signo)
        except (CantidadInvalidaError, CantidadFueraDeRangoError) as error:
            error.extension = {"linea": indice}
            raise
    return list(lineas)


def validar_transferencia(
    *,
    ubicacion_origen_id: UUID,
    ubicacion_destino_id: UUID,
    lineas: Sequence[LineaDeOperacion],
    observacion: str | None,
) -> TransferenciaValidada:
    """STK-07, D6: origen distinto del destino (`UBICACIONES_IGUALES`), de 1 a 200 líneas
    sin producto repetido, cantidades enteras mayores que cero y observación válida."""
    if ubicacion_origen_id == ubicacion_destino_id:
        raise UbicacionesIgualesError("El origen y el destino de la transferencia son iguales.")
    return TransferenciaValidada(
        ubicacion_origen_id=ubicacion_origen_id,
        ubicacion_destino_id=ubicacion_destino_id,
        lineas=_validar_lineas(lineas, con_signo=False),
        observacion=_validar_observacion(observacion),
    )


def expandir_transferencia(
    transferencia: TransferenciaValidada, *, transferencia_id: UUID
) -> list[LineaDeMovimiento]:
    """Por cada línea, la salida del origen y después la entrada al destino (D9: cada
    salida se aplica antes que su entrada). Sin costo: se valorizan al promedio vigente
    (CST-12). `origen_id` es la transferencia."""
    movimientos: list[LineaDeMovimiento] = []
    for linea in transferencia.lineas:
        for ubicacion_id, cantidad, tipo in (
            (transferencia.ubicacion_origen_id, -linea.cantidad_base, TRANSFERENCIA_SALIDA),
            (transferencia.ubicacion_destino_id, linea.cantidad_base, TRANSFERENCIA_ENTRADA),
        ):
            movimientos.append(
                LineaDeMovimiento(
                    producto_id=linea.producto_id,
                    ubicacion_id=ubicacion_id,
                    cantidad_base=cantidad,
                    tipo=tipo,
                    costo_unitario=None,
                    origen_tipo=ORIGEN_TRANSFERENCIA,
                    origen_id=transferencia_id,
                )
            )
    return movimientos


def validar_ajuste(
    *,
    ubicacion_id: UUID,
    motivo_id: UUID,
    lineas: Sequence[LineaDeOperacion],
    observacion: str | None,
) -> AjusteValidado:
    """STK-08, D6: de 1 a 200 líneas sin producto repetido, cantidades enteras distintas
    de cero (signos mezclados admitidos) y observación válida. El motivo se valida aparte
    (`validar_motivo_de_ajuste`) porque requiere leerlo de la base."""
    return AjusteValidado(
        ubicacion_id=ubicacion_id,
        motivo_id=motivo_id,
        lineas=_validar_lineas(lineas, con_signo=True),
        observacion=_validar_observacion(observacion),
    )


def expandir_ajuste(ajuste: AjusteValidado, *, ajuste_id: UUID) -> list[LineaDeMovimiento]:
    """Un movimiento `AJUSTE` por línea, con el motivo del ajuste y sin costo (se
    valoriza al promedio vigente, D3). `origen_id` es el ajuste."""
    return [
        LineaDeMovimiento(
            producto_id=linea.producto_id,
            ubicacion_id=ajuste.ubicacion_id,
            cantidad_base=linea.cantidad_base,
            tipo=AJUSTE,
            costo_unitario=None,
            origen_tipo=ORIGEN_AJUSTE,
            origen_id=ajuste_id,
            motivo_id=ajuste.motivo_id,
        )
        for linea in ajuste.lineas
    ]


def validar_motivo_de_ajuste(*, activo: bool, ambito: str) -> None:
    """TR-09, D6: el motivo del ajuste es activo y del ámbito `AJUSTE_STOCK`."""
    if not activo or ambito != AMBITO_MOTIVO_DE_AJUSTE:
        raise MotivoInvalidoError(f"El motivo no es un motivo activo de {AMBITO_MOTIVO_DE_AJUSTE}.")


def validar_ingreso_con_costo(*, cantidad_base: int, costo_promedio: Decimal | None) -> None:
    """D3: un ajuste positivo de un producto sin promedio es `PRODUCTO_SIN_COSTO`. Un
    egreso no lo exige: se valoriza al promedio vigente, nulo si no hay."""
    if cantidad_base > 0 and costo_promedio is None:
        raise ProductoSinCostoError(
            "El producto no tiene costo promedio: cargá su stock con stock inicial o una compra."
        )
