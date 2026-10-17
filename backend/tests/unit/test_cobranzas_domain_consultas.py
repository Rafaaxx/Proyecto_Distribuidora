"""Change 17, tarea 10.1: reglas puras de las consultas de `cobranzas`
(`cobranzas/domain/consultas.py`): cursor opaco, rango de fechas de negocio y límite de página.

Reglas citadas: TR-04 y `design.md` D14.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.modules.cobranzas.domain.consultas import (
    acotar_limite,
    codificar_cursor,
    decodificar_cursor,
    rango_de_instantes,
)
from app.modules.cobranzas.domain.errores import CursorInvalidoError, RangoDeFechasInvalidoError


@pytest.mark.parametrize(
    "momento",
    [
        datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC),
    ],
)
def test_el_cursor_se_decodifica_al_mismo_momento_e_identificador(momento: datetime) -> None:
    id_ = uuid4()

    assert decodificar_cursor(codificar_cursor(momento, id_)) == (momento, id_)


@pytest.mark.parametrize("cursor", ["", "no-es-un-cursor", "bm8tZXMtdW4tY3Vyc29y", "ñ"])
def test_un_cursor_ilegible_es_cursor_invalido(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        decodificar_cursor(cursor)

    assert (error.value.codigo, error.value.status_http) == ("CURSOR_INVALIDO", 422)


def test_el_hasta_se_incluye_entero_en_la_zona_de_la_organizacion() -> None:
    """TR-04: en Buenos Aires (UTC-3), el 9 de octubre va de las 03:00 UTC del 9 a las 03:00 UTC
    del 10."""
    inicio, fin = rango_de_instantes(
        date(2026, 10, 9), date(2026, 10, 9), "America/Argentina/Buenos_Aires"
    )

    assert inicio == datetime(2026, 10, 9, 3, 0, tzinfo=UTC)
    assert fin == datetime(2026, 10, 10, 3, 0, tzinfo=UTC)


def test_sin_fechas_no_hay_limites() -> None:
    assert rango_de_instantes(None, None, "America/Argentina/Buenos_Aires") == (None, None)


def test_un_rango_invertido_es_rango_de_fechas_invalido() -> None:
    with pytest.raises(RangoDeFechasInvalidoError) as error:
        rango_de_instantes(date(2026, 10, 10), date(2026, 10, 9), "UTC")

    assert error.value.codigo == "RANGO_DE_FECHAS_INVALIDO"


@pytest.mark.parametrize(
    ("pedido", "esperado"), [(None, 50), (0, 1), (-5, 1), (10, 10), (200, 200), (999, 200)]
)
def test_el_limite_se_acota_de_1_a_200(pedido: int | None, esperado: int) -> None:
    assert acotar_limite(pedido) == esperado
