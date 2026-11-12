"""Importador de productos con presentaciones (`specs/importacion/importacion-de-maestros`,
`design.md` D4, D5, D6): una fila por presentación, agrupadas por `codigo`, solo altas,
sobre `catalogo.service.crear_producto`.

Las mismas reglas que `PRODUCTO_CREAR` (TR-10): el servicio valida CAT-01 a CAT-03 y rechaza
los duplicados y las referencias inactivas con sus códigos. Acá se agrupan las filas, se
resuelven las referencias por clave natural dentro de la organización (D4, INV-21) y cada
producto se escribe en su propio savepoint: un error en cualquier presentación impide el
alta de ese producto entero y se informa en la fila de la presentación culpable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar
from uuid import UUID

from app.core.errors import DomainError
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.service import DatosPresentacion
from app.modules.configuracion import service as configuracion_service
from app.modules.importacion.domain.errores import ErrorDeValor
from app.modules.importacion.domain.informe import ErrorDeFila, traducir_error
from app.modules.importacion.domain.planilla import FilaPlanilla
from app.modules.importacion.domain.productos import (
    ProductoDeGrupo,
    agrupar_por_codigo,
    analizar_grupo,
    columna_del_error,
    fila_del_error,
)
from app.modules.importacion.domain.referencias import clave_de_texto, resolver_unica
from app.modules.importacion.importadores.base import (
    ContextoDeImportacion,
    ejecutar_en_savepoint,
)
from app.modules.proveedores import service as proveedores_service

TIPO = "PRODUCTOS"

T = TypeVar("T")


class _Memo:
    """Una búsqueda por clave natural se hace una vez por clave distinta del archivo,
    no una vez por fila: un archivo de 2.000 filas repite las mismas categorías."""

    def __init__(self) -> None:
        self._resultados: dict[tuple[str, str], list[Any]] = {}

    def buscar(self, tipo: str, clave: str, buscar: Callable[[], list[T]]) -> list[T]:
        indice = (tipo, clave_de_texto(clave))
        if indice not in self._resultados:
            self._resultados[indice] = buscar()
        return self._resultados[indice]


def _resolver_referencias(
    contexto: ContextoDeImportacion, memo: _Memo, producto: ProductoDeGrupo
) -> tuple[tuple[UUID, UUID | None, UUID, UUID] | None, list[ErrorDeFila]]:
    """`(categoria_id, marca_id, proveedor_id, alicuota_id)` o los errores de cada
    referencia que no se pudo resolver, todos en la primera fila del producto."""
    org, sesion = contexto.organizacion_id, contexto.sesion
    errores: list[ErrorDeFila] = []

    def resolver(
        tipo: str, columna: str, texto: str, que: str, buscar: Callable[[], list[Any]]
    ) -> UUID | None:
        try:
            return resolver_unica(  # type: ignore[no-any-return]
                memo.buscar(tipo, texto, buscar), columna=columna, valor=texto, que=que
            ).id
        except ErrorDeValor as error:
            errores.append(traducir_error(TIPO, producto.fila, error))
            return None

    categoria_id = resolver(
        "categoria",
        "categoria",
        producto.categoria,
        "una categoría",
        lambda: catalogo_service.buscar_categorias_por_nombre(
            org,
            producto.categoria,
            sesion,  # type: ignore[arg-type]
        ),
    )
    marca_id = (
        resolver(
            "marca",
            "marca",
            producto.marca,
            "una marca",
            lambda: catalogo_service.buscar_marcas_por_nombre(
                org,
                producto.marca or "",
                sesion,  # type: ignore[arg-type]
            ),
        )
        if producto.marca
        else None
    )
    proveedor_id = resolver(
        "proveedor",
        "proveedor",
        producto.proveedor,
        "un proveedor",
        lambda: proveedores_service.buscar_proveedores_por_nombre(
            org,
            producto.proveedor,
            sesion,  # type: ignore[arg-type]
        ),
    )
    alicuota_id = resolver(
        "alicuota",
        "alicuota",
        producto.alicuota_texto,
        "una alícuota",
        lambda: configuracion_service.buscar_alicuotas_por_valor(
            org,
            producto.alicuota,
            sesion,  # type: ignore[arg-type]
        ),
    )
    if errores or categoria_id is None or proveedor_id is None or alicuota_id is None:
        return None, errores
    return (categoria_id, marca_id, proveedor_id, alicuota_id), []


def importar_productos(
    contexto: ContextoDeImportacion, filas: Sequence[FilaPlanilla]
) -> list[ErrorDeFila]:
    errores: list[ErrorDeFila] = []
    memo = _Memo()
    for grupo in agrupar_por_codigo(filas):
        producto, errores_de_lectura = analizar_grupo(grupo)
        if producto is None:
            errores.extend(errores_de_lectura)
            continue
        referencias, errores_de_referencia = _resolver_referencias(contexto, memo, producto)
        if referencias is None:
            errores.extend(errores_de_referencia)
            continue
        categoria_id, marca_id, proveedor_id, alicuota_id = referencias

        def crear(
            producto: ProductoDeGrupo = producto,
            categoria_id: UUID = categoria_id,
            marca_id: UUID | None = marca_id,
            proveedor_id: UUID = proveedor_id,
            alicuota_id: UUID = alicuota_id,
        ) -> None:
            catalogo_service.crear_producto(
                contexto.organizacion_id,
                contexto.sesion,  # type: ignore[arg-type]
                contexto.reloj,
                codigo=producto.codigo,
                nombre=producto.nombre,
                categoria_id=categoria_id,
                marca_id=marca_id,
                proveedor_id=proveedor_id,
                unidad_base=producto.unidad_base,
                alicuota_id=alicuota_id,
                presentaciones=[
                    DatosPresentacion(
                        nombre=p.nombre,
                        unidades_base=p.unidades_base,
                        usar_en_venta=p.usar_en_venta,
                        usar_en_compra=p.usar_en_compra,
                        es_referencia=p.es_referencia,
                    )
                    for p in producto.presentaciones
                ],
                actor_id=contexto.usuario_id,
            )

        def fila_del_servicio(error: DomainError, producto: ProductoDeGrupo = producto) -> int:
            return fila_del_error(
                error.codigo,
                producto.presentaciones,
                producto.fila,
                nombre_vacio=not producto.nombre,
            )

        def columna_del_servicio(
            error: DomainError, producto: ProductoDeGrupo = producto
        ) -> str | None:
            return columna_del_error(error.codigo, nombre_vacio=not producto.nombre)

        error = ejecutar_en_savepoint(
            TIPO,
            contexto.sesion,
            crear,
            fila=fila_del_servicio,
            columna=columna_del_servicio,
        )
        if error is not None:
            errores.append(error)
    return errores
