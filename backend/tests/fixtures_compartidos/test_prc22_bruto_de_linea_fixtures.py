"""Change 13, tarea 3.2: ejecuta contra `app.modules.precios.domain.bruto_de_linea` los
casos compartidos de `shared/fixtures/calculo/prc-22-bruto-de-linea.json` cuya entrada
declara `"motor": "prc22"` (PRC-22, `design.md` D10; `02` §10.4).

Cada caso es una prueba con su `id`. Los mismos casos corre Vitest en
`frontend/tests/unit/calculo/prc22.fixtures.test.ts` (ADR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from cargador import descubrir_casos

from app.modules.precios.domain.bruto_de_linea import calcular_bruto_de_linea

_CASOS_PRC22 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "prc22"]

if not _CASOS_PRC22:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "prc22" en '
        "shared/fixtures/calculo/ -- el arnés de bruto_de_linea.py quedaría mudo"
    )


def _ejecutar(entrada: dict[str, Any]) -> dict[str, Any]:
    bruto = calcular_bruto_de_linea(
        Decimal(entrada["precio_referencia"]),
        entrada["unidades_referencia"],
        entrada["cantidad_base"],
    )
    return {"bruto": str(bruto)}


@pytest.mark.parametrize("caso", _CASOS_PRC22, ids=[caso.id for caso in _CASOS_PRC22])
def test_caso_compartido_de_prc22(caso: Any) -> None:
    salida_esperada = caso.salida_esperada

    if "error" in salida_esperada:
        with pytest.raises(Exception) as error:  # noqa: B017 (se afirma el código abajo)
            _ejecutar(caso.entrada)
        assert getattr(error.value, "codigo", None) == salida_esperada["error"]
        return

    assert _ejecutar(caso.entrada) == salida_esperada
