"""Dominio puro de la anulación de venta (change 19).
Sin dependencias de FastAPI ni SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.ventas.domain.errores import (
    ConsumidorFinalSinDevolucionError,
    DevolucionInvalidaError,
    ObservacionInvalidaError,
    VentaYaAnuladaError,
)

MAXIMO_OBSERVACION = 500
_CUANTAS = Decimal("1")
_COSTO = Decimal("0.000001")
_REDONDEO = ROUND_HALF_UP


def _d(v: str | Decimal | int | float) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return Decimal(str(v))
    return Decimal(str(v))


def _s(v: Decimal) -> str:
    q = v.quantize(Decimal("0.01"), rounding=_REDONDEO)
    return f"{q:.2f}"


@dataclass(frozen=True)
class MovimientoAnulacion:
    tipo: str
    importe: str


@dataclass(frozen=True)
class EfectoCuentaAnulacion:
    movimientos: list[MovimientoAnulacion]
    saldo_final_relativo: str


def validar_observacion(observacion: str | None) -> str | None:
    """VTA-20, D1: hasta 500 caracteres (medidos antes de recortar); devuelve la observación a
    guardar, recortada (`None` si vino vacía)."""
    if observacion is None:
        return None
    if len(observacion) > MAXIMO_OBSERVACION:
        raise ObservacionInvalidaError(
            f"La observación admite hasta {MAXIMO_OBSERVACION} caracteres "
            f"y tiene {len(observacion)}."
        )
    return observacion.strip() or None


def validar_venta_anulable(estado: str) -> None:
    if estado == "ANULADA":
        raise VentaYaAnuladaError("La venta ya fue anulada")


def validar_devolucion(
    tiene_cobranza: bool | None,
    devuelve_dinero: bool | None,
    es_consumidor_final: bool,
) -> None:
    """VTA-22, CLI-03, D2, D3: con cobranza confirmada `devuelve_dinero` se indica (y al consumidor
    final no se le puede dejar el dinero); sin ella se omite."""
    if tiene_cobranza:
        if devuelve_dinero is None:
            raise DevolucionInvalidaError("Hay que indicar si se devuelve el dinero cobrado")
        if devuelve_dinero is False and es_consumidor_final:
            raise ConsumidorFinalSinDevolucionError("Al consumidor final no se le devuelve dinero")
    elif devuelve_dinero is not None:
        raise DevolucionInvalidaError("No corresponde devolver dinero en este caso")


def efecto_en_cuenta(
    total_venta: str | Decimal,
    importe_cobranza: str | Decimal | None,
    devuelve_dinero: bool | None,
) -> EfectoCuentaAnulacion:
    total = _d(total_venta)
    cobro = Decimal("0") if importe_cobranza is None else _d(importe_cobranza)
    if cobro < Decimal("0"):
        cobro = Decimal("0")

    movimientos: list[MovimientoAnulacion] = []
    movimientos.append(MovimientoAnulacion(tipo="ANULACION_VENTA", importe=_s(total)))

    if devuelve_dinero is True and cobro > Decimal("0"):
        movimientos.append(MovimientoAnulacion(tipo="ANULACION_COBRANZA", importe=_s(cobro)))

    if cobro == Decimal("0"):
        saldo = -total
    elif devuelve_dinero is True:
        saldo = Decimal("0")
    else:
        saldo = -(cobro)
    return EfectoCuentaAnulacion(movimientos=movimientos, saldo_final_relativo=_s(saldo))


@dataclass(frozen=True)
class LineaReingreso:
    producto_id: str
    presentacion_id: str
    cantidad_unidad_base: int
    costo_unitario: str | None


def lineas_de_reingreso(lineas: Iterable[dict[str, Any]]) -> list[LineaReingreso]:
    resultado: list[LineaReingreso] = []
    for linea in lineas:
        costo = linea.get("costo_unitario")
        costo_s = None if costo is None else f"{_d(costo).quantize(_COSTO, rounding=_REDONDEO):.6f}"
        resultado.append(
            LineaReingreso(
                producto_id=str(linea["producto_id"]),
                presentacion_id=str(linea["presentacion_id"]),
                cantidad_unidad_base=int(linea["cantidad_unidad_base"]),
                costo_unitario=costo_s,
            )
        )
    return resultado
