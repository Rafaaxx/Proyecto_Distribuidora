"""Change 09, tarea 3.1: ejecuta contra
`app.modules.costeo.domain.costo_promedio` los casos compartidos de
`shared/fixtures/calculo/` cuya entrada declara `"motor": "cst11"` (CST-11 y
CST-12, `01` §6.2, `02` §10.4, `design.md` D14).

ROJO a propósito (tarea 3.1, grupo 3): el dominio de `costeo` todavía no existe
-- se implementa en la tarea 4.1. Este archivo prueba que el cargador descubre
los casos de `cst-11-costo-promedio.json`; la importación inexistente es la
evidencia de ROJO. Cada caso es una prueba con su `id` (spec
`sistema/calculo-compartido`, "Cada caso compartido es una prueba
identificable en ambas suites")."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.costeo.domain.costo_promedio import calcular_egreso, calcular_ingreso

_CASOS_CST11 = [
    caso
    for caso in descubrir_casos()
    if caso.entrada.get("motor") == "cst11" and caso.entrada.get("operacion") != "reversion"
]
# Las operaciones `reversion` (CMP-06, change 11) las ejecuta
# `test_cst11_reversion_fixtures.py`.

if not _CASOS_CST11:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "cst11" en '
        "shared/fixtures/calculo/ -- el arnés de costo_promedio.py quedaría mudo"
    )


def _decimal_o_none(valor: str | None) -> Decimal | None:
    return None if valor is None else Decimal(valor)


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    """Corre la operación del caso y devuelve la salida con el mismo formato
    (cadenas para los costos) que `salida_esperada`."""
    if entrada["operacion"] == "ingreso":
        ingreso = calcular_ingreso(
            stock_previo=entrada["stock_previo"],
            promedio_previo=_decimal_o_none(entrada["promedio_previo"]),
            cantidad=entrada["cantidad"],
            costo_ingreso=entrada["costo_ingreso"],
        )
        return {"promedio_nuevo": str(ingreso.promedio_nuevo), "stock_nuevo": ingreso.stock_nuevo}

    egreso = calcular_egreso(
        stock_previo=entrada["stock_previo"],
        promedio_previo=_decimal_o_none(entrada["promedio_previo"]),
        cantidad=entrada["cantidad"],
    )
    return {
        "promedio_nuevo": None if egreso.promedio_nuevo is None else str(egreso.promedio_nuevo),
        "stock_nuevo": egreso.stock_nuevo,
        "costo_valorizacion": (
            None if egreso.costo_valorizacion is None else str(egreso.costo_valorizacion)
        ),
    }


@pytest.mark.parametrize("caso", _CASOS_CST11, ids=[caso.id for caso in _CASOS_CST11])
def test_caso_compartido_de_cst11(caso: Any) -> None:
    entrada = caso.entrada
    salida_esperada = caso.salida_esperada

    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(entrada) == salida_esperada
