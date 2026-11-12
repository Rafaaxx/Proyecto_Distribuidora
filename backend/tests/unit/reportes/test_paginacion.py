"""Tarea 21.1 (change 26, `design.md` D14): la paginación de las listas de los reportes, pura.

Reglas citadas: REP-01 (el reporte se recalcula siempre: el sobre sale de cada pedido).
"""

from __future__ import annotations

import pytest

from app.modules.reportes.domain.paginacion import (
    TAMANO_DE_PAGINA,
    armar_sobre,
    desplazamiento_de,
)


def test_el_tamano_de_pagina_es_fijo_en_cincuenta() -> None:
    assert TAMANO_DE_PAGINA == 50


@pytest.mark.parametrize(("pagina", "esperado"), [(1, 0), (2, 50), (3, 100), (10, 450)])
def test_el_desplazamiento_de_una_pagina(pagina: int, esperado: int) -> None:
    assert desplazamiento_de(pagina) == esperado


@pytest.mark.parametrize(
    ("total_filas", "paginas"), [(0, 0), (1, 1), (49, 1), (50, 1), (51, 2), (100, 2), (120, 3)]
)
def test_la_cantidad_de_paginas_es_el_techo_de_filas_sobre_cincuenta(
    total_filas: int, paginas: int
) -> None:
    sobre = armar_sobre(["x"], pagina=1, total_filas=total_filas)

    assert sobre.paginas == paginas
    assert sobre.total_filas == total_filas
    assert sobre.tamano == 50


def test_el_sobre_lleva_las_filas_y_la_pagina_pedida() -> None:
    sobre = armar_sobre(["a", "b"], pagina=3, total_filas=102)

    assert (sobre.filas, sobre.pagina, sobre.paginas) == (["a", "b"], 3, 3)


def test_una_pagina_posterior_a_la_ultima_no_es_error() -> None:
    sobre = armar_sobre([], pagina=9, total_filas=120)

    assert (sobre.filas, sobre.pagina, sobre.total_filas, sobre.paginas) == ([], 9, 120, 3)


def test_sin_filas_no_hay_paginas() -> None:
    sobre = armar_sobre([], pagina=1, total_filas=0)

    assert (sobre.filas, sobre.paginas) == ([], 0)
