"""Casos de uso de lectura de `descuentos` para su propia API (`CLAUDE.md` §7; change 16).
Interno del módulo: `descuentos/api.py` lo usa para armar las respuestas de sus rutas; los otros
módulos leen `descuentos` por `service.py`.

Toda lectura filtra por la organización del token y responde `RecursoNoEncontradoError` (404) si
la regla no existe en ella (INV-21, SEG-07). Los nombres de las entidades de los alcances vienen
de `catalogo/service.py` en una consulta por tipo de entidad: `descuentos` no importa sus modelos
ni sus repositorios (D19).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.catalogo import service as catalogo_service
from app.modules.descuentos import repository
from app.modules.descuentos.domain.errores import RecursoNoEncontradoError
from app.modules.descuentos.domain.estados import estado_derivado
from app.modules.descuentos.models import ReglaDescuento, ReglaDescuentoAlcance
from app.modules.descuentos.schemas import (
    AccionTipoApi,
    AlcanceReglaResponse,
    EstadoReglaApi,
    MedidaApi,
    OperadorApi,
    ReglaDescuentoResponse,
    ReglasDescuentoResponse,
    TipoAlcanceApi,
    TipoReglaApi,
)


def _nombres_de_alcances(
    organizacion_id: UUID, alcances: Sequence[ReglaDescuentoAlcance], sesion: Session
) -> dict[tuple[str, UUID], str]:
    """`{(tipo, entidad_id): nombre}` de todos los alcances, en una consulta por tipo."""
    consultas = {
        "PRODUCTO": catalogo_service.nombres_de_productos,
        "CATEGORIA": catalogo_service.nombres_de_categorias,
        "MARCA": catalogo_service.nombres_de_marcas,
    }
    nombres: dict[tuple[str, UUID], str] = {}
    for tipo, consulta in consultas.items():
        ids = {a.alcance_id for a in alcances if a.alcance_tipo == tipo}
        if ids:
            for entidad_id, nombre in consulta(organizacion_id, ids, sesion).items():
                nombres[(tipo, entidad_id)] = nombre
    return nombres


def _como_respuesta(
    regla: ReglaDescuento,
    alcances: Sequence[ReglaDescuentoAlcance],
    nombres: dict[tuple[str, UUID], str],
    ahora: datetime,
) -> ReglaDescuentoResponse:
    return ReglaDescuentoResponse(
        id=regla.id,
        nombre=regla.nombre,
        tipo=cast(TipoReglaApi, regla.tipo),
        medida=cast(MedidaApi, regla.medida),
        operador=cast(OperadorApi, regla.operador),
        umbral=str(regla.umbral),
        accion_tipo=cast(AccionTipoApi, regla.accion_tipo),
        accion_porcentaje=None if regla.accion_porcentaje is None else str(regla.accion_porcentaje),
        accion_importe=None if regla.accion_importe is None else str(regla.accion_importe),
        prioridad=regla.prioridad,
        acumulable=regla.acumulable,
        vigencia_desde=regla.vigencia_desde,
        vigencia_hasta=regla.vigencia_hasta,
        estado=cast(EstadoReglaApi, estado_derivado(regla, ahora)),
        alcances=[
            AlcanceReglaResponse(
                tipo=cast(TipoAlcanceApi, a.alcance_tipo),
                entidad_id=a.alcance_id,
                nombre=nombres.get((a.alcance_tipo, a.alcance_id), ""),
            )
            for a in alcances
        ],
        creado_en=regla.creado_en,
        actualizado_en=regla.actualizado_en,
    )


def obtener_regla(
    organizacion_id: UUID, regla_id: UUID, sesion: Session, *, ahora: datetime
) -> ReglaDescuentoResponse:
    """La regla con sus alcances y el nombre de cada entidad; 404 si no existe en la
    organización. Es la respuesta de las cuatro escrituras."""
    regla = repository.obtener_regla(organizacion_id, regla_id, sesion)
    if regla is None:
        raise RecursoNoEncontradoError(f"La regla {regla_id} no existe en esta organización.")
    alcances = repository.listar_alcances(organizacion_id, [regla_id], sesion)[regla_id]
    nombres = _nombres_de_alcances(organizacion_id, alcances, sesion)
    return _como_respuesta(regla, alcances, nombres, ahora)


def listar_reglas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    estado: EstadoReglaApi | None,
    ahora: datetime,
    limite: int,
    cursor: str | None,
) -> ReglasDescuentoResponse:
    """Una página de reglas con sus alcances y el nombre de cada entidad, en tres consultas
    (reglas, alcances y nombres por tipo), sin sumar nada en Python."""
    reglas, siguiente = repository.listar_reglas_paginado(
        organizacion_id, sesion, estado=estado, ahora=ahora, limite=limite, cursor=cursor
    )
    por_regla = repository.listar_alcances(organizacion_id, [r.id for r in reglas], sesion)
    todos = [a for lista in por_regla.values() for a in lista]
    nombres = _nombres_de_alcances(organizacion_id, todos, sesion)
    return ReglasDescuentoResponse(
        items=[_como_respuesta(r, por_regla[r.id], nombres, ahora) for r in reglas],
        siguiente_cursor=siguiente,
    )
