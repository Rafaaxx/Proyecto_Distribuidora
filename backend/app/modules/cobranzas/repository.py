"""Acceso a datos de `cobranzas` (change 17; `design.md` D2, D16, D18).

Solo SQL: las reglas viven en `domain/` y el orden de las operaciones en `service.py`. Toda
función recibe `organizacion_id` como primer parámetro y filtra por él (INV-21,
`docs/02-arquitectura.md` §8). Sin `commit`: la transacción la gestiona el bus.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.cobranzas.domain.consultas import codificar_cursor, decodificar_cursor
from app.modules.cobranzas.domain.errores import (
    CobranzaDuplicadaError,
    CobranzaYaAnuladaError,
    RecursoNoEncontradoError,
)
from app.modules.cobranzas.models import Cobranza, CobranzaAnulacion, CobranzaMedio

FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""`cobranzas` no tiene catálogo global: toda función recibe `organizacion_id` primero."""


@dataclass(frozen=True)
class DatosDeCobranza:
    """Lo que se inserta de una cobranza. Nace siempre `CONFIRMADA`: no se inserta una cobranza
    ya anulada (COB-01, TR-06)."""

    id: UUID
    cliente_id: UUID
    venta_id: UUID | None
    origen: str
    importe: Decimal
    jornada_id: UUID | None
    observacion: str | None
    operation_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    registered_at: datetime


@dataclass(frozen=True)
class DatosDeMedioDeCobranza:
    medio_pago_id: UUID
    importe: Decimal
    referencia: str | None


def existe_cobranza(organizacion_id: UUID, sesion: Session, *, cobranza_id: UUID) -> bool:
    """Si la organización ya tiene una cobranza con ese identificador (`02` §9). La clave
    primaria es global: un identificador ocupado por otra organización lo traduce el guardado
    (`_guardar_con_traduccion`) al mismo `COBRANZA_DUPLICADA`, sin leer datos ajenos."""
    return (
        sesion.scalar(
            select(Cobranza.id).where(
                Cobranza.organizacion_id == organizacion_id, Cobranza.id == cobranza_id
            )
        )
        is not None
    )


def _guardar_con_traduccion(
    organizacion_id: UUID, sesion: Session, mutar: Callable[[], None]
) -> None:
    """Ejecuta `mutar` dentro de un `SAVEPOINT` y traduce la violación de integridad a un error
    de dominio de código estable: el identificador repetido (carrera con otro comando) a
    `COBRANZA_DUPLICADA` y una referencia inexistente o de otra organización (FK compuesta,
    INV-02) a 404. `mutar` DEBE ejecutar la mutación dentro de este `with`."""
    del organizacion_id  # No filtra nada: la mutación ya trae su organización.
    try:
        with sesion.begin_nested():
            mutar()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "pk_cobranza" in mensaje:
            raise CobranzaDuplicadaError(
                "El identificador de la cobranza ya fue usado por otra operación."
            ) from error
        if "fk_cobranza__cliente" in mensaje:
            raise RecursoNoEncontradoError(
                "El cliente indicado no existe en esta organización."
            ) from error
        if "fk_cobranza_medio__medio_pago" in mensaje:
            raise RecursoNoEncontradoError(
                "El medio de pago indicado no existe en esta organización."
            ) from error
        raise


def insertar_cobranza(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cobranza: DatosDeCobranza,
    medios: list[DatosDeMedioDeCobranza],
) -> Cobranza:
    """Inserta la cobranza `CONFIRMADA` y sus medios, en la transacción de quien llama (INV-01,
    INV-08: la suma de los medios la valida el dominio). La posición de cada medio (`orden`,
    desde 0) es la de la lista."""
    fila = Cobranza(
        id=cobranza.id,
        organizacion_id=organizacion_id,
        cliente_id=cobranza.cliente_id,
        venta_id=cobranza.venta_id,
        origen=cobranza.origen,
        importe=cobranza.importe,
        estado="CONFIRMADA",
        jornada_id=cobranza.jornada_id,
        observacion=cobranza.observacion,
        operation_id=cobranza.operation_id,
        usuario_id=cobranza.usuario_id,
        dispositivo_id=cobranza.dispositivo_id,
        occurred_at=cobranza.occurred_at,
        registered_at=cobranza.registered_at,
    )
    filas_de_medio = [
        CobranzaMedio(
            id=nuevo_id(),
            organizacion_id=organizacion_id,
            cobranza_id=cobranza.id,
            orden=orden,
            medio_pago_id=medio.medio_pago_id,
            importe=medio.importe,
            referencia=medio.referencia,
        )
        for orden, medio in enumerate(medios)
    ]

    def _mutar() -> None:
        sesion.add(fila)
        sesion.flush()  # la cobranza antes que sus medios (FK compuesta)
        for medio in filas_de_medio:
            sesion.add(medio)

    _guardar_con_traduccion(organizacion_id, sesion, _mutar)
    return fila


def obtener_cobranza(organizacion_id: UUID, cobranza_id: UUID, sesion: Session) -> Cobranza | None:
    """La cobranza de la organización sin bloquearla (INV-21: otra organización no existe)."""
    return sesion.scalar(
        select(Cobranza).where(
            Cobranza.organizacion_id == organizacion_id, Cobranza.id == cobranza_id
        )
    )


