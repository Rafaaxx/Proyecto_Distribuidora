"""Handlers de comandos de las jornadas (change 15; `design.md` D1, D2, D3).

`JORNADA_ABRIR` v1: `ONLINE` y `admite_offline=False` (`02` §6.5, RUT-03), permiso
`ABRIR_JORNADA`. El usuario y el dispositivo de la jornada salen del sobre (de la sesión),
nunca del contenido (`extra="forbid"`). El permiso se comprueba ACÁ y primero, igual que en
`commands.py`: un rechazo no deja jornada, ni reserva, ni auditoría (el bus revierte). Los
handlers no atrapan errores de dominio ni hacen `commit`.

El resultado que se guarda y se reenvía tal cual ante un doble envío (INV-06) es la jornada
completa; la auditoría la escribe el bus (ADR-022), sin motivo para la apertura.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.commands.auditoria import DatosDeAuditoria
from app.commands.catalogo import declarar_tipo
from app.commands.observaciones import ObservacionProducida
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.stock import service as stock_service
from app.modules.stock.models import Jornada

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `stock/commands.py` y `sync/service.py::ResultadoHandler`."""

ResultadoHandlerConAuditoria = tuple[
    str,
    dict[str, object] | None,
    str | None,
    tuple[ObservacionProducida, ...],
    DatosDeAuditoria,
]
"""Extensión con el dato de auditoría (como `stock/commands.py`): el bus copia el `motivo_id`
a su única fila (AUD-01, AUD-02, D8)."""

PERMISO_ABRIR_JORNADA = "ABRIR_JORNADA"
PERMISO_RENDIR_JORNADA = "RENDIR_JORNADA"
PERMISO_LIBERAR_UBICACION = "LIBERAR_UBICACION"


def _exigir_permiso(sobre: SobreComando, sesion: SesionDeHandler, codigo_permiso: str) -> None:
    """403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el permiso (SEG-06). Va
    PRIMERO: un rechazo no puede dejar nada escrito."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


def resultado_de_jornada(jornada: Jornada) -> dict[str, object]:
    """La jornada tal como la devuelve cada comando de jornada y la ruta: ids como texto y
    momentos en ISO 8601 (se guarda en `comando.resultado`, JSON)."""

    def _texto(valor: object) -> str | None:
        return None if valor is None else str(valor)

    def _momento(valor: object) -> str | None:
        return None if valor is None else valor.isoformat()  # type: ignore[attr-defined]

    return {
        "jornada_id": str(jornada.id),
        "ubicacion_id": str(jornada.ubicacion_id),
        "usuario_id": str(jornada.usuario_id),
        "dispositivo_id": str(jornada.dispositivo_id),
        "estado": jornada.estado,
        "abierta_en": _momento(jornada.abierta_en),
        "rendida_en": _momento(jornada.rendida_en),
        "rendida_por_id": _texto(jornada.rendida_por_id),
        "cerrada_en": _momento(jornada.cerrada_en),
        "cerrada_por_id": _texto(jornada.cerrada_por_id),
        "liberada_en": _momento(jornada.liberada_en),
        "liberada_por_id": _texto(jornada.liberada_por_id),
        "motivo_liberacion_id": _texto(jornada.motivo_liberacion_id),
        "observacion_liberacion": jornada.observacion_liberacion,
    }


class JornadaAbrirContenidoV1(BaseModel):
    """Solo `ubicacion_id`. `extra="forbid"`: `organizacion_id` sale del token (INV-21) y el
    usuario y el dispositivo, de la sesión (RUT-03)."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_id: UUID


def manejar_jornada_abrir(
    sobre: SobreComando,
    contenido: JornadaAbrirContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_ABRIR_JORNADA)
    jornada = stock_service.abrir_jornada(
        sobre.organizacion_id,
        sesion,
        reloj,
        ubicacion_id=contenido.ubicacion_id,
        usuario_id=sobre.usuario_id,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
        occurred_at=sobre.occurred_at,
    )
    return "ACEPTADO", resultado_de_jornada(jornada), None


registrar_handler("JORNADA_ABRIR", 1, JornadaAbrirContenidoV1)(manejar_jornada_abrir)
declarar_tipo(
    "JORNADA_ABRIR", admite_online=True, admite_offline=False, permisos=("ABRIR_JORNADA",)
)


class JornadaTransicionContenidoV1(BaseModel):
    """Solo `jornada_id`. `extra="forbid"`: la organización y el usuario salen de la sesión
    (INV-21)."""

    model_config = ConfigDict(extra="forbid")

    jornada_id: UUID


def manejar_jornada_rendir(
    sobre: SobreComando,
    contenido: JornadaTransicionContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_RENDIR_JORNADA)
    jornada = stock_service.rendir_jornada(
        sobre.organizacion_id,
        sesion,
        jornada_id=contenido.jornada_id,
        usuario_id=sobre.usuario_id,
        occurred_at=sobre.occurred_at,
    )
    return "ACEPTADO", resultado_de_jornada(jornada), None


def manejar_jornada_cerrar(
    sobre: SobreComando,
    contenido: JornadaTransicionContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, PERMISO_RENDIR_JORNADA)
    jornada = stock_service.cerrar_jornada(
        sobre.organizacion_id,
        sesion,
        jornada_id=contenido.jornada_id,
        usuario_id=sobre.usuario_id,
        occurred_at=sobre.occurred_at,
    )
    return "ACEPTADO", resultado_de_jornada(jornada), None


registrar_handler("JORNADA_RENDIR", 1, JornadaTransicionContenidoV1)(manejar_jornada_rendir)
declarar_tipo(
    "JORNADA_RENDIR", admite_online=True, admite_offline=False, permisos=("RENDIR_JORNADA",)
)
registrar_handler("JORNADA_CERRAR", 1, JornadaTransicionContenidoV1)(manejar_jornada_cerrar)
declarar_tipo(
    "JORNADA_CERRAR", admite_online=True, admite_offline=False, permisos=("RENDIR_JORNADA",)
)


class JornadaLiberarContenidoV1(BaseModel):
    """`jornada_id`, `motivo_id` y una observación opcional (el largo lo valida el dominio:
    `OBSERVACION_INVALIDA`). `extra="forbid"` (INV-21)."""

    model_config = ConfigDict(extra="forbid")

    jornada_id: UUID
    motivo_id: UUID
    observacion: str | None = None


def manejar_jornada_liberar(
    sobre: SobreComando,
    contenido: JornadaLiberarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandlerConAuditoria:
    """Libera la jornada y devuelve el motivo como dato de auditoría (D8): el único comando de
    jornada que lo hace."""
    _exigir_permiso(sobre, sesion, PERMISO_LIBERAR_UBICACION)
    jornada = stock_service.liberar_jornada(
        sobre.organizacion_id,
        sesion,
        jornada_id=contenido.jornada_id,
        usuario_id=sobre.usuario_id,
        motivo_id=contenido.motivo_id,
        observacion=contenido.observacion,
        occurred_at=sobre.occurred_at,
    )
    return (
        "ACEPTADO",
        resultado_de_jornada(jornada),
        None,
        (),
        DatosDeAuditoria(motivo_id=contenido.motivo_id),
    )


registrar_handler("JORNADA_LIBERAR", 1, JornadaLiberarContenidoV1)(manejar_jornada_liberar)
declarar_tipo(
    "JORNADA_LIBERAR", admite_online=True, admite_offline=False, permisos=("LIBERAR_UBICACION",)
)
