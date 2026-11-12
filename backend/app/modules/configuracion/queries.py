"""Casos de uso de lectura de `configuracion` para su propia API (change 05,
`design.md` D12; tarea 9.6). Mismo patrón que `catalogo/queries.py` (tarea
9.2): interno del propio módulo, llama a `repository.py` directamente.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.configuracion import repository
from app.modules.configuracion.models import AlicuotaIva, MedioPago, Motivo


def listar_alicuotas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
) -> tuple[list[AlicuotaIva], str | None]:
    return repository.listar_alicuotas_paginado(
        organizacion_id, sesion, limite=limite, cursor=cursor
    )


def listar_medios_pago_todos(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    """Todos los medios de pago de la organización, activos o no, por nombre (change 17b, D6)."""
    return repository.listar_medios_pago_todos(organizacion_id, sesion)


def listar_motivos_todos(
    organizacion_id: UUID, sesion: Session, ambito: str | None = None
) -> list[Motivo]:
    """Todos los motivos, activos o no, por ámbito y nombre (change 20c, D12)."""
    return repository.listar_motivos_todos(organizacion_id, sesion, ambito)
