"""Acceso a datos de `jornada` (change 15; `design.md` D1, D3, D9, D10).

Archivo propio de jornadas dentro de `stock` (D1): `service.py` sigue siendo la única puerta
pública. Aquí solo hay SQL; las reglas viven en `domain/jornadas.py` y el orden de las
operaciones en `jornadas_casos.py`.

La unicidad de la toma la deciden los tres índices únicos parciales de la base (INV-16, D3,
`02` §7.5): `insertar_jornada` traduce la violación de cada uno a su error de dominio, sin una
verificación previa que la reemplace. Si una apertura viola varios a la vez, PostgreSQL
informa el primero por orden de creación del índice (ubicación, usuario, dispositivo).
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.stock import repository
from app.modules.stock.domain.errores import (
    DispositivoConJornadaError,
    UbicacionTomadaError,
    UsuarioConJornadaError,
)
from app.modules.stock.domain.jornadas import ABIERTA, ESTADOS_NO_CERRADOS
from app.modules.stock.domain.kardex import codificar_cursor, decodificar_cursor
from app.modules.stock.models import Jornada, Ubicacion

# Cada índice único parcial y el error que significa su violación (D3).
_INDICES_A_ERROR = (
    ("ux_jornada__ubicacion_abierta", UbicacionTomadaError, "La ubicación ya está tomada."),
    ("ux_jornada__usuario_abierta", UsuarioConJornadaError, "El usuario ya tiene una jornada."),
    (
        "ux_jornada__dispositivo_abierta",
        DispositivoConJornadaError,
        "El dispositivo ya tiene una jornada.",
    ),
)


def bloquear_ubicacion(
    organizacion_id: UUID, sesion: Session, *, ubicacion_id: UUID
) -> Ubicacion | None:
    """La ubicación de la organización `FOR UPDATE`, o `None` (D9): la apertura se espera
    con todo movimiento sobre esa ubicación, que la toma `FOR SHARE`."""
    return repository.obtener_ubicacion(
        organizacion_id, sesion, ubicacion_id=ubicacion_id, para_actualizar=True
    )


def insertar_jornada(
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    ubicacion_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    registered_at: datetime,
    creado_en: datetime,
) -> Jornada:
    """Inserta una jornada `ABIERTA` ya validada por `domain/`, dentro de un `SAVEPOINT`:
    la violación de un índice único parcial se traduce a `UBICACION_TOMADA`,
    `USUARIO_CON_JORNADA` o `DISPOSITIVO_CON_JORNADA` y la transacción sigue utilizable."""
    jornada = Jornada(
        id=jornada_id,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        ubicacion_id=ubicacion_id,
        estado=ABIERTA,
        operation_id=operation_id,
        occurred_at=occurred_at,
        registered_at=registered_at,
        creado_en=creado_en,
        abierta_en=occurred_at,
    )
    try:
        with sesion.begin_nested():
            sesion.add(jornada)
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        for indice, clase_de_error, texto in _INDICES_A_ERROR:
            if indice in mensaje:
                raise clase_de_error(texto) from error
        raise
    return jornada


def existe_jornada(organizacion_id: UUID, sesion: Session, *, jornada_id: UUID) -> bool:
    """Si la jornada existe en la organización, sin mirar su dueño ni su estado (D12)."""
    return (
        sesion.scalar(
            select(Jornada.id).where(
                Jornada.organizacion_id == organizacion_id, Jornada.id == jornada_id
            )
        )
        is not None
    )


def jornada_es_de(
    organizacion_id: UUID,
    sesion: Session,
    *,
    jornada_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
) -> bool:
    """Si la jornada existe en la organización y es de ese usuario en ese dispositivo, en
    cualquier estado (change 17, D12). Lectura sin bloqueo: el usuario y el dispositivo de una
    jornada no cambian (INV-05)."""
    return (
        sesion.scalar(
            select(Jornada.id).where(
                Jornada.organizacion_id == organizacion_id,
                Jornada.id == jornada_id,
                Jornada.usuario_id == usuario_id,
                Jornada.dispositivo_id == dispositivo_id,
            )
        )
        is not None
    )


def leer_jornada_compartida(
    organizacion_id: UUID, sesion: Session, *, jornada_id: UUID
) -> Jornada | None:
    """La jornada de la organización leída `FOR SHARE`, o `None` (change 17, D12, D18): es el
    nivel 5 del orden de bloqueo (`02` §7.3), el mismo que toman las operaciones que usan la
    jornada. Una liberación o un cierre (`FOR UPDATE`) espera a la operación en curso y al
    revés: la operación ve la jornada antes o después del cambio, nunca a medias."""
    return sesion.scalars(
        select(Jornada)
        .where(Jornada.organizacion_id == organizacion_id, Jornada.id == jornada_id)
        .with_for_update(read=True)
    ).one_or_none()


def bloquear_jornada(organizacion_id: UUID, sesion: Session, *, jornada_id: UUID) -> Jornada | None:
    """La jornada de la organización `FOR UPDATE`, o `None` (D9): las transiciones la toman
    así, revalidan el estado y no tocan stock ni saldos. Una jornada de otra organización no
    se ve (INV-21)."""
    return sesion.scalars(
        select(Jornada)
        .where(Jornada.organizacion_id == organizacion_id, Jornada.id == jornada_id)
        .with_for_update()
    ).one_or_none()


def bloquear_jornadas_no_cerradas(
    organizacion_id: UUID, sesion: Session, *, ubicaciones: Collection[UUID]
) -> dict[UUID, Jornada]:
    """La jornada no cerrada de cada ubicación (a lo sumo una, INV-16), leída `FOR SHARE` por
    `ubicacion_id` ascendente: es el nivel 5 del orden de bloqueo (D9, `02` §7.3), después de
    `stock_saldo`. Una liberación o un cierre (`FOR UPDATE`) espera a los movimientos en
    curso de esa jornada y al revés. Las ubicaciones sin jornada no cerrada no aparecen."""
    if not ubicaciones:
        return {}
    filas = sesion.scalars(
        select(Jornada)
        .where(
            Jornada.organizacion_id == organizacion_id,
            Jornada.ubicacion_id.in_(ubicaciones),
            Jornada.estado.in_(ESTADOS_NO_CERRADOS),
        )
        .order_by(Jornada.ubicacion_id)
        .with_for_update(read=True)
    ).all()
    return {fila.ubicacion_id: fila for fila in filas}


def jornadas_no_cerradas(
    organizacion_id: UUID, sesion: Session, *, ubicaciones: Collection[UUID]
) -> dict[UUID, Jornada]:
    """La jornada no cerrada de cada ubicación pedida, SIN bloquear (lecturas, change 15
    tarea 10.2): para mostrar quién tiene tomada una ubicación. Las libres no aparecen."""
    if not ubicaciones:
        return {}
    filas = sesion.scalars(
        select(Jornada).where(
            Jornada.organizacion_id == organizacion_id,
            Jornada.ubicacion_id.in_(ubicaciones),
            Jornada.estado.in_(ESTADOS_NO_CERRADOS),
        )
    ).all()
    return {fila.ubicacion_id: fila for fila in filas}


def listar_jornadas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    ubicacion_id: UUID | None,
    usuario_id: UUID | None,
    estado: str | None,
    desde: datetime | None,
    hasta: datetime | None,
    cursor: str | None,
    limite: int,
) -> tuple[list[tuple[Jornada, str]], str | None]:
    """Jornadas de la organización, de la más reciente a la más antigua por cursor
    `(abierta_en, id)` descendente (índice `ix_jornada__abierta_en`), cada una con el nombre de
    su ubicación. `desde` (inclusive) y `hasta` (exclusive) son instantes ya convertidos desde
    las fechas de negocio. Devuelve `(filas, cursor_siguiente)`. Solo lee."""
    consulta = (
        select(Jornada, Ubicacion.nombre)
        .join(
            Ubicacion,
            (Ubicacion.organizacion_id == Jornada.organizacion_id)
            & (Ubicacion.id == Jornada.ubicacion_id),
        )
        .where(Jornada.organizacion_id == organizacion_id)
    )
    if ubicacion_id is not None:
        consulta = consulta.where(Jornada.ubicacion_id == ubicacion_id)
    if usuario_id is not None:
        consulta = consulta.where(Jornada.usuario_id == usuario_id)
    if estado is not None:
        consulta = consulta.where(Jornada.estado == estado)
    if desde is not None:
        consulta = consulta.where(Jornada.abierta_en >= desde)
    if hasta is not None:
        consulta = consulta.where(Jornada.abierta_en < hasta)
    if cursor is not None:
        momento, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(tuple_(Jornada.abierta_en, Jornada.id) < (momento, id_cursor))
    consulta = consulta.order_by(Jornada.abierta_en.desc(), Jornada.id.desc()).limit(limite + 1)
    filas = [(jornada, nombre) for jornada, nombre in sesion.execute(consulta).all()]
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1][0]
        return pagina, codificar_cursor(ultima.abierta_en, ultima.id)
    return filas, None


def obtener_jornada(
    organizacion_id: UUID, sesion: Session, *, jornada_id: UUID
) -> tuple[Jornada, str] | None:
    """La jornada con el nombre de su ubicación, sin bloquear, o `None` si no existe en la
    organización (INV-21)."""
    fila = sesion.execute(
        select(Jornada, Ubicacion.nombre)
        .join(
            Ubicacion,
            (Ubicacion.organizacion_id == Jornada.organizacion_id)
            & (Ubicacion.id == Jornada.ubicacion_id),
        )
        .where(Jornada.organizacion_id == organizacion_id, Jornada.id == jornada_id)
    ).one_or_none()
    return None if fila is None else (fila[0], fila[1])


def bloquear_jornada_abierta_de(
    organizacion_id: UUID, sesion: Session, *, usuario_id: UUID, dispositivo_id: UUID
) -> UUID | None:
    """El identificador de la jornada `ABIERTA` del usuario en ese dispositivo, leída `FOR SHARE`,
    o `None` (change 17, D8, D18): es el nivel 5 del orden de bloqueo (`02` §7.3), el mismo que
    toman los movimientos de stock sobre la jornada de su ubicación. Una liberación o un cierre
    (`FOR UPDATE`) espera a la operación en curso y al revés. Como mucho una por usuario y
    dispositivo (`ux_jornada__*_abierta`)."""
    return sesion.scalar(
        select(Jornada.id)
        .where(
            Jornada.organizacion_id == organizacion_id,
            Jornada.usuario_id == usuario_id,
            Jornada.dispositivo_id == dispositivo_id,
            Jornada.estado == ABIERTA,
        )
        .with_for_update(read=True)
    )


def jornada_no_cerrada_de(
    organizacion_id: UUID, sesion: Session, *, usuario_id: UUID, dispositivo_id: UUID
) -> tuple[Jornada, str] | None:
    """La jornada `ABIERTA` o `EN_RENDICION` del usuario en ese dispositivo, o `None` (RUT-01,
    ADR-005). Como mucho una por usuario y dispositivo (`ux_jornada__*_abierta`)."""
    fila = sesion.execute(
        select(Jornada, Ubicacion.nombre)
        .join(
            Ubicacion,
            (Ubicacion.organizacion_id == Jornada.organizacion_id)
            & (Ubicacion.id == Jornada.ubicacion_id),
        )
        .where(
            Jornada.organizacion_id == organizacion_id,
            Jornada.usuario_id == usuario_id,
            Jornada.dispositivo_id == dispositivo_id,
            Jornada.estado.in_(ESTADOS_NO_CERRADOS),
        )
    ).one_or_none()
    return None if fila is None else (fila[0], fila[1])
