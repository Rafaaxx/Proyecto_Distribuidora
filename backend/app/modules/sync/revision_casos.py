"""Casos de uso de la revisión de observaciones (change 25; `design.md` D1; SYN-08, INV-01).

Orquestan el orden de las operaciones: validan con `domain/revision.py` y leen y escriben con
`revision_repository`. No importan `service.py`. Sin `commit`: la transacción la gestiona el bus.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.resumen import leer_vinculo
from app.modules.sync import revision_repository as repository
from app.modules.sync.domain import revision as dominio
from app.modules.sync.domain.errores import RecursoNoEncontradoError


@dataclass(frozen=True)
class ObservacionesResueltas:
    observaciones: tuple[UUID, ...]
    resuelto_en: datetime
    comentario: str


def resolver_observaciones(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    observaciones: Sequence[UUID],
    comentario: str,
) -> ObservacionesResueltas:
    """`OBSERVACION_RESOLVER` (SYN-08): resuelve en bloque con un comentario, o no resuelve
    ninguna (INV-01). La forma se valida antes de tocar la base; las filas se toman `FOR UPDATE`
    en orden de `id`; una que falta o es de otra organización es 404 (INV-21) y una ya resuelta,
    `OBSERVACION_YA_RESUELTA`. Solo escribe las columnas de la resolución: no toca la operación,
    su comando ni los libros."""
    ids = dominio.validar_observaciones(observaciones)
    texto = dominio.validar_comentario(comentario)
    estados = repository.bloquear_observaciones(organizacion_id, sesion, ids)
    if len(estados) != len(ids):
        raise RecursoNoEncontradoError("No se encontró alguna de las observaciones.")
    dominio.validar_pendientes(estados)
    momento = reloj.now()
    repository.marcar_resueltas(
        organizacion_id, sesion, ids, usuario_id=usuario_id, momento=momento, comentario=texto
    )
    return ObservacionesResueltas(observaciones=ids, resuelto_en=momento, comentario=texto)


ORIGEN_RECHAZO = "RECHAZO"
ORIGEN_CUARENTENA = "CUARENTENA"


@dataclass(frozen=True)
class RechazoResuelto:
    id: UUID
    origen: str
    resuelto_en: datetime
    comentario: str
    vinculo_tipo: str | None
    vinculo_id: UUID | None


def resolver_rechazo(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    usuario_id: UUID,
    origen: str,
    rechazo_id: UUID,
    comentario: str,
    vinculo_tipo: str | None,
    vinculo_id: UUID | None,
) -> RechazoResuelto:
    """`RECHAZO_RESOLVER` (SYN-06, SYN-08; `design.md` D7): da por revisado un rechazo (o una
    cuarentena) con un comentario y, si la operación ocurrió, el vínculo a la que la corrige. NO
    reenvía ni reprocesa el comando ni crea nada. Orden: el comentario (antes de tocar la base), el
    registro `FOR UPDATE` (404 si falta o es de otra organización: INV-21), que esté pendiente
    (`RECHAZO_YA_RESUELTO`), el tipo de vínculo que admite su comando (`VINCULO_INVALIDO`) y que la
    operación vinculada exista en la organización (404), leída por el módulo dueño."""
    texto = dominio.validar_comentario(comentario)
    if origen == ORIGEN_CUARENTENA:
        cuarentena = repository.bloquear_cuarentena(organizacion_id, sesion, rechazo_id)
        if cuarentena is None:
            raise RecursoNoEncontradoError("No se encontró la cuarentena.")
        dominio.validar_rechazo_pendiente(cuarentena.revisado_en is None)
        tipo_de_comando = cuarentena.tipo
    else:
        rechazo = repository.bloquear_rechazo(organizacion_id, sesion, rechazo_id)
        if rechazo is None:
            raise RecursoNoEncontradoError("No se encontró el rechazo.")
        dominio.validar_rechazo_pendiente(rechazo.estado == repository.PENDIENTE)
        tipo_de_comando = rechazo.tipo

    dominio.validar_tipo_de_vinculo(tipo_de_comando, vinculo_tipo)
    if (
        vinculo_tipo is not None
        and vinculo_id is not None
        and not leer_vinculo(organizacion_id, sesion, vinculo_tipo, vinculo_id)
    ):
        raise RecursoNoEncontradoError("No se encontró la operación vinculada.")

    momento = reloj.now()
    escribir = (
        repository.marcar_cuarentena_revisada
        if origen == ORIGEN_CUARENTENA
        else repository.marcar_rechazo_resuelto
    )
    escribir(
        organizacion_id,
        sesion,
        rechazo_id,
        usuario_id=usuario_id,
        momento=momento,
        comentario=texto,
        vinculo_tipo=vinculo_tipo,
        vinculo_id=vinculo_id,
    )
    return RechazoResuelto(
        id=rechazo_id,
        origen=origen,
        resuelto_en=momento,
        comentario=texto,
        vinculo_tipo=vinculo_tipo,
        vinculo_id=vinculo_id,
    )
