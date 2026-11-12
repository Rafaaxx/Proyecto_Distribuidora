"""Unitarias del dominio de lectura de `cuentas_corrientes` (tarea 4.1/4.2):
cursor `(occurred_at, id)`, límite de página y rango de fechas de negocio del
estado de cuenta (`design.md` D9, CC-07, TR-04).

Funciones puras (`CLAUDE.md` §4): ninguna toca la base.
"""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.modules.cuentas_corrientes.domain.errores import (
    CursorInvalidoError,
    RangoDeFechasInvalidoError,
)
from app.modules.cuentas_corrientes.domain.estado_de_cuenta import (
    LIMITE_DEFAULT,
    LIMITE_MAXIMO,
    codificar_cursor,
    decodificar_cursor,
    limite_efectivo,
    rango_de_instantes,
)

MENDOZA = "America/Argentina/Mendoza"

# --- límite de página (D9: por defecto 50, máximo 200) ----------------------


def test_los_limites_de_pagina_son_los_de_d9() -> None:
    assert (LIMITE_DEFAULT, LIMITE_MAXIMO) == (50, 200)


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [(None, 50), (10, 10), (200, 200), (201, 200), (100000, 200), (0, 1), (-5, 1)],
)
def test_el_limite_se_acota_al_rango_permitido(pedido: int | None, esperado: int) -> None:
    assert limite_efectivo(pedido) == esperado


# --- cursor (occurred_at, id) -----------------------------------------------


@pytest.mark.parametrize(
    "momento",
    [
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 9, 29, 23, 59, 59, 123456, tzinfo=UTC),
        datetime(2026, 3, 1, 8, 30, tzinfo=ZoneInfo(MENDOZA)),
    ],
)
def test_el_cursor_recupera_exactamente_el_momento_y_el_id(momento: datetime) -> None:
    id_ = uuid4()

    recuperado_momento, recuperado_id = decodificar_cursor(codificar_cursor(momento, id_))

    assert recuperado_momento == momento
    assert recuperado_momento.utcoffset() == momento.utcoffset()
    assert recuperado_id == id_


def test_dos_movimientos_del_mismo_momento_tienen_cursores_distintos() -> None:
    """D9: el desempate por `id` es lo que hace estable la paginación."""
    momento = datetime(2026, 1, 1, tzinfo=UTC)

    assert codificar_cursor(momento, UUID(int=1)) != codificar_cursor(momento, UUID(int=2))


@pytest.mark.parametrize(
    "cursor",
    ["", "no-es-base64!!", "YWJj", "MjAyNi0wMS0wMXxub3VuaWQ="],
)
def test_un_cursor_malformado_se_rechaza(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        decodificar_cursor(cursor)
    assert error.value.codigo == "CURSOR_INVALIDO"


def test_un_cursor_sin_zona_horaria_se_rechaza() -> None:
    """Un momento sin zona no es un `timestamptz`: no se adivina una."""
    ingenuo = codificar_cursor(datetime(2026, 1, 1, tzinfo=UTC), uuid4())
    valor = base64.urlsafe_b64decode(ingenuo).decode().replace("+00:00", "")
    manipulado = base64.urlsafe_b64encode(valor.encode()).decode()

    with pytest.raises(CursorInvalidoError):
        decodificar_cursor(manipulado)


# --- rango de fechas de negocio (TR-04) --------------------------------------


def test_sin_fechas_no_hay_rango() -> None:
    assert rango_de_instantes(None, None, MENDOZA) == (None, None)


def test_desde_es_el_inicio_del_dia_en_la_zona_de_la_organizacion() -> None:
    desde, hasta = rango_de_instantes(date(2026, 3, 1), None, MENDOZA)

    assert hasta is None
    assert desde == datetime(2026, 3, 1, 0, 0, tzinfo=ZoneInfo(MENDOZA))
    # Mendoza es UTC-3: el inicio del día local es las 03:00 UTC.
    assert desde == datetime(2026, 3, 1, 3, 0, tzinfo=UTC)


def test_hasta_incluye_todo_el_dia_y_es_el_inicio_del_dia_siguiente() -> None:
    _, hasta = rango_de_instantes(None, date(2026, 3, 31), MENDOZA)

    assert hasta == datetime(2026, 4, 1, 0, 0, tzinfo=ZoneInfo(MENDOZA))
    assert hasta == datetime(2026, 4, 1, 3, 0, tzinfo=UTC)


def test_el_mismo_dia_como_desde_y_hasta_es_un_rango_de_veinticuatro_horas() -> None:
    desde, hasta = rango_de_instantes(date(2026, 3, 1), date(2026, 3, 1), MENDOZA)

    assert desde is not None
    assert hasta is not None
    assert hasta - desde == timedelta(hours=24)


def test_la_zona_de_la_organizacion_cambia_el_instante() -> None:
    """La misma fecha de negocio es un instante distinto en otra zona."""
    en_mendoza, _ = rango_de_instantes(date(2026, 3, 1), None, MENDOZA)
    en_madrid, _ = rango_de_instantes(date(2026, 3, 1), None, "Europe/Madrid")

    assert en_mendoza != en_madrid
    assert en_madrid == datetime(2026, 2, 28, 23, 0, tzinfo=UTC)


def test_un_rango_invertido_se_rechaza() -> None:
    with pytest.raises(RangoDeFechasInvalidoError) as error:
        rango_de_instantes(date(2026, 3, 2), date(2026, 3, 1), MENDOZA)
    assert error.value.codigo == "RANGO_DE_FECHAS_INVALIDO"
