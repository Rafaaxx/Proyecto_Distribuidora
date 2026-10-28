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

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import PermisoRequeridoError
from app.core.money import redondear_importe
from app.modules.catalogo import service as catalogo_service
from app.modules.clientes import service as clientes_service
from app.modules.cobranzas import service as cobranzas_service
from app.modules.configuracion import service as configuracion_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.descuentos import service as descuentos_service
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
from app.modules.ventas.domain.nota import saldo_de_la_nota
from app.modules.ventas.domain.numero import armar_numero
from app.modules.ventas.models import Venta, VentaLinea, VentaLineaDescuento


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
class DescuentoDelDetalle:
    """Un descuento congelado de una línea (DSC-08) con los nombres de su regla, su motivo y su
    autorizador (nulos si la referencia ya no se puede resolver o no aplica)."""

    descuento: VentaLineaDescuento
    regla_nombre: str | None
    motivo_nombre: str | None
    autorizador_nombre: str | None


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
    descuentos: list[DescuentoDelDetalle] = field(default_factory=list)


@dataclass(frozen=True)
class MotivoDeLista:
    motivo_id: UUID
    nombre: str | None


@dataclass(frozen=True)
class CreditoDelDetalle:
    """El snapshot de crédito de la venta (CRE-10) con el nombre de quien autorizó."""

    limite: Decimal | None
    saldo_considerado: Decimal | None
    disponible: Decimal | None
    exceso: Decimal | None
    politica: str | None
    resolucion: str
    autorizador_id: UUID | None
    autorizador_nombre: str | None


@dataclass(frozen=True)
class AnulacionDelDetalle:
    """El bloque de anulación del detalle (change 19, D14): momento, usuario y motivo con sus
    nombres (nulos si la referencia ya no se puede resolver), observación y si se devolvió el
    dinero (`None` si la venta no tenía cobro)."""

    anulada_en: datetime
    usuario_id: UUID
    usuario_nombre: str | None
    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    devuelve_dinero: bool | None


