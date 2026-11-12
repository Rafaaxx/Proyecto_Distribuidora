"""Casos de uso de lectura de `cobranzas` (`02` §5.1; change 17, tarea 10.1, `design.md` D14).

Solo lee: ninguna función escribe ni bloquea. Todas reciben `organizacion_id` primero y lo usan
para filtrar (INV-21): una cobranza de otra organización es inexistente
(`RecursoNoEncontradoError`, 404). Los nombres de cliente, usuario, medio y motivo se resuelven por
el `service.py` de su módulo (`CLAUDE.md` §4), por lote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.clientes import service as clientes_service
from app.modules.cobranzas import repository
from app.modules.cobranzas.domain.consultas import acotar_limite, rango_de_instantes
from app.modules.cobranzas.domain.errores import RecursoNoEncontradoError
from app.modules.cobranzas.models import Cobranza, CobranzaAnulacion
from app.modules.configuracion import service as configuracion_service
from app.modules.identidad import service as identidad_service


@dataclass(frozen=True)
class CobranzaDelListado:
    """Una cobranza con los nombres que la pantalla muestra. El nombre es `None` si la
    referencia ya no se puede resolver."""

    cobranza: Cobranza
    cliente_nombre: str | None
    usuario_nombre: str | None


@dataclass(frozen=True)
class PaginaDeCobranzas:
    items: list[CobranzaDelListado]
    cursor_siguiente: str | None


@dataclass(frozen=True)
class MedioDelDetalle:
    medio_pago_id: UUID
    medio_nombre: str | None
    importe: Decimal
    referencia: str | None


@dataclass(frozen=True)
class AnulacionDelDetalle:
    """La anulación de la cobranza (COB-05): qué motivo, observación, quién y cuándo."""

    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    anulada_en: datetime


@dataclass(frozen=True)
class DetalleDeCobranza:
    resumen: CobranzaDelListado
    medios: list[MedioDelDetalle]
    anulacion: AnulacionDelDetalle | None


def _con_nombres(
    organizacion_id: UUID, sesion: Session, cobranzas: list[Cobranza]
) -> list[CobranzaDelListado]:
    clientes = clientes_service.nombres_de_clientes(
        organizacion_id, {c.cliente_id for c in cobranzas}, sesion
    )
    usuarios = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, {c.usuario_id for c in cobranzas}, sesion
    )
    return [
        CobranzaDelListado(
            cobranza=c,
            cliente_nombre=clientes.get(c.cliente_id),
            usuario_nombre=usuarios.get(c.usuario_id),
        )
        for c in cobranzas
    ]


def listar_cobranzas(
    organizacion_id: UUID,
    sesion: Session,
    *,
    cliente_id: UUID | None = None,
    estado: str | None = None,
    usuario_id: UUID | None = None,
    jornada_id: UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: int | None = None,
) -> PaginaDeCobranzas:
    """Cobranzas de la organización, de la más reciente a la más vieja, paginadas por cursor.

    Filtrable por cliente, estado, usuario, jornada y rango de fechas (de negocio, en la zona de
    la organización, `hasta` inclusivo: TR-04). `desde` posterior a `hasta` es
    `RANGO_DE_FECHAS_INVALIDO` y un cursor ilegible es `CURSOR_INVALIDO`. `limite` va de 1 a 200
    (la API responde 422 fuera de rango; acá solo se acota por seguridad)."""
    organizacion = identidad_service.obtener_organizacion(organizacion_id, sesion)
    if organizacion is None:
        raise RecursoNoEncontradoError("La organización no existe.")
    inicio, fin = rango_de_instantes(desde, hasta, organizacion.zona_horaria)
    filas, cursor_siguiente = repository.listar_cobranzas_paginado(
        organizacion_id,
        sesion,
        limite=acotar_limite(limite),
        cursor=cursor,
        cliente_id=cliente_id,
        estado=estado,
        usuario_id=usuario_id,
        jornada_id=jornada_id,
        desde=inicio,
        hasta=fin,
    )
    return PaginaDeCobranzas(
        items=_con_nombres(organizacion_id, sesion, filas), cursor_siguiente=cursor_siguiente
    )


def _anulacion_del_detalle(
    organizacion_id: UUID, sesion: Session, anulacion: CobranzaAnulacion
) -> AnulacionDelDetalle:
    motivo = configuracion_service.obtener_motivo(organizacion_id, anulacion.motivo_id, sesion)
    usuarios = identidad_service.obtener_nombres_de_usuarios(
        organizacion_id, {anulacion.usuario_id}, sesion
    )
    return AnulacionDelDetalle(
        motivo_id=anulacion.motivo_id,
        motivo_nombre=None if motivo is None else motivo.nombre,
        observacion=anulacion.observacion,
        usuario_id=anulacion.usuario_id,
        usuario_nombre=usuarios.get(anulacion.usuario_id),
        anulada_en=anulacion.occurred_at,
    )


def obtener_detalle_de_cobranza(
    organizacion_id: UUID, cobranza_id: UUID, sesion: Session
) -> DetalleDeCobranza:
    """La cobranza con sus medios (con nombre y referencia) y, si está anulada, su anulación con
    motivo, observación, usuario y momento (COB-02, COB-05). 404 si no existe en la organización
    (INV-21). Las observaciones de sincronización las agrega quien expone el detalle."""
    cobranza = repository.obtener_cobranza(organizacion_id, cobranza_id, sesion)
    if cobranza is None:
        raise RecursoNoEncontradoError(f"La cobranza {cobranza_id} no existe en esta organización.")

    medios: list[MedioDelDetalle] = []
    for medio in repository.listar_medios_de_cobranza(organizacion_id, cobranza.id, sesion):
        fila_medio = configuracion_service.obtener_medio_pago(
            organizacion_id, medio.medio_pago_id, sesion
        )
        medios.append(
            MedioDelDetalle(
                medio_pago_id=medio.medio_pago_id,
                medio_nombre=None if fila_medio is None else fila_medio.nombre,
                importe=medio.importe,
                referencia=medio.referencia,
            )
        )
    anulacion = repository.obtener_anulacion(organizacion_id, cobranza.id, sesion)
    return DetalleDeCobranza(
        resumen=_con_nombres(organizacion_id, sesion, [cobranza])[0],
        medios=medios,
        anulacion=(
            None
            if anulacion is None
            else _anulacion_del_detalle(organizacion_id, sesion, anulacion)
        ),
    )
