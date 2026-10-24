"""Acceso a datos de `descuentos` (`docs/02-arquitectura.md` §8, `CLAUDE.md` §4). Mismo contrato
no negociable que `precios/repository.py`: todo método público recibe `organizacion_id` como
primer parámetro obligatorio y lo usa para filtrar toda consulta
(`tests/unit/test_repositorios_organizacion_obligatoria.py`).

`guardar_con_traduccion_de_integridad` ejecuta la mutación dentro de un `SAVEPOINT`
(`begin_nested`) para que un `IntegrityError` no deje la sesión inutilizable. Una clave foránea
compuesta que rechaza una entidad de otra organización o inexistente se traduce a
`RECURSO_NO_ENCONTRADO` (404, INV-21; mismo criterio que ADR-035).

La carga de relaciones es siempre explícita: este módulo no declara `relationship()`.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Collection, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.descuentos.domain.errores import CursorInvalidoError, RecursoNoEncontradoError
from app.modules.descuentos.models import ReglaDescuento, ReglaDescuentoAlcance

LIMITE_PAGINA_MAXIMO = 100
LIMITE_PAGINA_DEFAULT = 50

FUNCIONES_SIN_ORGANIZACION_ID: frozenset[str] = frozenset()
"""Ninguna: toda lectura y escritura de `descuentos` filtra por organización (INV-21)."""

_FK_A_RECURSO = {
    "fk_regla_descuento_alcance__regla": "La regla",
    "fk_regla_descuento_alcance__producto": "El producto",
    "fk_regla_descuento_alcance__categoria": "La categoría",
    "fk_regla_descuento_alcance__marca": "La marca",
}


def guardar_con_traduccion_de_integridad(
    organizacion_id: UUID, sesion: Session, mutar: Callable[[], None]
) -> None:
    """`mutar` DEBE ejecutar la mutación (`sesion.add(...)` o las asignaciones de atributos)
    DENTRO de este `with`, nunca antes de llamarlo."""
    del organizacion_id  # No filtra nada: la mutación ya trae su organización.
    try:
        with sesion.begin_nested():
            mutar()
    except IntegrityError as error:
        mensaje = str(getattr(error, "orig", error))
        for restriccion, recurso in _FK_A_RECURSO.items():
            if restriccion in mensaje:
                raise RecursoNoEncontradoError(
                    f"{recurso} no existe en esta organización."
                ) from error
        raise


# --- reglas -------------------------------------------------------------------------------


def crear_regla(
    organizacion_id: UUID,
    sesion: Session,
    *,
    regla_id: UUID,
    nombre: str,
    tipo: str,
    medida: str,
    operador: str,
    umbral: Decimal,
    accion_tipo: str,
    accion_porcentaje: Decimal | None,
    accion_importe: Decimal | None,
    prioridad: int,
    acumulable: bool,
    vigencia_desde: datetime | None,
    vigencia_hasta: datetime | None,
    estado: str,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> ReglaDescuento:
    regla = ReglaDescuento(
        id=regla_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        tipo=tipo,
        medida=medida,
        operador=operador,
        umbral=umbral,
        accion_tipo=accion_tipo,
        accion_porcentaje=accion_porcentaje,
        accion_importe=accion_importe,
        prioridad=prioridad,
        acumulable=acumulable,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        estado=estado,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(regla))
    return regla


def obtener_regla(organizacion_id: UUID, regla_id: UUID, sesion: Session) -> ReglaDescuento | None:
    return sesion.scalars(
        select(ReglaDescuento)
        .where(ReglaDescuento.organizacion_id == organizacion_id, ReglaDescuento.id == regla_id)
        .execution_options(populate_existing=True)
    ).one_or_none()


def nombres_de_reglas(
    organizacion_id: UUID, regla_ids: frozenset[UUID], sesion: Session
) -> dict[UUID, str]:
    """El nombre de cada regla pedida de la organización, en una sola consulta."""
    if not regla_ids:
        return {}
    filas = sesion.execute(
        select(ReglaDescuento.id, ReglaDescuento.nombre).where(
            ReglaDescuento.organizacion_id == organizacion_id, ReglaDescuento.id.in_(regla_ids)
        )
    ).all()
    return {regla_id: nombre for regla_id, nombre in filas}


def obtener_regla_para_actualizar(
    organizacion_id: UUID, regla_id: UUID, sesion: Session
) -> ReglaDescuento | None:
    """La regla con su fila bloqueada (`FOR UPDATE`): dos transiciones o ediciones simultáneas
    de la misma regla se serializan y la segunda revalida el estado que dejó la primera."""
    return sesion.scalars(
        select(ReglaDescuento)
        .where(ReglaDescuento.organizacion_id == organizacion_id, ReglaDescuento.id == regla_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def reemplazar_datos_de_borrador(
    organizacion_id: UUID,
    sesion: Session,
    regla: ReglaDescuento,
    *,
    nombre: str,
    tipo: str,
    medida: str,
    operador: str,
    umbral: Decimal,
    accion_tipo: str,
    accion_porcentaje: Decimal | None,
    accion_importe: Decimal | None,
    prioridad: int,
    acumulable: bool,
    vigencia_desde: datetime | None,
    vigencia_hasta: datetime | None,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> ReglaDescuento:
    def mutar() -> None:
        regla.nombre = nombre
        regla.tipo = tipo
        regla.medida = medida
        regla.operador = operador
        regla.umbral = umbral
        regla.accion_tipo = accion_tipo
        regla.accion_porcentaje = accion_porcentaje
        regla.accion_importe = accion_importe
        regla.prioridad = prioridad
        regla.acumulable = acumulable
        regla.vigencia_desde = vigencia_desde
        regla.vigencia_hasta = vigencia_hasta
        regla.actualizado_en = momento
        regla.actualizado_por_id = actualizado_por_id
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return regla


def cambiar_estado(
    organizacion_id: UUID,
    sesion: Session,
    regla: ReglaDescuento,
    *,
    estado: str,
    vigencia_desde: datetime | None,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> ReglaDescuento:
    def mutar() -> None:
        regla.estado = estado
        regla.vigencia_desde = vigencia_desde
        regla.actualizado_en = momento
        regla.actualizado_por_id = actualizado_por_id
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return regla


def fijar_vigencia_hasta(
    organizacion_id: UUID,
    sesion: Session,
    regla: ReglaDescuento,
    *,
    vigencia_hasta: datetime | None,
    momento: datetime,
    actualizado_por_id: UUID | None,
) -> ReglaDescuento:
    def mutar() -> None:
        regla.vigencia_hasta = vigencia_hasta
        regla.actualizado_en = momento
        regla.actualizado_por_id = actualizado_por_id
        sesion.flush()

    guardar_con_traduccion_de_integridad(organizacion_id, sesion, mutar)
    return regla


def listar_reglas_aplicables(
    organizacion_id: UUID, momento: datetime, sesion: Session
) -> list[ReglaDescuento]:
    """Las reglas `ACTIVA` vigentes en `momento` (`desde <= momento < hasta`, D16), por prioridad
    y, a igual prioridad, por antigüedad (el identificador es un UUIDv7 ordenable)."""
    return list(
        sesion.scalars(
            select(ReglaDescuento)
            .where(
                ReglaDescuento.organizacion_id == organizacion_id,
                ReglaDescuento.estado == "ACTIVA",
                ReglaDescuento.vigencia_desde <= momento,
                or_(
                    ReglaDescuento.vigencia_hasta.is_(None),
                    ReglaDescuento.vigencia_hasta > momento,
                ),
            )
            .order_by(ReglaDescuento.prioridad, ReglaDescuento.id)
            .execution_options(populate_existing=True)
        )
    )


def _codificar_cursor(regla_id: UUID) -> str:
    return base64.urlsafe_b64encode(str(regla_id).encode("ascii")).decode("ascii")


def _decodificar_cursor(cursor: str) -> UUID:
    try:
        return UUID(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
    except ValueError as error:  # incluye UnicodeError, binascii.Error y UUID inválido
        raise CursorInvalidoError("El cursor de paginación no es válido.") from error


def listar_reglas_paginado(
    organizacion_id: UUID,
    sesion: Session,
    *,
    estado: str | None,
    ahora: datetime,
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> tuple[list[ReglaDescuento], str | None]:
    """Las reglas de la organización de la más nueva a la más vieja (el identificador es un
    UUIDv7 ordenable), paginadas por cursor (`02` §11). `estado` filtra por el estado que se
    informa: `VENCIDA` es derivado (activa o pausada con la vigencia hasta ya pasada, `01` §18) y
    por eso `ACTIVA` y `PAUSADA` excluyen las vencidas. Devuelve `(reglas, cursor_siguiente)`; el
    cursor es `None` en la última página."""
    limite_efectivo = min(max(limite, 1), LIMITE_PAGINA_MAXIMO)
    consulta = select(ReglaDescuento).where(ReglaDescuento.organizacion_id == organizacion_id)
    vencida = and_(
        ReglaDescuento.estado.in_(("ACTIVA", "PAUSADA")),
        ReglaDescuento.vigencia_hasta.is_not(None),
        ReglaDescuento.vigencia_hasta <= ahora,
    )
    if estado == "VENCIDA":
        consulta = consulta.where(vencida)
    elif estado == "BORRADOR":
        consulta = consulta.where(ReglaDescuento.estado == "BORRADOR")
    elif estado is not None:
        consulta = consulta.where(ReglaDescuento.estado == estado, ~vencida)
    if cursor is not None:
        consulta = consulta.where(ReglaDescuento.id < _decodificar_cursor(cursor))
    consulta = (
        consulta.order_by(ReglaDescuento.id.desc())
        .limit(limite_efectivo + 1)
        .execution_options(populate_existing=True)
    )
    filas = list(sesion.scalars(consulta).all())
    if len(filas) > limite_efectivo:
        pagina = filas[:limite_efectivo]
        return pagina, _codificar_cursor(pagina[-1].id)
    return filas, None


# --- alcances -----------------------------------------------------------------------------


def insertar_alcance(
    organizacion_id: UUID,
    sesion: Session,
    *,
    regla_id: UUID,
    alcance_tipo: str,
    alcance_id: UUID,
    momento: datetime,
) -> ReglaDescuentoAlcance:
    alcance = ReglaDescuentoAlcance(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        regla_id=regla_id,
        alcance_tipo=alcance_tipo,
        alcance_id=alcance_id,
        creado_en=momento,
    )
    guardar_con_traduccion_de_integridad(organizacion_id, sesion, lambda: sesion.add(alcance))
    return alcance


def borrar_alcances_de_borrador(organizacion_id: UUID, sesion: Session, regla_id: UUID) -> None:
    """Único `DELETE` del módulo (`app_runtime` solo lo tiene sobre esta tabla, D17): el
    servicio lo llama únicamente para reemplazar los alcances de una regla en `BORRADOR`."""
    sesion.execute(
        delete(ReglaDescuentoAlcance).where(
            ReglaDescuentoAlcance.organizacion_id == organizacion_id,
            ReglaDescuentoAlcance.regla_id == regla_id,
        )
    )
    sesion.flush()
    sesion.expire_all()


def listar_alcances(
    organizacion_id: UUID, regla_ids: Collection[UUID], sesion: Session
) -> dict[UUID, list[ReglaDescuentoAlcance]]:
    """Los alcances de cada regla pedida, en un orden estable (tipo y entidad)."""
    if not regla_ids:
        return {}
    filas = sesion.scalars(
        select(ReglaDescuentoAlcance)
        .where(
            ReglaDescuentoAlcance.organizacion_id == organizacion_id,
            ReglaDescuentoAlcance.regla_id.in_(regla_ids),
        )
        .order_by(
            ReglaDescuentoAlcance.regla_id,
            ReglaDescuentoAlcance.alcance_tipo,
            ReglaDescuentoAlcance.alcance_id,
        )
        .execution_options(populate_existing=True)
    )
    por_regla: dict[UUID, list[ReglaDescuentoAlcance]] = {
        identificador: [] for identificador in regla_ids
    }
    for fila in filas:
        por_regla[fila.regla_id].append(fila)
    return por_regla


def insertar_alcances(
    organizacion_id: UUID,
    sesion: Session,
    *,
    regla_id: UUID,
    alcances: Sequence[tuple[str, UUID]],
    momento: datetime,
) -> None:
    for alcance_tipo, alcance_id in alcances:
        insertar_alcance(
            organizacion_id,
            sesion,
            regla_id=regla_id,
            alcance_tipo=alcance_tipo,
            alcance_id=alcance_id,
            momento=momento,
        )
