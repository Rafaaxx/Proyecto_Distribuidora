"""Casos de uso de lectura de `ventas` (`02` §5.1; change 18a, tareas 9.1 y 9.2, `design.md` D19,
tabla de permisos aprobada por el usuario el 2026-10-20).

Solo lee: ninguna función escribe ni bloquea (los candados de la confirmación son de
`service.py`). Todas reciben `organizacion_id` primero y lo usan para filtrar (INV-21): una venta
de otra organización es inexistente (`RecursoNoEncontradoError`, 404). Los nombres de cliente,
usuario, ubicación, producto, presentación, lista y motivo se resuelven por el `service.py` de su
módulo (`CLAUDE.md` §4), por lote. El costo de cada línea solo sale si quien
llama dice `con_costos` (el permiso `VER_COSTOS` lo decide la API); `precios_para_vender` NUNCA
lleva costos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import PermisoRequeridoError
from app.modules.catalogo import service as catalogo_service
from app.modules.clientes import service as clientes_service
from app.modules.cobranzas import service as cobranzas_service
from app.modules.configuracion import service as configuracion_service
from app.modules.identidad import service as identidad_service
from app.modules.precios import service as precios_service
from app.modules.stock import service as stock_service
from app.modules.ventas import repository
from app.modules.ventas.domain.consultas import (
    acotar_limite,
    codificar_cursor_de_producto,
    decodificar_cursor_de_producto,
    rango_de_instantes,
)
from app.modules.ventas.domain.errores import (
    RecursoNoEncontradoError,
    VersionNoPermitidaError,
)
from app.modules.ventas.domain.numero import armar_numero
from app.modules.ventas.models import Venta, VentaLinea


@dataclass(frozen=True)
class VentaDelListado:
    """Una venta con los nombres que la pantalla muestra. El nombre es `None` si la referencia ya
    no se puede resolver."""

    venta: Venta
    cliente_nombre: str | None
    usuario_nombre: str | None
    ubicacion_nombre: str | None


@dataclass(frozen=True)
class PaginaDeVentas:
    items: list[VentaDelListado]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class LineaDelDetalle:
    """Una línea congelada con los nombres de su producto y presentación. `costo_unitario`,
    `costo_total` son `None` sin `con_costos` (VTA-05, `01` §19) y también cuando la línea se
    vendió sin costo (D10). No hay utilidad: es de los reportes (REP-04, ajuste del 2026-10-20)."""

    linea: VentaLinea
    producto_nombre: str | None
    presentacion_nombre: str | None
    costo_unitario: Decimal | None
    costo_total: Decimal | None


@dataclass(frozen=True)
class MotivoDeLista:
    motivo_id: UUID
    nombre: str | None


@dataclass(frozen=True)
class DetalleDeVenta:
    resumen: VentaDelListado
    lista_nombre: str | None
    version_numero: int | None
    motivo_lista: MotivoDeLista | None
    cobranza: cobranzas_service.CobranzaDeVenta | None
    lineas: list[LineaDelDetalle]


def _con_nombres(
    organizacion_id: UUID, sesion: Session, ventas: list[Venta]
) -> list[VentaDelListado]:
    clientes = clientes_service.nombres_de_clientes(
        organizacion_id, {v.cliente_id for v in ventas}, sesion
    )
    usuarios = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, {v.usuario_id for v in ventas}, sesion
    )
    ubicaciones = stock_service.nombres_de_ubicaciones(
        organizacion_id, sesion, {v.ubicacion_id for v in ventas}
    )
    return [
        VentaDelListado(
            venta=v,
            cliente_nombre=clientes.get(v.cliente_id),
            usuario_nombre=usuarios.get(v.usuario_id),
            ubicacion_nombre=ubicaciones.get(v.ubicacion_id),
        )
        for v in ventas
    ]


def listar_ventas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cliente_id: UUID | None = None,
    usuario_id: UUID | None = None,
    jornada_id: UUID | None = None,
    ubicacion_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PaginaDeVentas:
    """Ventas de la organización, de la más reciente a la más vieja, paginadas por cursor.

    Filtrable por cliente, usuario, jornada, ubicación y rango de fechas (de negocio, en la zona
    de la organización, `hasta` inclusivo: TR-04). `desde` posterior a `hasta` es
    `RANGO_DE_FECHAS_INVALIDO` y un cursor ilegible es `CURSOR_INVALIDO`. `limite` va de 1 a 200
    (la API responde 422 fuera de rango; acá solo se acota por seguridad)."""
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    if organizacion is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    inicio, fin = rango_de_instantes(desde, hasta, organizacion.zona_horaria)
    filas, cursor_siguiente = repository.listar_ventas_paginado(
        organizacion_id,
        sesion,
        limite=acotar_limite(limite),
        cursor=cursor,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        jornada_id=jornada_id,
        ubicacion_id=ubicacion_id,
        desde=inicio,
        hasta=fin,
    )
    return PaginaDeVentas(
        items=_con_nombres(organizacion_id, sesion, filas), cursor_siguiente=cursor_siguiente
    )


def _linea_del_detalle(
    linea: VentaLinea,
    productos: dict[UUID, str],
    presentaciones: dict[UUID, str],
    *,
    con_costos: bool,
) -> LineaDelDetalle:
    return LineaDelDetalle(
        linea=linea,
        producto_nombre=productos.get(linea.producto_id),
        presentacion_nombre=presentaciones.get(linea.presentacion_id),
        costo_unitario=linea.costo_unitario if con_costos else None,
        costo_total=linea.costo_total if con_costos else None,
    )


def obtener_detalle_de_venta(
    organizacion_id: UUID, venta_id: UUID, sesion: Session, *, con_costos: bool
) -> DetalleDeVenta:
    """La venta tal como quedó congelada: cabecera con nombres, lista y versión (con el motivo si
    se eligió otra), líneas en su presentación, cobranza enlazada. 404 si no existe en la
    organización (INV-21). Las observaciones de sincronización las agrega quien expone el
    detalle. El costo de cada línea solo con `con_costos` (VTA-05)."""
    venta = repository.obtener_venta(organizacion_id, venta_id, sesion)
    if venta is None:
        raise RecursoNoEncontradoError(f"La venta {venta_id} no existe en esta organización.")
    lineas = repository.listar_lineas_de_venta(organizacion_id, venta.id, sesion)
    productos = catalogo_service.nombres_de_productos(
        organizacion_id, {linea.producto_id for linea in lineas}, sesion
    )
    presentaciones = catalogo_service.nombres_de_presentaciones(
        organizacion_id, {linea.presentacion_id for linea in lineas}, sesion
    )
    version = precios_service.datos_de_versiones(
        organizacion_id, sesion, [venta.lista_version_id]
    ).get(venta.lista_version_id)
    motivo = (
        None
        if venta.motivo_lista_id is None
        else configuracion_service.obtener_motivo(organizacion_id, venta.motivo_lista_id, sesion)
    )
    return DetalleDeVenta(
        resumen=_con_nombres(organizacion_id, sesion, [venta])[0],
        lista_nombre=None if version is None else version.lista_nombre,
        version_numero=None if version is None else version.numero,
        motivo_lista=(
            None
            if venta.motivo_lista_id is None
            else MotivoDeLista(venta.motivo_lista_id, None if motivo is None else motivo.nombre)
        ),
        cobranza=cobranzas_service.cobranza_de_venta(organizacion_id, sesion, venta_id=venta.id),
        lineas=[
            _linea_del_detalle(linea, productos, presentaciones, con_costos=con_costos)
            for linea in lineas
        ],
    )


# --- lecturas de apoyo a la pantalla de venta (tarea 9.2) -------------------------------------


@dataclass(frozen=True)
class NumeracionDelDispositivo:
    """Prefijo, último correlativo y el número que sigue (D4)."""

    prefijo: str
    ultimo_correlativo: int
    siguiente_numero: str


def numeracion_del_dispositivo(
    organizacion_id: UUID, sesion: Session, *, dispositivo_id: UUID
) -> NumeracionDelDispositivo:
    """La numeración del dispositivo de la sesión (VTA-06, D4). Un dispositivo que no existe en
    la organización responde como inexistente (INV-21)."""
    numeracion = identidad_service.obtener_numeracion_de_dispositivo(
        organizacion_id, sesion, dispositivo_id=dispositivo_id
    )
    if numeracion is None:
        raise RecursoNoEncontradoError(f"El dispositivo {dispositivo_id} no existe.")
    return NumeracionDelDispositivo(
        prefijo=numeracion.prefijo,
        ultimo_correlativo=numeracion.ultimo_correlativo,
        siguiente_numero=armar_numero(numeracion.prefijo, numeracion.ultimo_correlativo + 1),
    )


def versiones_elegibles(
    organizacion_id: UUID, sesion: Session, *, lista_id: UUID, momento: datetime
) -> tuple[precios_service.VersionElegible, ...]:
    """Las versiones que una venta puede elegir en la lista a `momento` (PRC-21, D6)."""
    return precios_service.versiones_elegibles(
        organizacion_id, sesion, lista_id=lista_id, momento=momento
    )


@dataclass(frozen=True)
class ItemDePrecio:
    """Un producto activo con el precio de la versión (o sin precio), sus presentaciones de venta
    y, si se pidió una ubicación, su stock en unidad base. Sin costos ni márgenes."""

    producto: catalogo_service.ProductoParaVender
    precio_referencia: Decimal | None
    unidades_referencia: int | None
    stock_base: int | None


@dataclass(frozen=True)
class PreciosParaVender:
    lista_id: UUID
    lista_nombre: str
    version_id: UUID
    version_numero: int
    ubicacion_id: UUID | None
    items: list[ItemDePrecio]
    cursor_siguiente: str | None


def _exigir_usar_lista_anterior(permitido: bool) -> None:
    """D6, mínimo privilegio: elegir otra lista o una versión que no es la vigente exige
    `USAR_LISTA_ANTERIOR` (403 `PERMISO_REQUERIDO`, como el resto de los permisos por parámetro)."""
    if not permitido:
        raise PermisoRequeridoError(
            "Falta el permiso USAR_LISTA_ANTERIOR para consultar otra lista o una versión que "
            "no es la vigente (PRC-21, D6)."
        )


def precios_para_vender(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ahora: datetime,
    cliente_id: UUID | None,
    lista_id: UUID | None,
    version_id: UUID | None,
    ubicacion_id: UUID | None,
    puede_usar_lista_anterior: bool,
    texto: str | None = None,
    producto_id: UUID | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PreciosParaVender:
    """Lo que la pantalla de venta necesita (PRC-20, PRC-21, PRC-22, D7, D19): una página de los
    productos activos con el precio de la versión aplicable (la elegida, o la vigente de la lista
    elegida, o la de la lista del cliente o la predeterminada), sus presentaciones de venta y,
    con `ubicacion_id`, el stock de esa ubicación; los productos sin precio, marcados (`precio`
    nulo: nunca se les inventa uno, PRC-10). NUNCA costos.

    Busca (`texto`: nombre o código), pagina por cursor de código y trae un producto
    (`producto_id`) en SQL; el precio y el stock se leen solo para la página (ajuste del
    2026-10-20). Sin `puede_usar_lista_anterior` solo se consulta la versión vigente de la lista
    que la venta usaría por defecto para el cliente: otra lista u otra versión es
    `PERMISO_REQUERIDO` (403, D6). Una ubicación ajena es 404 y una inactiva `UBICACION_INACTIVA`
    (409); un cliente o una lista ajenos, 404; una versión programada, anulada o de otra lista,
    `VERSION_NO_PERMITIDA` (409), igual que en la confirmación (PRC-21)."""
    despues_de_codigo = None if cursor is None else decodificar_cursor_de_producto(cursor)

    lista_asignada_id: UUID | None = None
    if cliente_id is not None:
        cliente = clientes_service.obtener_cliente_por_id(organizacion_id, cliente_id, sesion)
        if cliente is None:
            raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe.")
        lista_asignada_id = cliente.lista_precio_id
    elegida_id = lista_id
    if elegida_id is None or not puede_usar_lista_anterior:
        aplicable_id = precios_service.resolver_lista_aplicable(
            organizacion_id, sesion, lista_asignada_id=lista_asignada_id
        ).lista_id
        if elegida_id is not None and elegida_id != aplicable_id:
            _exigir_usar_lista_anterior(puede_usar_lista_anterior)
        elegida_id = aplicable_id
    precios_service.validar_lista_asignable(organizacion_id, sesion, lista_id=elegida_id)

    pagina = catalogo_service.productos_activos_para_vender(
        organizacion_id,
        sesion,
        limite=acotar_limite(limite),
        texto=texto,
        producto_id=producto_id,
        despues_de_codigo=despues_de_codigo,
    )
    ids_de_la_pagina = [producto.producto_id for producto in pagina.items]

    stock = (
        None
        if ubicacion_id is None
        else stock_service.stock_de_ubicacion_para_vender(
            organizacion_id, sesion, ubicacion_id=ubicacion_id, producto_ids=ids_de_la_pagina
        )
    )

    if version_id is None or not puede_usar_lista_anterior:
        vigentes = precios_service.resolver_precios(
            organizacion_id,
            sesion,
            lista_id=elegida_id,
            momento=ahora,
            producto_ids=ids_de_la_pagina,
        )
        if version_id is not None and version_id != vigentes.version_id:
            _exigir_usar_lista_anterior(puede_usar_lista_anterior)
        version_resuelta, precios = vigentes.version_id, vigentes.precios
    else:
        elegida = precios_service.resolver_precios_de_version(
            organizacion_id, sesion, version_id=version_id, producto_ids=ids_de_la_pagina
        )
        elegibles = {
            version.version_id
            for version in precios_service.versiones_elegibles(
                organizacion_id, sesion, lista_id=elegida_id, momento=ahora
            )
        }
        if elegida.lista_id != elegida_id or elegida.version_id not in elegibles:
            raise VersionNoPermitidaError(
                "La versión elegida no se puede usar: es programada, está anulada o es de otra "
                "lista (PRC-21)."
            )
        version_resuelta, precios = elegida.version_id, elegida.precios
    datos = precios_service.datos_de_versiones(organizacion_id, sesion, [version_resuelta])[
        version_resuelta
    ]

    items = [
        ItemDePrecio(
            producto=producto,
            precio_referencia=None if precio is None else precio.precio_final,
            unidades_referencia=None if precio is None else precio.unidades_referencia,
            stock_base=None if stock is None else stock.get(producto.producto_id, 0),
        )
        for producto in pagina.items
        for precio in [precios.get(producto.producto_id)]
    ]
    return PreciosParaVender(
        lista_id=datos.lista_id,
        lista_nombre=datos.lista_nombre,
        version_id=version_resuelta,
        version_numero=datos.numero,
        ubicacion_id=ubicacion_id,
        items=items,
        cursor_siguiente=(
            codificar_cursor_de_producto(pagina.items[-1].codigo) if pagina.hay_mas else None
        ),
    )
