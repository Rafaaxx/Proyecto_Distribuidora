"""Change 16, tarea 7.2: máquina de estados y vigencia de una regla de descuento (spec
`descuentos/reglas-de-descuento`, requisitos "Una regla se activa y se pausa siguiendo su máquina de
estados" y "La vigencia delimita cuándo aplica una regla"; `01` §18, DSC-01, DSC-05, TR-05;
`design.md` D15, D16)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.descuentos.domain.errores import (
    ReglaEstadoInvalidoError,
    ReglaNoEsBorradorError,
    VigenciaInvalidaError,
)
from app.modules.descuentos.domain.estados import (
    ESTADO_VENCIDA,
    activar,
    aplica_en,
    estado_derivado,
    exigir_borrador,
    pausar,
    validar_fin_de_vigencia,
)

AHORA = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
DIA = timedelta(days=1)


@dataclass(frozen=True)
class _Regla:
    estado: str
    vigencia_desde: datetime | None
    vigencia_hasta: datetime | None = None


# --- máquina de estados (`01` §18) --------------------------------------------------------


def test_activar_un_borrador_sin_vigencia_desde_usa_el_momento_de_la_activacion() -> None:
    estado, desde = activar("BORRADOR", None, None, AHORA)

    assert estado == "ACTIVA"
    assert desde == AHORA


def test_activar_un_borrador_con_vigencia_desde_futura_la_respeta() -> None:
    estado, desde = activar("BORRADOR", AHORA + 5 * DIA, None, AHORA)

    assert (estado, desde) == ("ACTIVA", AHORA + 5 * DIA)


def test_reactivar_una_pausada_conserva_su_vigencia_desde() -> None:
    desde_original = AHORA - 3 * DIA

    estado, desde = activar("PAUSADA", desde_original, None, AHORA)

    assert (estado, desde) == ("ACTIVA", desde_original)


def test_pausar_una_activa() -> None:
    assert pausar("ACTIVA") == "PAUSADA"


@pytest.mark.parametrize("estado", ["BORRADOR", "PAUSADA"])
def test_pausar_solo_se_acepta_desde_activa(estado: str) -> None:
    with pytest.raises(ReglaEstadoInvalidoError) as error:
        pausar(estado)
    assert error.value.codigo == "REGLA_ESTADO_INVALIDO"
    assert error.value.status_http == 409


def test_activar_una_activa_se_rechaza() -> None:
    with pytest.raises(ReglaEstadoInvalidoError):
        activar("ACTIVA", AHORA - DIA, None, AHORA)


@pytest.mark.parametrize("estado", ["VENCIDA", "FINALIZADA", ""])
def test_un_estado_que_no_se_almacena_no_se_activa_ni_se_pausa(estado: str) -> None:
    with pytest.raises(ReglaEstadoInvalidoError):
        activar(estado, AHORA - DIA, None, AHORA)
    with pytest.raises(ReglaEstadoInvalidoError):
        pausar(estado)


def test_activar_una_regla_con_la_vigencia_hasta_pasada_se_rechaza() -> None:
    with pytest.raises(VigenciaInvalidaError) as error:
        activar("PAUSADA", AHORA - 10 * DIA, AHORA - DIA, AHORA)
    assert error.value.codigo == "VIGENCIA_INVALIDA"


def test_activar_justo_en_la_vigencia_hasta_se_rechaza_porque_el_extremo_es_excluido() -> None:
    with pytest.raises(VigenciaInvalidaError):
        activar("PAUSADA", AHORA - 10 * DIA, AHORA, AHORA)


def test_activar_con_la_vigencia_hasta_futura_se_acepta() -> None:
    estado, _ = activar("BORRADOR", None, AHORA + DIA, AHORA)

    assert estado == "ACTIVA"


def test_activar_un_borrador_cuya_vigencia_desde_es_posterior_a_la_hasta_se_rechaza() -> None:
    # El estado no importa: la vigencia desde efectiva (futura) deja la hasta antes de empezar.
    with pytest.raises(VigenciaInvalidaError):
        activar("BORRADOR", AHORA + 10 * DIA, AHORA + 2 * DIA, AHORA)


def test_el_error_de_estado_precede_al_de_vigencia() -> None:
    with pytest.raises(ReglaEstadoInvalidoError):
        activar("ACTIVA", AHORA - 10 * DIA, AHORA - DIA, AHORA)


@given(st.lists(st.sampled_from(["ACTIVAR", "PAUSAR"]), max_size=30))
def test_ninguna_secuencia_de_transiciones_aceptadas_vuelve_a_borrador(
    pasos: list[str],
) -> None:
    """Propiedad (01 §18): desde `BORRADOR`, aplicar transiciones y descartar las rechazadas
    nunca devuelve la regla a `BORRADOR`, y el estado siempre es uno de los tres."""
    estado = "BORRADOR"
    visitados = {estado}
    desde: datetime | None = None
    for paso in pasos:
        try:
            if paso == "ACTIVAR":
                estado, desde = activar(estado, desde, None, AHORA)
            else:
                estado = pausar(estado)
        except ReglaEstadoInvalidoError:
            continue
        visitados.add(estado)
        assert estado != "BORRADOR"
    assert visitados <= {"BORRADOR", "ACTIVA", "PAUSADA"}


# --- edición (D15) ------------------------------------------------------------------------


def test_un_borrador_se_edita() -> None:
    exigir_borrador("BORRADOR")


@pytest.mark.parametrize("estado", ["ACTIVA", "PAUSADA"])
def test_una_regla_activada_o_pausada_no_se_edita(estado: str) -> None:
    with pytest.raises(ReglaNoEsBorradorError) as error:
        exigir_borrador(estado)
    assert error.value.codigo == "REGLA_NO_ES_BORRADOR"
    assert error.value.status_http == 409


def test_fijar_el_fin_de_la_vigencia_posterior_al_inicio_se_acepta() -> None:
    validar_fin_de_vigencia(AHORA - DIA, AHORA + DIA)
    validar_fin_de_vigencia(None, AHORA + DIA)
    validar_fin_de_vigencia(AHORA - DIA, None)


@pytest.mark.parametrize("hasta", [AHORA - DIA, AHORA - 2 * DIA])
def test_fijar_un_fin_de_vigencia_no_posterior_al_inicio_se_rechaza(hasta: datetime) -> None:
    with pytest.raises(VigenciaInvalidaError):
        validar_fin_de_vigencia(AHORA - DIA, hasta)


# --- vigencia (D16, DSC-05 paso 2) ---------------------------------------------------------


def test_aplica_con_el_extremo_desde_incluido() -> None:
    regla = _Regla("ACTIVA", AHORA, AHORA + DIA)

    assert aplica_en(regla, AHORA) is True
    assert aplica_en(regla, AHORA - timedelta(microseconds=1)) is False


def test_no_aplica_con_el_extremo_hasta_excluido() -> None:
    regla = _Regla("ACTIVA", AHORA - DIA, AHORA)

    assert aplica_en(regla, AHORA - timedelta(microseconds=1)) is True
    assert aplica_en(regla, AHORA) is False


def test_una_regla_sin_vigencia_hasta_aplica_siempre_despues_de_la_desde() -> None:
    regla = _Regla("ACTIVA", AHORA - DIA)

    assert aplica_en(regla, AHORA + 3650 * DIA) is True


@pytest.mark.parametrize("estado", ["BORRADOR", "PAUSADA"])
def test_solo_aplica_una_regla_activa(estado: str) -> None:
    assert aplica_en(_Regla(estado, AHORA - DIA), AHORA) is False


def test_una_regla_sin_vigencia_desde_no_aplica() -> None:
    assert aplica_en(_Regla("ACTIVA", None), AHORA) is False


def test_una_regla_programada_no_aplica_hoy_y_si_el_dia_de_su_inicio() -> None:
    regla = _Regla("ACTIVA", AHORA + 5 * DIA)

    assert aplica_en(regla, AHORA) is False
    assert aplica_en(regla, AHORA + 5 * DIA) is True


# --- estado derivado -----------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["ACTIVA", "PAUSADA"])
def test_activa_o_pausada_con_la_hasta_pasada_se_informa_vencida(estado: str) -> None:
    regla = _Regla(estado, AHORA - 10 * DIA, AHORA - DIA)

    assert estado_derivado(regla, AHORA) == ESTADO_VENCIDA == "VENCIDA"


def test_la_hasta_exactamente_ahora_ya_esta_vencida() -> None:
    assert estado_derivado(_Regla("ACTIVA", AHORA - DIA, AHORA), AHORA) == "VENCIDA"


@pytest.mark.parametrize(
    "regla",
    [
        _Regla("ACTIVA", AHORA - DIA, AHORA + DIA),
        _Regla("ACTIVA", AHORA - DIA, None),
        _Regla("PAUSADA", AHORA - DIA, AHORA + DIA),
        _Regla("BORRADOR", None, AHORA - DIA),  # un borrador no vence
    ],
)
def test_una_regla_vigente_o_borrador_conserva_su_estado(regla: _Regla) -> None:
    assert estado_derivado(regla, AHORA) == regla.estado
