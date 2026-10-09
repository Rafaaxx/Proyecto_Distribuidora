"""Endpoints de `stock` (change 09, grupo 7, tareas 7.1 y 7.2; `design.md` D1, D2,
D3, D5, D11).

**Escrituras** (tres, cada una con su ruta DEDICADA, mismo patrón que
`cuentas_corrientes/api.py`): `POST /stock/ubicaciones` (`UBICACION_CREAR`),
`PUT /stock/ubicaciones/{id}` (`UBICACION_MODIFICAR`) y `POST /stock/iniciales`
(`STOCK_INICIAL_REGISTRAR`). El despacho genérico de `POST /sync/comandos` no
ejecuta handlers `ONLINE` (deuda nominada al change 17), así que cada ruta declara
`requiere_comando_online` (exige `Operation-Id`, SYN-01/TR-07) y delega en
`sync_service.procesar_comando`. El permiso se declara en la ruta para el ratchet
(`ADMIN_CONFIGURACION`, D2; `IMPORTAR_DATOS`, D1) y el handler lo vuelve a
comprobar primero (un lote de sincronización llega por otro camino). La respuesta
de un stock inicial sale de `comando.resultado`: un reenvío devuelve lo mismo
(INV-06).

**Lecturas** (tres): `GET /stock/ubicaciones`, `GET /stock/ubicaciones/{id}/saldos`
y `GET /stock/kardex`, con `TRANSFERIR_STOCK` (D3-A: quien mueve stock necesita
verlo). Los campos de costo se OMITEN de la respuesta si el usuario no tiene
`VER_COSTOS` (`response_model_exclude_unset`, ver `schemas.py`). El promedio vigente
por producto NO vive acá sino con su entidad, en
`GET /catalogo/productos/{producto_id}/costo` (enmienda a D3, 2026-09-30).
Un `limite` fuera de 1 a 200 es un error de validación (422), no un recorte
silencioso (ADR-034 punto 6).

`organizacion_id` sale siempre del token (INV-21). Una ubicación o un producto
ajeno o inexistente responde 404 (lo hace el servicio, antes de leer el libro), así
que la respuesta no revela saldos ni movimientos ajenos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
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
from app.modules.stock import commands as stock_commands
from app.modules.stock import queries as stock_queries
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import CostoInvalidoError, RecursoNoEncontradoError
from app.modules.stock.schemas import (
    AjusteAnuladoResponse,
    AjusteAnularRequest,
    AjusteCrearRequest,
    AjusteResponse,
    DetalleDeAjusteResponse,
    DetalleDeTransferenciaResponse,
    KardexResponse,
    PaginaDeAjustesResponse,
    PaginaDeTransferenciasResponse,
    PaginaUbicaciones,
    StockDeUbicacionResponse,
    StockInicialRegistrarRequest,
    StockInicialResponse,
    TransferenciaAnuladaResponse,
    TransferenciaAnularRequest,
    TransferenciaCrearRequest,
    TransferenciaResponse,
    UbicacionCrearRequest,
    UbicacionModificarRequest,
    UbicacionResponse,
    ajuste_anulado_response,
    ajuste_response,
    detalle_de_ajuste_response,
    detalle_de_transferencia_response,
    kardex_response,
    pagina_de_ajustes_response,
    pagina_de_transferencias_response,
    stock_de_ubicacion_response,
)
from app.modules.sync import service as sync_service

PERMISO_UBICACIONES = "ADMIN_CONFIGURACION"
PERMISO_STOCK_INICIAL = "IMPORTAR_DATOS"
PERMISO_LECTURA = "TRANSFERIR_STOCK"
PERMISO_TRANSFERIR = "TRANSFERIR_STOCK"
PERMISO_AJUSTAR = "AJUSTAR_STOCK"
PERMISO_REGISTRAR_COMPRA = "REGISTRAR_COMPRA"  # D18: el formulario de compra lista ubicaciones
PERMISO_VER_COSTOS = "VER_COSTOS"

router = APIRouter(prefix="/stock", tags=["stock"])


def _resultado_de(comando: sync_service.Comando) -> dict[str, object]:
    assert comando.resultado is not None
    return comando.resultado


def _ubicacion_o_404(
    organizacion_id: UUID, ubicacion_id: UUID, sesion: Session
) -> UbicacionResponse:
    ubicacion = stock_service.obtener_ubicacion(organizacion_id, sesion, ubicacion_id)
    if ubicacion is None:
        raise RecursoNoEncontradoError(
            f"La ubicación {ubicacion_id} no existe en esta organización."
        )
    return UbicacionResponse.model_validate(ubicacion)


def _tiene_ver_costos(contexto: ContextoAutenticado, sesion: Session) -> bool:
    permisos = identidad_service.listar_permisos_del_usuario(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    return PERMISO_VER_COSTOS in permisos


# --- escrituras (7.1) --------------------------------------------------------------


@router.post("/ubicaciones", response_model=UbicacionResponse, status_code=201)
def crear_ubicacion(
    datos: UbicacionCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_UBICACIONES))],
    sesion: Annotated[Session, Depends(get_session)],
) -> UbicacionResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "nombre": datos.nombre,
        "tipo": datos.tipo,
        "requiere_toma": datos.requiere_toma,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="UBICACION_CREAR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return stock_commands.manejar_ubicacion_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    ubicacion_id = UUID(str(_resultado_de(comando)["ubicacion_id"]))
    return _ubicacion_o_404(entrada.contexto.organizacion_id, ubicacion_id, sesion)


@router.put("/ubicaciones/{ubicacion_id}", response_model=UbicacionResponse)
def modificar_ubicacion(
    ubicacion_id: UUID,
    datos: UbicacionModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_UBICACIONES))],
    sesion: Annotated[Session, Depends(get_session)],
) -> UbicacionResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "ubicacion_id": str(ubicacion_id),
        "nombre": datos.nombre,
        "tipo": datos.tipo,
        "requiere_toma": datos.requiere_toma,
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="UBICACION_MODIFICAR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return stock_commands.manejar_ubicacion_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return _ubicacion_o_404(entrada.contexto.organizacion_id, ubicacion_id, sesion)


@router.post("/iniciales", response_model=StockInicialResponse, status_code=201)
def registrar_stock_inicial(
    datos: StockInicialRegistrarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_STOCK_INICIAL))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> StockInicialResponse:
    lineas: list[ContenidoComando] = []
    for linea in datos.lineas:
        if isinstance(linea.costo_unitario, float):
            # La huella canónica del comando no admite `float` (INV-03): un número
            # con decimales en el JSON se rechaza acá con el mismo código de dominio
            # que el resto de los costos mal formados, en vez de un error interno.
            raise CostoInvalidoError('El costo debe enviarse como texto, por ejemplo "1000.50".')
        lineas.append(
            {
                "producto_id": str(linea.producto_id),
                "cantidad_base": linea.cantidad_base,
                "costo_unitario": linea.costo_unitario,
            }
        )
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "ubicacion_id": str(datos.ubicacion_id),
        "lineas": lineas,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="STOCK_INICIAL_REGISTRAR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return stock_commands.manejar_stock_inicial_registrar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return StockInicialResponse.model_validate(_resultado_de(comando))


@router.post("/transferencias", response_model=TransferenciaResponse, status_code=201)
def registrar_transferencia(
    datos: TransferenciaCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_TRANSFERIR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> TransferenciaResponse:
    """`STOCK_TRANSFERIR` (change 14, STK-07): mueve stock entre dos ubicaciones como una
    sola operación atómica. 201 con la transferencia, su estado y los saldos resultantes en
    origen y destino; sin costos. Con `PERMITIR_STOCK_NEGATIVO` una salida que no alcanza se
    acepta y la respuesta lista `STOCK_NEGATIVO` en `observaciones`."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "ubicacion_origen_id": str(datos.ubicacion_origen_id),
        "ubicacion_destino_id": str(datos.ubicacion_destino_id),
        "lineas": [
            {"producto_id": str(linea.producto_id), "cantidad_base": linea.cantidad_base}
            for linea in datos.lineas
        ],
        "observacion": datos.observacion,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="STOCK_TRANSFERIR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: object,
    ) -> sync_service.ResultadoHandler | sync_service.ResultadoHandlerConObservaciones:
        return stock_commands.manejar_stock_transferir(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    return TransferenciaResponse.model_validate({**resultado, "id": resultado["transferencia_id"]})


@router.post(
    "/ajustes",
    response_model=AjusteResponse,
    response_model_exclude_unset=True,
    status_code=201,
)
def registrar_ajuste(
    datos: AjusteCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_AJUSTAR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> AjusteResponse:
    """`STOCK_AJUSTAR` (change 14, STK-08): corrige el stock de una ubicación con un motivo
    como una sola operación atómica. 201 con el ajuste, su estado y los saldos resultantes;
    `costo_unitario` de cada línea (string) solo con `VER_COSTOS`. Un ajuste nunca deja
    stock negativo: `STOCK_INSUFICIENTE` (409) aunque el usuario tenga `PERMITIR_STOCK_NEGATIVO`."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "ubicacion_id": str(datos.ubicacion_id),
        "motivo_id": str(datos.motivo_id),
        "lineas": [
            {"producto_id": str(linea.producto_id), "cantidad_base": linea.cantidad_base}
            for linea in datos.lineas
        ],
        "observacion": datos.observacion,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="STOCK_AJUSTAR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: object,
    ) -> sync_service.ResultadoHandlerConAuditoria:
        return stock_commands.manejar_stock_ajustar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    costos: dict[UUID, Decimal | None] | None = None
    if _tiene_ver_costos(entrada.contexto, sesion):
        costos = {
            linea.producto_id: linea.costo_unitario
            for linea in stock_service.lineas_de_ajuste(
                entrada.contexto.organizacion_id, sesion, UUID(str(resultado["ajuste_id"]))
            )
        }
    return ajuste_response(resultado, costos=costos)


@router.post(
    "/transferencias/{transferencia_id}/anulacion", response_model=TransferenciaAnuladaResponse
)
def anular_transferencia(
    transferencia_id: UUID,
    datos: TransferenciaAnularRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_TRANSFERIR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> TransferenciaAnuladaResponse:
    """`STOCK_TRANSFERENCIA_ANULAR` (change 14, TR-06, D5): anula por completo una transferencia
    confirmada con un motivo del ámbito `ANULACION_TRANSFERENCIA`. 200 con la transferencia
    `ANULADA`, los datos de la anulación y los saldos resultantes; sin costos. Con
    `TRANSFERIR_STOCK` se anula la propia; la de otro usuario exige además
    `ANULAR_TRANSFERENCIA` (403 `PERMISO_REQUERIDO`). Si el destino no alcanza,
    `STOCK_INSUFICIENTE` (409) salvo `PERMITIR_STOCK_NEGATIVO`, que la acepta con
    `STOCK_NEGATIVO` en `observaciones`."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "transferencia_id": str(transferencia_id),
        "motivo_id": str(datos.motivo_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="STOCK_TRANSFERENCIA_ANULAR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: object,
    ) -> sync_service.ResultadoHandlerConAuditoria:
        return stock_commands.manejar_stock_transferencia_anular(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    return TransferenciaAnuladaResponse.model_validate(
        {**resultado, "id": resultado["transferencia_id"]}
    )


@router.post(
    "/ajustes/{ajuste_id}/anulacion",
    response_model=AjusteAnuladoResponse,
    response_model_exclude_unset=True,
)
def anular_ajuste(
    ajuste_id: UUID,
    datos: AjusteAnularRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_AJUSTAR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> AjusteAnuladoResponse:
    """`STOCK_AJUSTE_ANULAR` (change 14, TR-06, D5): anula por completo un ajuste confirmado,
    propio o de otro usuario, con un motivo del ámbito `ANULACION_AJUSTE`. 200 con el ajuste
    `ANULADA`, los datos de la anulación y el saldo resultante de cada línea; `costo_unitario`
    (string) solo con `VER_COSTOS`. Si el stock de un ajuste positivo ya salió,
    `STOCK_INSUFICIENTE` (409) salvo `PERMITIR_STOCK_NEGATIVO`, que la acepta con
    `STOCK_NEGATIVO` en `observaciones`."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "ajuste_id": str(ajuste_id),
        "motivo_id": str(datos.motivo_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="STOCK_AJUSTE_ANULAR",
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
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: object,
    ) -> sync_service.ResultadoHandlerConAuditoria:
        return stock_commands.manejar_stock_ajuste_anular(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    costos: dict[UUID, Decimal | None] | None = None
    if _tiene_ver_costos(entrada.contexto, sesion):
        costos = {
            linea.producto_id: linea.costo_unitario
            for linea in stock_service.lineas_de_ajuste(
                entrada.contexto.organizacion_id, sesion, UUID(str(resultado["ajuste_id"]))
            )
        }
    return ajuste_anulado_response(resultado, costos=costos)


# --- lecturas (7.2) ----------------------------------------------------------------


@router.get("/ubicaciones", response_model=PaginaUbicaciones)
def listar_ubicaciones(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_LECTURA, PERMISO_REGISTRAR_COMPRA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    activo: bool | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaUbicaciones:
    """Ubicaciones de la organización, con filtro opcional por estado, paginadas
    por cursor (spec `ubicaciones`, escenario "Listar ubicaciones")."""
    pagina = stock_service.listar_ubicaciones(
        contexto.organizacion_id, sesion, activo=activo, cursor=cursor, limite=limite
    )
    return PaginaUbicaciones(
        items=[UbicacionResponse.model_validate(u) for u in pagina.ubicaciones],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router.get(
    "/ubicaciones/{ubicacion_id}/saldos",
    response_model=StockDeUbicacionResponse,
    response_model_exclude_unset=True,
)
def obtener_saldos_de_ubicacion(
    ubicacion_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_LECTURA))],
    sesion: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> StockDeUbicacionResponse:
    """Stock de una ubicación por producto en unidad base (STK-01), con las
    unidades de la presentación de referencia para mostrarlo en cajas + unidades
    (CAT-08). El promedio solo viaja con `VER_COSTOS` (D3-A). 404 si la ubicación
    es ajena o inexistente."""
    stock = stock_service.stock_por_ubicacion(
        contexto.organizacion_id, sesion, ubicacion_id=ubicacion_id, cursor=cursor, limite=limite
    )
    return stock_de_ubicacion_response(stock, con_costos=_tiene_ver_costos(contexto, sesion))


@router.get("/transferencias", response_model=PaginaDeTransferenciasResponse)
def listar_transferencias(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_TRANSFERIR))],
    sesion: Annotated[Session, Depends(get_session)],
    ubicacion_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaDeTransferenciasResponse:
    """Transferencias de la organización, más recientes primero, con su estado (change 14,
    D7). `ubicacion_id` alcanza origen y destino; `desde` y `hasta` son fechas de negocio en la
    zona de la organización. Un `limite` fuera de 1 a 200 es 422. Sin costos."""
    pagina = stock_queries.listar_transferencias(
        contexto.organizacion_id,
        sesion,
        ubicacion_id=ubicacion_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return pagina_de_transferencias_response(pagina)


@router.get("/transferencias/{transferencia_id}", response_model=DetalleDeTransferenciaResponse)
def obtener_transferencia(
    transferencia_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_TRANSFERIR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> DetalleDeTransferenciaResponse:
    """Detalle de una transferencia con sus líneas (código, nombre y unidades de referencia) y,
    si está anulada, el motivo, el usuario y el momento de la anulación. 404 si es de otra
    organización o no existe."""
    return detalle_de_transferencia_response(
        stock_queries.obtener_detalle_de_transferencia(
            contexto.organizacion_id, sesion, transferencia_id
        )
    )


@router.get("/ajustes", response_model=PaginaDeAjustesResponse)
def listar_ajustes(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_AJUSTAR))],
    sesion: Annotated[Session, Depends(get_session)],
    ubicacion_id: UUID | None = None,
    motivo_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaDeAjustesResponse:
    """Ajustes de la organización, más recientes primero, con su estado y su motivo (change 14,
    D7). Mismos filtros y paginación que las transferencias, más `motivo_id`. Sin costos."""
    pagina = stock_queries.listar_ajustes(
        contexto.organizacion_id,
        sesion,
        ubicacion_id=ubicacion_id,
        motivo_id=motivo_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return pagina_de_ajustes_response(pagina)


@router.get(
    "/ajustes/{ajuste_id}",
    response_model=DetalleDeAjusteResponse,
    response_model_exclude_unset=True,
)
def obtener_ajuste(
    ajuste_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_AJUSTAR))],
    sesion: Annotated[Session, Depends(get_session)],
) -> DetalleDeAjusteResponse:
    """Detalle de un ajuste con su motivo, sus líneas y, si está anulado, los datos de la
    anulación. `costo_unitario` de cada línea (string) solo con `VER_COSTOS` (ADR-036). 404 si
    es de otra organización o no existe."""
    return detalle_de_ajuste_response(
        stock_queries.obtener_detalle_de_ajuste(contexto.organizacion_id, sesion, ajuste_id),
        con_costos=_tiene_ver_costos(contexto, sesion),
    )


@router.get("/kardex", response_model=KardexResponse, response_model_exclude_unset=True)
def obtener_kardex(
    producto_id: UUID,
    ubicacion_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_LECTURA))],
    sesion: Annotated[Session, Depends(get_session)],
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> KardexResponse:
    """Kardex de un producto en una ubicación (STK-04, D11): `desde` y `hasta`
    son fechas de negocio en la zona de la organización; el acumulado es el de la
    historia completa. El costo de cada movimiento solo viaja con `VER_COSTOS`
    (D3-A). 404 si el producto o la ubicación son ajenos o inexistentes."""
    kardex = stock_service.kardex(
        contexto.organizacion_id,
        sesion,
        producto_id=producto_id,
        ubicacion_id=ubicacion_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return kardex_response(kardex, con_costos=_tiene_ver_costos(contexto, sesion))
