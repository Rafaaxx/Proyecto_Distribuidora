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
from app.commands.credenciales import CredencialDePin
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
    AlcanceDeReglaResponse,
    AutorizadorContextoResponse,
    ContextoDeVentaResponse,
    CreditoContextoResponse,
    CreditoParaVenderResponse,
    DescuentoManualContextoResponse,
    DescuentosAplicablesResponse,
    MotivoContextoResponse,
    NumeracionResponse,
    PaginaVentas,
    PreciosParaVenderResponse,
    PresentacionParaVenderResponse,
    ProductoParaVenderResponse,
    ReglaAplicableResponse,
    VentaCobranzaResponse,
    VentaConfirmarRequest,
    VentaConfirmarResponse,
    VentaCreditoResponse,
    VentaDetalleResponse,
    VentaLineaDescuentoResponse,
    VentaLineaResponse,
    VentaMotivoResponse,
    VentaObservacionResponse,
    VentaResumenResponse,
    VersionElegibleResponse,
    VersionesElegiblesResponse,
    armar_contenido_de_venta,
)

PERMISO_VENDER = "VENDER"
PERMISO_ANULAR_VENTA = "ANULAR_VENTA"
PERMISO_USAR_LISTA_ANTERIOR = "USAR_LISTA_ANTERIOR"
PERMISO_VER_COSTOS = "VER_COSTOS"
_OPERACION_TIPO = "VENTA"

router = APIRouter(prefix="/ventas", tags=["ventas"])


