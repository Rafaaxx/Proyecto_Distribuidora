"""Reglas puras de la anulación de transferencias y ajustes (TR-06, STK-07, STK-08, INV-15,
CST-12, `design.md` D5, D5.1, D5.2, D5.4; change 14).

Una anulación es total y única: escribe movimientos inversos que reutilizan los tipos de
STK-03 con otro `origen_tipo` (D5.1) y repiten el `costo_unitario` del movimiento original,
nulo incluido (D5 punto 4, D5.2). No importa infraestructura (`02` §5.2): el servicio lee la
cabecera, las líneas y los movimientos originales y le pasa a estas funciones solo los datos.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.modules.stock.domain.errores import (
    AjusteYaAnuladoError,
    MotivoInvalidoError,
    TransferenciaYaAnuladaError,
)
from app.modules.stock.domain.movimientos import (
    AJUSTE,
    ORIGEN_ANULACION_AJUSTE,
    ORIGEN_ANULACION_TRANSFERENCIA,
    TRANSFERENCIA_ENTRADA,
    TRANSFERENCIA_SALIDA,
    LineaDeMovimiento,
)
from app.modules.stock.domain.operaciones import LineaDeOperacion

ESTADO_CONFIRMADA = "CONFIRMADA"
ESTADO_ANULADA = "ANULADA"
AMBITO_ANULACION_TRANSFERENCIA = "ANULACION_TRANSFERENCIA"
AMBITO_ANULACION_AJUSTE = "ANULACION_AJUSTE"
PERMISO_TRANSFERIR = "TRANSFERIR_STOCK"
PERMISO_ANULAR_TRANSFERENCIA = "ANULAR_TRANSFERENCIA"
PERMISO_PERMITIR_STOCK_NEGATIVO = "PERMITIR_STOCK_NEGATIVO"

Operacion = Literal["TRANSFERENCIA", "AJUSTE"]


@dataclass(frozen=True)
class MovimientoOriginal:
    """Un movimiento del libro que originó una transferencia, tal como quedó escrito."""

    producto_id: UUID
    ubicacion_id: UUID
    cantidad_base: int
    tipo: str
    costo_unitario: Decimal | None


@dataclass(frozen=True)
class LineaDeAjusteOriginal:
    """Una línea de un ajuste confirmado: su cantidad con signo y el costo con que se
    valorizó (nulo si el producto no tenía promedio)."""

    producto_id: UUID
    cantidad_base: int
    costo_unitario: Decimal | None


def validar_anulable(estado: str, *, operacion: Operacion) -> None:
    """D5 punto 1: solo una operación `CONFIRMADA` se anula; la segunda vez es
    `TRANSFERENCIA_YA_ANULADA` / `AJUSTE_YA_ANULADO` (409)."""
    if estado == ESTADO_CONFIRMADA:
        return
    if operacion == "TRANSFERENCIA":
        raise TransferenciaYaAnuladaError("La transferencia ya está anulada.")
    raise AjusteYaAnuladoError("El ajuste ya está anulado.")


def puede_anular_transferencia(
    creador_id: UUID, usuario_id: UUID, permisos: Collection[str]
) -> bool:
    """D5 punto 5, D5.4: `TRANSFERIR_STOCK` es siempre necesario. Con él se anula la propia;
    la de otro usuario además exige `ANULAR_TRANSFERENCIA`, que por sí solo no alcanza."""
    if PERMISO_TRANSFERIR not in permisos:
        return False
    return creador_id == usuario_id or PERMISO_ANULAR_TRANSFERENCIA in permisos


def validar_motivo_de_anulacion(*, activo: bool, ambito: str, ambito_esperado: str) -> None:
    """TR-09, D5 punto 2: el motivo de la anulación es activo y del ámbito de la operación
    (`ANULACION_TRANSFERENCIA` o `ANULACION_AJUSTE`); si no, `MOTIVO_INVALIDO`."""
    if not activo or ambito != ambito_esperado:
        raise MotivoInvalidoError(f"El motivo no es un motivo activo de {ambito_esperado}.")


def expandir_anulacion_transferencia(
    *,
    transferencia_id: UUID,
    lineas: Sequence[LineaDeOperacion],
    originales: Sequence[MovimientoOriginal],
) -> list[LineaDeMovimiento]:
    """Por cada línea (en su orden), la salida del destino y después la entrada al origen
    (D9: la que puede dejar negativo va primero), cada una con la cantidad y el costo de
    SU movimiento original. `origen_id` es la transferencia anulada."""
    por_producto: dict[tuple[UUID, str], MovimientoOriginal] = {
        (original.producto_id, original.tipo): original for original in originales
    }
    inversos: list[LineaDeMovimiento] = []
    for linea in lineas:
        entrada = por_producto.get((linea.producto_id, TRANSFERENCIA_ENTRADA))
        salida = por_producto.get((linea.producto_id, TRANSFERENCIA_SALIDA))
        if entrada is None or salida is None:
            raise ValueError(
                f"Faltan los movimientos originales de la transferencia {transferencia_id} "
                f"para el producto {linea.producto_id}."
            )
        for tipo, original in (
            (TRANSFERENCIA_SALIDA, entrada),
            (TRANSFERENCIA_ENTRADA, salida),
        ):
            inversos.append(
                LineaDeMovimiento(
                    producto_id=original.producto_id,
                    ubicacion_id=original.ubicacion_id,
                    cantidad_base=-original.cantidad_base,
                    tipo=tipo,
                    costo_unitario=original.costo_unitario,
                    origen_tipo=ORIGEN_ANULACION_TRANSFERENCIA,
                    origen_id=transferencia_id,
                )
            )
    return inversos


def expandir_anulacion_ajuste(
    *,
    ajuste_id: UUID,
    ubicacion_id: UUID,
    motivo_anulacion_id: UUID,
    lineas: Sequence[LineaDeAjusteOriginal],
) -> list[LineaDeMovimiento]:
    """Un `AJUSTE` de signo contrario por línea, al costo de la línea original (nulo
    incluido) y con el motivo de la ANULACIÓN en `motivo_id` (D5.1). `origen_id` es el
    ajuste anulado."""
    return [
        LineaDeMovimiento(
            producto_id=linea.producto_id,
            ubicacion_id=ubicacion_id,
            cantidad_base=-linea.cantidad_base,
            tipo=AJUSTE,
            costo_unitario=linea.costo_unitario,
            origen_tipo=ORIGEN_ANULACION_AJUSTE,
            origen_id=ajuste_id,
            motivo_id=motivo_anulacion_id,
        )
        for linea in lineas
    ]
