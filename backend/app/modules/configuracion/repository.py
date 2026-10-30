"""Acceso a datos de `configuracion`: los tres catálogos configurables
(`docs/02-arquitectura.md` §8; TR-09).

Contrato no negociable: todo método público recibe `organizacion_id` como
primer parámetro obligatorio y filtra toda consulta por él (tarea 6.3). No
existe operación de borrado (spec `catalogos-configurables`): un catálogo se
desactiva, nunca se elimina (`docs/03` §2.5).
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.configuracion.domain.valores import NombreDuplicadoError, ValorDuplicadoError
from app.modules.configuracion.models import AlicuotaIva, MedioPago, Motivo

LIMITE_PAGINA_MAXIMO = 100
LIMITE_PAGINA_DEFAULT = 50

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
    with _traduciendo_alicuota_duplicada(sesion):
        sesion.add(alicuota)
        sesion.flush()
    return alicuota


@contextmanager
def _traduciendo_alicuota_duplicada(sesion: Session) -> Iterator[None]:
    """Ejecuta la escritura en un `SAVEPOINT` y traduce la violación de `ux_alicuota_iva__nombre`
    a `NOMBRE_DUPLICADO` y la de `ux_alicuota_iva__valor` a `VALOR_DUPLICADO` (409, change 20c,
    D7); cualquier otra falla de integridad sube."""
    try:
        with sesion.begin_nested():
            yield
    except IntegrityError as error:
        causa = str(getattr(error, "orig", error))
        if "ux_alicuota_iva__nombre" in causa:
            raise NombreDuplicadoError(
                "Ya existe una alícuota con ese nombre en la organización."
            ) from error
        if "ux_alicuota_iva__valor" in causa:
            raise ValorDuplicadoError(
                "Ya existe una alícuota con ese porcentaje en la organización."
            ) from error
        raise


def bloquear_alicuotas(organizacion_id: UUID, sesion: Session) -> list[AlicuotaIva]:
    """Las alícuotas de la organización con `FOR UPDATE`, en orden de `id` (change 20c, D8): dos
    bajas simultáneas se serializan acá, y una baja espera a quien tiene la alícuota con
    `FOR SHARE` (alta o modificación de un producto, D9)."""
    consulta = (
        select(AlicuotaIva)
        .where(AlicuotaIva.organizacion_id == organizacion_id)
        .order_by(AlicuotaIva.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(sesion.execute(consulta).scalars().all())


def obtener_alicuota_para_compartir(
    organizacion_id: UUID, sesion: Session, alicuota_id: UUID
) -> AlicuotaIva | None:
    """La alícuota con `FOR SHARE` (change 20c, D9): el alta o la modificación de un producto la
    lee así, y una baja concurrente (`FOR UPDATE`) espera a que ese producto confirme."""
    consulta = (
        select(AlicuotaIva)
        .where(AlicuotaIva.organizacion_id == organizacion_id, AlicuotaIva.id == alicuota_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return sesion.execute(consulta).scalar_one_or_none()


def actualizar_alicuota(
    organizacion_id: UUID,
    sesion: Session,
    alicuota: AlicuotaIva,
    *,
    nombre: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> AlicuotaIva:
    """Reemplaza nombre y estado; el valor no se toca (change 20c, D6)."""
    assert alicuota.organizacion_id == organizacion_id
    with _traduciendo_alicuota_duplicada(sesion):
        alicuota.nombre = nombre
        alicuota.activo = activo
        alicuota.actualizado_en = momento
        alicuota.actualizado_por_id = actualizado_por_id
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


def _codificar_cursor(valor: str) -> str:
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def _decodificar_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")


def listar_alicuotas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[AlicuotaIva], str | None]:
    """Paginación por cursor (`02` §11; change 05, `design.md` D12): ordenada
    por `nombre`, con límite máximo `LIMITE_PAGINA_MAXIMO`. Devuelve todas
    las alícuotas (activas e inactivas, con su `activo`) de la organización
    -- el cliente filtra a activas (D12). Nunca una fila de otra
    organización. Devuelve `(alicuotas, cursor_siguiente)`; `cursor_siguiente`
    es `None` en la última página."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)
    consulta = select(AlicuotaIva).where(AlicuotaIva.organizacion_id == organizacion_id)
    if cursor is not None:
        consulta = consulta.where(AlicuotaIva.nombre > _decodificar_cursor(cursor))
    consulta = consulta.order_by(AlicuotaIva.nombre).limit(limite_efectivo + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        cursor_siguiente: str | None = _codificar_cursor(pagina[-1].nombre)
    else:
        pagina = filas
        cursor_siguiente = None
    return pagina, cursor_siguiente


def buscar_alicuotas_por_valor(
    organizacion_id: UUID, sesion: Session, valor: Decimal
) -> list[AlicuotaIva]:
    """Alícuotas de la organización con ese valor exacto (fracción: 21% es `0.21`),
    activas o no (change 10, `design.md` D4)."""
    consulta = (
        select(AlicuotaIva)
        .where(AlicuotaIva.organizacion_id == organizacion_id, AlicuotaIva.valor == valor)
        .order_by(AlicuotaIva.nombre, AlicuotaIva.id)
    )
    return list(sesion.scalars(consulta).all())


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
    with _traduciendo_nombre_duplicado(sesion):
        sesion.add(medio_pago)
        sesion.flush()
    return medio_pago


@contextmanager
def _traduciendo_nombre_duplicado(
    sesion: Session,
    indice: str = "ux_medio_pago__nombre",
    mensaje: str = "Ya existe un medio de pago con ese nombre en la organización.",
) -> Iterator[None]:
    """Ejecuta la escritura en un `SAVEPOINT` y traduce la violación del índice único de nombre
    (`ux_medio_pago__nombre` por omisión) a `NOMBRE_DUPLICADO` (409, change 17b, D3 y change 20c,
    D3); cualquier otra falla de integridad sube."""
    try:
        with sesion.begin_nested():
            yield
    except IntegrityError as error:
        if indice in str(getattr(error, "orig", error)):
            raise NombreDuplicadoError(mensaje) from error
        raise


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


def listar_medios_pago_todos(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    """Todos los medios de la organización, activos o no, ordenados por nombre (change 17b, D6)."""
    consulta = (
        select(MedioPago)
        .where(MedioPago.organizacion_id == organizacion_id)
        .order_by(func.lower(MedioPago.nombre), MedioPago.id)
    )
    return list(sesion.execute(consulta).scalars().all())


def bloquear_medios_pago(organizacion_id: UUID, sesion: Session) -> list[MedioPago]:
    """Los medios de la organización con `FOR UPDATE`, en orden de `id` (change 17b, D4): dos
    bajas simultáneas se serializan acá y la segunda cuenta con el estado ya confirmado de la
    primera (`populate_existing` evita devolver un estado en caché)."""
    consulta = (
        select(MedioPago)
        .where(MedioPago.organizacion_id == organizacion_id)
        .order_by(MedioPago.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(sesion.execute(consulta).scalars().all())


def actualizar_medio_pago(
    organizacion_id: UUID,
    sesion: Session,
    medio_pago: MedioPago,
    *,
    nombre: str,
    requiere_referencia: bool,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> MedioPago:
    """Reemplazo completo de los campos editables de un medio ya leído (change 17b, D2). Un
    medio de otra organización no se toca: lo defiende la comprobación de abajo."""
    if medio_pago.organizacion_id != organizacion_id:
        raise ValueError("El medio de pago no pertenece a la organización indicada.")
    medio_pago.nombre = nombre
    medio_pago.requiere_referencia = requiere_referencia
    medio_pago.activo = activo
    medio_pago.actualizado_en = momento
    medio_pago.actualizado_por_id = actualizado_por_id
    with _traduciendo_nombre_duplicado(sesion):
        sesion.flush()
    return medio_pago


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
    with _traduciendo_nombre_duplicado(sesion, *_NOMBRE_DUPLICADO_MOTIVO):
        sesion.add(motivo)
        sesion.flush()
    return motivo


_NOMBRE_DUPLICADO_MOTIVO = (
    "ux_motivo__nombre",
    "Ya existe un motivo con ese nombre en el ámbito de la organización.",
)


def listar_motivos_todos(
    organizacion_id: UUID, sesion: Session, ambito: str | None = None
) -> list[Motivo]:
    """Todos los motivos de la organización, activos o no, por ámbito y nombre (change 20c,
    D12). Con `ambito`, solo los de ese ámbito."""
    consulta = select(Motivo).where(Motivo.organizacion_id == organizacion_id)
    if ambito is not None:
        consulta = consulta.where(Motivo.ambito == ambito)
    consulta = consulta.order_by(Motivo.ambito, func.lower(Motivo.nombre), Motivo.id)
    return list(sesion.execute(consulta).scalars().all())


def bloquear_motivos_del_ambito(
    organizacion_id: UUID, sesion: Session, ambito: str
) -> list[Motivo]:
    """Los motivos del ámbito de la organización con `FOR UPDATE`, en orden de `id` (change 20c,
    D4): dos bajas simultáneas se serializan acá y la segunda cuenta con el estado ya confirmado
    de la primera."""
    consulta = (
        select(Motivo)
        .where(Motivo.organizacion_id == organizacion_id, Motivo.ambito == ambito)
        .order_by(Motivo.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list(sesion.execute(consulta).scalars().all())


def actualizar_motivo(
    organizacion_id: UUID,
    sesion: Session,
    motivo: Motivo,
    *,
    nombre: str,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> Motivo:
    """Reemplazo de nombre y estado de un motivo ya leído (change 20c, D2). El ámbito no se
    toca. Un motivo de otra organización no se modifica."""
    if motivo.organizacion_id != organizacion_id:
        raise ValueError("El motivo no pertenece a la organización indicada.")
    motivo.nombre = nombre
    motivo.activo = activo
    motivo.actualizado_en = momento
    motivo.actualizado_por_id = actualizado_por_id
    with _traduciendo_nombre_duplicado(sesion, *_NOMBRE_DUPLICADO_MOTIVO):
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
