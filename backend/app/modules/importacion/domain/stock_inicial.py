"""Importación de stock inicial: de la fila de planilla a la línea del servicio
(`specs/importacion/puesta-en-marcha`, `design.md` D4, D13).

Puro. La planilla trae `cantidad_base` entera y `costo_unitario` por unidad base: el mismo
contrato que `STOCK_INICIAL_REGISTRAR` (ADR-037 punto 5), sin conversiones ni redondeos. La
cantidad se lee como entero (INV-04) y el costo con coma decimal, sin punto flotante (INV-03),
y viaja como cadena decimal. Las reglas de negocio (cantidad distinta de cero, costo
obligatorio si ingresa y prohibido si egresa, mayor que cero y con hasta 6 decimales, saldo no
negativo, producto sin otras operaciones) son del servicio de `stock`: acá no se repiten.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import obligatorio
from app.modules.importacion.domain.valores import a_decimal, a_entero


@dataclass(frozen=True)
class DatosDeStockInicial:
    """Una fila de stock inicial ya leída. `ubicacion` y `producto_codigo` siguen siendo
    texto: el importador los resuelve contra los datos de la organización (D4)."""

    ubicacion: str
    producto_codigo: str
    cantidad_base: int
    costo_unitario: str | None


def datos_de_stock_inicial(fila: FilaPlanilla) -> DatosDeStockInicial:
    """Lee la fila o lanza el `ErrorDeValor` de la primera celda ilegible (con su
    columna). Un costo vacío es `None`: el servicio decide si la línea lo necesita."""
    valores = fila.valores
    texto_costo = valores["costo_unitario"].strip()
    return DatosDeStockInicial(
        ubicacion=obligatorio(valores["ubicacion"], columna="ubicacion"),
        producto_codigo=obligatorio(valores["producto_codigo"], columna="producto_codigo"),
        cantidad_base=a_entero(valores["cantidad_base"], columna="cantidad_base"),
        costo_unitario=(
            str(a_decimal(texto_costo, columna="costo_unitario")) if texto_costo else None
        ),
    )


def ordenar_para_bloqueo[T](
    items: Sequence[T], *, clave: Callable[[T], tuple[object, ...]]
) -> list[T]:
    """Orden ascendente por `clave` (producto, ubicación) para respetar el orden global de
    bloqueo (`02` §7.3). Es estable: dos filas con la misma clave conservan el orden del
    archivo, así una corrección negativa sigue a su ingreso."""
    return sorted(items, key=clave)
