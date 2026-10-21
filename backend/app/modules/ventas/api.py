"""Endpoints de negocio de `ventas` (change 18a, tarea 7.8; `design.md` D1, D17).

Mismo criterio que `cobranzas/api.py`: la escritura (`POST /ventas`) declara
`requiere_comando_online` (exige `Operation-Id`, SYN-01/TR-07, y el permiso `VENDER` por ruta) y
delega en `sync_service.procesar_comando`, que valida el contenido, reserva la operación, ejecuta
el handler y registra la auditoría. El import de `app.modules.ventas.commands` puebla el registro
de handlers al arrancar la aplicación.

Toda escritura de negocio pasa por el bus: no hay un endpoint que lo esquive (`CLAUDE.md` §4).

Lecturas (change 18a, tareas 9.1 y 9.2, `design.md` D19, tabla aprobada por el usuario el
2026-10-20): `GET /ventas` y `GET /ventas/{id}` con `VENDER` o `ANULAR_VENTA` (todas las de la
organización; el costo de cada línea solo con `VER_COSTOS`); `GET /ventas/precios`
y `GET /ventas/numeracion` con `VENDER`; `GET /ventas/versiones` con `USAR_LISTA_ANTERIOR`.
**Las rutas fijas se declaran ANTES que `/{venta_id}`**: si no, FastAPI intenta interpretar
`precios` como un UUID y responde 422 (mismo criterio que `/proveedores/opciones`).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    requiere_algun_permiso,
    requiere_comando_online,
    requiere_permiso,
)
from app.core.clock import SystemClock
from app.modules.identidad import service as identidad_service
from app.modules.sync import service as sync_service
from app.modules.ventas import commands as ventas_commands
from app.modules.ventas import queries as ventas_queries
from app.modules.ventas.schemas import (
    NumeracionResponse,
    PaginaVentas,
    PreciosParaVenderResponse,
    PresentacionParaVenderResponse,
    ProductoParaVenderResponse,
    VentaCobranzaResponse,
    VentaConfirmarRequest,
    VentaConfirmarResponse,
    VentaDetalleResponse,
    VentaLineaResponse,
    VentaMotivoResponse,
    VentaObservacionResponse,
    VentaResumenResponse,
    VersionElegibleResponse,
    VersionesElegiblesResponse,
)

PERMISO_VENDER = "VENDER"
PERMISO_ANULAR_VENTA = "ANULAR_VENTA"
PERMISO_USAR_LISTA_ANTERIOR = "USAR_LISTA_ANTERIOR"
PERMISO_VER_COSTOS = "VER_COSTOS"
_OPERACION_TIPO = "VENTA"

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _texto(valor: UUID | None) -> str | None:
    return None if valor is None else str(valor)


@router.post("", response_model=VentaConfirmarResponse, status_code=201)
def confirmar_venta(
    datos: VentaConfirmarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
) -> VentaConfirmarResponse:
    """`POST /ventas` (VTA-12). El resultado sale de `comando.resultado`, no de una relectura
    (INV-06); los importes viajan y vuelven como string (INV-03)."""
    reloj = SystemClock()
    cobranza = datos.cobranza
    contenido: dict[str, ContenidoComando] = {
        "venta_id": str(datos.venta_id),
        "numero": datos.numero,
        "cliente_id": str(datos.cliente_id),
        "ubicacion_id": _texto(datos.ubicacion_id),
        "lista_id": _texto(datos.lista_id),
        "lista_version_id": _texto(datos.lista_version_id),
        "motivo_lista_id": _texto(datos.motivo_lista_id),
        "lineas": [
            {
                "linea_id": str(linea.linea_id),
                "producto_id": str(linea.producto_id),
                "presentacion_id": str(linea.presentacion_id),
                "cantidad": linea.cantidad,
                "lista_version_id": str(linea.lista_version_id),
                "precio_referencia": linea.precio_referencia,
                "unidades_referencia": linea.unidades_referencia,
                "importe_bruto": linea.importe_bruto,
            }
            for linea in datos.lineas
        ],
        "total": datos.total,
        "cobranza": (
            None
            if cobranza is None
            else {
                "cobranza_id": str(cobranza.cobranza_id),
                "medios": [
                    {
                        "medio_pago_id": str(medio.medio_pago_id),
                        "importe": medio.importe,
                        "referencia": medio.referencia,
                    }
                    for medio in cobranza.medios
                ],
                "observacion": cobranza.observacion,
            }
        ),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="VENTA_CONFIRMAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = cast(
        ventas_commands.VentaConfirmarContenidoV1,
        registro.validar_contenido(handler_registrado, sobre.contenido),
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandlerConAuditoria:
        return ventas_commands.manejar_venta_confirmar(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = comando.resultado
    assert resultado is not None
    cobranza_id = resultado["cobranza_id"]
    return VentaConfirmarResponse(
        venta_id=UUID(str(resultado["venta_id"])),
        numero=str(resultado["numero"]),
        estado=str(resultado["estado"]),
        total=str(resultado["total"]),
        saldo=str(resultado["saldo"]),
        cobranza_id=None if cobranza_id is None else UUID(str(cobranza_id)),
    )


# --- lecturas (change 18a, tareas 9.1 y 9.2; `design.md` D19) ---------------------------------


def _resumen_de(item: ventas_queries.VentaDelListado) -> VentaResumenResponse:
    venta = item.venta
    return VentaResumenResponse(
        venta_id=venta.id,
        numero=venta.numero,
        occurred_at=venta.occurred_at,
        cliente_id=venta.cliente_id,
        cliente_nombre=item.cliente_nombre,
        usuario_id=venta.usuario_id,
        usuario_nombre=item.usuario_nombre,
        ubicacion_id=venta.ubicacion_id,
        ubicacion_nombre=item.ubicacion_nombre,
        jornada_id=venta.jornada_id,
        total=str(venta.total),
        estado=venta.estado,
        estado_facturacion=venta.estado_facturacion,
        modo_confirmacion=venta.modo_confirmacion,
    )


def _texto_o_nulo(valor: object | None) -> str | None:
    return None if valor is None else str(valor)


@router.get("", response_model=PaginaVentas)
def listar_ventas(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_VENDER, PERMISO_ANULAR_VENTA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    cliente_id: UUID | None = None,
    usuario_id: UUID | None = None,
    jornada_id: UUID | None = None,
    ubicacion_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaVentas:
    """Ventas de la organización de la más reciente a la más vieja, por cursor (D19, aprobada
    por el usuario el 2026-10-20): `VENDER` o `ANULAR_VENTA`, todas las de la organización.
    `desde` y `hasta` son fechas de negocio inclusivas en la zona de la organización (TR-04); un
    `limite` fuera de 1 a 200 es 422, y un rango invertido o un cursor ilegible también, con su
    código."""
    pagina = ventas_queries.listar_ventas(
        contexto.organizacion_id,
        sesion,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
        jornada_id=jornada_id,
        ubicacion_id=ubicacion_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return PaginaVentas(
        items=[_resumen_de(item) for item in pagina.items],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router.get("/precios", response_model=PreciosParaVenderResponse)
def obtener_precios_para_vender(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
    cliente_id: UUID | None = None,
    lista_id: UUID | None = None,
    version_id: UUID | None = None,
    ubicacion_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    producto_id: UUID | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PreciosParaVenderResponse:
    """Lo que la pantalla de venta lee (D19): una página de productos activos con el precio de la
    versión, sus presentaciones de venta y, con `ubicacion_id`, el stock de esa ubicación; los
    productos sin precio, marcados. `VENDER`. NUNCA costos, ni siquiera con `VER_COSTOS`.

    `q` busca en nombre o código sin distinguir mayúsculas; `producto_id` trae uno; `cursor` y
    `limite` (1 a 200, por defecto 50) paginan por código; el precio y el stock se calculan solo
    para la página (ajuste aprobado el 2026-10-20). Sin `USAR_LISTA_ANTERIOR` solo se consulta la
    versión vigente de la lista que la venta usaría para ese cliente: otra lista u otra versión
    es 403 `PERMISO_REQUERIDO` (D6). Una ubicación inactiva es `UBICACION_INACTIVA` (409); lo
    ajeno, 404."""
    permisos = identidad_service.listar_permisos_del_usuario(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    precios = ventas_queries.precios_para_vender(
        contexto.organizacion_id,
        sesion,
        ahora=SystemClock().now(),
        cliente_id=cliente_id,
        lista_id=lista_id,
        version_id=version_id,
        ubicacion_id=ubicacion_id,
        puede_usar_lista_anterior=PERMISO_USAR_LISTA_ANTERIOR in permisos,
        texto=(q or "").strip() or None,
        producto_id=producto_id,
        cursor=cursor,
        limite=limite,
    )
    return PreciosParaVenderResponse(
        lista_id=precios.lista_id,
        lista_nombre=precios.lista_nombre,
        version_id=precios.version_id,
        version_numero=precios.version_numero,
        ubicacion_id=precios.ubicacion_id,
        items=[
            ProductoParaVenderResponse(
                producto_id=item.producto.producto_id,
                codigo=item.producto.codigo,
                nombre=item.producto.nombre,
                precio_referencia=_texto_o_nulo(item.precio_referencia),
                unidades_referencia=item.unidades_referencia,
                sin_precio=item.precio_referencia is None,
                stock_base=item.stock_base,
                presentaciones=[
                    PresentacionParaVenderResponse(
                        presentacion_id=p.presentacion_id,
                        nombre=p.nombre,
                        unidades_base=p.unidades_base,
                        es_referencia=p.es_referencia,
                    )
                    for p in item.producto.presentaciones
                ],
            )
            for item in precios.items
        ],
        cursor_siguiente=precios.cursor_siguiente,
    )


@router.get("/numeracion", response_model=NumeracionResponse)
def obtener_numeracion(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
) -> NumeracionResponse:
    """Prefijo, último correlativo y número que sigue del dispositivo de la sesión (VTA-06, D4).
    `VENDER`. No recibe parámetros: el dispositivo sale del token."""
    numeracion = ventas_queries.numeracion_del_dispositivo(
        contexto.organizacion_id, sesion, dispositivo_id=contexto.dispositivo_id
    )
    return NumeracionResponse(
        prefijo=numeracion.prefijo,
        ultimo_correlativo=numeracion.ultimo_correlativo,
        siguiente_numero=numeracion.siguiente_numero,
    )


@router.get("/versiones", response_model=VersionesElegiblesResponse)
def listar_versiones_elegibles(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_USAR_LISTA_ANTERIOR))
    ],
    sesion: Annotated[Session, Depends(get_session)],
    lista_id: UUID,
) -> VersionesElegiblesResponse:
    """Las versiones de la lista que una venta puede elegir (PRC-21, D6): la vigente y las
    históricas, de la más nueva a la más vieja. `USAR_LISTA_ANTERIOR` (403 sin él). Lista ajena,
    404."""
    versiones = ventas_queries.versiones_elegibles(
        contexto.organizacion_id, sesion, lista_id=lista_id, momento=SystemClock().now()
    )
    return VersionesElegiblesResponse(
        items=[
            VersionElegibleResponse(
                version_id=v.version_id,
                numero=v.numero,
                estado=v.estado,
                vigencia_desde=v.vigencia_desde,
                vigencia_hasta=v.vigencia_hasta,
            )
            for v in versiones
        ]
    )


@router.get("/{venta_id}", response_model=VentaDetalleResponse)
def obtener_venta(
    venta_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_VENDER, PERMISO_ANULAR_VENTA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> VentaDetalleResponse:
    """Detalle de una venta (D19): líneas en su presentación, totales, cobranza enlazada, lista
    y versión con el motivo, y las observaciones de sincronización (SYN-07). `VENDER` o
    `ANULAR_VENTA`; el costo de cada línea solo con `VER_COSTOS` (nulo sin él; no hay utilidad,
    REP-04).
    404 si es de otra organización o no existe (INV-21, SEG-07)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    detalle = ventas_queries.obtener_detalle_de_venta(
        contexto.organizacion_id, venta_id, sesion, con_costos=PERMISO_VER_COSTOS in permisos
    )
    observaciones = sync_service.listar_observaciones_de_operacion(
        contexto.organizacion_id, sesion, operacion_tipo=_OPERACION_TIPO, operacion_id=venta_id
    )
    venta = detalle.resumen.venta
    cobranza = detalle.cobranza
    motivo = detalle.motivo_lista
    return VentaDetalleResponse(
        **_resumen_de(detalle.resumen).model_dump(),
        registered_at=venta.registered_at,
        dispositivo_id=venta.dispositivo_id,
        lista_id=venta.lista_id,
        lista_nombre=detalle.lista_nombre,
        version_id=venta.lista_version_id,
        version_numero=detalle.version_numero,
        motivo_lista=(
            None
            if motivo is None
            else VentaMotivoResponse(motivo_id=motivo.motivo_id, nombre=motivo.nombre)
        ),
        modo_impositivo=venta.modo_impositivo,
        total_neto=str(venta.total_neto),
        total_iva=str(venta.total_iva),
        importe_facturado=str(venta.importe_facturado),
        cobranza=(
            None
            if cobranza is None
            else VentaCobranzaResponse(
                cobranza_id=cobranza.cobranza_id,
                importe=str(cobranza.importe),
                estado=cobranza.estado,
            )
        ),
        lineas=[
            VentaLineaResponse(
                linea_id=item.linea.id,
                orden=item.linea.orden,
                producto_id=item.linea.producto_id,
                producto_nombre=item.producto_nombre,
                presentacion_id=item.linea.presentacion_id,
                presentacion_nombre=item.presentacion_nombre,
                lista_version_id=item.linea.lista_version_id,
                unidades_presentacion=item.linea.unidades_presentacion,
                cantidad=item.linea.cantidad,
                cantidad_base=item.linea.cantidad_base,
                precio_referencia=str(item.linea.precio_referencia),
                unidades_referencia=item.linea.unidades_referencia,
                importe_bruto=str(item.linea.importe_bruto),
                importe_descuento=str(item.linea.importe_descuento),
                importe_neto=str(item.linea.importe_neto),
                alicuota=str(item.linea.alicuota),
                importe_iva=str(item.linea.importe_iva),
                costo_unitario=_texto_o_nulo(item.costo_unitario),
                costo_total=_texto_o_nulo(item.costo_total),
            )
            for item in detalle.lineas
        ],
        observaciones=[
            VentaObservacionResponse(
                codigo=o.codigo,
                estado=o.estado,
                detalle={} if o.detalle is None else dict(o.detalle),
            )
            for o in observaciones
        ],
    )
