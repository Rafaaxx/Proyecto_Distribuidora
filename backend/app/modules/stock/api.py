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
    requiere_comando_online,
    requiere_permiso,
)
from app.core.clock import SystemClock
from app.modules.identidad import service as identidad_service
from app.modules.stock import commands as stock_commands
from app.modules.stock import service as stock_service
from app.modules.stock.domain.errores import CostoInvalidoError, RecursoNoEncontradoError
from app.modules.stock.schemas import (
    KardexResponse,
    PaginaUbicaciones,
    StockDeUbicacionResponse,
    StockInicialRegistrarRequest,
    StockInicialResponse,
    UbicacionCrearRequest,
    UbicacionModificarRequest,
    UbicacionResponse,
    kardex_response,
    stock_de_ubicacion_response,
)
from app.modules.sync import service as sync_service

PERMISO_UBICACIONES = "ADMIN_CONFIGURACION"
PERMISO_STOCK_INICIAL = "IMPORTAR_DATOS"
PERMISO_LECTURA = "TRANSFERIR_STOCK"
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


# --- lecturas (7.2) ----------------------------------------------------------------


@router.get("/ubicaciones", response_model=PaginaUbicaciones)
def listar_ubicaciones(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_LECTURA))],
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
