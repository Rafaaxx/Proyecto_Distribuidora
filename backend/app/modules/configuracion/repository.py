"""Acceso a datos de `configuracion`: los tres catálogos configurables
(`docs/02-arquitectura.md` §8; TR-09).

Contrato no negociable: todo método público recibe `organizacion_id` como
primer parámetro obligatorio y filtra toda consulta por él (tarea 6.3). No
existe operación de borrado (spec `catalogos-configurables`): un catálogo se
desactiva, nunca se elimina (`docs/03` §2.5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.configuracion.models import AlicuotaIva, MedioPago, Motivo

# --- alicuota_iva ---------------------------------------------------------


def crear_alicuota(
    organizacion_id: UUID,
    sesion: Session,
    *,
    nombre: str,
    valor: Decimal,
    momento: datetime,
    activo: bool = True,
    actualizado_por_id: UUID | None = None,
) -> AlicuotaIva:
    alicuota = AlicuotaIva(
        organizacion_id=organizacion_id,
        nombre=nombre,
        valor=valor,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(alicuota)
    sesion.flush()
    return alicuota


def obtener_alicuota_por_id(
    organizacion_id: UUID, sesion: Session, alicuota_id: UUID
) -> AlicuotaIva | None:
    consulta = select(AlicuotaIva).where(
        AlicuotaIva.organizacion_id == organizacion_id, AlicuotaIva.id == alicuota_id
    )
    return sesion.execute(consulta).scalar_one_or_none()


def listar_alicuotas_activas(organizacion_id: UUID, sesion: Session) -> list[AlicuotaIva]:
    consulta = select(AlicuotaIva).where(
        AlicuotaIva.organizacion_id == organizacion_id, AlicuotaIva.activo.is_(True)
    )
    return list(sesion.execute(consulta).scalars().all())


def desactivar_alicuota(
    organizacion_id: UUID,
    sesion: Session,
    alicuota_id: UUID,
    *,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> AlicuotaIva | None:
    alicuota = obtener_alicuota_por_id(organizacion_id, sesion, alicuota_id)
    if alicuota is None:
        return None
    alicuota.activo = False
    alicuota.actualizado_en = momento
    alicuota.actualizado_por_id = actualizado_por_id
    sesion.flush()
    return alicuota


# --- medio_pago ------------------------------------------------------------


def crear_medio_pago(
    organizacion_id: UUID,
    sesion: Session,
    *,
    nombre: str,
    requiere_referencia: bool,
    momento: datetime,
    activo: bool = True,
    actualizado_por_id: UUID | None = None,
) -> MedioPago:
    medio_pago = MedioPago(
        organizacion_id=organizacion_id,
        nombre=nombre,
        requiere_referencia=requiere_referencia,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(medio_pago)
    sesion.flush()
    return medio_pago


def obtener_medio_pago_por_id(
    organizacion_id: UUID, sesion: Session, medio_pago_id: UUID
) -> MedioPago | None:
    consulta = select(MedioPago).where(
        MedioPago.organizacion_id == organizacion_id, MedioPago.id == medio_pago_id
    )
    return sesion.execute(consulta).scalar_one_or_none()


def listar_medios_pago_activos(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    consulta = select(MedioPago).where(
        MedioPago.organizacion_id == organizacion_id, MedioPago.activo.is_(True)
    )
    return list(sesion.execute(consulta).scalars().all())


def desactivar_medio_pago(
    organizacion_id: UUID,
    sesion: Session,
    medio_pago_id: UUID,
    *,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> MedioPago | None:
    medio_pago = obtener_medio_pago_por_id(organizacion_id, sesion, medio_pago_id)
    if medio_pago is None:
        return None
    medio_pago.activo = False
    medio_pago.actualizado_en = momento
    medio_pago.actualizado_por_id = actualizado_por_id
    sesion.flush()
    return medio_pago


# --- motivo ------------------------------------------------------------


def crear_motivo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ambito: str,
    nombre: str,
    momento: datetime,
    activo: bool = True,
    actualizado_por_id: UUID | None = None,
) -> Motivo:
    motivo = Motivo(
        organizacion_id=organizacion_id,
        ambito=ambito,
        nombre=nombre,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(motivo)
    sesion.flush()
    return motivo


def obtener_motivo_por_id(organizacion_id: UUID, sesion: Session, motivo_id: UUID) -> Motivo | None:
    consulta = select(Motivo).where(
        Motivo.organizacion_id == organizacion_id, Motivo.id == motivo_id
    )
    return sesion.execute(consulta).scalar_one_or_none()


def listar_motivos_activos(organizacion_id: UUID, sesion: Session) -> list[Motivo]:
    consulta = select(Motivo).where(
        Motivo.organizacion_id == organizacion_id, Motivo.activo.is_(True)
    )
    return list(sesion.execute(consulta).scalars().all())


def listar_motivos_por_ambito(organizacion_id: UUID, sesion: Session, ambito: str) -> list[Motivo]:
    consulta = select(Motivo).where(
        Motivo.organizacion_id == organizacion_id,
        Motivo.ambito == ambito,
        Motivo.activo.is_(True),
    )
    return list(sesion.execute(consulta).scalars().all())


def desactivar_motivo(
    organizacion_id: UUID,
    sesion: Session,
    motivo_id: UUID,
    *,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Motivo | None:
    motivo = obtener_motivo_por_id(organizacion_id, sesion, motivo_id)
    if motivo is None:
        return None
    motivo.activo = False
    motivo.actualizado_en = momento
    motivo.actualizado_por_id = actualizado_por_id
    sesion.flush()
    return motivo
