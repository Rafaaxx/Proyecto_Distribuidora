"""INV-12 y CST-11 en el dominio puro, con Hypothesis (tarea 4.4; `docs/02` §15).

INV-12: el stock de cada producto y ubicación es igual a la suma de sus
movimientos (STK-04). Acá se prueba la definición pura, sin base de datos:

1. aplicar los movimientos uno por uno (`aplicar_movimiento`) da lo mismo que la
   suma de los movimientos de cada par producto-ubicación (`saldo_de`);
2. el resultado no depende del orden;
3. el stock total de un producto es la suma de sus saldos por ubicación;
4. un movimiento inverso deja el saldo como estaba (TR-06).

CST-11 sobre secuencias de ingresos y egresos:

5. el stock total es la suma de los ingresos menos los egresos;
6. el promedio queda entre el menor y el mayor de los costos ingresados;
7. el promedio de una secuencia de ingresos coincide con el promedio ponderado
   exacto redondeado una sola vez, salvo el error inevitable de que el promedio
   vigente se guarda con 6 decimales (`numeric(18,6)`, `design.md` D10) y el
   ingreso siguiente parte de ese valor ya redondeado: cada ingreso puede
   desviar a lo sumo medio millonésimo, así que la diferencia total no supera
   `n x 0,0000005`. Con UN solo ingreso el resultado es exactamente el ponderado;
8. un egreso no cambia el promedio (CST-12).

La contraparte contra PostgreSQL (`stock_saldo` = suma SQL del libro) es la tarea
9.2 (`test_inv12_stock_postgres.py`).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext

from hypothesis import given
from hypothesis import strategies as st

from app.core.money import redondear_costo
from app.modules.costeo.domain.costo_promedio import calcular_egreso, calcular_ingreso
from app.modules.stock.domain.movimientos import aplicar_movimiento, saldo_de

_PRODUCTOS = ("P1", "P2", "P3")
_UBICACIONES = ("DEPOSITO", "CAMION_1", "CAMION_2")

_CANTIDADES = st.integers(min_value=-1_000, max_value=1_000).filter(lambda n: n != 0)
_MOVIMIENTOS = st.lists(
    st.tuples(st.sampled_from(_PRODUCTOS), st.sampled_from(_UBICACIONES), _CANTIDADES),
    max_size=80,
)

# Costos válidos de `numeric(18,6)`: micro-unidades enteras, sin pasar por `float`
# (INV-03).
_COSTOS = st.integers(min_value=1, max_value=5_000_000_000).map(
    lambda micro: (Decimal(micro) / 1_000_000).quantize(Decimal("0.000001"))
)
_CANTIDADES_DE_INGRESO = st.integers(min_value=1, max_value=10_000)
_INGRESOS = st.lists(st.tuples(_CANTIDADES_DE_INGRESO, _COSTOS), min_size=1, max_size=25)

_MEDIO_MILLONESIMO = Decimal("0.0000005")


def _por_pares(
    movimientos: list[tuple[str, str, int]],
) -> dict[tuple[str, str], list[int]]:
    agrupados: dict[tuple[str, str], list[int]] = defaultdict(list)
    for producto, ubicacion, cantidad in movimientos:
        agrupados[(producto, ubicacion)].append(cantidad)
    return agrupados


def _aplicar_uno_por_uno(movimientos: list[tuple[str, str, int]]) -> dict[tuple[str, str], int]:
    saldos: dict[tuple[str, str], int] = defaultdict(int)
    for producto, ubicacion, cantidad in movimientos:
        saldos[(producto, ubicacion)] = aplicar_movimiento(saldos[(producto, ubicacion)], cantidad)
    return dict(saldos)


@given(_MOVIMIENTOS)
def test_inv12_aplicar_uno_por_uno_es_la_suma_de_los_movimientos_de_cada_par(
    movimientos: list[tuple[str, str, int]],
) -> None:
    saldos = _aplicar_uno_por_uno(movimientos)

    esperado = {par: saldo_de(cantidades) for par, cantidades in _por_pares(movimientos).items()}
    assert saldos == esperado


@given(_MOVIMIENTOS, st.randoms(use_true_random=False))
def test_inv12_el_saldo_no_depende_del_orden_de_los_movimientos(
    movimientos: list[tuple[str, str, int]], azar: object
) -> None:
    barajados = list(movimientos)
    azar.shuffle(barajados)  # type: ignore[attr-defined]

    assert _aplicar_uno_por_uno(barajados) == _aplicar_uno_por_uno(movimientos)


@given(_MOVIMIENTOS)
def test_inv12_el_stock_total_es_la_suma_de_los_saldos_por_ubicacion(
    movimientos: list[tuple[str, str, int]],
) -> None:
    saldos = _aplicar_uno_por_uno(movimientos)

    for producto in _PRODUCTOS:
        de_las_ubicaciones = sum(s for (p, _), s in saldos.items() if p == producto)
        del_producto = saldo_de(c for p, _, c in movimientos if p == producto)
        assert de_las_ubicaciones == del_producto


@given(_MOVIMIENTOS, st.sampled_from(_PRODUCTOS), st.sampled_from(_UBICACIONES), _CANTIDADES)
def test_inv12_un_movimiento_inverso_deja_el_saldo_como_estaba(
    movimientos: list[tuple[str, str, int]], producto: str, ubicacion: str, cantidad: int
) -> None:
    """TR-06: las correcciones usan movimientos inversos."""
    antes = _aplicar_uno_por_uno(movimientos)

    despues = _aplicar_uno_por_uno(
        [*movimientos, (producto, ubicacion, cantidad), (producto, ubicacion, -cantidad)]
    )

    assert {par: s for par, s in despues.items() if s != 0} == {
        par: s for par, s in antes.items() if s != 0
    }


# --- CST-11 y CST-12 sobre secuencias -----------------------------------------


def _promedio_ponderado_exacto(ingresos: list[tuple[int, Decimal]]) -> Decimal:
    with localcontext() as contexto:
        contexto.prec = 60
        total = sum((Decimal(q) * costo for q, costo in ingresos), Decimal(0))
        return redondear_costo(total / Decimal(sum(q for q, _ in ingresos)))


def _aplicar_ingresos(
    ingresos: list[tuple[int, Decimal]],
) -> tuple[int, Decimal | None]:
    stock = 0
    promedio: Decimal | None = None
    for cantidad, costo in ingresos:
        resultado = calcular_ingreso(
            stock_previo=stock, promedio_previo=promedio, cantidad=cantidad, costo_ingreso=costo
        )
        stock, promedio = resultado.stock_nuevo, resultado.promedio_nuevo
    return stock, promedio


@given(_INGRESOS)
def test_cst11_el_stock_total_es_la_suma_de_los_ingresos(
    ingresos: list[tuple[int, Decimal]],
) -> None:
    stock, _ = _aplicar_ingresos(ingresos)

    assert stock == sum(q for q, _ in ingresos)


@given(_INGRESOS)
def test_cst11_el_promedio_queda_entre_el_menor_y_el_mayor_costo(
    ingresos: list[tuple[int, Decimal]],
) -> None:
    _, promedio = _aplicar_ingresos(ingresos)

    assert promedio is not None
    assert min(c for _, c in ingresos) <= promedio <= max(c for _, c in ingresos)


@given(_INGRESOS)
def test_cst11_el_promedio_coincide_con_el_ponderado_exacto_salvo_medio_millonesimo_por_ingreso(
    ingresos: list[tuple[int, Decimal]],
) -> None:
    _, promedio = _aplicar_ingresos(ingresos)

    assert promedio is not None
    diferencia = abs(promedio - _promedio_ponderado_exacto(ingresos))
    assert diferencia <= _MEDIO_MILLONESIMO * len(ingresos)


@given(_CANTIDADES_DE_INGRESO, _COSTOS)
def test_cst11_un_solo_ingreso_da_exactamente_su_costo(cantidad: int, costo: Decimal) -> None:
    _, promedio = _aplicar_ingresos([(cantidad, costo)])

    assert promedio == costo


@given(_CANTIDADES_DE_INGRESO, _COSTOS, _CANTIDADES_DE_INGRESO, _COSTOS)
def test_cst11_dos_ingresos_dan_exactamente_el_ponderado_redondeado_una_vez(
    q1: int, c1: Decimal, q2: int, c2: Decimal
) -> None:
    """Con dos ingresos no hay un promedio intermedio redondeado que arrastre
    error: el primero es exactamente `c1`."""
    _, promedio = _aplicar_ingresos([(q1, c1), (q2, c2)])

    assert promedio == _promedio_ponderado_exacto([(q1, c1), (q2, c2)])


@given(_INGRESOS, st.lists(st.integers(min_value=1, max_value=50_000), max_size=10))
def test_cst12_los_egresos_no_cambian_el_promedio_y_restan_del_stock(
    ingresos: list[tuple[int, Decimal]], egresos: list[int]
) -> None:
    stock, promedio = _aplicar_ingresos(ingresos)

    for cantidad in egresos:
        resultado = calcular_egreso(stock_previo=stock, promedio_previo=promedio, cantidad=cantidad)
        assert resultado.promedio_nuevo == promedio
        assert resultado.costo_valorizacion == promedio
        assert resultado.stock_nuevo == stock - cantidad
        stock = resultado.stock_nuevo

    assert stock == sum(q for q, _ in ingresos) - sum(egresos)
