"""Change 06, tarea 2.2: ejecuta contra
`app.modules.proveedores.domain.costo_base.calcular_costo_base` los casos
compartidos de `shared/fixtures/calculo/` cuya entrada declara
`"motor": "cst02"` (CST-02, `02` §10.4, `design.md` D11).

ROJO a propósito (tarea 2.2, grupo 2): `calcular_costo_base` todavía no
existe -- se implementa recién en la tarea 6.3. Este archivo prueba que el
cargador descubre los 14 casos de `cst-02-costo-base.json` y falla al
importar la función de dominio; ambos hechos son la evidencia de ROJO."""

from __future__ import annotations

from decimal import Decimal

import pytest
from cargador import descubrir_casos

from app.modules.proveedores.domain.costo_base import calcular_costo_base

_CASOS_CST02 = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "cst02"]

if not _CASOS_CST02:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "cst02" en '
        "shared/fixtures/calculo/ -- el arnés de costo_base.py quedaría mudo"
    )


@pytest.mark.parametrize("caso", _CASOS_CST02, ids=[caso.id for caso in _CASOS_CST02])
def test_caso_compartido_de_cst02(caso: object) -> None:
    entrada = caso.entrada  # type: ignore[attr-defined]
    salida_esperada = caso.salida_esperada  # type: ignore[attr-defined]

    if salida_esperada.get("error"):
        with pytest.raises(Exception):  # noqa: B017 (6.3 define la excepción exacta; acá es ROJO)
            calcular_costo_base(
                valor=Decimal(entrada["valor"]),
                incluye_iva=entrada["incluye_iva"],
                alicuota=Decimal(entrada["alicuota"]),
                bonificacion=Decimal(entrada["bonificacion"]),
                unidades=entrada["unidades"],
            )
        return

    resultado = calcular_costo_base(
        valor=Decimal(entrada["valor"]),
        incluye_iva=entrada["incluye_iva"],
        alicuota=Decimal(entrada["alicuota"]),
        bonificacion=Decimal(entrada["bonificacion"]),
        unidades=entrada["unidades"],
    )
    assert str(resultado) == salida_esperada["costo_base"]
