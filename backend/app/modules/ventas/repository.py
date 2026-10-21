"""Acceso a datos de `ventas`. Toda consulta filtra por `organizacion_id` (INV-02, INV-21) y la
carga de relaciones es siempre explícita (`CLAUDE.md` §4)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.ventas.domain.consultas import codificar_cursor, decodificar_cursor
from app.modules.ventas.domain.errores import NumeroDuplicadoError
from app.modules.ventas.models import Venta, VentaLinea


def presentacion_figura_en_alguna_linea(
    organizacion_id: UUID, presentacion_id: UUID, sesion: Session
) -> bool:
    """`True` si la presentación figura en alguna línea de venta, de cualquier estado de venta
    (INV-18, TR-06: una venta anulada sigue contando)."""
    consulta = select(
        exists().where(
            VentaLinea.organizacion_id == organizacion_id,
            VentaLinea.presentacion_id == presentacion_id,
        )
    )
    return bool(sesion.scalar(consulta))


def existe_venta(organizacion_id: UUID, venta_id: UUID, sesion: Session) -> bool:
    """`True` si el identificador ya lo usa una venta de la organización."""
    consulta = select(
        exists().where(Venta.organizacion_id == organizacion_id, Venta.id == venta_id)
    )
    return bool(sesion.scalar(consulta))


def existe_numero(organizacion_id: UUID, numero: str, sesion: Session) -> bool:
    """`True` si una venta de la organización ya usa el número (VTA-06)."""
    consulta = select(
        exists().where(Venta.organizacion_id == organizacion_id, Venta.numero == numero)
    )
    return bool(sesion.scalar(consulta))


def insertar_venta(sesion: Session, venta: Venta, lineas: Sequence[VentaLinea]) -> None:
    """Escribe la cabecera y sus líneas de una vez (INV-01); las tablas son de solo inserción.
    Una carrera por el mismo número viola `ux_venta__numero` y se traduce a `NUMERO_DUPLICADO`
    (la otra transacción ya confirmó entre la lectura previa y este insert); el punto de
    guardado deja la transacción usable para que el bus la revierta con su error."""
    try:
        with sesion.begin_nested():
            sesion.add(venta)
            sesion.flush()
    except IntegrityError as error:
        if "ux_venta__numero" in str(error.orig):
            raise NumeroDuplicadoError(f"El número {venta.numero} ya fue usado.") from error
        raise
    sesion.add_all(lineas)
    sesion.flush()


def listar_ventas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    cliente_id: UUID | None,
    usuario_id: UUID | None,
    jornada_id: UUID | None,
    ubicacion_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
) -> tuple[list[Venta], str | None]:
    """Ventas de la organización de la más reciente a la más vieja, por cursor
    `(occurred_at, id)` descendente (índices `ix_venta__occurred_at`, `ix_venta__cliente` e
    `ix_venta__usuario`, D16). `desde` es inclusivo y `hasta` exclusivo (instantes: ver
    `rango_de_instantes`). Devuelve `(filas, cursor_siguiente)`."""
    consulta = select(Venta).where(Venta.organizacion_id == organizacion_id)
    if cliente_id is not None:
        consulta = consulta.where(Venta.cliente_id == cliente_id)
    if usuario_id is not None:
        consulta = consulta.where(Venta.usuario_id == usuario_id)
    if jornada_id is not None:
        consulta = consulta.where(Venta.jornada_id == jornada_id)
    if ubicacion_id is not None:
        consulta = consulta.where(Venta.ubicacion_id == ubicacion_id)
    if desde is not None:
        consulta = consulta.where(Venta.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(Venta.occurred_at < hasta)
    if cursor is not None:
        momento, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(tuple_(Venta.occurred_at, Venta.id) < (momento, id_cursor))
    consulta = consulta.order_by(Venta.occurred_at.desc(), Venta.id.desc()).limit(limite + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1]
        return pagina, codificar_cursor(ultima.occurred_at, ultima.id)
    return filas, None


def obtener_venta(organizacion_id: UUID, venta_id: UUID, sesion: Session) -> Venta | None:
    """La venta de la organización sin bloquearla (INV-21: la de otra organización no existe)."""
    return sesion.scalar(
        select(Venta).where(Venta.organizacion_id == organizacion_id, Venta.id == venta_id)
    )


def listar_lineas_de_venta(
    organizacion_id: UUID, venta_id: UUID, sesion: Session
) -> list[VentaLinea]:
    """Las líneas de la venta en el orden en que se cargaron (a lo sumo 200, D8)."""
    return list(
        sesion.scalars(
            select(VentaLinea)
            .where(VentaLinea.organizacion_id == organizacion_id, VentaLinea.venta_id == venta_id)
            .order_by(VentaLinea.orden)
        ).all()
    )
