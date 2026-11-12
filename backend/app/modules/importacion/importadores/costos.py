"""Importador de costos informados (`specs/importacion/importacion-de-maestros`, `design.md`
D4, D8): una fila por costo, sobre `proveedores.service.informar_costos`.

Cada fila se registra por el mismo camino que `COSTO_INFORMAR` (TR-10): lote de una fila, con
el proveedor actual del producto (CAT-06), costo base derivado según CST-02, sin sobrescribir
costos anteriores (CST-03) y con la presentación de compra activa del producto (que queda
congelada, INV-18). El producto se resuelve por código y la presentación por nombre dentro
del producto (D4); el error del servicio, que informa el índice dentro del lote, se traduce
a la fila de la planilla. La repetición de producto, presentación y vigencia dentro del
archivo se detecta antes (`FILA_DUPLICADA`), igual que el lote de `COSTO_INFORMAR`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from app.modules.catalogo import service as catalogo_service
from app.modules.identidad import service as identidad_service
from app.modules.importacion.domain.costos import claves_de_costo, datos_de_costo
from app.modules.importacion.domain.duplicados import marcar_duplicadas
from app.modules.importacion.domain.informe import ErrorDeFila
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.referencias import clave_de_texto, resolver_unica
from app.modules.importacion.importadores.base import (
    ContextoDeImportacion,
    ejecutar_en_savepoint,
)
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.service import CostoDelLote

TIPO = "COSTOS"


def importar_costos(
    contexto: ContextoDeImportacion, filas: Sequence[FilaPlanilla]
) -> list[ErrorDeFila]:
    org, sesion = contexto.organizacion_id, contexto.sesion
    # CST-06, D6: la regla de la organización se lee una vez, `FOR SHARE`, y vale para todo
    # el archivo: un cambio de condición concurrente espera a esta importación. Cada fila
    # la vuelve a leer en `informar_costos`, que es quien rechaza `incluye_iva` (D4).
    computa_credito_fiscal = identidad_service.organizacion_computa_credito_fiscal(
        org,
        sesion,  # type: ignore[arg-type]
        para_compartir=True,
    )
    productos: dict[str, list[Any]] = {}
    presentaciones: dict[UUID, list[Any]] = {}

    def productos_de(codigo: str) -> list[Any]:
        clave = clave_de_texto(codigo)
        if clave not in productos:
            productos[clave] = catalogo_service.buscar_productos_por_codigo(
                org,
                codigo,
                sesion,  # type: ignore[arg-type]
            )
        return productos[clave]

    def presentaciones_de(producto_id: UUID) -> list[Any]:
        if producto_id not in presentaciones:
            presentaciones[producto_id] = catalogo_service.listar_presentaciones_de_producto(
                org,
                producto_id,
                sesion,  # type: ignore[arg-type]
            )
        return presentaciones[producto_id]

    def registrar(fila: FilaPlanilla) -> Callable[[], None]:
        def accion() -> None:
            datos = datos_de_costo(fila, computa_credito_fiscal=computa_credito_fiscal is not False)
            producto = resolver_unica(
                productos_de(datos.producto_codigo),
                columna="producto_codigo",
                valor=datos.producto_codigo,
                que="un producto",
            )
            coincidentes = [
                p
                for p in presentaciones_de(producto.id)
                if clave_de_texto(p.nombre) == clave_de_texto(datos.presentacion)
            ]
            presentacion = resolver_unica(
                coincidentes,
                columna="presentacion",
                valor=datos.presentacion,
                que="una presentación del producto",
            )
            proveedores_service.informar_costos(
                org,
                sesion,  # type: ignore[arg-type]
                contexto.reloj,
                proveedor_id=producto.proveedor_id,
                costos=[
                    CostoDelLote(
                        producto_id=producto.id,
                        presentacion_id=presentacion.id,
                        valor=datos.valor,
                        incluye_iva=datos.incluye_iva,
                        bonificacion=datos.bonificacion,
                        vigencia_desde=datos.vigencia_desde,
                        observacion=datos.observacion,
                    )
                ],
                operation_id=contexto.operation_id,
                actor_id=contexto.usuario_id,
            )

        return accion

    duplicadas = marcar_duplicadas(filas, claves_de_costo)
    errores: list[ErrorDeFila] = []
    for fila in filas:
        if fila.fila in duplicadas:
            errores.append(duplicadas[fila.fila])
            continue
        error = ejecutar_en_savepoint(
            TIPO,
            contexto.sesion,
            registrar(fila),
            fila=fila.fila,
            filas_de_lote=[fila.fila],  # el lote es de una fila: el índice 0 es esta fila
        )
        if error is not None:
            errores.append(error)
    return errores
