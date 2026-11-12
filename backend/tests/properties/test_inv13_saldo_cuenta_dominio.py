"""INV-13 en el dominio puro, con Hypothesis (tarea 3.2; `docs/02` §15).

INV-13: el saldo de cada cuenta corriente es igual a la suma de sus
movimientos (CC-04). Acá se prueba la definición pura, sin base de datos:

1. aplicar los efectos uno por uno (`efecto_sobre_saldo`) da lo mismo que la
   suma de los que aumentan menos la suma de los que reducen (`saldo_de`);
2. el resultado no depende del orden de los movimientos.

La contraparte contra PostgreSQL (`saldo_cuenta` = suma SQL del libro) es la
tarea 8.2 (`test_inv13_saldo_cuenta_postgres.py`).
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.modules.cuentas_corrientes.domain.catalogo import AUMENTA, REDUCE, SENTIDOS
from app.modules.cuentas_corrientes.domain.importe import IMPORTE_MAXIMO, validar_importe
from app.modules.cuentas_corrientes.domain.reglas import efecto_sobre_saldo, saldo_de

# Importes válidos de `numeric(14,2)`: centavos enteros positivos. Se construyen
# desde enteros para no pasar por `float` (INV-03) y se pasan por
# `validar_importe`, que es el camino real de un importe de entrada.
_IMPORTES = st.integers(min_value=1, max_value=int(IMPORTE_MAXIMO * 100)).map(
    lambda centavos: validar_importe(Decimal(centavos) / 100)
)

_MOVIMIENTOS = st.lists(st.tuples(st.sampled_from(SENTIDOS), _IMPORTES), max_size=60)


def _aplicar_uno_por_uno(movimientos: list[tuple[str, Decimal]]) -> Decimal:
    saldo = Decimal("0.00")
    for sentido, importe in movimientos:
        saldo += efecto_sobre_saldo(sentido, importe)
    return saldo


@given(_MOVIMIENTOS)
def test_inv13_aplicar_los_efectos_uno_por_uno_es_aumentan_menos_reducen(
    movimientos: list[tuple[str, Decimal]],
) -> None:
    aumentan = sum((importe for sentido, importe in movimientos if sentido == AUMENTA), Decimal(0))
    reducen = sum((importe for sentido, importe in movimientos if sentido == REDUCE), Decimal(0))

    assert _aplicar_uno_por_uno(movimientos) == aumentan - reducen
    assert saldo_de(movimientos) == aumentan - reducen


@given(_MOVIMIENTOS, st.randoms(use_true_random=False))
def test_inv13_el_saldo_no_depende_del_orden_de_los_movimientos(
    movimientos: list[tuple[str, Decimal]], azar: object
) -> None:
    barajados = list(movimientos)
    azar.shuffle(barajados)  # type: ignore[attr-defined]

    assert _aplicar_uno_por_uno(barajados) == _aplicar_uno_por_uno(movimientos)
    assert saldo_de(barajados) == saldo_de(movimientos)


@given(_MOVIMIENTOS, _IMPORTES)
def test_inv13_un_movimiento_inverso_deja_el_saldo_como_estaba(
    movimientos: list[tuple[str, Decimal]], importe: Decimal
) -> None:
    """CC-06, TR-06: las correcciones usan movimientos inversos; sumar un
    aumento y una reducción del mismo importe no cambia el saldo."""
    antes = saldo_de(movimientos)

    despues = saldo_de([*movimientos, (AUMENTA, importe), (REDUCE, importe)])

    assert despues == antes
