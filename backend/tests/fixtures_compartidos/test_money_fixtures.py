"""Ejecuta contra `core/money.py` los casos compartidos de
`shared/fixtures/calculo/` cuya entrada declara `"motor": "money"`.

Spec `calculo-compartido`: cada caso compartido es una prueba identificable
en ambas suites, con el `id` del caso en el nombre de la prueba (Python y
TypeScript comparan la misma representación decimal exacta).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from cargador import descubrir_casos

from app.core.money import redondear_costo, redondear_importe

_OPERACIONES = {
    "redondear_importe": redondear_importe,
    "redondear_costo": redondear_costo,
}

_CASOS_MONEY = [caso for caso in descubrir_casos() if caso.entrada.get("motor") == "money"]

# Guardia de deriva: si el fixture semilla dejara de tener casos de `money`,
# esta suite no debe quedar en silencio con 0 pruebas parametrizadas.
if not _CASOS_MONEY:
    raise AssertionError(
        'No se descubrió ningún caso compartido con "motor": "money" en '
        "shared/fixtures/calculo/ -- el arnés de money.py quedaría mudo"
    )


@pytest.mark.parametrize(
    "caso",
    _CASOS_MONEY,
    ids=[caso.id for caso in _CASOS_MONEY],
)
def test_caso_compartido_de_money(caso: object) -> None:
    entrada = caso.entrada  # type: ignore[attr-defined]
    operacion = _OPERACIONES[entrada["operacion"]]

    resultado = operacion(entrada["valor"])

    esperado = Decimal(caso.salida_esperada["resultado"])  # type: ignore[attr-defined]
    assert resultado == esperado
    # Comparación de texto exacto, sin tolerancia numérica (`02` §10.2).
    assert str(resultado) == caso.salida_esperada["resultado"]  # type: ignore[attr-defined]
