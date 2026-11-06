"""Change 25, tarea 6.1 (`design.md` D3): el cursor opaco `(registered_at, operacion_id)` de la
bandeja. Regla citada: SYN-08 (paginación estable de lo pendiente)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.modules.sync.domain import revision
from app.modules.sync.domain.errores import CursorInvalidoError


@pytest.mark.parametrize(
    "momento",
    [
        datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 31, 23, 59, 59, 123456, tzinfo=UTC),
    ],
)
def test_el_cursor_se_decodifica_al_mismo_momento_y_operacion(momento: datetime) -> None:
    operacion = uuid4()

    cursor = revision.codificar_cursor(momento, operacion)

    assert revision.decodificar_cursor(cursor) == (momento, operacion)


@pytest.mark.parametrize(
    "cursor",
    ["", "no-es-base64!", "bm9fdGllbmVfc2VwYXJhZG9y"],
)
def test_un_cursor_ilegible_es_cursor_invalido(cursor: str) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        revision.decodificar_cursor(cursor)

    assert error.value.codigo == "CURSOR_INVALIDO"


def test_un_cursor_sin_zona_horaria_es_invalido() -> None:
    import base64

    sin_zona = base64.urlsafe_b64encode(f"2026-11-05T12:00:00|{UUID(int=1)}".encode()).decode(
        "ascii"
    )

    with pytest.raises(CursorInvalidoError):
        revision.decodificar_cursor(sin_zona)