@dataclass(frozen=True)
class DetalleDeVenta:
    resumen: VentaDelListado
    lista_nombre: str | None
    version_numero: int | None
    motivo_lista: MotivoDeLista | None
    cobranza: cobranzas_service.CobranzaDeVenta | None
    lineas: list[LineaDelDetalle]
    credito: CreditoDelDetalle | None = None
    """`None` en una venta anterior al change 18b (sin snapshot de crédito)."""
    anulacion: AnulacionDelDetalle | None = None
    """`None` si la venta no está anulada (change 19)."""
    cliente_es_consumidor_final: bool = False
    """Marca del cliente de la venta (change 19, D16): la pantalla de anulación fija la devolución
    del consumidor final y quien solo tiene `ANULAR_VENTA` no lee `/clientes`."""


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
    estado: str | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PaginaDeVentas:
    """Ventas de la organización, de la más reciente a la más vieja, paginadas por cursor.

    Filtrable por cliente, usuario, jornada, ubicación, estado (change 19, D14: `CONFIRMADA` o
    `ANULADA`, lo valida la API) y rango de fechas (de negocio, en la zona
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
        estado=estado,
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
    descuentos: list[DescuentoDelDetalle],
) -> LineaDelDetalle:
    return LineaDelDetalle(
        linea=linea,
        producto_nombre=productos.get(linea.producto_id),
        presentacion_nombre=presentaciones.get(linea.presentacion_id),
        costo_unitario=linea.costo_unitario if con_costos else None,
        costo_total=linea.costo_total if con_costos else None,
        descuentos=descuentos,
    )


def _anulacion_del_detalle(
    organizacion_id: UUID, sesion: Session, venta_id: UUID
) -> AnulacionDelDetalle | None:
    anulacion = repository.obtener_anulacion_de_venta(organizacion_id, venta_id, sesion)
    if anulacion is None:
        return None
    usuarios = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, {anulacion.usuario_id}, sesion
    )
    motivo = configuracion_service.obtener_motivo(organizacion_id, anulacion.motivo_id, sesion)
    return AnulacionDelDetalle(
        anulada_en=anulacion.occurred_at,
        usuario_id=anulacion.usuario_id,
        usuario_nombre=usuarios.get(anulacion.usuario_id),
        motivo_id=anulacion.motivo_id,
        motivo_nombre=None if motivo is None else motivo.nombre,
        observacion=anulacion.observacion,
        devuelve_dinero=anulacion.devuelve_dinero,
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
    descuentos = repository.listar_descuentos_de_venta(organizacion_id, venta.id, sesion)
    reglas = descuentos_service.nombres_de_reglas(
        organizacion_id, {d.regla_id for d in descuentos if d.regla_id is not None}, sesion
    )
    motivos_de_descuento = {
        motivo_id: configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
        for motivo_id in {d.motivo_id for d in descuentos if d.motivo_id is not None}
    }
    autorizadores_ids = {d.autorizador_id for d in descuentos if d.autorizador_id is not None}
    if venta.credito_autorizador_id is not None:
        autorizadores_ids.add(venta.credito_autorizador_id)
    autorizadores = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, autorizadores_ids, sesion
    )
    por_linea: dict[UUID, list[DescuentoDelDetalle]] = {}
    for descuento in descuentos:
        motivo_del_descuento = (
            None if descuento.motivo_id is None else motivos_de_descuento[descuento.motivo_id]
        )
        por_linea.setdefault(descuento.venta_linea_id, []).append(
            DescuentoDelDetalle(
                descuento=descuento,
                regla_nombre=None if descuento.regla_id is None else reglas.get(descuento.regla_id),
                motivo_nombre=None if motivo_del_descuento is None else motivo_del_descuento.nombre,
                autorizador_nombre=(
                    None
                    if descuento.autorizador_id is None
                    else autorizadores.get(descuento.autorizador_id)
                ),
            )
        )
    credito = (
        None
        if venta.credito_resolucion is None
        else CreditoDelDetalle(
            limite=venta.credito_limite,
            saldo_considerado=venta.credito_saldo_considerado,
            disponible=venta.credito_disponible,
            exceso=venta.credito_exceso,
            politica=venta.credito_politica,
            resolucion=venta.credito_resolucion,
            autorizador_id=venta.credito_autorizador_id,
            autorizador_nombre=(
                None
                if venta.credito_autorizador_id is None
                else autorizadores.get(venta.credito_autorizador_id)
            ),
        )
    )
    cliente = clientes_service.obtener_cliente_por_id(organizacion_id, venta.cliente_id, sesion)
    return DetalleDeVenta(
        anulacion=_anulacion_del_detalle(organizacion_id, sesion, venta.id),
        cliente_es_consumidor_final=cliente is not None and cliente.es_consumidor_final,
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
            _linea_del_detalle(
                linea,
                productos,
                presentaciones,
                con_costos=con_costos,
                descuentos=por_linea.get(linea.id, []),
            )
            for linea in lineas
        ],
        credito=credito,
    )


@dataclass(frozen=True)
class OrganizacionDeLaNota:
    nombre: str
    cuit: str | None
    domicilio: str | None
    telefono: str | None


@dataclass(frozen=True)
class ClienteDeLaNota:
    nombre: str
    razon_social: str | None
    documento_tipo: str | None
    documento_numero: str | None
    direccion: str
    es_consumidor_final: bool


@dataclass(frozen=True)
class LineaDeLaNota:
    """Una línea congelada tal como la imprime la nota: sin costos (D2)."""

    linea: VentaLinea
    producto_nombre: str | None
    presentacion_nombre: str | None


@dataclass(frozen=True)
class CobranzaDeLaNota:
    importe: Decimal
    estado: str
    medios: list[cobranzas_service.MedioDeCobranza]


@dataclass(frozen=True)
class NotaDeVenta:
    """Todo lo que la nota de venta imprime (change 20, D2), en una sola lectura. Los valores de
    la venta son los congelados (INV-10); nunca se recalcula ni se rechaza por modo (D14)."""

    venta: Venta
    organizacion: OrganizacionDeLaNota
    zona_horaria: str
    muestra_saldo: bool
    cliente: ClienteDeLaNota
    vendedor_nombre: str | None
    lineas: list[LineaDeLaNota]
    cobranza: CobranzaDeLaNota | None
    saldo_resultante: Decimal | None
    anulacion: AnulacionDelDetalle | None


def obtener_nota_de_venta(organizacion_id: UUID, venta_id: UUID, sesion: Session) -> NotaDeVenta:
    """Los datos de la nota de venta de `venta_id` (VTA-13, D2): la organización con su domicilio
    y teléfono, el cliente, las líneas congeladas en su orden, la cobranza con sus medios, el
    saldo resultante (D4) y la anulación (D5). 404 si la venta no existe en la organización
    (INV-21, SEG-07). Los datos ajenos se leen por el `service.py` de su módulo."""
    venta = repository.obtener_venta(organizacion_id, venta_id, sesion)
    if venta is None:
        raise RecursoNoEncontradoError(f"La venta {venta_id} no existe en esta organización.")
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    cliente = clientes_service.obtener_cliente_por_id(organizacion_id, venta.cliente_id, sesion)
    if organizacion is None or configuracion is None or cliente is None:
        raise RecursoNoEncontradoError(f"La venta {venta_id} no existe en esta organización.")

    lineas = repository.listar_lineas_de_venta(organizacion_id, venta.id, sesion)
    productos = catalogo_service.nombres_de_productos(
        organizacion_id, {linea.producto_id for linea in lineas}, sesion
    )
    presentaciones = catalogo_service.nombres_de_presentaciones(
        organizacion_id, {linea.presentacion_id for linea in lineas}, sesion
    )
    usuarios = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, {venta.usuario_id}, sesion
    )
    cobranza_de_venta = cobranzas_service.cobranza_de_venta(
        organizacion_id, sesion, venta_id=venta.id
    )
    cobranza = (
        None
        if cobranza_de_venta is None
        else CobranzaDeLaNota(
            importe=cobranza_de_venta.importe,
            estado=cobranza_de_venta.estado,
            medios=cobranzas_service.medios_de_cobranza(
                organizacion_id, sesion, cobranza_id=cobranza_de_venta.cobranza_id
            ),
        )
    )
    cobrado = Decimal("0.00") if cobranza is None else cobranza.importe
    return NotaDeVenta(
        venta=venta,
        organizacion=OrganizacionDeLaNota(
            nombre=organizacion.nombre,
            cuit=organizacion.cuit,
            domicilio=configuracion.nota_venta_domicilio,
            telefono=configuracion.nota_venta_telefono,
        ),
        zona_horaria=organizacion.zona_horaria,
        muestra_saldo=configuracion.nota_venta_muestra_saldo,
        cliente=ClienteDeLaNota(
            nombre=cliente.nombre,
            razon_social=cliente.razon_social,
            documento_tipo=cliente.documento_tipo,
            documento_numero=cliente.documento_numero,
            direccion=cliente.direccion,
            es_consumidor_final=cliente.es_consumidor_final,
        ),
        vendedor_nombre=usuarios.get(venta.usuario_id),
        lineas=[
            LineaDeLaNota(
                linea=linea,
                producto_nombre=productos.get(linea.producto_id),
                presentacion_nombre=presentaciones.get(linea.presentacion_id),
            )
            for linea in lineas
        ],
        cobranza=cobranza,
        saldo_resultante=saldo_de_la_nota(
            configuracion.nota_venta_muestra_saldo,
            cliente.es_consumidor_final,
            venta.estado,
            venta.credito_saldo_considerado,
            venta.total,
            cobrado,
        ),
        anulacion=_anulacion_del_detalle(organizacion_id, sesion, venta.id),
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


# --- Contexto de venta y crédito para vender (change 18b, D15 y D16) ------------------------

_AMBITO_DESCUENTO_MANUAL = "DESCUENTO_MANUAL"
_PERMISO_DESCUENTO_MANUAL = "DESCUENTO_MANUAL"
_PERMISO_AUTORIZAR_DESCUENTO = "AUTORIZAR_DESCUENTO"
_PERMISO_SUPERAR_CREDITO = "SUPERAR_CREDITO"


@dataclass(frozen=True)
class DescuentoManualDelContexto:
    habilitado: bool
    motivo_obligatorio: bool
    tiene_permiso: bool
    tope: Decimal | None
    """Fracción del tope aplicable (el propio si lo tiene, si no el del rol); nulo si el usuario no
    tiene `DESCUENTO_MANUAL`."""
    puede_autorizar: bool


@dataclass(frozen=True)
class MotivoDelContexto:
    id: UUID
    nombre: str


@dataclass(frozen=True)
class ContextoDeVenta:
    """Lo que quien vende necesita antes de armar el pedido (D15, SYN-11). El bootstrap del
    change 21 reutiliza `contexto_de_venta`."""

    descuento_manual: DescuentoManualDelContexto
    puede_superar_credito: bool
    motivos: list[MotivoDelContexto]
    autorizadores: list[identidad_service.AutorizadorDisponible]


def contexto_de_venta(
    organizacion_id: UUID, sesion: Session, *, usuario_id: UUID
) -> ContextoDeVenta:
    """Tope, permisos, motivos activos del ámbito `DESCUENTO_MANUAL` y autorizadores de
    `usuario_id` (DSC-06, SYN-11; `design.md` D15). Solo lee, siempre con los datos vigentes. El
    tope no sale de `GET /yo` ni del token. Un usuario que no existe en la organización no se
    encuentra (INV-21)."""
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    if configuracion is None:
        raise RecursoNoEncontradoError("La organización no tiene configuración.")
    usuario = identidad_service.obtener_datos_para_descuento_manual(
        organizacion_id, usuario_id, sesion
    )
    if usuario is None:
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe.")
    tiene_permiso = _PERMISO_DESCUENTO_MANUAL in usuario.permisos
    tope = (
        (usuario.tope_rol if usuario.tope_propio is None else usuario.tope_propio)
        if tiene_permiso
        else None
    )
    motivos = configuracion_service.listar_motivos_por_ambito(
        organizacion_id, sesion, _AMBITO_DESCUENTO_MANUAL
    )
    return ContextoDeVenta(
        descuento_manual=DescuentoManualDelContexto(
            habilitado=configuracion.descuento_manual_habilitado,
            motivo_obligatorio=configuracion.motivo_obligatorio_descuento is True,
            tiene_permiso=tiene_permiso,
            tope=tope,
            puede_autorizar=_PERMISO_AUTORIZAR_DESCUENTO in usuario.permisos,
        ),
        puede_superar_credito=_PERMISO_SUPERAR_CREDITO in usuario.permisos,
        motivos=sorted(
            (MotivoDelContexto(motivo.id, motivo.nombre) for motivo in motivos),
            key=lambda motivo: (motivo.nombre, motivo.id),
        ),
        autorizadores=identidad_service.listar_autorizadores_disponibles(
            organizacion_id, sesion, excluir_usuario_id=usuario_id
        ),
    )


@dataclass(frozen=True)
class ReglaParaVender:
    """Una regla activa y vigente con su nombre, tal como la muestra la pantalla de venta."""

    nombre: str
    regla: descuentos_service.ReglaAplicable


def descuentos_aplicables(
    organizacion_id: UUID, sesion: Session, *, ahora: datetime
) -> list[ReglaParaVender]:
    """Las reglas `ACTIVA` vigentes en `ahora` con sus alcances y su nombre, por prioridad y
    antigüedad (DSC-01, DSC-05; ADR-050). Es la lectura de quien vende: no pide
    `GESTIONAR_DESCUENTOS` y no expone nada que no sea la regla (la pantalla calcula con la
    gemela del motor y el servidor decide, TR-10). Solo lee; filtra por la organización
    (INV-21)."""
    reglas = descuentos_service.reglas_aplicables(organizacion_id, sesion, ahora)
    nombres = descuentos_service.nombres_de_reglas(
        organizacion_id, {UUID(regla.id) for regla in reglas}, sesion
    )
    return [ReglaParaVender(nombres[UUID(regla.id)], regla) for regla in reglas]


@dataclass(frozen=True)
class CreditoParaVender:
    """El crédito de un cliente visto por quien vende (D16, `01` §19)."""

    cliente_id: UUID
    limite: Decimal | None
    """Nulo = sin control (CRE-01)."""
    saldo: Decimal
    disponible: Decimal | None
    """Límite menos saldo (negativo si el cliente ya está excedido); nulo sin límite."""
    politica: str
    tolerancia_tipo: str | None
    tolerancia_valor: Decimal | None


def credito_para_vender(
    organizacion_id: UUID, sesion: Session, *, cliente_id: UUID
) -> CreditoParaVender:
    """Límite, saldo, disponible, política y tolerancia aplicables de `cliente_id`, con la
    herencia de la organización ya resuelta (CRE-01, CRE-03, CRE-06; `design.md` D16). Es la única
    lectura que expone el disponible y la política aplicable; la pantalla evalúa con la gemela de
    `cre01` y el servidor decide (TR-10). Solo lee. Un cliente que no existe o es de otra
    organización responde como inexistente (INV-21)."""
    datos = clientes_service.resolver_datos_de_credito(organizacion_id, cliente_id, sesion)
    saldo = cuentas_corrientes_service.obtener_saldo(
        organizacion_id, sesion, cuenta_tipo="CLIENTE", entidad_id=cliente_id
    )
    return CreditoParaVender(
        cliente_id=cliente_id,
        limite=datos.limite,
        saldo=saldo,
        disponible=None if datos.limite is None else redondear_importe(datos.limite - saldo),
        politica=datos.politica,
        tolerancia_tipo=datos.tolerancia_tipo,
        tolerancia_valor=datos.tolerancia_valor,
    )
