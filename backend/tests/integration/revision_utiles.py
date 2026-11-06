"""Utilidades de las pruebas de la revisión de observaciones (change 25, Lote 2).

Siembra por el repositorio de `sync` un comando `ACEPTADO_CON_OBSERVACIONES` con sus
observaciones `PENDIENTE`, sin pasar por el handler de la venta o la cobranza: lo que se prueba
es la lectura y la resolución de las observaciones, no cómo se produjeron.

Es un módulo y no un `conftest.py` por el mismo motivo que `stock_utiles`: `tests/integration`
no es un paquete.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands.observaciones import ObservacionProducida
from app.core.ids import nuevo_id
from app.modules.sync import repository as sync_repository
from app.modules.sync import service as sync_service

MOMENTO = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


class ComandoObservado(NamedTuple):
    comando_id: UUID
    operacion_id: UUID
    observaciones: list[UUID]


def sembrar_observaciones(
    sesion: Session,
    organizacion_id: UUID,
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    codigos: tuple[str, ...] = ("STOCK_NEGATIVO",),
    detalles: tuple[dict[str, object] | None, ...] | None = None,
    operacion_tipo: str = "VENTA",
    operacion_id: UUID | None = None,
    tipo_de_comando: str = "VENTA_CONFIRMAR",
    registered_at: datetime = MOMENTO,
    jornada_id: UUID | None = None,
    modo: str = "OFFLINE",
) -> ComandoObservado:
    """Un comando aceptado con una observación pendiente por cada código de `codigos`."""
    operacion = operacion_id or uuid4()
    reserva = sync_repository.reservar_comando(
        sesion,
        comando_id=nuevo_id(),
        organizacion_id=organizacion_id,
        operation_id=uuid4(),
        tipo=tipo_de_comando,
        version=1,
        modo=modo,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        huella=uuid4().hex,
        app_version="prueba",
        occurred_at=registered_at,
        registered_at=registered_at,
        jornada_id=jornada_id,
    )
    sync_repository.finalizar_comando(
        sesion,
        reserva.comando,
        estado="ACEPTADO_CON_OBSERVACIONES",
        resultado=None,
        error_codigo=None,
    )
    ids: list[UUID] = []
    for posicion, codigo in enumerate(codigos):
        detalle = None if detalles is None else detalles[posicion]
        observacion = sync_service.registrar_observacion(
            sesion,
            comando_id=reserva.comando.id,
            organizacion_id=organizacion_id,
            observacion=ObservacionProducida(
                codigo=codigo,
                operacion_tipo=operacion_tipo,
                operacion_id=operacion,
                detalle=detalle,
            ),
        )
        ids.append(observacion.id)
    return ComandoObservado(reserva.comando.id, operacion, ids)


def estados_de(sesion: Session, observaciones: list[UUID]) -> dict[UUID, str]:
    """`{id: estado}` leído sin caché (la aplicación escribe con otra conexión)."""
    sesion.rollback()
    filas = sesion.execute(
        text("SELECT id, estado FROM observacion WHERE id = ANY(:ids)"), {"ids": observaciones}
    )
    return {fila.id: fila.estado for fila in filas}


def sembrar_rechazo(
    sesion: Session,
    organizacion_id: UUID,
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    tipo: str = "VENTA_CONFIRMAR",
    jornada_id: UUID | None = None,
    contenido: dict[str, object] | None = None,
    error_codigo: str = "TOTALES_INCONSISTENTES",
    operation_id: UUID | None = None,
    secuencia: int = 1,
    recibido_en: datetime = MOMENTO,
) -> UUID:
    """Un rechazo `PENDIENTE` por el repositorio de `sync` (lo que deja `procesar_lote`)."""
    operacion = operation_id or uuid4()
    nuevo = nuevo_id()
    sync_repository.crear_rechazo(
        sesion,
        rechazo_id=nuevo,
        organizacion_id=organizacion_id,
        operation_id=operacion,
        tipo=tipo,
        version=1,
        modo="OFFLINE",
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        jornada_id=jornada_id,
        secuencia=secuencia,
        occurred_at=recibido_en,
        app_version="1.0.0",
        contenido=contenido if contenido is not None else {},
        error_codigo=error_codigo,
        recibido_en=recibido_en,
    )
    return nuevo


def sembrar_cuarentena(
    sesion: Session,
    organizacion_id: UUID,
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    tipo: str = "VENTA_CONFIRMAR",
    contenido: dict[str, object] | None = None,
    operation_id: UUID | None = None,
    recibido_en: datetime = MOMENTO,
) -> UUID:
    """Un comando en cuarentena `PENDIENTE` (sin revisar)."""
    nuevo = nuevo_id()
    sync_repository.crear_cuarentena(
        sesion,
        cuarentena_id=nuevo,
        organizacion_id=organizacion_id,
        dispositivo_id=dispositivo_id,
        usuario_id=usuario_id,
        operation_id=operation_id or uuid4(),
        tipo=tipo,
        contenido=contenido if contenido is not None else {},
        motivo="DISPOSITIVO_REVOCADO",
        recibido_en=recibido_en,
    )
    return nuevo


def resolver_por_sql(
    sesion: Session,
    organizacion_id: UUID,
    operacion_id: UUID,
    usuario_id: UUID,
    comentario: str = "Se corrigió con un ajuste",
) -> None:
    """Deja `RESUELTA` toda observación de la operación (lo que escribe `OBSERVACION_RESOLVER`),
    para probar cómo la muestra el detalle de la operación (change 25, D11, SYN-08)."""
    sesion.execute(
        text(
            "UPDATE observacion SET estado = 'RESUELTA', resuelto_por_id = :u, "
            "resuelto_en = :m, comentario = :c "
            "WHERE organizacion_id = :o AND operacion_id = :op"
        ),
        {"u": usuario_id, "m": MOMENTO, "c": comentario, "o": organizacion_id, "op": operacion_id},
    )
    sesion.commit()
