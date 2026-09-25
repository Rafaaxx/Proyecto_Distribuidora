"""Validación pura del lote de `COSTO_INFORMAR` (`design.md` D12, tarea
6.4). No valida existencia ni actividad de proveedor/producto/presentación
(eso pasa por datos, es responsabilidad del servicio, tarea 8.3) -- solo la
forma del lote en sí: cardinalidad, duplicados y los campos numéricos de
cada costo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.modules.proveedores.domain.errores import (
    BonificacionInvalidaError,
    CostosInvalidosError,
    ValorInvalidoError,
)

_MAXIMO_COSTOS_POR_LOTE = 200
_DECIMALES_VALOR = 2
_DECIMALES_BONIFICACION = 6


@dataclass(frozen=True, slots=True)
class CostoDelLote:
    """Un costo dentro del lote de `COSTO_INFORMAR` (CST-01, D12)."""

    producto_id: UUID
    presentacion_id: UUID
    valor: Decimal
    incluye_iva: bool
    bonificacion: Decimal
    vigencia_desde: date
    observacion: str | None


def _cantidad_de_decimales(valor: Decimal) -> int:
    _signo, _digitos, exponente = valor.as_tuple()
    assert isinstance(exponente, int)
    return max(0, -exponente)


def _validar_valor(valor: Decimal, fila: int) -> None:
    if valor <= 0:
        raise ValorInvalidoError(
            "El valor informado debe ser mayor a cero.", extension={"fila": fila}
        )
    if _cantidad_de_decimales(valor) > _DECIMALES_VALOR:
        raise ValorInvalidoError(
            "El valor informado no puede tener más de 2 decimales (no se redondea, se rechaza).",
            extension={"fila": fila},
        )


def _validar_bonificacion(bonificacion: Decimal, fila: int) -> None:
    if bonificacion < 0 or bonificacion >= 1:
        raise BonificacionInvalidaError(
            "La bonificación debe estar entre 0 (inclusive) y 1 (exclusive).",
            extension={"fila": fila},
        )
    if _cantidad_de_decimales(bonificacion) > _DECIMALES_BONIFICACION:
        raise BonificacionInvalidaError(
            "La bonificación no puede tener más de 6 decimales (no se redondea, se rechaza).",
            extension={"fila": fila},
        )


def validar_lote_de_costos(costos: list[CostoDelLote]) -> None:
    """Levanta `COSTOS_INVALIDOS` si el lote está vacío o tiene más de 200
    costos (errores de lote completo, sin fila); levanta `COSTOS_INVALIDOS`
    con `fila` (contrato-api.md P9) si repite `(producto, presentación,
    vigencia desde)` -- `fila` es el índice de la segunda ocurrencia, la que
    hace fallar el lote; levanta `VALOR_INVALIDO`/`BONIFICACION_INVALIDA`,
    también con `fila`, si algún costo del lote tiene ese campo fuera de
    rango o con más decimales de los permitidos."""
    if not costos:
        raise CostosInvalidosError("El lote de costos no puede estar vacío.")
    if len(costos) > _MAXIMO_COSTOS_POR_LOTE:
        raise CostosInvalidosError(
            f"El lote de costos no puede tener más de {_MAXIMO_COSTOS_POR_LOTE} costos "
            f"(recibidos: {len(costos)})."
        )

    claves_vistas: dict[tuple[UUID, UUID, date], int] = {}
    for fila, costo in enumerate(costos):
        clave = (costo.producto_id, costo.presentacion_id, costo.vigencia_desde)
        if clave in claves_vistas:
            raise CostosInvalidosError(
                "El lote no puede repetir el mismo producto, presentación y vigencia desde "
                f"({costo.producto_id}, {costo.presentacion_id}, {costo.vigencia_desde}).",
                extension={"fila": fila},
            )
        claves_vistas[clave] = fila

        _validar_valor(costo.valor, fila)
        _validar_bonificacion(costo.bonificacion, fila)
