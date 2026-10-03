"""Interfaz pública de `configuracion` (`CLAUDE.md` §4): alta, listado de
activos, listado por ámbito y desactivación de los tres catálogos
configurables (TR-09).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.modules.configuracion import repository
from app.modules.configuracion.domain.valores import (
    validar_ambito_motivo,
    validar_nombre_medio_pago,
    validar_valor_alicuota,
)
from app.modules.configuracion.models import AlicuotaIva, MedioPago, Motivo

# --- alicuota_iva -----------------------------------------------------------


def crear_alicuota(
    organizacion_id: UUID, sesion: Session, reloj: Clock, *, nombre: str, valor: Decimal
) -> AlicuotaIva:
    validar_valor_alicuota(valor)
    return repository.crear_alicuota(
        organizacion_id, sesion, nombre=nombre, valor=valor, momento=reloj.now()
    )


def listar_alicuotas_activas(organizacion_id: UUID, sesion: Session) -> list[AlicuotaIva]:
    return repository.listar_alicuotas_activas(organizacion_id, sesion)


def obtener_alicuota_por_id(
    organizacion_id: UUID, alicuota_id: UUID, sesion: Session
) -> AlicuotaIva | None:
    """Lectura pública de una alícuota por id (change 05, `design.md`:
    "`catalogo` la consume por `configuracion/service.py`", `CLAUDE.md` §4:
    un módulo usa a otro solo a través de su `service.py`). Nunca devuelve
    la fila de otra organización: el filtro va siempre por
    `organizacion_id`."""
    return repository.obtener_alicuota_por_id(organizacion_id, sesion, alicuota_id)


def buscar_alicuotas_por_valor(
    organizacion_id: UUID, valor: Decimal, sesion: Session
) -> list[AlicuotaIva]:
    """Lectura pública para la importación (change 10, `design.md` D4: alícuota por
    porcentaje): las alícuotas de la organización con ese valor exacto (fracción, 21%
    es `0.21`), activas o no; el alta de producto rechaza después una inactiva con
    `ALICUOTA_INACTIVA`. Nunca devuelve las de otra organización."""
    return repository.buscar_alicuotas_por_valor(organizacion_id, sesion, valor)


def desactivar_alicuota(
    organizacion_id: UUID, sesion: Session, reloj: Clock, alicuota_id: UUID
) -> AlicuotaIva | None:
    return repository.desactivar_alicuota(organizacion_id, sesion, alicuota_id, momento=reloj.now())


# --- medio_pago --------------------------------------------------------------


def crear_medio_pago(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    nombre: str,
    requiere_referencia: bool,
) -> MedioPago:
    validar_nombre_medio_pago(nombre)
    return repository.crear_medio_pago(
        organizacion_id,
        sesion,
        nombre=nombre,
        requiere_referencia=requiere_referencia,
        momento=reloj.now(),
    )


def obtener_medio_pago(
    organizacion_id: UUID, medio_pago_id: UUID, sesion: Session
) -> MedioPago | None:
    """Lectura pública de un medio de pago por id, activo o no (change 11: compras de
    contado). Nunca devuelve la fila de otra organización."""
    return repository.obtener_medio_pago_por_id(organizacion_id, sesion, medio_pago_id)


def listar_medios_pago_activos(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    return repository.listar_medios_pago_activos(organizacion_id, sesion)


def desactivar_medio_pago(
    organizacion_id: UUID, sesion: Session, reloj: Clock, medio_pago_id: UUID
) -> MedioPago | None:
    return repository.desactivar_medio_pago(
        organizacion_id, sesion, medio_pago_id, momento=reloj.now()
    )


# --- motivo -------------------------------------------------------------------


def crear_motivo(
    organizacion_id: UUID, sesion: Session, reloj: Clock, *, ambito: str, nombre: str
) -> Motivo:
    validar_ambito_motivo(ambito)
    return repository.crear_motivo(
        organizacion_id, sesion, ambito=ambito, nombre=nombre, momento=reloj.now()
    )


def obtener_motivo(organizacion_id: UUID, motivo_id: UUID, sesion: Session) -> Motivo | None:
    """Lectura pública de un motivo por id, activo o no (change 11: anulación de
    compras). Nunca devuelve la fila de otra organización."""
    return repository.obtener_motivo_por_id(organizacion_id, sesion, motivo_id)


def listar_motivos_activos(organizacion_id: UUID, sesion: Session) -> list[Motivo]:
    return repository.listar_motivos_activos(organizacion_id, sesion)


def listar_motivos_por_ambito(organizacion_id: UUID, sesion: Session, ambito: str) -> list[Motivo]:
    validar_ambito_motivo(ambito)
    return repository.listar_motivos_por_ambito(organizacion_id, sesion, ambito)


def desactivar_motivo(
    organizacion_id: UUID, sesion: Session, reloj: Clock, motivo_id: UUID
) -> Motivo | None:
    return repository.desactivar_motivo(organizacion_id, sesion, motivo_id, momento=reloj.now())
