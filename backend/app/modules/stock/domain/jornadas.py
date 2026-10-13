"""Reglas puras de la jornada y de la toma de una ubicación (RUT-01, RUT-03, RUT-08, RUT-09,
STK-09, INV-16; `01` §18; `design.md` D2, D3, D6, D13; change 15).

La máquina de estados es la de `01` §18: `ABIERTA → EN_RENDICION → CERRADA` y
`ABIERTA | EN_RENDICION → LIBERADA`. No importa infraestructura (`02` §5.2): el servicio lee
la jornada y la ubicación y le pasa a estas funciones solo los datos.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.modules.stock.domain.errores import (
    JornadaEstadoInvalidoError,
    MotivoInvalidoError,
    ObservacionInvalidaError,
    UbicacionInactivaError,
    UbicacionSinTomaError,
    UbicacionTomadaError,
)

ABIERTA = "ABIERTA"
EN_RENDICION = "EN_RENDICION"
CERRADA = "CERRADA"
LIBERADA = "LIBERADA"
ESTADOS = (ABIERTA, EN_RENDICION, CERRADA, LIBERADA)
ESTADOS_NO_CERRADOS = frozenset({ABIERTA, EN_RENDICION})

AMBITO_LIBERACION_JORNADA = "LIBERACION_JORNADA"
MAXIMO_OBSERVACION_LIBERACION = 500


def esta_no_cerrada(estado: str) -> bool:
    """INV-16: una jornada `ABIERTA` o `EN_RENDICION` ocupa su ubicación; una `CERRADA` o
    `LIBERADA` no."""
    return estado in ESTADOS_NO_CERRADOS


def _transitar(estado: str, *, desde: frozenset[str], hacia: str, accion: str) -> str:
    if estado not in desde:
        raise JornadaEstadoInvalidoError(f"No se puede {accion} una jornada {estado}.")
    return hacia


def rendir(estado: str) -> str:
    """`ABIERTA → EN_RENDICION`; cualquier otro estado (rendir dos veces incluido) es
    `JORNADA_ESTADO_INVALIDO`."""
    return _transitar(estado, desde=frozenset({ABIERTA}), hacia=EN_RENDICION, accion="rendir")


def cerrar(estado: str) -> str:
    """`EN_RENDICION → CERRADA`: no se cierra lo que no se rindió (D2)."""
    return _transitar(estado, desde=frozenset({EN_RENDICION}), hacia=CERRADA, accion="cerrar")


def liberar(estado: str) -> str:
    """`ABIERTA | EN_RENDICION → LIBERADA` (RUT-09)."""
    return _transitar(estado, desde=ESTADOS_NO_CERRADOS, hacia=LIBERADA, accion="liberar")


def validar_ubicacion_para_abrir(*, activa: bool, requiere_toma: bool) -> None:
    """D3: solo se abre una jornada sobre una ubicación activa (ADR-038) que requiere toma
    (RUT-01). Primero la actividad."""
    if not activa:
        raise UbicacionInactivaError("La ubicación está inactiva.")
    if not requiere_toma:
        raise UbicacionSinTomaError("La ubicación no requiere toma: no admite jornada.")


def normalizar_observacion_de_liberacion(observacion: str | None) -> str | None:
    """D13: recortada, vacía equivale a `None`, hasta 500 caracteres."""
    if observacion is None:
        return None
    recortada = observacion.strip()
    if len(recortada) > MAXIMO_OBSERVACION_LIBERACION:
        raise ObservacionInvalidaError(
            f"La observación admite hasta {MAXIMO_OBSERVACION_LIBERACION} caracteres."
        )
    return recortada or None


def validar_motivo_de_liberacion(*, activo: bool, ambito: str) -> None:
    """TR-09, D13: el motivo es activo y del ámbito `LIBERACION_JORNADA`; si no,
    `MOTIVO_INVALIDO`."""
    if not activo or ambito != AMBITO_LIBERACION_JORNADA:
        raise MotivoInvalidoError(
            f"El motivo no es un motivo activo de {AMBITO_LIBERACION_JORNADA}."
        )


# --- toma de una ubicación (STK-09, D6) ---------------------------------------------------


class DecisionDeToma(StrEnum):
    """Quién mueve una ubicación: nadie la tomó, su jornada, o quien tiene
    `LIBERAR_UBICACION` por excepción."""

    LIBRE = "LIBRE"
    DE_LA_JORNADA = "DE_LA_JORNADA"
    POR_EXCEPCION = "POR_EXCEPCION"


@dataclass(frozen=True)
class JornadaDeUbicacion:
    """La jornada no cerrada de una ubicación, tal como la lee el servicio."""

    id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    estado: str


def decidir_toma(
    jornada: JornadaDeUbicacion | None,
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    puede_operar_ubicacion_tomada: bool,
    jornada_id_del_sobre: UUID | None = None,
) -> DecisionDeToma:
    """D6: sin jornada no cerrada la ubicación está libre; la jornada `ABIERTA` la mueve su
    usuario desde su dispositivo (y, si el sobre trae una jornada, tiene que ser esa); con
    `LIBERAR_UBICACION` se mueve por excepción en `ABIERTA` y `EN_RENDICION`; todo lo demás
    es `UBICACION_TOMADA`."""
    if jornada is None:
        return DecisionDeToma.LIBRE
    es_de_la_jornada = (
        jornada.estado == ABIERTA
        and jornada.usuario_id == usuario_id
        and jornada.dispositivo_id == dispositivo_id
    )
    if es_de_la_jornada:
        if jornada_id_del_sobre is not None and jornada_id_del_sobre != jornada.id:
            raise UbicacionTomadaError("La jornada del comando no es la que tomó la ubicación.")
        return DecisionDeToma.DE_LA_JORNADA
    if puede_operar_ubicacion_tomada:
        return DecisionDeToma.POR_EXCEPCION
    raise UbicacionTomadaError("La ubicación está tomada por una jornada.")
