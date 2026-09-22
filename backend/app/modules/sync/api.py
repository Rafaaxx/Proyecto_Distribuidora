"""`POST /api/v1/sync/comandos`: el lote de sincronización (change 04,
grupo 8, tarea 8.6; `02` §6.1, §6.4).

Decisión de diseño tomada dentro del alcance de este grupo (mismo criterio
que 3.3/4.5/6.2/7.3, reportada para confirmación humana): esta ruta usa
`Depends(obtener_contexto_autenticado)`, NO `Depends(requiere_permiso(...))`
como el resto de las rutas de negocio. `requiere_permiso` exige UN código de
permiso fijo por ruta (`design.md` D5), pero un lote puede traer comandos de
tipos distintos, cada uno con su propio permiso de negocio -- no hay un solo
permiso que declarar acá arriba. La validación de permisos por comando
(SEG-06, `02` §6.3 paso 4) es responsabilidad del handler resuelto por
`app.commands.registro` para cada tipo, no de esta ruta; queda fuera del
alcance de este grupo porque ningún handler real está registrado todavía
(el catálogo de tipos llega recién en el grupo 11). Por eso esta ruta se
declara EXENTA del ratchet de permiso por ruta
(`tests/integration/test_ratchet_permiso_por_ruta.py::RUTAS_EXENTAS_DE_PERMISO`),
de forma explícita y enumerable -- igual criterio que las rutas de `/auth` y
de sistema, con una razón distinta y documentada en ese archivo.

Sí requiere autenticación: sin token, `obtener_contexto_autenticado` lanza
`AccessTokenAusenteError` (401) antes de tocar la base (tarea 8.5, escenario
"Un lote sin sesión no se procesa").
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands.huella import ContenidoComando
from app.core.autenticacion import ContextoAutenticado, obtener_contexto_autenticado
from app.core.clock import SystemClock
from app.modules.sync import service as sync_service
from app.modules.sync.schemas import (
    ItemLoteComandoRequest,
    LoteComandosRequest,
    LoteComandosResponse,
    ResultadoItemLoteResponse,
)
from app.modules.sync.service import ItemLote

router = APIRouter(prefix="/sync", tags=["sync"])


def _item_lote_desde_request(item: ItemLoteComandoRequest) -> ItemLote:
    # `cast`, no una conversión real (`schemas.py` explica por qué Pydantic
    # no puede tipar `contenido` como `ContenidoComando` directamente):
    # `item.contenido` es un `dict[str, object]` que Pydantic decodificó de
    # un cuerpo JSON, así que solo puede contener las formas de dato que
    # `ContenidoComando` admite -- el `cast` documenta esa garantía en vez
    # de tolerar `Any` en silencio (`CLAUDE.md` §5).
    contenido = cast(dict[str, ContenidoComando], item.contenido)
    return ItemLote(
        operation_id=item.operation_id,
        tipo=item.tipo,
        version=item.version,
        modo=item.modo,
        usuario_id=item.usuario_id,
        dispositivo_id=item.dispositivo_id,
        occurred_at=item.occurred_at,
        secuencia=item.secuencia,
        app_version=item.app_version,
        contenido=contenido,
        jornada_id=item.jornada_id,
    )


@router.post("/comandos", response_model=LoteComandosResponse)
def sincronizar_lote(
    datos: LoteComandosRequest,
    contexto: Annotated[ContextoAutenticado, Depends(obtener_contexto_autenticado)],
    sesion: Annotated[Session, Depends(get_session)],
) -> LoteComandosResponse:
    """Procesa el lote de la cola del dispositivo (`02` §6.4, tareas 8.1 a
    8.10). `organizacion_id`, `usuario_id` y `dispositivo_id` de la sesión
    vienen siempre del token (`contexto`), nunca del cuerpo -- cada ítem
    declara los suyos solo para que `sync_service.procesar_lote` pueda
    rechazar una cola ajena (`ColaAjenaError`) en vez de reatribuirla en
    silencio."""
    items = [_item_lote_desde_request(item) for item in datos.items]
    resultados = sync_service.procesar_lote(
        sesion,
        SystemClock(),
        organizacion_id=contexto.organizacion_id,
        usuario_id=contexto.usuario_id,
        dispositivo_id=contexto.dispositivo_id,
        items=items,
    )
    return LoteComandosResponse(
        resultados=[
            ResultadoItemLoteResponse(
                operation_id=resultado.operation_id,
                estado=resultado.estado,
                resultado=resultado.resultado,
                error_codigo=resultado.error_codigo,
            )
            for resultado in resultados
        ]
    )
