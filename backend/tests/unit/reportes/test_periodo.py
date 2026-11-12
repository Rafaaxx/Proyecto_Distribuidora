"""Tarea 1.2 (change 26, `design.md` D1): el período de los reportes, puro.

Reglas citadas: TR-04 (fechas de negocio en la zona de la organización), REP-02.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.reportes.domain.errores import (
    PeriodoDemasiadoLargoError,
    RangoDeFechasInvalidoError,
)
from app.modules.reportes.domain.periodo import TOPE_DE_DIAS, resolver_periodo

MENDOZA = "America/Argentina/Mendoza"


def test_sin_fechas_es_el_mes_en_curso_hasta_hoy() -> None:
    periodo = resolver_periodo(None, None, hoy=date(2026, 11, 6), zona_horaria=MENDOZA)

    assert (periodo.desde, periodo.hasta) == (date(2026, 11, 1), date(2026, 11, 6))
    assert periodo.zona_horaria == MENDOZA


def test_el_mes_en_curso_sigue_a_la_fecha_de_hoy() -> None:
    periodo = resolver_periodo(None, None, hoy=date(2026, 2, 28), zona_horaria=MENDOZA)

    assert (periodo.desde, periodo.hasta) == (date(2026, 2, 1), date(2026, 2, 28))


def test_solo_desde_llega_hasta_hoy() -> None:
    periodo = resolver_periodo(
        date(2026, 10, 15), None, hoy=date(2026, 11, 6), zona_horaria=MENDOZA
    )

    assert (periodo.desde, periodo.hasta) == (date(2026, 10, 15), date(2026, 11, 6))


def test_solo_hasta_empieza_el_dia_uno_de_ese_mes() -> None:
    periodo = resolver_periodo(None, date(2026, 9, 20), hoy=date(2026, 11, 6), zona_horaria=MENDOZA)

    assert (periodo.desde, periodo.hasta) == (date(2026, 9, 1), date(2026, 9, 20))


def test_las_fechas_explicitas_se_respetan() -> None:
    periodo = resolver_periodo(
        date(2026, 10, 1), date(2026, 10, 31), hoy=date(2026, 11, 6), zona_horaria=MENDOZA
    )

    assert (periodo.desde, periodo.hasta) == (date(2026, 10, 1), date(2026, 10, 31))


def test_el_intervalo_es_semiabierto_en_la_zona_de_la_organizacion() -> None:
    """TR-04: `hasta` se incluye entero (el fin es el inicio del día siguiente, en la zona)."""
    periodo = resolver_periodo(
        date(2026, 11, 1), date(2026, 11, 30), hoy=date(2026, 11, 30), zona_horaria=MENDOZA
    )
    zona = ZoneInfo(MENDOZA)

    assert periodo.inicio == datetime(2026, 11, 1, 0, 0, tzinfo=zona)
    assert periodo.fin == datetime(2026, 12, 1, 0, 0, tzinfo=zona)
    # 2026-11-01T02:30Z es el 31 de octubre a las 23:30 en Mendoza: queda fuera de noviembre.
    cerca_de_medianoche = datetime(2026, 11, 1, 2, 30, tzinfo=UTC)
    assert not periodo.inicio <= cerca_de_medianoche < periodo.fin
    assert periodo.inicio <= datetime(2026, 11, 1, 3, 0, tzinfo=UTC) < periodo.fin


def test_un_rango_invertido_es_rechazado() -> None:
    with pytest.raises(RangoDeFechasInvalidoError) as error:
        resolver_periodo(
            date(2026, 11, 10), date(2026, 11, 1), hoy=date(2026, 11, 20), zona_horaria=MENDOZA
        )

    assert error.value.codigo == "RANGO_DE_FECHAS_INVALIDO"
    assert error.value.status_http == 422


def test_un_desde_posterior_a_hoy_sin_hasta_queda_invertido() -> None:
    with pytest.raises(RangoDeFechasInvalidoError):
        resolver_periodo(date(2026, 12, 1), None, hoy=date(2026, 11, 6), zona_horaria=MENDOZA)


def test_un_dia_solo_es_un_periodo_valido() -> None:
    periodo = resolver_periodo(
        date(2026, 11, 6), date(2026, 11, 6), hoy=date(2026, 11, 6), zona_horaria=MENDOZA
    )

    assert periodo.desde == periodo.hasta == date(2026, 11, 6)


def test_366_dias_se_aceptan() -> None:
    periodo = resolver_periodo(
        date(2025, 1, 1), date(2026, 1, 1), hoy=date(2026, 11, 6), zona_horaria=MENDOZA
    )

    assert TOPE_DE_DIAS == 366
    assert (periodo.hasta - periodo.desde).days + 1 == 366


def test_367_dias_son_rechazados() -> None:
    with pytest.raises(PeriodoDemasiadoLargoError) as error:
        resolver_periodo(
            date(2025, 1, 1), date(2026, 1, 2), hoy=date(2026, 11, 6), zona_horaria=MENDOZA
        )

    assert error.value.codigo == "PERIODO_DEMASIADO_LARGO"
    assert error.value.status_http == 422
