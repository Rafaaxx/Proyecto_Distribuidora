"""Endpoints de negocio de `cobranzas` (change 17, grupo 7; `design.md` D2, D14).

Mismo criterio que `proveedores/api.py`: la escritura (`POST /cobranzas`) declara
`requiere_comando_online` (exige `Operation-Id`, SYN-01/TR-07, y el permiso `REGISTRAR_COBRANZA`
por ruta) y delega en `sync_service.procesar_comando`, que valida el contenido, reserva la
operación, ejecuta el handler y registra la auditoría. El import de
`app.modules.cobranzas.commands` puebla el registro de handlers al arrancar la aplicación.

Toda escritura de negocio pasa por el bus: no hay un endpoint que lo esquive (`CLAUDE.md` §4).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, cast
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
)
from app.core.clock import SystemClock
from app.modules.cobranzas import commands as cobranzas_commands
from app.modules.cobranzas import queries as cobranzas_queries
from app.modules.cobranzas.schemas import (
    CobranzaAnulacionResponse,
    CobranzaAnularRequest,
    CobranzaAnularResponse,
    CobranzaDetalleResponse,
    CobranzaMedioResponse,
    CobranzaObservacionResponse,
    CobranzaRegistrarRequest,
    CobranzaRegistrarResponse,
    CobranzaResumenResponse,
    PaginaCobranzas,
)
from app.modules.sync import service as sync_service

PERMISO_REGISTRAR_COBRANZA = "REGISTRAR_COBRANZA"
PERMISO_ANULAR_COBRANZA = "ANULAR_COBRANZA"
_OPERACION_TIPO = "COBRANZA"
"""Tipo con el que se registran las observaciones de SYN-07 de una cobranza."""

router = APIRouter(prefix="/cobranzas", tags=["cobranzas"])


def _resultado_de(comando: sync_service.Comando) -> dict[str, object]:
    assert comando.resultado is not None
    return comando.resultado


@router.post("", response_model=CobranzaRegistrarResponse, status_code=201)
def registrar_cobranza(
    datos: CobranzaRegistrarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_REGISTRAR_COBRANZA))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CobranzaRegistrarResponse:
    """`POST /cobranzas` (change 17, tarea 7.3). El resultado sale de `comando.resultado`, no de
    una relectura: un reenvío idempotente del mismo `Operation-Id` devuelve exactamente lo mismo
    (INV-06). Los importes viajan y vuelven como string (INV-03) y los errores de medio traen su
    posición desde 0 en el Problem Details (`02` §11, COB-02)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "cobranza_id": str(datos.cobranza_id),
        "cliente_id": str(datos.cliente_id),
        "importe": datos.importe,
        "medios": [
            {
                "medio_pago_id": str(medio.medio_pago_id),
                "importe": medio.importe,
                "referencia": medio.referencia,
            }
            for medio in datos.medios
        ],
        "observacion": datos.observacion,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="COBRANZA_REGISTRAR",
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
        cobranzas_commands.CobranzaRegistrarContenidoV1,
        registro.validar_contenido(handler_registrado, sobre.contenido),
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler | sync_service.ResultadoHandlerConObservaciones:
        return cobranzas_commands.manejar_cobranza_registrar(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    return CobranzaRegistrarResponse(
        cobranza_id=UUID(str(resultado["cobranza_id"])),
        estado=str(resultado["estado"]),
        importe=str(resultado["importe"]),
        saldo=str(resultado["saldo"]),
        jornada_id=None if resultado["jornada_id"] is None else UUID(str(resultado["jornada_id"])),
    )


@router.post("/{cobranza_id}/anulacion", response_model=CobranzaAnularResponse)
def anular_cobranza(
    cobranza_id: UUID,
    datos: CobranzaAnularRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_ANULAR_COBRANZA))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CobranzaAnularResponse:
    """`POST /cobranzas/{id}/anulacion` (change 17, tarea 9.1; COB-05). El resultado sale de
    `comando.resultado`: un reenvío idempotente del mismo `Operation-Id` devuelve lo mismo
    (INV-06). Si la cobranza ya está anulada, es de una venta o el motivo no sirve, lo decide el
    servicio con su código estable y el Problem Details (`02` §11)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "cobranza_id": str(cobranza_id),
        "motivo_id": str(datos.motivo_id),
        "observacion": datos.observacion,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="COBRANZA_ANULAR",
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
        cobranzas_commands.CobranzaAnularContenidoV1,
        registro.validar_contenido(handler_registrado, sobre.contenido),
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandlerConAuditoria:
        return cobranzas_commands.manejar_cobranza_anular(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    return CobranzaAnularResponse(
        cobranza_id=UUID(str(resultado["cobranza_id"])),
        estado=str(resultado["estado"]),
        importe=str(resultado["importe"]),
        saldo=str(resultado["saldo"]),
    )


def _resumen_de(item: cobranzas_queries.CobranzaDelListado) -> CobranzaResumenResponse:
    cobranza = item.cobranza
    return CobranzaResumenResponse(
        cobranza_id=cobranza.id,
        occurred_at=cobranza.occurred_at,
        cliente_id=cobranza.cliente_id,
        cliente_nombre=item.cliente_nombre,
        importe=str(cobranza.importe),
        estado=cobranza.estado,
        origen=cobranza.origen,
        venta_id=cobranza.venta_id,
        usuario_id=cobranza.usuario_id,
        usuario_nombre=item.usuario_nombre,
        jornada_id=cobranza.jornada_id,
    )


@router.get("", response_model=PaginaCobranzas)
def listar_cobranzas(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_REGISTRAR_COBRANZA, PERMISO_ANULAR_COBRANZA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    cliente_id: UUID | None = None,
    estado: Literal["CONFIRMADA", "ANULADA"] | None = None,
    usuario_id: UUID | None = None,
    jornada_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaCobranzas:
    """Cobranzas de la organización de la más reciente a la más vieja, por cursor (change 17,
    tarea 10.1; `design.md` D14, aprobada por el usuario el 2026-10-16): `REGISTRAR_COBRANZA` o
    `ANULAR_COBRANZA`, todas las de la organización. `desde` y `hasta` son fechas de negocio
    inclusivas en la zona de la organización (TR-04); un `limite` fuera de 1 a 200 o un `estado`
    desconocido son 422, y un rango invertido o un cursor ilegible también, con su código."""
    pagina = cobranzas_queries.listar_cobranzas(
        contexto.organizacion_id,
        sesion,
        cliente_id=cliente_id,
        estado=estado,
        usuario_id=usuario_id,
        jornada_id=jornada_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return PaginaCobranzas(
        items=[_resumen_de(item) for item in pagina.items],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router.get("/{cobranza_id}", response_model=CobranzaDetalleResponse)
def obtener_cobranza(
    cobranza_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_REGISTRAR_COBRANZA, PERMISO_ANULAR_COBRANZA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CobranzaDetalleResponse:
    """Detalle de una cobranza: medios con nombre y referencia, jornada, observación, la anulación
    si existe y las observaciones de sincronización (COB-02, COB-05, SYN-07). 404 si es de otra
    organización o no existe (INV-21, SEG-07)."""
    detalle = cobranzas_queries.obtener_detalle_de_cobranza(
        contexto.organizacion_id, cobranza_id, sesion
    )
    observaciones = sync_service.listar_observaciones_de_operacion(
        contexto.organizacion_id,
        sesion,
        operacion_tipo=_OPERACION_TIPO,
        operacion_id=cobranza_id,
    )
    anulacion = detalle.anulacion
    return CobranzaDetalleResponse(
        **_resumen_de(detalle.resumen).model_dump(),
        observacion=detalle.resumen.cobranza.observacion,
        registered_at=detalle.resumen.cobranza.registered_at,
        medios=[
            CobranzaMedioResponse(
                medio_pago_id=medio.medio_pago_id,
                medio_nombre=medio.medio_nombre,
                importe=str(medio.importe),
                referencia=medio.referencia,
            )
            for medio in detalle.medios
        ],
        anulacion=(
            None
            if anulacion is None
            else CobranzaAnulacionResponse(
                motivo_id=anulacion.motivo_id,
                motivo_nombre=anulacion.motivo_nombre,
                observacion=anulacion.observacion,
                usuario_id=anulacion.usuario_id,
                usuario_nombre=anulacion.usuario_nombre,
                anulada_en=anulacion.anulada_en,
            )
        ),
        observaciones=[
            CobranzaObservacionResponse(
                codigo=observacion.codigo,
                estado=observacion.estado,
                detalle=observacion.detalle,
            )
            for observacion in observaciones
        ],
    )
