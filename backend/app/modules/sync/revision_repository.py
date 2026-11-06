"""Acceso a datos de la revisión de observaciones (change 25; `design.md` D1, D3, D5).

Las lecturas agregan en la base (`CLAUDE.md` §4: reportes y saldos con SQL, nunca filas a Python
para sumar) y filtran siempre por `organizacion_id` (INV-21). Sin `commit`: la transacción la
gestiona el bus.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Uuid,
    and_,
    case,
    cast,
    func,
    literal,
    null,
    select,
    tuple_,
    union_all,
    update,
)
from sqlalchemy.orm import Session

from app.modules.sync.models import Comando, ComandoCuarentena, ComandoRechazado, Observacion

PENDIENTE = "PENDIENTE"
RESUELTA = "RESUELTA"
RESUELTO = "RESUELTO"


def bloquear_observaciones(
    organizacion_id: UUID, sesion: Session, ids: Sequence[UUID]
) -> dict[UUID, str]:
    """`{id: estado}` de las observaciones de la organización, tomadas `FOR UPDATE` en orden de
    `id` (el mismo orden para todos: dos resoluciones en bloque con listas cruzadas no se
    interbloquean, `design.md` D1). Las que no existen o son de otra organización no aparecen."""
    consulta = (
        select(Observacion.id, Observacion.estado)
        .where(Observacion.organizacion_id == organizacion_id, Observacion.id.in_(ids))
        .order_by(Observacion.id)
        .with_for_update()
    )
    return {fila.id: fila.estado for fila in sesion.execute(consulta)}


def marcar_resueltas(
    organizacion_id: UUID,
    sesion: Session,
    ids: Collection[UUID],
    *,
    usuario_id: UUID,
    momento: datetime,
    comentario: str,
) -> None:
    """Escribe la resolución: las únicas columnas que `app_runtime` puede actualizar (D2)."""
    sesion.execute(
        update(Observacion)
        .where(Observacion.organizacion_id == organizacion_id, Observacion.id.in_(ids))
        .values(
            estado=RESUELTA,
            resuelto_por_id=usuario_id,
            resuelto_en=momento,
            comentario=comentario,
        )
        .execution_options(synchronize_session=False)
    )
    sesion.flush()


def bloquear_rechazo(
    organizacion_id: UUID, sesion: Session, rechazo_id: UUID
) -> ComandoRechazado | None:
    """El rechazo de la organización tomado `FOR UPDATE` (D7). No toma la jornada: el orden de
    bloqueos con la rendición es jornada y luego lectura del rechazo (D9, precisión 5)."""
    return sesion.scalar(
        select(ComandoRechazado)
        .where(
            ComandoRechazado.organizacion_id == organizacion_id, ComandoRechazado.id == rechazo_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def bloquear_cuarentena(
    organizacion_id: UUID, sesion: Session, cuarentena_id: UUID
) -> ComandoCuarentena | None:
    """La cuarentena de la organización tomada `FOR UPDATE` (D7)."""
    return sesion.scalar(
        select(ComandoCuarentena)
        .where(
            ComandoCuarentena.organizacion_id == organizacion_id,
            ComandoCuarentena.id == cuarentena_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def marcar_rechazo_resuelto(
    organizacion_id: UUID,
    sesion: Session,
    rechazo_id: UUID,
    *,
    usuario_id: UUID,
    momento: datetime,
    comentario: str,
    vinculo_tipo: str | None,
    vinculo_id: UUID | None,
) -> None:
    """Escribe la resolución del rechazo: las únicas columnas que `app_runtime` puede cambiar."""
    sesion.execute(
        update(ComandoRechazado)
        .where(
            ComandoRechazado.organizacion_id == organizacion_id, ComandoRechazado.id == rechazo_id
        )
        .values(
            estado=RESUELTO,
            resuelto_por_id=usuario_id,
            resuelto_en=momento,
            comentario=comentario,
            vinculo_tipo=vinculo_tipo,
            vinculo_id=vinculo_id,
        )
        .execution_options(synchronize_session=False)
    )
    sesion.flush()


def marcar_cuarentena_revisada(
    organizacion_id: UUID,
    sesion: Session,
    cuarentena_id: UUID,
    *,
    usuario_id: UUID,
    momento: datetime,
    comentario: str,
    vinculo_tipo: str | None,
    vinculo_id: UUID | None,
) -> None:
    """Escribe la revisión de la cuarentena (columnas `revisado_*`, comentario y vínculo)."""
    sesion.execute(
        update(ComandoCuarentena)
        .where(
            ComandoCuarentena.organizacion_id == organizacion_id,
            ComandoCuarentena.id == cuarentena_id,
        )
        .values(
            revisado_en=momento,
            revisado_por_id=usuario_id,
            comentario=comentario,
            vinculo_tipo=vinculo_tipo,
            vinculo_id=vinculo_id,
        )
        .execution_options(synchronize_session=False)
    )
    sesion.flush()


@dataclass(frozen=True)
class FiltroDeBandeja:
    """Filtros de la bandeja (D3). `estado` es `PENDIENTE` (operaciones con al menos un aviso
    pendiente), `RESUELTA` (todos resueltos) o `TODAS`. `desde` incluye y `hasta` excluye, sobre
    el momento de llegada (`registered_at`) del comando."""

    estado: str = PENDIENTE
    codigos: Sequence[str] = ()
    tipos: Sequence[str] = ()
    usuario_id: UUID | None = None
    jornada_id: UUID | None = None
    desde: datetime | None = None
    hasta: datetime | None = None


@dataclass(frozen=True)
class ClaveDeOperacion:
    operacion_tipo: str
    operacion_id: UUID
    llegada: datetime


@dataclass(frozen=True)
class FilaDeObservacion:
    """Una observación con los datos del comando que la produjo."""

    id: UUID
    operacion_tipo: str
    operacion_id: UUID
    codigo: str
    detalle: dict[str, object] | None
    estado: str
    resuelto_por_id: UUID | None
    resuelto_en: datetime | None
    comentario: str | None
    usuario_id: UUID
    dispositivo_id: UUID
    jornada_id: UUID | None
    modo: str
    occurred_at: datetime
    registered_at: datetime


def _union_con_comando() -> object:
    return and_(
        Comando.organizacion_id == Observacion.organizacion_id,
        Comando.id == Observacion.comando_id,
    )


def pagina_de_operaciones(
    organizacion_id: UUID,
    sesion: Session,
    filtro: FiltroDeBandeja,
    *,
    despues_de: tuple[datetime, UUID] | None,
    limite: int,
) -> list[ClaveDeOperacion]:
    """Las operaciones observadas que cumplen el filtro, de la llegada más reciente a la más
    antigua, agrupadas en la base (`limite` + 1 si hay más: lo decide quien llama). Los filtros de
    código, usuario, jornada y fechas restringen las filas antes de agrupar."""
    llegada = func.min(Comando.registered_at)
    consulta = (
        select(Observacion.operacion_tipo, Observacion.operacion_id, llegada.label("llegada"))
        .join(Comando, _union_con_comando())  # type: ignore[arg-type]
        .where(Observacion.organizacion_id == organizacion_id)
        .group_by(Observacion.operacion_tipo, Observacion.operacion_id)
        .order_by(llegada.desc(), Observacion.operacion_id.desc())
        .limit(limite)
    )
    if filtro.codigos:
        consulta = consulta.where(Observacion.codigo.in_(filtro.codigos))
    if filtro.tipos:
        consulta = consulta.where(Observacion.operacion_tipo.in_(filtro.tipos))
    if filtro.usuario_id is not None:
        consulta = consulta.where(Comando.usuario_id == filtro.usuario_id)
    if filtro.jornada_id is not None:
        consulta = consulta.where(Comando.jornada_id == filtro.jornada_id)
    if filtro.desde is not None:
        consulta = consulta.where(Comando.registered_at >= filtro.desde)
    if filtro.hasta is not None:
        consulta = consulta.where(Comando.registered_at < filtro.hasta)
    if filtro.estado == PENDIENTE:
        consulta = consulta.having(func.bool_or(Observacion.estado == PENDIENTE))
    elif filtro.estado == RESUELTA:
        consulta = consulta.having(func.bool_and(Observacion.estado == RESUELTA))
    if despues_de is not None:
        consulta = consulta.having(
            tuple_(llegada, Observacion.operacion_id)
            < tuple_(literal(despues_de[0]), literal(despues_de[1]))
        )
    return [
        ClaveDeOperacion(fila.operacion_tipo, fila.operacion_id, fila.llegada)
        for fila in sesion.execute(consulta)
    ]


def observaciones_de_operaciones(
    organizacion_id: UUID, sesion: Session, claves: Sequence[ClaveDeOperacion]
) -> list[FilaDeObservacion]:
    """TODAS las observaciones de las operaciones indicadas (no solo las que cumplieron el filtro
    de código), en una consulta, con los datos de su comando."""
    if not claves:
        return []
    consulta = (
        select(
            Observacion.id,
            Observacion.operacion_tipo,
            Observacion.operacion_id,
            Observacion.codigo,
            Observacion.detalle,
            Observacion.estado,
            Observacion.resuelto_por_id,
            Observacion.resuelto_en,
            Observacion.comentario,
            Comando.usuario_id,
            Comando.dispositivo_id,
            Comando.jornada_id,
            Comando.modo,
            Comando.occurred_at,
            Comando.registered_at,
        )
        .join(Comando, _union_con_comando())  # type: ignore[arg-type]
        .where(
            Observacion.organizacion_id == organizacion_id,
            tuple_(Observacion.operacion_tipo, Observacion.operacion_id).in_(
                [(clave.operacion_tipo, clave.operacion_id) for clave in claves]
            ),
        )
        .order_by(Observacion.id)
    )
    return [
        FilaDeObservacion(
            id=fila.id,
            operacion_tipo=fila.operacion_tipo,
            operacion_id=fila.operacion_id,
            codigo=fila.codigo,
            detalle=fila.detalle,
            estado=fila.estado,
            resuelto_por_id=fila.resuelto_por_id,
            resuelto_en=fila.resuelto_en,
            comentario=fila.comentario,
            usuario_id=fila.usuario_id,
            dispositivo_id=fila.dispositivo_id,
            jornada_id=fila.jornada_id,
            modo=fila.modo,
            occurred_at=fila.occurred_at,
            registered_at=fila.registered_at,
        )
        for fila in sesion.execute(consulta)
    ]


def pendientes_por_codigo(organizacion_id: UUID, sesion: Session) -> dict[str, int]:
    """Observaciones pendientes por código, contadas en la base sobre el índice parcial."""
    consulta = (
        select(Observacion.codigo, func.count())
        .where(Observacion.organizacion_id == organizacion_id, Observacion.estado == PENDIENTE)
        .group_by(Observacion.codigo)
    )
    return {codigo: cantidad for codigo, cantidad in sesion.execute(consulta)}


def contar_rechazos_pendientes(organizacion_id: UUID, sesion: Session) -> int:
    consulta = (
        select(func.count())
        .select_from(ComandoRechazado)
        .where(
            ComandoRechazado.organizacion_id == organizacion_id,
            ComandoRechazado.estado == "PENDIENTE",
        )
    )
    return int(sesion.scalar(consulta) or 0)


def contar_cuarentenas_pendientes(organizacion_id: UUID, sesion: Session) -> int:
    consulta = (
        select(func.count())
        .select_from(ComandoCuarentena)
        .where(
            ComandoCuarentena.organizacion_id == organizacion_id,
            ComandoCuarentena.revisado_en.is_(None),
        )
    )
    return int(sesion.scalar(consulta) or 0)


@dataclass(frozen=True)
class FiltroDeRechazos:
    """Filtros de la lista de rechazos (D6, D7). `estado` es `PENDIENTE`, `RESUELTO` o `TODOS`;
    `origen` es `RECHAZO`, `CUARENTENA` o `None` (los dos). La cuarentena no tiene jornada: con
    `jornada_id` solo entran rechazos."""

    estado: str = PENDIENTE
    origen: str | None = None
    tipos: Sequence[str] = ()
    usuario_id: UUID | None = None
    jornada_id: UUID | None = None


@dataclass(frozen=True)
class FilaDeRechazo:
    """Un rechazo o una cuarentena, con `origen` que dice cuál de las dos tablas es."""

    origen: str
    id: UUID
    operation_id: UUID
    tipo: str
    usuario_id: UUID
    dispositivo_id: UUID
    jornada_id: UUID | None
    codigo: str
    recibido_en: datetime
    occurred_at: datetime | None
    estado: str
    resuelto_por_id: UUID | None
    resuelto_en: datetime | None
    comentario: str | None
    vinculo_tipo: str | None
    vinculo_id: UUID | None
    contenido: object


def _columnas_de_rechazo() -> list[object]:
    r = ComandoRechazado
    return [
        literal("RECHAZO").label("origen"),
        r.id.label("id"),
        r.organizacion_id.label("organizacion_id"),
        r.operation_id.label("operation_id"),
        r.tipo.label("tipo"),
        r.usuario_id.label("usuario_id"),
        r.dispositivo_id.label("dispositivo_id"),
        r.jornada_id.label("jornada_id"),
        r.error_codigo.label("codigo"),
        r.recibido_en.label("recibido_en"),
        r.occurred_at.label("occurred_at"),
        r.estado.label("estado"),
        r.resuelto_por_id.label("resuelto_por_id"),
        r.resuelto_en.label("resuelto_en"),
        r.comentario.label("comentario"),
        r.vinculo_tipo.label("vinculo_tipo"),
        r.vinculo_id.label("vinculo_id"),
        r.contenido.label("contenido"),
    ]


def _columnas_de_cuarentena() -> list[object]:
    c = ComandoCuarentena
    return [
        literal("CUARENTENA").label("origen"),
        c.id.label("id"),
        c.organizacion_id.label("organizacion_id"),
        c.operation_id.label("operation_id"),
        c.tipo.label("tipo"),
        c.usuario_id.label("usuario_id"),
        c.dispositivo_id.label("dispositivo_id"),
        cast(null(), Uuid).label("jornada_id"),
        c.motivo.label("codigo"),
        c.recibido_en.label("recibido_en"),
        cast(null(), DateTime(timezone=True)).label("occurred_at"),
        case((c.revisado_en.is_(None), PENDIENTE), else_=RESUELTO).label("estado"),
        c.revisado_por_id.label("resuelto_por_id"),
        c.revisado_en.label("resuelto_en"),
        c.comentario.label("comentario"),
        c.vinculo_tipo.label("vinculo_tipo"),
        c.vinculo_id.label("vinculo_id"),
        c.contenido.label("contenido"),
    ]


def _rechazos_y_cuarentenas(organizacion_id: UUID, filtro: FiltroDeRechazos) -> object:
    """`UNION ALL` de las dos tablas, ya filtradas por organización y por el filtro (INV-21)."""
    partes = []
    if filtro.origen in (None, "RECHAZO"):
        consulta = select(*_columnas_de_rechazo()).where(  # type: ignore[call-overload]
            ComandoRechazado.organizacion_id == organizacion_id
        )
        if filtro.estado != "TODOS":
            consulta = consulta.where(
                ComandoRechazado.estado == (PENDIENTE if filtro.estado == PENDIENTE else RESUELTO)
            )
        if filtro.tipos:
            consulta = consulta.where(ComandoRechazado.tipo.in_(filtro.tipos))
        if filtro.usuario_id is not None:
            consulta = consulta.where(ComandoRechazado.usuario_id == filtro.usuario_id)
        if filtro.jornada_id is not None:
            consulta = consulta.where(ComandoRechazado.jornada_id == filtro.jornada_id)
        partes.append(consulta)
    if filtro.origen in (None, "CUARENTENA") and filtro.jornada_id is None:
        consulta = select(*_columnas_de_cuarentena()).where(  # type: ignore[call-overload]
            ComandoCuarentena.organizacion_id == organizacion_id
        )
        if filtro.estado == PENDIENTE:
            consulta = consulta.where(ComandoCuarentena.revisado_en.is_(None))
        elif filtro.estado == RESUELTO:
            consulta = consulta.where(ComandoCuarentena.revisado_en.is_not(None))
        if filtro.tipos:
            consulta = consulta.where(ComandoCuarentena.tipo.in_(filtro.tipos))
        if filtro.usuario_id is not None:
            consulta = consulta.where(ComandoCuarentena.usuario_id == filtro.usuario_id)
        partes.append(consulta)
    return union_all(*partes).subquery() if partes else None


def _a_fila(fila: object) -> FilaDeRechazo:
    return FilaDeRechazo(
        origen=fila.origen,  # type: ignore[attr-defined]
        id=fila.id,  # type: ignore[attr-defined]
        operation_id=fila.operation_id,  # type: ignore[attr-defined]
        tipo=fila.tipo,  # type: ignore[attr-defined]
        usuario_id=fila.usuario_id,  # type: ignore[attr-defined]
        dispositivo_id=fila.dispositivo_id,  # type: ignore[attr-defined]
        jornada_id=fila.jornada_id,  # type: ignore[attr-defined]
        codigo=fila.codigo,  # type: ignore[attr-defined]
        recibido_en=fila.recibido_en,  # type: ignore[attr-defined]
        occurred_at=fila.occurred_at,  # type: ignore[attr-defined]
        estado=fila.estado,  # type: ignore[attr-defined]
        resuelto_por_id=fila.resuelto_por_id,  # type: ignore[attr-defined]
        resuelto_en=fila.resuelto_en,  # type: ignore[attr-defined]
        comentario=fila.comentario,  # type: ignore[attr-defined]
        vinculo_tipo=fila.vinculo_tipo,  # type: ignore[attr-defined]
        vinculo_id=fila.vinculo_id,  # type: ignore[attr-defined]
        contenido=fila.contenido,  # type: ignore[attr-defined]
    )


def pagina_de_rechazos(
    organizacion_id: UUID,
    sesion: Session,
    filtro: FiltroDeRechazos,
    *,
    despues_de: tuple[datetime, UUID] | None,
    limite: int,
) -> list[FilaDeRechazo]:
    """Los rechazos y las cuarentenas de la organización, del más reciente al más antiguo
    (`recibido_en`, `id`), ordenados y paginados en la base (`limite` ya incluye el de más que
    usa quien llama para saber si hay otra página)."""
    union = _rechazos_y_cuarentenas(organizacion_id, filtro)
    if union is None:
        return []
    consulta = select(union).order_by(  # type: ignore[call-overload]
        union.c.recibido_en.desc(),  # type: ignore[attr-defined]
        union.c.id.desc(),  # type: ignore[attr-defined]
    )
    if despues_de is not None:
        consulta = consulta.where(
            tuple_(union.c.recibido_en, union.c.id)  # type: ignore[attr-defined]
            < tuple_(literal(despues_de[0]), literal(despues_de[1]))
        )
    return [_a_fila(fila) for fila in sesion.execute(consulta.limit(limite))]


def rechazo_o_cuarentena_por_id(
    organizacion_id: UUID, sesion: Session, id_: UUID
) -> FilaDeRechazo | None:
    """Un rechazo o una cuarentena de la organización por su `id` (los dos son UUIDv7 propios),
    o `None` si ninguna lo tiene (INV-21: uno de otra organización tampoco existe)."""
    union = _rechazos_y_cuarentenas(organizacion_id, FiltroDeRechazos(estado="TODOS"))
    assert union is not None
    fila = sesion.execute(select(union).where(union.c.id == id_)).first()  # type: ignore[attr-defined,call-overload]
    return None if fila is None else _a_fila(fila)


def operaciones_aceptadas_despues(
    organizacion_id: UUID, sesion: Session, operation_ids: Collection[UUID]
) -> set[UUID]:
    """Los `operation_id` que el servidor terminó aceptando (un reenvío posterior los aceptó): se
    cruzan con `comando` en una consulta (SYN-06)."""
    if not operation_ids:
        return set()
    consulta = select(Comando.operation_id).where(
        Comando.organizacion_id == organizacion_id,
        Comando.operation_id.in_(list(operation_ids)),
        Comando.estado.in_(("ACEPTADO", "ACEPTADO_CON_OBSERVACIONES")),
    )
    return set(sesion.scalars(consulta))
