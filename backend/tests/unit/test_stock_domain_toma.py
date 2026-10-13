"""Tarea 3.2 (change 15, `design.md` D6; STK-09): la decisión pura de quién puede mover una
ubicación tomada (`decidir_toma` en `stock/domain/jornadas.py`).

Reglas citadas: STK-09, INV-16, RUT-09.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.stock.domain.errores import UbicacionTomadaError
from app.modules.stock.domain.jornadas import (
    DecisionDeToma,
    JornadaDeUbicacion,
    decidir_toma,
)

JUAN = uuid4()
PEDRO = uuid4()
V03 = uuid4()
V04 = uuid4()


def _jornada(estado: str = "ABIERTA") -> JornadaDeUbicacion:
    return JornadaDeUbicacion(id=uuid4(), usuario_id=JUAN, dispositivo_id=V03, estado=estado)


def test_una_ubicacion_sin_jornada_no_cerrada_se_mueve_libremente() -> None:
    """RUT-02: la carga antes de la apertura y el remanente después del cierre."""
    for permiso in (False, True):
        assert (
            decidir_toma(
                None,
                usuario_id=PEDRO,
                dispositivo_id=V04,
                puede_operar_ubicacion_tomada=permiso,
            )
            is DecisionDeToma.LIBRE
        )


def test_el_dueno_de_la_jornada_abierta_en_su_dispositivo_mueve_de_la_jornada() -> None:
    jornada = _jornada()

    decision = decidir_toma(
        jornada, usuario_id=JUAN, dispositivo_id=V03, puede_operar_ubicacion_tomada=False
    )

    assert decision is DecisionDeToma.DE_LA_JORNADA


def test_la_decision_de_la_jornada_vale_aunque_el_dueno_tenga_el_permiso_de_excepcion() -> None:
    """D6 punto 2 antes que el 3: si es de la jornada, el movimiento lleva su `jornada_id` y
    no se marca como excepción."""
    decision = decidir_toma(
        _jornada(), usuario_id=JUAN, dispositivo_id=V03, puede_operar_ubicacion_tomada=True
    )

    assert decision is DecisionDeToma.DE_LA_JORNADA


@pytest.mark.parametrize("estado", ["ABIERTA", "EN_RENDICION"])
def test_con_el_permiso_se_mueve_por_excepcion_en_cualquier_estado_no_cerrado(
    estado: str,
) -> None:
    decision = decidir_toma(
        _jornada(estado),
        usuario_id=PEDRO,
        dispositivo_id=V04,
        puede_operar_ubicacion_tomada=True,
    )

    assert decision is DecisionDeToma.POR_EXCEPCION


@pytest.mark.parametrize(
    ("usuario", "dispositivo", "estado", "caso"),
    [
        (PEDRO, V04, "ABIERTA", "otro usuario y otro dispositivo"),
        (PEDRO, V03, "ABIERTA", "otro usuario en el dispositivo de la jornada"),
        (JUAN, V04, "ABIERTA", "mismo usuario en otro dispositivo"),
        (JUAN, V03, "EN_RENDICION", "la propia jornada en rendición sin el permiso"),
    ],
)
def test_los_demas_casos_se_rechazan_con_ubicacion_tomada(
    usuario: object, dispositivo: object, estado: str, caso: str
) -> None:
    with pytest.raises(UbicacionTomadaError) as error:
        decidir_toma(
            _jornada(estado),
            usuario_id=usuario,  # type: ignore[arg-type]
            dispositivo_id=dispositivo,  # type: ignore[arg-type]
            puede_operar_ubicacion_tomada=False,
        )
    assert error.value.codigo == "UBICACION_TOMADA", caso
    assert error.value.status_http == 409


def test_cuando_el_sobre_trae_una_jornada_tiene_que_ser_la_de_la_ubicacion() -> None:
    jornada = _jornada()

    assert (
        decidir_toma(
            jornada,
            usuario_id=JUAN,
            dispositivo_id=V03,
            puede_operar_ubicacion_tomada=False,
            jornada_id_del_sobre=jornada.id,
        )
        is DecisionDeToma.DE_LA_JORNADA
    )
    with pytest.raises(UbicacionTomadaError):
        decidir_toma(
            jornada,
            usuario_id=JUAN,
            dispositivo_id=V03,
            puede_operar_ubicacion_tomada=False,
            jornada_id_del_sobre=uuid4(),
        )


def test_la_excepcion_no_depende_de_la_jornada_que_traiga_el_sobre() -> None:
    """D6 punto 3: quien tiene `LIBERAR_UBICACION` mueve en cualquier estado de la jornada."""
    decision = decidir_toma(
        _jornada(),
        usuario_id=PEDRO,
        dispositivo_id=V04,
        puede_operar_ubicacion_tomada=True,
        jornada_id_del_sobre=uuid4(),
    )

    assert decision is DecisionDeToma.POR_EXCEPCION


@pytest.mark.parametrize("permiso", [False, True])
def test_una_ubicacion_libre_no_se_rechaza_aunque_el_sobre_traiga_una_jornada(
    permiso: bool,
) -> None:
    """Decisión del usuario (2026-10-09), STK-09: la puerta decide por ubicación. Una
    transferencia de un vehículo tomado a un depósito libre trae la jornada en el sobre, y el
    depósito (sin jornada no cerrada) responde `LIBRE`, sin rechazo."""
    decision = decidir_toma(
        None,
        usuario_id=JUAN,
        dispositivo_id=V03,
        puede_operar_ubicacion_tomada=permiso,
        jornada_id_del_sobre=uuid4(),
    )

    assert decision is DecisionDeToma.LIBRE