def obtener_cobranza_de_venta(
    organizacion_id: UUID, venta_id: UUID, sesion: Session
) -> Cobranza | None:
    """La cobranza en el acto de una venta (origen `VENTA`), sin bloquearla, o `None`. A lo
    sumo una por venta (VTA-11); una de otra organización no se devuelve (INV-21)."""
    return sesion.scalar(
        select(Cobranza).where(
            Cobranza.organizacion_id == organizacion_id, Cobranza.venta_id == venta_id
        )
    )


def obtener_cobranza_para_actualizar(
    organizacion_id: UUID, cobranza_id: UUID, sesion: Session
) -> Cobranza | None:
    """La cobranza bloqueada `FOR UPDATE`, con el estado releído de la base (D18: la anulación
    revalida con la fila tomada, antes del saldo)."""
    return sesion.scalar(
        select(Cobranza)
        .where(Cobranza.organizacion_id == organizacion_id, Cobranza.id == cobranza_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


@dataclass(frozen=True)
class DatosDeAnulacion:
    """Lo que se inserta de la anulación de una cobranza (COB-05)."""

    cobranza_id: UUID
    motivo_id: UUID
    observacion: str | None
    operation_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    registered_at: datetime


def marcar_anulada(
    organizacion_id: UUID, sesion: Session, *, cobranza: Cobranza, anulacion: DatosDeAnulacion
) -> CobranzaAnulacion:
    """Deja la cobranza `ANULADA` (la única columna que `app_runtime` puede actualizar, INV-05) e
    inserta su anulación. El `UNIQUE` de `cobranza_id` impide dos anulaciones aunque se saltara
    el bloqueo del servicio (D16)."""
    fila = CobranzaAnulacion(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        cobranza_id=anulacion.cobranza_id,
        motivo_id=anulacion.motivo_id,
        observacion=anulacion.observacion,
        operation_id=anulacion.operation_id,
        usuario_id=anulacion.usuario_id,
        dispositivo_id=anulacion.dispositivo_id,
        occurred_at=anulacion.occurred_at,
        registered_at=anulacion.registered_at,
    )
    try:
        with sesion.begin_nested():
            cobranza.estado = "ANULADA"
            sesion.add(fila)
            sesion.flush()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        if "ux_cobranza_anulacion__cobranza" in mensaje:
            raise CobranzaYaAnuladaError("La cobranza ya está anulada.") from error
        if "fk_cobranza_anulacion__motivo" in mensaje:
            raise RecursoNoEncontradoError(
                "El motivo indicado no existe en esta organización."
            ) from error
        raise
    return fila


def listar_cobranzas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    limite: int,
    cursor: str | None,
    cliente_id: UUID | None,
    estado: str | None,
    usuario_id: UUID | None,
    jornada_id: UUID | None,
    desde: datetime | None,
    hasta: datetime | None,
) -> tuple[list[Cobranza], str | None]:
    """Cobranzas de la organización de la más reciente a la más vieja, por cursor
    `(occurred_at, id)` descendente (índices `ix_cobranza__occurred_at` y `ix_cobranza__cliente`,
    D16). `desde` es inclusivo y `hasta` exclusivo (instantes: ver `rango_de_instantes`).
    Devuelve `(filas, cursor_siguiente)`."""
    consulta = select(Cobranza).where(Cobranza.organizacion_id == organizacion_id)
    if cliente_id is not None:
        consulta = consulta.where(Cobranza.cliente_id == cliente_id)
    if estado is not None:
        consulta = consulta.where(Cobranza.estado == estado)
    if usuario_id is not None:
        consulta = consulta.where(Cobranza.usuario_id == usuario_id)
    if jornada_id is not None:
        consulta = consulta.where(Cobranza.jornada_id == jornada_id)
    if desde is not None:
        consulta = consulta.where(Cobranza.occurred_at >= desde)
    if hasta is not None:
        consulta = consulta.where(Cobranza.occurred_at < hasta)
    if cursor is not None:
        momento, id_cursor = decodificar_cursor(cursor)
        consulta = consulta.where(tuple_(Cobranza.occurred_at, Cobranza.id) < (momento, id_cursor))
    consulta = consulta.order_by(Cobranza.occurred_at.desc(), Cobranza.id.desc()).limit(limite + 1)

    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite:
        pagina = filas[:limite]
        ultima = pagina[-1]
        return pagina, codificar_cursor(ultima.occurred_at, ultima.id)
    return filas, None


def listar_medios_de_cobranza(
    organizacion_id: UUID, cobranza_id: UUID, sesion: Session
) -> list[CobranzaMedio]:
    """Los medios de la cobranza en el orden en que se cargaron (a lo sumo 20, D2)."""
    return list(
        sesion.scalars(
            select(CobranzaMedio)
            .where(
                CobranzaMedio.organizacion_id == organizacion_id,
                CobranzaMedio.cobranza_id == cobranza_id,
            )
            .order_by(CobranzaMedio.orden)
        ).all()
    )


def obtener_anulacion(
    organizacion_id: UUID, cobranza_id: UUID, sesion: Session
) -> CobranzaAnulacion | None:
    """La anulación de la cobranza, si la tiene (a lo sumo una, D16)."""
    return sesion.scalar(
        select(CobranzaAnulacion).where(
            CobranzaAnulacion.organizacion_id == organizacion_id,
            CobranzaAnulacion.cobranza_id == cobranza_id,
        )
    )
