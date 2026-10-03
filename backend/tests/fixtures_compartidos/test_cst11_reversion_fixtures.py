"""Change 11, tarea 1.2: ejecuta contra `costeo.domain.costo_promedio.calcular_reversion`
los casos compartidos de `cst-11-costo-promedio.json` cuya operación es `reversion`
(CMP-06, CST-13, `design.md` D9).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.costeo.domain.costo_promedio import calcular_reversion

_CASOS = [
    caso
    for caso in descubrir_casos()
    if caso.entrada.get("motor") == "cst11" and caso.entrada.get("operacion") == "reversion"
]

if not _CASOS:
    raise AssertionError("No hay casos de reversión de CST-11 en shared/fixtures/calculo/")


@pytest.mark.parametrize("caso", _CASOS, ids=[caso.id for caso in _CASOS])
def test_caso_compartido_de_reversion(caso: Any) -> None:
    entrada = caso.entrada
    resultado = calcular_reversion(
        stock_previo=entrada["stock_previo"],
        promedio_previo=Decimal(entrada["promedio_previo"]),
        cantidad=entrada["cantidad"],
        costo_ingreso=entrada["costo_ingreso"],
    )
    assert {
        "promedio_nuevo": str(resultado.promedio_nuevo),
        "stock_nuevo": resultado.stock_nuevo,
        "recalculado": resultado.recalculado,
    } == caso.salida_esperada
