"""Rutas de la revisión de observaciones: `/api/v1/observaciones` (change 25; `design.md` D1, D3,
D5). La escritura pasa por el bus de comandos (`CLAUDE.md` §4); las lecturas, solo leen. Todas
exigen `REVISAR_OBSERVACIONES`. La organización sale siempre del token (INV-21)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
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
from app.modules.sync import revision_commands, revision_queries
from app.modules.sync import service as sync_service
from app.modules.sync.revision_repository import FiltroDeBandeja, FiltroDeRechazos
from app.modules.sync.schemas import (
    LineaResumidaResponse,
    MedioResumidoResponse,
    NombresDeObservacionResponse,
    ObservacionDeBandejaResponse,
    OperacionObservadaResponse,
    PaginaDeObservacionesResponse,
    PaginaDeRechazosResponse,
    RechazoResponse,
    ResolucionDeRechazoResponse,
    ResolucionResponse,
    ResolverObservacionesRequest,
    ResolverRechazoRequest,
    ResumenDeContenidoResponse,
    ResumenDeOperacionResponse,
    ResumenDePendientesResponse,
)

PERMISO_REVISAR_OBSERVACIONES = "REVISAR_OBSERVACIONES"

router = APIRouter(prefix="/observaciones", tags=["observaciones"])


@router.post("/resolucion", response_model=ResolucionResponse)
def resolver_observaciones(
    datos: ResolverObservacionesRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_REVISAR_OBSERVACIONES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ResolucionResponse:
    """`OBSERVACION_RESOLVER` (SYN-08): da por revisadas de 1 a 100 observaciones, con un
    comentario de 1 a 500 caracteres. 200 con las resueltas; `OBSERVACIONES_INVALIDAS` y
    `COMENTARIO_INVALIDO` responden 422, una ya resuelta `OBSERVACION_YA_RESUELTA` 409 y una
    inexistente o de otra organización 404. Todo o nada (INV-01)."""
    contenido: dict[str, ContenidoComando] = {
        "observaciones": [str(id_) for id_ in datos.observaciones],
        "comentario": datos.comentario,
    }
    reloj = SystemClock()
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="OBSERVACION_RESOLVER",
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
    contenido_validado: BaseModel = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return revision_commands.manejar_observacion_resolver(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return ResolucionResponse.model_validate(comando.resultado)


@router.post("/rechazos/{rechazo_id}/resolucion", response_model=ResolucionDeRechazoResponse)
def resolver_rechazo(
    rechazo_id: UUID,
    datos: ResolverRechazoRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_REVISAR_OBSERVACIONES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ResolucionDeRechazoResponse:
    """`RECHAZO_RESOLVER` (SYN-06, SYN-08): da por resuelto un rechazo sin conexión o una cuarentena
    con un comentario de 1 a 500 caracteres y, si la operación ocurrió, el vínculo a la que la
    corrige. NO reenvía ni crea nada. 200 con el registro; `COMENTARIO_INVALIDO` y
    `VINCULO_INVALIDO` responden 422, `RECHAZO_YA_RESUELTO` 409 y un registro o un vínculo
    inexistentes o de otra organización 404."""
    contenido: dict[str, ContenidoComando] = {
        "rechazo_id": str(rechazo_id),
        "origen": datos.origen,
        "comentario": datos.comentario,
    }
    if datos.vinculo is not None:
        contenido["vinculo"] = {"tipo": datos.vinculo.tipo, "id": str(datos.vinculo.id)}
    reloj = SystemClock()
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="RECHAZO_RESOLVER",
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
    contenido_validado: BaseModel = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return revision_commands.manejar_rechazo_resolver(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return ResolucionDeRechazoResponse.model_validate(comando.resultado)


def _pagina_response(pagina: revision_queries.PaginaDeBandeja) -> PaginaDeObservacionesResponse:
    return PaginaDeObservacionesResponse(
        items=[
            OperacionObservadaResponse(
                operacion_tipo=operacion.operacion_tipo,
                operacion_id=operacion.operacion_id,
                estado=operacion.estado,  # type: ignore[arg-type]
                resumen=(
                    None
                    if operacion.resumen is None
                    else ResumenDeOperacionResponse(
                        titulo=operacion.resumen.titulo,
                        tercero=operacion.resumen.tercero,
                        total=operacion.resumen.total,
                        momento=operacion.resumen.momento,
                    )
                ),
                usuario_id=operacion.usuario_id,
                usuario_nombre=operacion.usuario_nombre,
                dispositivo_id=operacion.dispositivo_id,
                jornada_id=operacion.jornada_id,
                modo=operacion.modo,  # type: ignore[arg-type]
                occurred_at=operacion.occurred_at,
                registered_at=operacion.registered_at,
                observaciones=[
                    ObservacionDeBandejaResponse(
                        id=o.id,
                        codigo=o.codigo,
                        detalle=o.detalle,
                        estado=o.estado,  # type: ignore[arg-type]
                        resuelto_por_id=o.resuelto_por_id,
                        resuelto_por_nombre=o.resuelto_por_nombre,
                        resuelto_en=o.resuelto_en,
                        comentario=o.comentario,
                        nombres=(
                            None
                            if o.nombres is None
                            else NombresDeObservacionResponse(
                                autorizador=o.nombres.autorizador,
                                producto=o.nombres.producto,
                                linea=o.nombres.linea,
                                vendedor_de_jornada=o.nombres.vendedor_de_jornada,
                            )
                        ),
                    )
                    for o in operacion.observaciones
                ],
            )
            for operacion in pagina.items
        ],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router.get("", response_model=PaginaDeObservacionesResponse)
def listar_observaciones(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_REVISAR_OBSERVACIONES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
    estado: Literal["PENDIENTE", "RESUELTA", "TODAS"] = "PENDIENTE",
    codigo: Annotated[list[str] | None, Query()] = None,
    tipo: Annotated[list[str] | None, Query()] = None,
    usuario_id: UUID | None = None,
    jornada_id: UUID | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=revision_queries.LIMITE_MAXIMO)] = 50,
) -> PaginaDeObservacionesResponse:
    """La bandeja de observaciones por operación (D3, SYN-07, SYN-08), de la llegada más reciente
    a la más antigua. `estado` `PENDIENTE` (por defecto) trae las operaciones con al menos un
    aviso pendiente, `RESUELTA` las que los tienen todos resueltos y `TODAS` las dos. `codigo` y
    `tipo` admiten varios valores; `desde` incluye y `hasta` excluye, sobre el momento de llegada.
    Un cursor ilegible es `CURSOR_INVALIDO`; `limite` va de 1 a 200 (422 fuera de rango)."""
    pagina = revision_queries.listar_bandeja(
        contexto.organizacion_id,
        sesion,
        FiltroDeBandeja(
            estado=estado,
            codigos=tuple(codigo or ()),
            tipos=tuple(tipo or ()),
            usuario_id=usuario_id,
            jornada_id=jornada_id,
            desde=desde,
            hasta=hasta,
        ),
        cursor=cursor,
        limite=limite,
    )
    return _pagina_response(pagina)


@router.get("/resumen", response_model=ResumenDePendientesResponse)
def resumen_de_pendientes(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_REVISAR_OBSERVACIONES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ResumenDePendientesResponse:
    """Lo pendiente de la organización para el aviso de `/admin` (D5, CRE-09): observaciones por
    código, rechazos y cuarentenas pendientes y el total."""
    resumen = revision_queries.resumen_de_pendientes(contexto.organizacion_id, sesion)
    return ResumenDePendientesResponse(
        observaciones_por_codigo=resumen.observaciones_por_codigo,
        observaciones_pendientes=resumen.observaciones_pendientes,
        rechazos_pendientes=resumen.rechazos_pendientes,
        cuarentenas_pendientes=resumen.cuarentenas_pendientes,
        total_pendiente=resumen.total_pendiente,
    )


def _rechazo_response(rechazo: revision_queries.RechazoLeido) -> RechazoResponse:
    resumen = rechazo.resumen
    return RechazoResponse(
        origen=rechazo.origen,  # type: ignore[arg-type]
        id=rechazo.id,
        operation_id=rechazo.operation_id,
        tipo=rechazo.tipo,
        estado=rechazo.estado,  # type: ignore[arg-type]
        codigo=rechazo.codigo,
        usuario_id=rechazo.usuario_id,
        usuario_nombre=rechazo.usuario_nombre,
        dispositivo_id=rechazo.dispositivo_id,
        jornada_id=rechazo.jornada_id,
        recibido_en=rechazo.recibido_en,
        occurred_at=rechazo.occurred_at,
        aceptada_despues=rechazo.aceptada_despues,
        resumen=(
            None
            if resumen is None
            else ResumenDeContenidoResponse(
                titulo=resumen.titulo,
                cliente=resumen.cliente,
                numero=resumen.numero,
                total=resumen.total,
                lineas=[
                    LineaResumidaResponse(
                        producto=linea.producto, cantidad=linea.cantidad, importe=linea.importe
                    )
                    for linea in resumen.lineas
                ],
                medios=[
                    MedioResumidoResponse(medio=medio.medio, importe=medio.importe)
                    for medio in resumen.medios
                ],
            )
        ),
        resuelto_por_id=rechazo.resuelto_por_id,
        resuelto_por_nombre=rechazo.resuelto_por_nombre,
        resuelto_en=rechazo.resuelto_en,
        comentario=rechazo.comentario,
        vinculo_tipo=rechazo.vinculo_tipo,  # type: ignore[arg-type]
        vinculo_id=rechazo.vinculo_id,
        contenido=rechazo.contenido,
    )


@router.get("/rechazos", response_model=PaginaDeRechazosResponse)
def listar_rechazos(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_REVISAR_OBSERVACIONES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
    estado: Literal["PENDIENTE", "RESUELTO", "TODOS"] = "PENDIENTE",
    origen: Literal["RECHAZO", "CUARENTENA"] | None = None,
    tipo: Annotated[list[str] | None, Query()] = None,
    usuario_id: UUID | None = None,
    jornada_id: UUID | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=revision_queries.LIMITE_MAXIMO)] = 50,
) -> PaginaDeRechazosResponse:
    """Los rechazos sin conexión y los comandos en cuarentena de la organización (SYN-06, SYN-09),
    del más reciente al más antiguo, con el resumen legible de lo que envió el teléfono, si el
    mismo `operation_id` se aceptó después y la resolución. `estado` `PENDIENTE` (por defecto),
    `RESUELTO` o `TODOS`; `origen`, `tipo` (varios), `usuario_id` y `jornada_id` filtran (la
    cuarentena no tiene jornada). Un cursor ilegible es `CURSOR_INVALIDO`."""
    pagina = revision_queries.listar_rechazos(
        contexto.organizacion_id,
        sesion,
        FiltroDeRechazos(
            estado=estado,
            origen=origen,
            tipos=tuple(tipo or ()),
            usuario_id=usuario_id,
            jornada_id=jornada_id,
        ),
        cursor=cursor,
        limite=limite,
    )
    return PaginaDeRechazosResponse(
        items=[_rechazo_response(r) for r in pagina.items],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router.get("/rechazos/{rechazo_id}", response_model=RechazoResponse)
def obtener_rechazo(
    rechazo_id: UUID,
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_REVISAR_OBSERVACIONES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> RechazoResponse:
    """Un rechazo o una cuarentena con lo crudo que envió el teléfono (`contenido`). 404 si no
    existe en la organización o es de otra (INV-21)."""
    return _rechazo_response(
        revision_queries.obtener_rechazo(contexto.organizacion_id, sesion, rechazo_id)
    )
