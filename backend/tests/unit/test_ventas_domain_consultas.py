"""Change 18a, tarea 9.2 (ajuste del 2026-10-20): el cursor por código de producto de
`GET /ventas/precios` (`ventas/domain/consultas.py`).

Reglas citadas: CAT-01 (el código es único por organización: clave estable del cursor) y
`design.md` D19.
"""

from __future__ import annotations

import pytest

from app.modules.ventas.domain.consultas import (
    codificar_cursor_de_producto,
    decodificar_cursor_de_producto,
)
from app.modules.ventas.domain.errores import CursorInvalidoError


@pytest.mark.parametrize("codigo", ["COD-0001", "VINO/Tinto 750ñ", "a|b"])
def test_el_cursor_de_producto_vuelve_al_codigo_original(codigo: str) -> None:
    assert decodificar_cursor_de_producto(codificar_cursor_de_producto(codigo)) == codigo


def test_codigos_distintos_dan_cursores_distintos() -> None:
    assert codificar_cursor_de_producto("A-1") != codificar_cursor_de_producto("A-2")


@pytest.mark.parametrize("ilegible", ["xx", "ñ", "////", "_w=="])
def test_un_cursor_de_producto_ilegible_es_cursor_invalido(ilegible: str) -> None:
    with pytest.raises(CursorInvalidoError) as error:
        decodificar_cursor_de_producto(ilegible)
    assert error.value.codigo == "CURSOR_INVALIDO"
