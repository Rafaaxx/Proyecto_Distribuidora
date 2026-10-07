"""Casos de uso de lectura de `precios` para su propia API (`CLAUDE.md` §7; change 13, grupo
5). Interno del módulo: `precios/api.py` lo usa para armar las respuestas de sus rutas; los
otros módulos leen `precios` por `service.py`.

Toda lectura filtra por la organización del token y responde `RecursoNoEncontradoError` (404)
si la lista no existe en ella (INV-21, SEG-07). Los nombres de las entidades del alcance de
una regla vienen de `catalogo/service.py` y `proveedores/service.py` en una consulta por tipo
de entidad: `precios` no importa sus modelos ni sus repositorios.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.identidad import service as identidad_service
from app.modules.precios import repository
from app.modules.precios import service as precios_service
from app.modules.precios.domain.borrador import relacion_con_la_base
from app.modules.precios.domain.errores import RecursoNoEncontradoError
from app.modules.precios.domain.versiones import VersionDeLista, estados_derivados
from app.modules.precios.models import ListaPrecio, ListaVersion, RedondeoCategoria, ReglaMargen
from app.modules.precios.schemas import (
    BorradorResponse,
    GeneracionResponse,
    ListaDetalleResponse,
    ListaOpcionesResponse,
    ListaOpcionResponse,
    ListaPredeterminadaResponse,
    ListaResponse,
    ListasResponse,
    PrecioDeVersionResponse,
    PrecioFijadoResponse,
    PreciosDeVersionResponse,
    PreciosVigentesResponse,
    PrecioVigenteResponse,
    PresentacionDeVentaResponse,
    ProductoSinPrecioResponse,
    RedondeoCategoriaResponse,
    ReglaResponse,
    ReglasResponse,
    SenalesResponse,
    VersionesResponse,
    VersionResponse,
)
from app.modules.proveedores import service as proveedores_service


def _lista_response(
    lista: ListaPrecio, version_vigente: dict[UUID, int], con_borrador: set[UUID]
) -> ListaResponse:
    return ListaResponse(
        id=lista.id,
        nombre=lista.nombre,
        redondeo_multiplo=lista.redondeo_multiplo,
        redondeo_direccion=lista.redondeo_direccion,
        activo=lista.activo,
        version_vigente=version_vigente.get(lista.id),
        tiene_borrador=lista.id in con_borrador,
        creado_en=lista.creado_en,
        actualizado_en=lista.actualizado_en,
    )


def _lista_o_404(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> ListaPrecio:
    lista = repository.obtener_lista(organizacion_id, lista_id, sesion)
    if lista is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no existe en esta organización.")
    return lista


def listar_listas(organizacion_id: UUID, sesion: Session, *, ahora: datetime) -> ListasResponse:
    """Las listas de la organización con su versión vigente y si tienen un borrador."""
    version_vigente, con_borrador = repository.resumen_de_versiones(
        organizacion_id, sesion, ahora=ahora
    )
    return ListasResponse(
        items=[
            _lista_response(lista, version_vigente, con_borrador)
            for lista in repository.listar_listas(organizacion_id, sesion)
        ]
    )


def obtener_lista(
    organizacion_id: UUID, lista_id: UUID, sesion: Session, *, ahora: datetime
) -> ListaResponse:
    lista = _lista_o_404(organizacion_id, lista_id, sesion)
    version_vigente, con_borrador = repository.resumen_de_versiones(
        organizacion_id, sesion, ahora=ahora
    )
    return _lista_response(lista, version_vigente, con_borrador)


def obtener_detalle_de_lista(
    organizacion_id: UUID, lista_id: UUID, sesion: Session, *, ahora: datetime
) -> ListaDetalleResponse:
    """El detalle de una lista con sus sobrescrituras de redondeo por categoría."""
    resumen = obtener_lista(organizacion_id, lista_id, sesion, ahora=ahora)
    redondeos = repository.listar_redondeos_de_categoria(organizacion_id, lista_id, sesion)
    nombres = catalogo_service.nombres_de_categorias(
        organizacion_id, {redondeo.categoria_id for redondeo in redondeos}, sesion
    )
    return ListaDetalleResponse(
        **resumen.model_dump(),
        redondeos_categoria=[_redondeo_response(r, nombres.get(r.categoria_id)) for r in redondeos],
    )


def _redondeo_response(
    redondeo: RedondeoCategoria, categoria_nombre: str | None
) -> RedondeoCategoriaResponse:
    return RedondeoCategoriaResponse(
        id=redondeo.id,
        categoria_id=redondeo.categoria_id,
        categoria_nombre=categoria_nombre,
        multiplo=redondeo.multiplo,
        direccion=redondeo.direccion,
        activo=redondeo.activo,
    )


def obtener_redondeo_de_categoria(
    organizacion_id: UUID, lista_id: UUID, categoria_id: UUID, sesion: Session
) -> RedondeoCategoriaResponse:
    for redondeo in repository.listar_redondeos_de_categoria(organizacion_id, lista_id, sesion):
        if redondeo.categoria_id == categoria_id:
            nombres = catalogo_service.nombres_de_categorias(
                organizacion_id, [categoria_id], sesion
            )
            return _redondeo_response(redondeo, nombres.get(categoria_id))
    raise RecursoNoEncontradoError(
        f"La lista {lista_id} no tiene sobrescritura para la categoría {categoria_id}."
    )


def listar_opciones_de_listas(organizacion_id: UUID, sesion: Session) -> ListaOpcionesResponse:
    """Lectura reducida: identificador y nombre de las listas activas (`design.md` D12)."""
    return ListaOpcionesResponse(
        items=[
            ListaOpcionResponse(id=lista.id, nombre=lista.nombre)
            for lista in repository.listar_listas_activas(organizacion_id, sesion)
        ]
    )


def _reglas_response(
    organizacion_id: UUID, reglas: list[ReglaMargen], sesion: Session
) -> list[ReglaResponse]:
    def ids(alcance: str) -> set[UUID]:
        return {
            regla.alcance_id
            for regla in reglas
            if regla.alcance_tipo == alcance and regla.alcance_id is not None
        }

    nombres: dict[tuple[str, UUID], str] = {}
    for alcance, buscar in (
        ("PRODUCTO", catalogo_service.nombres_de_productos),
        ("MARCA", catalogo_service.nombres_de_marcas),
        ("CATEGORIA", catalogo_service.nombres_de_categorias),
        ("PROVEEDOR", proveedores_service.nombres_de_proveedores),
    ):
        for entidad_id, nombre in buscar(organizacion_id, ids(alcance), sesion).items():
            nombres[(alcance, entidad_id)] = nombre
    return [
        ReglaResponse(
            id=regla.id,
            lista_id=regla.lista_id,
            alcance_tipo=regla.alcance_tipo,
            alcance_id=regla.alcance_id,
            alcance_nombre=(
                None
                if regla.alcance_id is None
                else nombres.get((regla.alcance_tipo, regla.alcance_id))
            ),
            tipo=regla.tipo,
            valor=regla.valor,
            activo=regla.activo,
            creado_en=regla.creado_en,
            actualizado_en=regla.actualizado_en,
        )
        for regla in reglas
    ]


def listar_reglas(organizacion_id: UUID, lista_id: UUID, sesion: Session) -> ReglasResponse:
    """Las reglas de una lista con el nombre de la entidad de su alcance."""
    _lista_o_404(organizacion_id, lista_id, sesion)
    reglas = repository.listar_reglas(organizacion_id, lista_id, sesion)
    return ReglasResponse(items=_reglas_response(organizacion_id, reglas, sesion))


def obtener_regla(
    organizacion_id: UUID, lista_id: UUID, regla_id: UUID, sesion: Session
) -> ReglaResponse:
    for regla in listar_reglas(organizacion_id, lista_id, sesion).items:
        if regla.id == regla_id:
            return regla
    raise RecursoNoEncontradoError(f"La regla {regla_id} no existe en esta lista.")


# --- borrador y precios de una versión (change 13, grupos 7 y 8) ----------------------------


def respuesta_de_generacion(
    organizacion_id: UUID, resultado: dict[str, object], sesion: Session
) -> GeneracionResponse:
    """La respuesta de `LISTA_GENERAR_BORRADOR` a partir del resultado del comando, con el
    nombre de cada producto sin precio. Sirve también para el reenvío idempotente: el
    resultado es el que quedó guardado."""
    filas = cast(list[dict[str, str]], resultado["productos_sin_precio"])
    sin_precio = [(UUID(fila["producto_id"]), fila["causa"]) for fila in filas]
    nombres = catalogo_service.nombres_de_productos(
        organizacion_id, {producto_id for producto_id, _ in sin_precio}, sesion
    )
    return GeneracionResponse(
        version_id=UUID(str(resultado["version_id"])),
        numero=cast(int, resultado["numero"]),
        regenerado=cast(bool, resultado["regenerado"]),
        cantidad_precios=cast(int, resultado["cantidad_precios"]),
        productos_sin_precio=[
            ProductoSinPrecioResponse(
                producto_id=producto_id, producto_nombre=nombres.get(producto_id), causa=causa
            )
            for producto_id, causa in sin_precio
        ],
        precios_con_otra_regla_iva=cast(int, resultado["precios_con_otra_regla_iva"]),
        precios_con_costos_distintos=cast(int, resultado["precios_con_costos_distintos"]),
    )


def respuesta_de_precio_fijado(resultado: dict[str, object]) -> PrecioFijadoResponse:
    precio = resultado["precio_final"]
    return PrecioFijadoResponse(
        version_id=UUID(str(resultado["version_id"])),
        producto_id=UUID(str(resultado["producto_id"])),
        precio_final=None if precio is None else str(precio),
        manual=cast(bool, resultado["manual"]),
    )


def _version_response(
    version: ListaVersion, nombres: dict[UUID, str], *, estado_derivado: str | None = None
) -> VersionResponse:
    return VersionResponse(
        id=version.id,
        lista_id=version.lista_id,
        numero=version.numero,
        estado=version.estado,
        estado_derivado=estado_derivado,
        vigencia_desde=version.vigencia_desde,
        vigencia_hasta=version.vigencia_hasta,
        version_base_id=version.version_base_id,
        generado_en=version.generado_en,
        creado_por_id=version.creado_por_id,
        creado_por_nombre=nombres.get(version.creado_por_id),
        creado_en=version.creado_en,
        publicado_por_id=version.publicado_por_id,
        publicado_por_nombre=(
            None if version.publicado_por_id is None else nombres.get(version.publicado_por_id)
        ),
        publicado_en=version.publicado_en,
        anulado_por_id=version.anulado_por_id,
        anulado_por_nombre=(
            None if version.anulado_por_id is None else nombres.get(version.anulado_por_id)
        ),
        anulado_en=version.anulado_en,
    )


def _nombres_de_autores(
    organizacion_id: UUID, versiones: list[ListaVersion], sesion: Session
) -> dict[UUID, str]:
    ids: set[UUID] = set()
    for version in versiones:
        ids.add(version.creado_por_id)
        if version.publicado_por_id is not None:
            ids.add(version.publicado_por_id)
        if version.anulado_por_id is not None:
            ids.add(version.anulado_por_id)
    return identidad_service.obtener_nombres_de_usuarios(organizacion_id, ids, sesion)


def _texto(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


def _senales_response(
    senales: precios_service.SenalesDePrecio, presentaciones: dict[UUID, str]
) -> SenalesResponse:
    presentacion_id = senales.presentacion_del_costo_id
    return SenalesResponse(
        sin_costo=senales.sin_costo,
        margen_menor=senales.margen_menor,
        costo_otra_regla_iva=senales.costo_otra_regla_iva,
        costos_distintos_por_presentacion=senales.costos_distintos_por_presentacion,
        presentacion_del_costo_id=presentacion_id,
        presentacion_del_costo_nombre=(
            None if presentacion_id is None else presentaciones.get(presentacion_id)
        ),
    )


def _precios_de_la_pagina(
    organizacion_id: UUID,
    version: ListaVersion,
    sesion: Session,
    *,
    con_senales: bool,
    ver_costos: bool,
    limite: int,
    cursor: str | None,
) -> tuple[list[PrecioDeVersionResponse], str | None]:
    """Una página de precios de la versión con el nombre del producto, la comparación con la
    versión base y -en un borrador- las señales; los campos de costo solo con `ver_costos`."""
    precios, siguiente = repository.listar_precios_paginado(
        organizacion_id, version.id, sesion, limite=limite, cursor=cursor
    )
    producto_ids = {precio.producto_id for precio in precios}
    nombres = catalogo_service.nombres_de_productos(organizacion_id, producto_ids, sesion)
    base = (
        {}
        if version.version_base_id is None
        else repository.precios_finales_por_producto(
            organizacion_id, version.version_base_id, producto_ids, sesion
        )
    )
    senales = (
        precios_service.senales_de_precios(organizacion_id, sesion, version, precios)
        if con_senales
        else {}
    )
    presentaciones = catalogo_service.nombres_de_presentaciones(
        organizacion_id,
        {
            s.presentacion_del_costo_id
            for s in senales.values()
            if s.presentacion_del_costo_id is not None
        },
        sesion,
    )
    de_venta = catalogo_service.presentaciones_de_venta_de_productos(
        organizacion_id, producto_ids, sesion
    )
    respuestas: list[PrecioDeVersionResponse] = []
    for precio in precios:
        senales_del_precio = senales.get(precio.producto_id)
        precio_base = base.get(precio.producto_id)
        respuestas.append(
            PrecioDeVersionResponse(
                producto_id=precio.producto_id,
                producto_nombre=nombres.get(precio.producto_id),
                unidades_referencia=precio.unidades_referencia,
                precio_final=str(precio.precio_final),
                manual=precio.manual,
                precio_version_base=None if precio_base is None else str(precio_base),
                relacion=relacion_con_la_base(precio.precio_final, precio_base),
                senales=(
                    None
                    if senales_del_precio is None
                    else _senales_response(senales_del_precio, presentaciones)
                ),
                presentaciones=[
                    PresentacionDeVentaResponse(nombre=p.nombre, unidades_base=p.unidades_base)
                    for p in de_venta.get(precio.producto_id, [])
                ],
                costo_referencia=_texto(precio.costo_referencia) if ver_costos else None,
                tipo_margen=precio.tipo_margen if ver_costos else None,
                valor_margen=_texto(precio.valor_margen) if ver_costos else None,
                precio_calculado=_texto(precio.precio_calculado) if ver_costos else None,
            )
        )
    return respuestas, siguiente


def obtener_borrador(
    organizacion_id: UUID,
    lista_id: UUID,
    sesion: Session,
    *,
    ver_costos: bool,
    limite: int,
    cursor: str | None,
) -> BorradorResponse:
    """El borrador de la lista con sus precios paginados, sus señales y, aparte, los
    productos activos sin precio con su causa. 404 si la lista es ajena o no tiene borrador."""
    _lista_o_404(organizacion_id, lista_id, sesion)
    borrador = repository.obtener_borrador(organizacion_id, lista_id, sesion)
    if borrador is None:
        raise RecursoNoEncontradoError(f"La lista {lista_id} no tiene borrador.")
    precios, siguiente = _precios_de_la_pagina(
        organizacion_id,
        borrador,
        sesion,
        con_senales=True,
        ver_costos=ver_costos,
        limite=limite,
        cursor=cursor,
    )
    sin_precio = precios_service.productos_sin_precio_del_borrador(
        organizacion_id, sesion, lista_id=lista_id
    )
    nombres = catalogo_service.nombres_de_productos(
        organizacion_id, {sin.producto_id for sin in sin_precio}, sesion
    )
    return BorradorResponse(
        version=_version_response(
            borrador, _nombres_de_autores(organizacion_id, [borrador], sesion)
        ),
        precios=precios,
        siguiente_cursor=siguiente,
        productos_sin_precio=[
            ProductoSinPrecioResponse(
                producto_id=sin.producto_id,
                producto_nombre=nombres.get(sin.producto_id),
                causa=sin.causa,
            )
            for sin in sin_precio
        ],
    )


def _versiones_response(
    organizacion_id: UUID, lista_id: UUID, sesion: Session, *, ahora: datetime
) -> list[VersionResponse]:
    """Todas las versiones de la lista con su estado derivado a `ahora` (PRC-03) y el nombre
    de sus autores, de la más nueva a la más antigua."""
    versiones = repository.listar_versiones(organizacion_id, lista_id, sesion)
    derivados = estados_derivados(
        [
            VersionDeLista(
                id=v.id,
                numero=v.numero,
                estado=v.estado,
                vigencia_desde=v.vigencia_desde,
                vigencia_hasta=v.vigencia_hasta,
            )
            for v in versiones
        ],
        ahora,
    )
    nombres = _nombres_de_autores(organizacion_id, versiones, sesion)
    return [_version_response(v, nombres, estado_derivado=derivados[v.id]) for v in versiones]


def listar_versiones(
    organizacion_id: UUID, lista_id: UUID, sesion: Session, *, ahora: datetime
) -> VersionesResponse:
    """Las versiones de una lista, de la más nueva a la más antigua, con su estado almacenado y
    derivado, sus vigencias y sus autores. 404 si la lista es ajena."""
    _lista_o_404(organizacion_id, lista_id, sesion)
    return VersionesResponse(
        items=_versiones_response(organizacion_id, lista_id, sesion, ahora=ahora)
    )


def obtener_version(
    organizacion_id: UUID, lista_id: UUID, version_id: UUID, sesion: Session, *, ahora: datetime
) -> VersionResponse:
    """Una versión de la lista con su estado derivado. 404 si la lista o la versión son ajenas
    o no existen."""
    _lista_o_404(organizacion_id, lista_id, sesion)
    for version in _versiones_response(organizacion_id, lista_id, sesion, ahora=ahora):
        if version.id == version_id:
            return version
    raise RecursoNoEncontradoError(f"La versión {version_id} no existe en la lista {lista_id}.")


def obtener_precios_de_version(
    organizacion_id: UUID,
    lista_id: UUID,
    version_id: UUID,
    sesion: Session,
    *,
    ahora: datetime,
    ver_costos: bool,
    limite: int,
    cursor: str | None,
) -> PreciosDeVersionResponse:
    """Los precios de cualquier versión de la lista -también histórica o anulada- paginados
    por cursor, con la comparación con su versión base. Las señales solo existen en un
    borrador. El costo de referencia, el margen y el precio calculado solo con `ver_costos`
    (D12). 404 si la lista o la versión son ajenas o no existen."""
    version = obtener_version(organizacion_id, lista_id, version_id, sesion, ahora=ahora)
    entidad = repository.obtener_version(organizacion_id, lista_id, version_id, sesion)
    assert entidad is not None  # `obtener_version` ya respondió 404 si no existía
    precios, siguiente = _precios_de_la_pagina(
        organizacion_id,
        entidad,
        sesion,
        con_senales=entidad.estado == "BORRADOR",
        ver_costos=ver_costos,
        limite=limite,
        cursor=cursor,
    )
    return PreciosDeVersionResponse(version=version, precios=precios, siguiente_cursor=siguiente)


def obtener_precios_vigentes(
    organizacion_id: UUID,
    lista_id: UUID,
    sesion: Session,
    *,
    momento: datetime,
    producto_ids: Collection[UUID] | None,
) -> PreciosVigentesResponse:
    """La versión vigente de la lista a `momento` y sus precios (PRC-20): resuelve por
    `precios_service.resolver_precios`. Lista ajena, 404; sin versión vigente,
    `LISTA_SIN_VERSION_VIGENTE`."""
    resuelto = precios_service.resolver_precios(
        organizacion_id, sesion, lista_id=lista_id, momento=momento, producto_ids=producto_ids
    )
    return PreciosVigentesResponse(
        version_id=resuelto.version_id,
        numero=resuelto.numero,
        vigencia_desde=resuelto.vigencia_desde,
        vigencia_hasta=resuelto.vigencia_hasta,
        precios=[
            PrecioVigenteResponse(
                producto_id=producto_id,
                precio_final=str(precio.precio_final),
                unidades_referencia=precio.unidades_referencia,
            )
            for producto_id, precio in resuelto.precios.items()
        ],
        productos_sin_precio=list(resuelto.productos_sin_precio),
    )


def obtener_lista_predeterminada(
    organizacion_id: UUID, sesion: Session
) -> ListaPredeterminadaResponse:
    """La lista predeterminada de la organización con su nombre y si está activa; todo en nulo
    si la organización no definió una (`01` §4, D11)."""
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    lista_id = None if configuracion is None else configuracion.lista_precio_default_id
    if lista_id is None:
        return ListaPredeterminadaResponse(lista_id=None, lista_nombre=None, activa=None)
    lista = _lista_o_404(organizacion_id, lista_id, sesion)
    return ListaPredeterminadaResponse(
        lista_id=lista.id, lista_nombre=lista.nombre, activa=lista.activo
    )