@router.post("", response_model=VentaConfirmarResponse, status_code=201)
def confirmar_venta(
    datos: VentaConfirmarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
) -> VentaConfirmarResponse:
    """`POST /ventas` (VTA-12). El resultado sale de `comando.resultado`, no de una relectura
    (INV-06); los importes viajan y vuelven como string (INV-03)."""
    reloj = SystemClock()
    contenido = cast(dict[str, ContenidoComando], armar_contenido_de_venta(datos))
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
    # Las credenciales (PIN) no entran al contenido ni a la huella: llegan al handler por
    # clausura y no se persisten ni se registran (change 18b, D2).
    credenciales = tuple(
        CredencialDePin(autorizador_id=c.autorizador_id, pin=c.pin) for c in datos.credenciales
    )
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = cast(
        ventas_commands.VentaConfirmarContenidoV1,
        registro.validar_contenido(handler_registrado, sobre.contenido),
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandlerConAuditoria:
        return ventas_commands.manejar_venta_confirmar(
            sobre,
            contenido_validado,
            sesion=sesion_protegida,
            reloj=reloj,
            credenciales=credenciales,
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
                categoria_id=item.producto.categoria_id,
                marca_id=item.producto.marca_id,
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


@router.get("/contexto", response_model=ContextoDeVentaResponse)
def obtener_contexto_de_venta(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ContextoDeVentaResponse:
    """Change 18b, D15 (SYN-11, DSC-06): el tope de descuento, los permisos, los motivos activos y
    los autorizadores de quien vende. `VENDER`. Sin parámetros: el usuario sale del token. Hasta el
    bootstrap del change 21, que reutiliza `ventas_queries.contexto_de_venta`."""
    datos = ventas_queries.contexto_de_venta(
        contexto.organizacion_id, sesion, usuario_id=contexto.usuario_id
    )
    manual = datos.descuento_manual
    return ContextoDeVentaResponse(
        descuento_manual=DescuentoManualContextoResponse(
            habilitado=manual.habilitado,
            motivo_obligatorio=manual.motivo_obligatorio,
            tiene_permiso=manual.tiene_permiso,
            tope=None if manual.tope is None else str(manual.tope),
            puede_autorizar=manual.puede_autorizar,
        ),
        credito=CreditoContextoResponse(puede_superar=datos.puede_superar_credito),
        motivos=[MotivoContextoResponse(id=m.id, nombre=m.nombre) for m in datos.motivos],
        autorizadores=[
            AutorizadorContextoResponse(
                id=a.usuario_id,
                nombre=a.nombre,
                puede_autorizar_descuento=a.puede_autorizar_descuento,
                puede_superar_credito=a.puede_superar_credito,
            )
            for a in datos.autorizadores
        ],
    )


@router.get("/descuentos-aplicables", response_model=DescuentosAplicablesResponse)
def obtener_descuentos_aplicables(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
) -> DescuentosAplicablesResponse:
    """Change 18b, apply del 2026-10-23 (DSC-01, DSC-05, ADR-050): las reglas activas y vigentes
    ahora, con su nombre y sus alcances, para que la pantalla de venta muestre los descuentos
    automáticos antes de confirmar. `VENDER` (no `GESTIONAR_DESCUENTOS`, DSC-04). Sin parámetros:
    la organización sale del token."""
    reglas = ventas_queries.descuentos_aplicables(
        contexto.organizacion_id, sesion, ahora=SystemClock().now()
    )
    return DescuentosAplicablesResponse(
        items=[
            ReglaAplicableResponse(
                id=UUID(item.regla.id),
                nombre=item.nombre,
                tipo=item.regla.tipo,
                medida=item.regla.medida,
                operador=item.regla.operador,
                umbral=str(item.regla.umbral),
                accion_tipo=item.regla.accion_tipo,
                accion_porcentaje=_texto_o_nulo(item.regla.accion_porcentaje),
                accion_importe=_texto_o_nulo(item.regla.accion_importe),
                acumulable=item.regla.acumulable,
                prioridad=item.regla.prioridad,
                alcances=[
                    AlcanceDeReglaResponse(tipo=a.tipo, entidad_id=UUID(a.entidad_id))
                    for a in item.regla.alcances
                ],
            )
            for item in reglas
        ]
    )


@router.get("/credito", response_model=CreditoParaVenderResponse)
def obtener_credito_para_vender(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VENDER))],
    sesion: Annotated[Session, Depends(get_session)],
    cliente_id: UUID,
) -> CreditoParaVenderResponse:
    """Change 18b, D16 (CRE-01, `01` §19): límite, saldo, disponible, política y tolerancia
    aplicables del cliente, con la herencia de la organización resuelta. `VENDER`. Cliente de otra
    organización o inexistente, 404."""
    credito = ventas_queries.credito_para_vender(
        contexto.organizacion_id, sesion, cliente_id=cliente_id
    )
    return CreditoParaVenderResponse(
        cliente_id=credito.cliente_id,
        limite=None if credito.limite is None else str(credito.limite),
        saldo=str(credito.saldo),
        disponible=None if credito.disponible is None else str(credito.disponible),
        politica=credito.politica,
        tolerancia_tipo=credito.tolerancia_tipo,
        tolerancia_valor=None
        if credito.tolerancia_valor is None
        else str(credito.tolerancia_valor),
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
                descuentos=[
                    VentaLineaDescuentoResponse(
                        origen=d.descuento.origen,
                        regla_id=d.descuento.regla_id,
                        regla_nombre=d.regla_nombre,
                        porcentaje=_texto_o_nulo(d.descuento.porcentaje),
                        importe=str(d.descuento.importe),
                        motivo_id=d.descuento.motivo_id,
                        motivo_nombre=d.motivo_nombre,
                        autorizador_id=d.descuento.autorizador_id,
                        autorizador_nombre=d.autorizador_nombre,
                    )
                    for d in item.descuentos
                ],
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
        credito=(
            None
            if detalle.credito is None
            else VentaCreditoResponse(
                limite=_texto_o_nulo(detalle.credito.limite),
                saldo_considerado=_texto_o_nulo(detalle.credito.saldo_considerado),
                disponible=_texto_o_nulo(detalle.credito.disponible),
                exceso=_texto_o_nulo(detalle.credito.exceso),
                politica=detalle.credito.politica,
                resolucion=detalle.credito.resolucion,
                autorizador_id=detalle.credito.autorizador_id,
                autorizador_nombre=detalle.credito.autorizador_nombre,
            )
        ),
    )
