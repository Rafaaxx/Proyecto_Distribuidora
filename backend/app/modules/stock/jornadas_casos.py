"""Casos de uso de las jornadas (change 15; `design.md` D1, D2, D3, D9).

Orquestan el orden de las operaciones: leen con `jornadas_repository` y deciden con
`domain/jornadas.py`. NUNCA importan `service.py` (que delega en este archivo): así no hay
ciclo. Sin `commit`: la transacción la gestiona el bus (`CLAUDE.md` §4).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.configuracion import service as configuracion_service
from app.modules.stock import jornadas_repository as repository
from app.modules.stock.domain import jornadas as dominio
from app.modules.stock.domain.errores import RecursoNoEncontradoError
from app.modules.stock.models import Jornada


def abrir_jornada(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    ubicacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
) -> Jornada:
    """`JORNADA_ABRIR` (RUT-01, RUT-03, INV-16): toma la ubicación `FOR UPDATE` (D9), exige
    que esté activa y que requiera toma (D3) y escribe la jornada `ABIERTA` del usuario y del
    dispositivo del sobre. Una ubicación inexistente o de otra organización es 404 (INV-21).
    La unicidad la decide el índice: no hay verificación previa."""
    ubicacion = repository.bloquear_ubicacion(organizacion_id, sesion, ubicacion_id=ubicacion_id)
    if ubicacion is None:
        raise RecursoNoEncontradoError(
            f"La ubicación {ubicacion_id} no existe en esta organización."
        )
    dominio.validar_ubicacion_para_abrir(
        activa=ubicacion.activo, requiere_toma=ubicacion.requiere_toma
    )
    ahora = reloj.now()
    return repository.insertar_jornada(
        organizacion_id,
        sesion,
        jornada_id=nuevo_id(),
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        ubicacion_id=ubicacion_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
        registered_at=ahora,
        creado_en=ahora,
    )


def existe_jornada(organizacion_id: UUID, sesion: Session, jornada_id: UUID) -> bool:
    """Si la jornada existe en la organización (D12). No evalúa su dueño ni su estado."""
    return repository.existe_jornada(organizacion_id, sesion, jornada_id=jornada_id)


def tiene_jornada_no_cerrada(
    organizacion_id: UUID, sesion: Session, *, usuario_id: UUID, dispositivo_id: UUID
) -> bool:
    """Si el usuario tiene una jornada `ABIERTA` o `EN_RENDICION` en ese dispositivo (INV-16,
    D19). Lectura pura, filtrada por organización (INV-21)."""
    return (
        repository.jornada_no_cerrada_de(
            organizacion_id, sesion, usuario_id=usuario_id, dispositivo_id=dispositivo_id
        )
        is not None
    )


def _jornada_bloqueada(organizacion_id: UUID, sesion: Session, jornada_id: UUID) -> Jornada:
    jornada = repository.bloquear_jornada(organizacion_id, sesion, jornada_id=jornada_id)
    if jornada is None:
        raise RecursoNoEncontradoError(f"La jornada {jornada_id} no existe en esta organización.")
    return jornada


def rendir_jornada(
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_id: UUID,
    usuario_id: UUID,
    occurred_at: datetime,
) -> Jornada:
    """`JORNADA_RENDIR` (`01` §18, D2): `ABIERTA → EN_RENDICION` con el momento y el usuario de
    la rendición. Sin conteo hasta el change 24. La ubicación sigue tomada (INV-16)."""
    jornada = _jornada_bloqueada(organizacion_id, sesion, jornada_id)
    jornada.estado = dominio.rendir(jornada.estado)
    jornada.rendida_en = occurred_at
    jornada.rendida_por_id = usuario_id
    sesion.flush()
    return jornada


def cerrar_jornada(
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_id: UUID,
    usuario_id: UUID,
    occurred_at: datetime,
) -> Jornada:
    """`JORNADA_CERRAR` (RUT-08, `01` §18): `EN_RENDICION → CERRADA`; la ubicación queda libre
    porque la jornada deja de estar no cerrada (INV-16)."""
    jornada = _jornada_bloqueada(organizacion_id, sesion, jornada_id)
    jornada.estado = dominio.cerrar(jornada.estado)
    jornada.cerrada_en = occurred_at
    jornada.cerrada_por_id = usuario_id
    sesion.flush()
    return jornada


def liberar_jornada(
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_id: UUID,
    usuario_id: UUID,
    motivo_id: UUID,
    observacion: str | None,
    occurred_at: datetime,
) -> Jornada:
    """`JORNADA_LIBERAR` (RUT-09, TR-09, D13): `ABIERTA | EN_RENDICION → LIBERADA` con un motivo
    activo del ámbito `LIBERACION_JORNADA` de la organización (ajeno o inexistente, 404;
    inactivo o de otro ámbito, `MOTIVO_INVALIDO`) y una observación opcional. No toca el stock
    de la ubicación. La jornada se toma `FOR UPDATE` antes de leer el motivo (D9)."""
    jornada = _jornada_bloqueada(organizacion_id, sesion, jornada_id)
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise RecursoNoEncontradoError("El motivo no existe en esta organización.")
    dominio.validar_motivo_de_liberacion(activo=motivo.activo, ambito=motivo.ambito)
    observacion_normalizada = dominio.normalizar_observacion_de_liberacion(observacion)
    jornada.estado = dominio.liberar(jornada.estado)
    jornada.liberada_en = occurred_at
    jornada.liberada_por_id = usuario_id
    jornada.motivo_liberacion_id = motivo_id
    jornada.observacion_liberacion = observacion_normalizada
    sesion.flush()
    return jornada
