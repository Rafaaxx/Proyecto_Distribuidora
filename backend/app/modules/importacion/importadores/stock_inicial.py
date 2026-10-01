"""Importador de stock inicial (`specs/importacion/puesta-en-marcha`, `design.md` D4, D7,
D13): una fila por línea, sobre `stock.service.registrar_stock_inicial`.

Cada fila se registra por el mismo servicio que `STOCK_INICIAL_REGISTRAR` (TR-10, ADR-037):
un ingreso con costo recalcula el promedio (CST-11); una cantidad negativa corrige sin
recalcularlo (CST-12) y no deja negativo el saldo; el producto no puede tener movimientos de
otro tipo (STK-10). Una línea por llamada, dentro de su savepoint, para que el error caiga en
la fila culpable. El momento es el `occurred_at` del sobre (D7-A: sin fecha de corte).

Orden de bloqueo (`02` §7.3): las filas se resuelven primero (ubicación por nombre y producto
por código, D4) y se escriben por (producto, ubicación) ascendentes con un orden estable, así
una corrección negativa sigue a su ingreso y una importación no se interbloquea con un stock
inicial por pantalla sobre los mismos productos.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modules.catalogo import service as catalogo_service
from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.informe import ErrorDeFila, traducir_error
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import clave_de_texto, resolver_unica
from app.modules.importacion.domain.stock_inicial import (
    DatosDeStockInicial,
    datos_de_stock_inicial,
    ordenar_para_bloqueo,
)
from app.modules.importacion.importadores.base import (
    ContextoDeImportacion,
    ejecutar_en_savepoint,
)
from app.modules.stock import service as stock_service
from app.modules.stock.service import LineaDeStockInicial

TIPO = "STOCK_INICIAL"


@dataclass(frozen=True)
class _FilaResuelta:
    fila: int
    datos: DatosDeStockInicial
    producto_id: UUID
    ubicacion_id: UUID


def importar_stock_inicial(
    contexto: ContextoDeImportacion, filas: Sequence[FilaPlanilla]
) -> list[ErrorDeFila]:
    org, sesion = contexto.organizacion_id, contexto.sesion
    productos: dict[str, list[Any]] = {}
    ubicaciones: dict[str, list[Any]] = {}

    def buscar(
        cache: dict[str, list[Any]], texto: str, buscador: Callable[[str], list[Any]]
    ) -> list[Any]:
        clave = clave_de_texto(texto)
        if clave not in cache:
            cache[clave] = buscador(texto)
        return cache[clave]

    def ubicaciones_por_nombre(nombre: str) -> list[Any]:
        return stock_service.buscar_ubicaciones_por_nombre(org, nombre, sesion)  # type: ignore[arg-type]

    def productos_por_codigo(codigo: str) -> list[Any]:
        return catalogo_service.buscar_productos_por_codigo(org, codigo, sesion)  # type: ignore[arg-type]

    errores: list[ErrorDeFila] = []
    resueltas: list[_FilaResuelta] = []
    for fila in filas:
        try:
            datos = datos_de_stock_inicial(fila)
            ubicacion = resolver_unica(
                buscar(ubicaciones, datos.ubicacion, ubicaciones_por_nombre),
                columna="ubicacion",
                valor=datos.ubicacion,
                que="una ubicación",
            )
            producto = resolver_unica(
                buscar(productos, datos.producto_codigo, productos_por_codigo),
                columna="producto_codigo",
                valor=datos.producto_codigo,
                que="un producto",
            )
        except ErrorDeValor as error:
            errores.append(traducir_error(TIPO, fila.fila, error))
            continue
        resueltas.append(_FilaResuelta(fila.fila, datos, producto.id, ubicacion.id))

    for resuelta in ordenar_para_bloqueo(
        resueltas, clave=lambda r: (r.producto_id, r.ubicacion_id)
    ):

        def registrar(r: _FilaResuelta = resuelta) -> None:
            stock_service.registrar_stock_inicial(
                org,
                sesion,  # type: ignore[arg-type]
                contexto.reloj,
                ubicacion_id=r.ubicacion_id,
                lineas=[
                    LineaDeStockInicial(
                        producto_id=r.producto_id,
                        cantidad_base=r.datos.cantidad_base,
                        costo_unitario=r.datos.costo_unitario,
                    )
                ],
                usuario_id=contexto.usuario_id,
                dispositivo_id=contexto.dispositivo_id,
                operation_id=contexto.operation_id,
                occurred_at=contexto.occurred_at,
            )

        fallo = ejecutar_en_savepoint(TIPO, sesion, registrar, fila=resuelta.fila)
        if fallo is not None:
            errores.append(fallo)
    return errores
