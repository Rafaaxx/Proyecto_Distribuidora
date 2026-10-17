"""Endpoints de `descuentos` (change 16, grupo 8; `design.md` D15, D16, D18, `Enfoque técnico`).

Cuatro escrituras y dos lecturas bajo `/api/v1/descuentos/reglas`. Cada escritura tiene su ruta
dedicada, mismo criterio que `precios/api.py`: declaran `requiere_comando_online` (exige
`Operation-Id`, SYN-01/TR-07) y delegan en `sync_service.procesar_comando`. Cada función de ruta
referencia `procesar_comando` ella misma (no a través de un auxiliar): es lo que el ratchet de
cobertura del bus inspecciona.

- `POST /descuentos/reglas` (`REGLA_DESCUENTO_CREAR`): la regla nace en `BORRADOR`.
- `PUT /descuentos/reglas/{regla_id}` (`REGLA_DESCUENTO_MODIFICAR`): reemplaza un borrador; en una
  regla activada o pausada solo fija la vigencia hasta (D15).
- `POST /descuentos/reglas/{regla_id}/activacion` (`REGLA_DESCUENTO_ACTIVAR`) y
  `POST /descuentos/reglas/{regla_id}/pausa` (`REGLA_DESCUENTO_PAUSAR`).

Las escrituras y las dos lecturas (listado con filtro de estado y cursor, y detalle) exigen
solo `GESTIONAR_DESCUENTOS` (`01` §19, D18). `organizacion_id` sale siempre del token,
nunca de la petición (INV-02, INV-21); un recurso de otra organización responde 404, no 403
(`CLAUDE.md` §4). No existe ninguna ruta que borre una regla (TR-06).

Cada respuesta es la regla con sus alcances y el nombre de cada entidad
(`queries.obtener_regla`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import SobreComando, construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    requiere_comando_online,
    requiere_permiso,
)
from app.core.clock import Clock, SystemClock
from app.modules.descuentos import commands as descuentos_commands
from app.modules.descuentos import queries
from app.modules.descuentos.domain.errores import PrioridadInvalidaError
from app.modules.descuentos.schemas import (
    EstadoReglaApi,
    ReglaDescuentoCrearRequest,
    ReglaDescuentoModificarRequest,
    ReglaDescuentoResponse,
    ReglasDescuentoResponse,
)
from app.modules.sync import service as sync_service

PERMISO_GESTIONAR_DESCUENTOS = "GESTIONAR_DESCUENTOS"

router = APIRouter(prefix="/descuentos", tags=["descuentos"])


def _preparar(
    entrada: EntradaComandoOnline, tipo: str, contenido: dict[str, ContenidoComando], reloj: Clock
) -> tuple[SobreComando, str, BaseModel]:
    """El sobre del comando, su huella y el contenido validado contra el esquema del handler
    registrado: lo común a las cuatro escrituras. Quien llama pasa los tres a
    `sync_service.procesar_comando`."""
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo=tipo,
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
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)
    return sobre, calcular_huella(sobre.contenido), contenido_validado


def _prioridad_entera(prioridad: int | float | None) -> int | None:
    """Un decimal (`1.5`, `2.0`) no es una prioridad: se rechaza con `PRIORIDAD_INVALIDA` antes de
    armar el sobre, porque el contenido de un comando no admite números con coma."""
    if isinstance(prioridad, float):
        raise PrioridadInvalidaError(f"La prioridad debe ser un entero (recibido {prioridad}).")
    return prioridad


def _iso(momento: datetime | None) -> str | None:
    """Los momentos viajan como cadena ISO 8601 en el contenido del comando."""
    return None if momento is None else momento.isoformat()


# --- escrituras ---------------------------------------------------------------------------


@router.post("/reglas", response_model=ReglaDescuentoResponse, status_code=201)
def crear_regla(
    datos: ReglaDescuentoCrearRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_DESCUENTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaDescuentoResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "REGLA_DESCUENTO_CREAR",
        {
            "nombre": datos.nombre,
            "tipo": datos.tipo,
            "medida": datos.medida,
            "operador": datos.operador,
            "umbral": datos.umbral,
            "accion_tipo": datos.accion_tipo,
            "accion_valor": datos.accion_valor,
            "prioridad": _prioridad_entera(datos.prioridad),
            "acumulable": datos.acumulable,
            "alcances": [{"tipo": a.tipo, "entidad_id": str(a.entidad_id)} for a in datos.alcances],
            "vigencia_desde": _iso(datos.vigencia_desde),
            "vigencia_hasta": _iso(datos.vigencia_hasta),
        },
        reloj,
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return descuentos_commands.manejar_regla_descuento_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return queries.obtener_regla(
        entrada.contexto.organizacion_id,
        UUID(str(comando.resultado["regla_id"])),
        sesion,
        ahora=reloj.now(),
    )


@router.put("/reglas/{regla_id}", response_model=ReglaDescuentoResponse)
def modificar_regla(
    regla_id: UUID,
    datos: ReglaDescuentoModificarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_DESCUENTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaDescuentoResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"regla_id": str(regla_id)}
    for campo in sorted(datos.model_fields_set):
        valor = getattr(datos, campo)
        if campo == "prioridad":
            contenido[campo] = _prioridad_entera(valor)
        elif campo == "alcances":
            contenido[campo] = (
                None
                if valor is None
                else [{"tipo": a.tipo, "entidad_id": str(a.entidad_id)} for a in valor]
            )
        elif campo in {"vigencia_desde", "vigencia_hasta"}:
            contenido[campo] = _iso(valor)
        else:
            contenido[campo] = valor
    sobre, huella, contenido_validado = _preparar(
        entrada, "REGLA_DESCUENTO_MODIFICAR", contenido, reloj
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return descuentos_commands.manejar_regla_descuento_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_regla(
        entrada.contexto.organizacion_id, regla_id, sesion, ahora=reloj.now()
    )


@router.post("/reglas/{regla_id}/activacion", response_model=ReglaDescuentoResponse)
def activar_regla(
    regla_id: UUID,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_DESCUENTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaDescuentoResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada, "REGLA_DESCUENTO_ACTIVAR", {"regla_id": str(regla_id)}, reloj
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return descuentos_commands.manejar_regla_descuento_activar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_regla(
        entrada.contexto.organizacion_id, regla_id, sesion, ahora=reloj.now()
    )


@router.post("/reglas/{regla_id}/pausa", response_model=ReglaDescuentoResponse)
def pausar_regla(
    regla_id: UUID,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_DESCUENTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaDescuentoResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada, "REGLA_DESCUENTO_PAUSAR", {"regla_id": str(regla_id)}, reloj
    )

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return descuentos_commands.manejar_regla_descuento_pausar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_regla(
        entrada.contexto.organizacion_id, regla_id, sesion, ahora=reloj.now()
    )


# --- lecturas (tarea 9.1, D18: solo `GESTIONAR_DESCUENTOS`) ---------------------------------


@router.get("/reglas", response_model=ReglasDescuentoResponse)
def listar_reglas(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_GESTIONAR_DESCUENTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
    estado: EstadoReglaApi | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReglasDescuentoResponse:
    """Las reglas de la organización, de la más nueva a la más vieja, paginadas por cursor.
    `estado` admite `VENCIDA` (derivado). Porcentajes e importes viajan como string."""
    return queries.listar_reglas(
        contexto.organizacion_id,
        sesion,
        estado=estado,
        ahora=SystemClock().now(),
        limite=limite,
        cursor=cursor,
    )


@router.get("/reglas/{regla_id}", response_model=ReglaDescuentoResponse)
def obtener_regla(
    regla_id: UUID,
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_GESTIONAR_DESCUENTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaDescuentoResponse:
    """El detalle de una regla con sus alcances y el nombre de cada entidad; 404 si es ajena."""
    return queries.obtener_regla(
        contexto.organizacion_id, regla_id, sesion, ahora=SystemClock().now()
    )
