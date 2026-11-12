"""Handlers de la revisión de observaciones (change 25; `design.md` D1; SYN-08).

`OBSERVACION_RESOLVER` v1: solo `ONLINE` (`admite_offline=False`), permiso
`REVISAR_OBSERVACIONES`. La organización y el usuario salen del sobre (de la sesión), nunca del
contenido (`extra="forbid"`, INV-21). El permiso se comprueba ACÁ y primero: un rechazo no deja
nada escrito. Los handlers no atrapan errores de dominio ni hacen `commit`. La auditoría la
escribe el bus (ADR-022), sin motivo.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.commands.catalogo import declarar_tipo
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.sync import revision_casos as casos

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler`."""

PERMISO_REVISAR_OBSERVACIONES = "REVISAR_OBSERVACIONES"


def exigir_permiso_de_revision(sobre: SobreComando, sesion: SesionDeHandler) -> None:
    """403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene `REVISAR_OBSERVACIONES`."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if PERMISO_REVISAR_OBSERVACIONES not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {PERMISO_REVISAR_OBSERVACIONES}.")


class ObservacionResolverContenidoV1(BaseModel):
    """`observaciones` (la forma la valida el dominio: `OBSERVACIONES_INVALIDAS`) y `comentario`
    (`COMENTARIO_INVALIDO`). Sin límites de Pydantic: el rechazo lleva el código estable."""

    model_config = ConfigDict(extra="forbid")

    observaciones: list[UUID]
    comentario: str


def manejar_observacion_resolver(
    sobre: SobreComando,
    contenido: ObservacionResolverContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    exigir_permiso_de_revision(sobre, sesion)
    resueltas = casos.resolver_observaciones(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=sobre.usuario_id,
        observaciones=contenido.observaciones,
        comentario=contenido.comentario,
    )
    resultado: dict[str, object] = {
        "observaciones": [str(id_) for id_ in resueltas.observaciones],
        "resuelto_en": resueltas.resuelto_en.isoformat(),
        "comentario": resueltas.comentario,
    }
    return "ACEPTADO", resultado, None


registrar_handler("OBSERVACION_RESOLVER", 1, ObservacionResolverContenidoV1)(
    manejar_observacion_resolver
)
declarar_tipo(
    "OBSERVACION_RESOLVER",
    admite_online=True,
    admite_offline=False,
    permisos=(PERMISO_REVISAR_OBSERVACIONES,),
)


class VinculoContenidoV1(BaseModel):
    """La operación cargada con conexión que corrige lo rechazado (D7)."""

    model_config = ConfigDict(extra="forbid")

    tipo: Literal["VENTA", "COBRANZA"]
    id: UUID


class RechazoResolverContenidoV1(BaseModel):
    """`origen` dice en qué tabla está el registro (`RECHAZO` o `CUARENTENA`). El comentario lo
    valida el dominio (`COMENTARIO_INVALIDO`)."""

    model_config = ConfigDict(extra="forbid")

    rechazo_id: UUID
    origen: Literal["RECHAZO", "CUARENTENA"]
    comentario: str
    vinculo: VinculoContenidoV1 | None = None


def manejar_rechazo_resolver(
    sobre: SobreComando,
    contenido: RechazoResolverContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    exigir_permiso_de_revision(sobre, sesion)
    resuelto = casos.resolver_rechazo(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=sobre.usuario_id,
        origen=contenido.origen,
        rechazo_id=contenido.rechazo_id,
        comentario=contenido.comentario,
        vinculo_tipo=None if contenido.vinculo is None else contenido.vinculo.tipo,
        vinculo_id=None if contenido.vinculo is None else contenido.vinculo.id,
    )
    resultado: dict[str, object] = {
        "id": str(resuelto.id),
        "origen": resuelto.origen,
        "estado": "RESUELTO",
        "resuelto_en": resuelto.resuelto_en.isoformat(),
        "comentario": resuelto.comentario,
        "vinculo_tipo": resuelto.vinculo_tipo,
        "vinculo_id": None if resuelto.vinculo_id is None else str(resuelto.vinculo_id),
    }
    return "ACEPTADO", resultado, None


registrar_handler("RECHAZO_RESOLVER", 1, RechazoResolverContenidoV1)(manejar_rechazo_resolver)
declarar_tipo(
    "RECHAZO_RESOLVER",
    admite_online=True,
    admite_offline=False,
    permisos=(PERMISO_REVISAR_OBSERVACIONES,),
)
