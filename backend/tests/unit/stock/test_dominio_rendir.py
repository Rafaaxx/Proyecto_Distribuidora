"""Tarea 7.2 (change 24, `design.md` D2; spec `stock/rendicion-de-jornada`): reglas puras de la
rendición v2 que no cubre el fixture compartido: qué jornada se puede rendir y la observación.

Reglas citadas: RUT-05, RUT-06, INV-04.
"""

from __future__ import annotations

import pytest

from app.modules.stock.domain import jornadas, rendicion
from app.modules.stock.domain.errores import (
    JornadaEstadoInvalidoError,
    JornadaSinEntregaError,
    ObservacionInvalidaError,
)


def test_una_jornada_abierta_y_entregada_se_puede_rendir() -> None:
    assert jornadas.validar_para_rendir("ABIERTA", entregada=True) == jornadas.EN_RENDICION


def test_una_jornada_abierta_sin_entrega_es_jornada_sin_entrega() -> None:
    with pytest.raises(JornadaSinEntregaError) as error:
        jornadas.validar_para_rendir("ABIERTA", entregada=False)

    assert (error.value.codigo, error.value.status_http) == ("JORNADA_SIN_ENTREGA", 409)


@pytest.mark.parametrize("estado", ["EN_RENDICION", "CERRADA", "LIBERADA"])
@pytest.mark.parametrize("entregada", [True, False])
def test_primero_el_estado_y_despues_la_entrega(estado: str, entregada: bool) -> None:
    """Una jornada que no está `ABIERTA` es `JORNADA_ESTADO_INVALIDO` tenga o no entrega."""
    with pytest.raises(JornadaEstadoInvalidoError):
        jornadas.validar_para_rendir(estado, entregada=entregada)


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [(None, None), ("", None), ("   ", None), ("  faltó una caja  ", "faltó una caja")],
)
def test_la_observacion_se_recorta_y_vacia_equivale_a_ninguna(
    entrada: str | None, esperada: str | None
) -> None:
    assert rendicion.normalizar_observacion(entrada) == esperada


def test_la_observacion_admite_hasta_quinientos_caracteres() -> None:
    assert rendicion.normalizar_observacion("a" * 500) == "a" * 500
    with pytest.raises(ObservacionInvalidaError):
        rendicion.normalizar_observacion("a" * 501)
