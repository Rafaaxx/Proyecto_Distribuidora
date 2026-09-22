"""Acceso a datos de `comando` para la reserva de idempotencia (change 04,
grupo 5, INV-06, `design.md` D3, `02` §6.3).

La reserva usa `INSERT ... ON CONFLICT (organizacion_id, operation_id) DO
NOTHING` (la restricción `ux_comando__org_operation_id` de la migración
`f6a7b8c9d0e1`, tarea 2.1) para que la garantía de unicidad viva en la
base, sin una consulta previa desde la aplicación: dos transacciones
concurrentes que intentan reservar el mismo `(organizacion_id,
operation_id)` no pueden creer ambas que ganaron -- PostgreSQL bloquea la
segunda hasta que la primera confirma o revierte (`design.md`, Risks).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.sync.models import Comando, ComandoCuarentena, Observacion


@dataclass(frozen=True)
class ResultadoReserva:
    """`gano` es `True` si esta llamada insertó la fila (el llamador debe
    ejecutar el handler); `False` si el `operation_id` ya existía en la
    organización (el llamador reutiliza `comando`)."""

    comando: Comando
    gano: bool


def reservar_comando(
    sesion: Session,
    *,
    comando_id: UUID,
    organizacion_id: UUID,
    operation_id: UUID,
    tipo: str,
    version: int,
    modo: str,
    usuario_id: UUID,
    dispositivo_id: UUID,
    huella: str,
    app_version: str,
    occurred_at: datetime,
    registered_at: datetime,
    secuencia: int = 0,
    jornada_id: UUID | None = None,
) -> ResultadoReserva:
    """Intenta reservar `(organizacion_id, operation_id)`. Sin `commit`: la
    transacción la gestiona quien llama (`02` §5.2).

    Usa `RETURNING id` en vez de `rowcount` para saber si la fila se
    insertó: `rowcount` de una sentencia `INSERT ... ON CONFLICT DO
    NOTHING` ejecutada vía el `Session` de la ORM no es fiable (puede
    reportar un valor que no distingue "insertó" de "chocó" según el
    dialecto y la forma de ejecución) -- `RETURNING` sí distingue
    exactamente: sin fila devuelta, no insertó nada (choque real)."""
    sentencia = (
        insert(Comando)
        .values(
            id=comando_id,
            organizacion_id=organizacion_id,
            operation_id=operation_id,
            tipo=tipo,
            version=version,
            modo=modo,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            jornada_id=jornada_id,
            secuencia=secuencia,
            huella=huella,
            app_version=app_version,
            estado="PROCESANDO",
            resultado=None,
            error_codigo=None,
            occurred_at=occurred_at,
            registered_at=registered_at,
        )
        .on_conflict_do_nothing(index_elements=["organizacion_id", "operation_id"])
        .returning(Comando.id)
    )
    fila_insertada = sesion.execute(sentencia).first()
    sesion.flush()

    if fila_insertada is not None:
        comando = sesion.get(Comando, comando_id)
        assert comando is not None  # se acaba de insertar en esta misma transacción.
        return ResultadoReserva(comando=comando, gano=True)

    existente = obtener_comando_por_operation_id(sesion, organizacion_id, operation_id)
    # El INSERT chocó: la fila ya existe (propia o de otra transacción ya
    # confirmada -- ver docstring de arriba sobre el bloqueo de PostgreSQL).
    assert existente is not None
    return ResultadoReserva(comando=existente, gano=False)


def obtener_comando_por_operation_id(
    sesion: Session, organizacion_id: UUID, operation_id: UUID
) -> Comando | None:
    consulta = select(Comando).where(
        Comando.organizacion_id == organizacion_id, Comando.operation_id == operation_id
    )
    return sesion.scalars(consulta).one_or_none()


def finalizar_comando(
    sesion: Session,
    comando: Comando,
    *,
    estado: str,
    resultado: dict[str, object] | None,
    error_codigo: str | None,
) -> None:
    """Registra el estado final de `comando` (SYN-04). Sin `commit`: la
    transacción la gestiona quien llama."""
    comando.estado = estado
    comando.resultado = resultado
    comando.error_codigo = error_codigo
    sesion.flush()


@dataclass(frozen=True)
class ResultadoCuarentena:
    """Mismo criterio que `ResultadoReserva` (arriba): `creado` es `True`
    solo si esta llamada insertó la fila; `False` si el `operation_id` ya
    estaba en cuarentena para esta organización (reenvío, change 04, tarea
    8.8, SYN-06, INV-06: el reenvío de un comando ya puesto en cuarentena no
    lo duplica)."""

    registro: ComandoCuarentena
    creado: bool


def crear_cuarentena(
    sesion: Session,
    *,
    cuarentena_id: UUID,
    organizacion_id: UUID,
    dispositivo_id: UUID,
    usuario_id: UUID,
    operation_id: UUID,
    tipo: str,
    contenido: Mapping[str, object],
    motivo: str,
    recibido_en: datetime,
) -> ResultadoCuarentena:
    """Inserta un registro de cuarentena con `INSERT ... ON CONFLICT (
    organizacion_id, operation_id) DO NOTHING` (misma técnica que
    `reservar_comando`, mismo motivo: la garantía de unicidad vive en la
    restricción `ux_comando_cuarentena__org_operation_id` de la base, sin
    una consulta previa desde la aplicación). Sin `commit`: quien llama
    (`sync/service.py::poner_en_cuarentena`) decide cuándo confirmar -- acá
    solo se arma la sentencia."""
    sentencia = (
        insert(ComandoCuarentena)
        .values(
            id=cuarentena_id,
            organizacion_id=organizacion_id,
            dispositivo_id=dispositivo_id,
            usuario_id=usuario_id,
            operation_id=operation_id,
            tipo=tipo,
            contenido=contenido,
            motivo=motivo,
            recibido_en=recibido_en,
            revisado_en=None,
            revisado_por_id=None,
        )
        .on_conflict_do_nothing(index_elements=["organizacion_id", "operation_id"])
        .returning(ComandoCuarentena.id)
    )
    fila_insertada = sesion.execute(sentencia).first()
    sesion.flush()

    if fila_insertada is not None:
        registro = sesion.get(ComandoCuarentena, cuarentena_id)
        assert registro is not None  # se acaba de insertar en esta misma transacción.
        return ResultadoCuarentena(registro=registro, creado=True)

    existente = obtener_cuarentena_por_operation_id(sesion, organizacion_id, operation_id)
    assert existente is not None
    return ResultadoCuarentena(registro=existente, creado=False)


def obtener_cuarentena_por_operation_id(
    sesion: Session, organizacion_id: UUID, operation_id: UUID
) -> ComandoCuarentena | None:
    consulta = select(ComandoCuarentena).where(
        ComandoCuarentena.organizacion_id == organizacion_id,
        ComandoCuarentena.operation_id == operation_id,
    )
    return sesion.scalars(consulta).one_or_none()


def crear_observacion(
    sesion: Session,
    *,
    observacion_id: UUID,
    organizacion_id: UUID,
    comando_id: UUID,
    operacion_tipo: str,
    operacion_id: UUID,
    codigo: str,
    detalle: Mapping[str, object] | None,
) -> Observacion:
    """Inserta una observación `PENDIENTE` (SYN-04, SYN-07, change 04,
    grupo 9, tarea 9.5). A diferencia de `reservar_comando`/`crear_cuarentena`,
    un `INSERT` simple: no hay reenvío que pueda duplicarla directamente --
    el reenvío de un comando ya aceptado nunca vuelve a ejecutar su handler
    (`procesar_idempotente`, grupo 5), así que este `INSERT` corre como
    mucho una vez por comando. Sin `commit`: la transacción la gestiona
    `procesar_comando` (grupo 6), igual que `finalizar_comando`."""
    observacion = Observacion(
        id=observacion_id,
        organizacion_id=organizacion_id,
        comando_id=comando_id,
        operacion_tipo=operacion_tipo,
        operacion_id=operacion_id,
        codigo=codigo,
        detalle=dict(detalle) if detalle is not None else None,
        estado="PENDIENTE",
        resuelto_por_id=None,
        resuelto_en=None,
        comentario=None,
    )
    sesion.add(observacion)
    sesion.flush()
    return observacion


def listar_observaciones_pendientes(
    sesion: Session, organizacion_id: UUID, codigo: str
) -> list[Observacion]:
    """Pendientes de una organización por código (tarea 9.6): ejercita el
    índice parcial `ix_observacion__org_codigo_pendiente` (`organizacion_id`,
    `codigo`) `WHERE estado = 'PENDIENTE'` (migración `f6a7b8c9d0e1`, tarea
    2.4)."""
    consulta = select(Observacion).where(
        Observacion.organizacion_id == organizacion_id,
        Observacion.codigo == codigo,
        Observacion.estado == "PENDIENTE",
    )
    return list(sesion.scalars(consulta).all())
