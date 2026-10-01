"""Tarea 4.1: dominio puro de `costeo` (CST-10 a CST-12, `design.md` D4, D6, D10).

Los casos numéricos canónicos viven en
`shared/fixtures/calculo/cst-11-costo-promedio.json` y los corre
`tests/fixtures_compartidos/test_cst11_costo_promedio_fixtures.py`; acá se
prueban los contratos que ese formato no expresa: tipos de entrada, límites,
códigos de error y estados inconsistentes.

Reglas citadas: CST-10, CST-11, CST-12, TR-02, TR-03, INV-03, INV-04.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.modules.costeo.domain.costo_promedio import (
    COSTO_MAXIMO,
    STOCK_MAXIMO,
    calcular_egreso,
    calcular_ingreso,
    validar_costo,
)
from app.modules.costeo.domain.errores import (
    CantidadInvalidaError,
    CostoInvalidoError,
    PromedioInconsistenteError,
    StockFueraDeRangoError,
)

# --- validar_costo (D6) ------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("1000", Decimal("1000.000000")),
        ("1000.5", Decimal("1000.500000")),
        ("0.000001", Decimal("0.000001")),
        ("999999999999.999999", COSTO_MAXIMO),
        (Decimal("31250.25"), Decimal("31250.250000")),
        (Decimal("7"), Decimal("7.000000")),
    ],
)
def test_validar_costo_acepta_decimales_exactos_y_fija_seis_decimales(
    entrada: str | Decimal, esperado: Decimal
) -> None:
    """D6-A: `costo_unitario > 0`, hasta 6 decimales sin redondear."""
    resultado = validar_costo(entrada)

    assert resultado == esperado
    assert resultado.as_tuple().exponent == -6


@pytest.mark.parametrize(
    "entrada",
    [
        "0",
        "0.000000",
        "-1",
        "-0.000001",
        "1000.0000001",
        Decimal("0.0000001"),
        "1e3",
        "abc",
        "",
        " 1000",
        "1.000.000",
        "1000000000000.000000",
        "NaN",
        "Infinity",
        Decimal("NaN"),
        Decimal("Infinity"),
        1000,
        1000.5,
        True,
        None,
    ],
)
def test_validar_costo_rechaza_todo_lo_que_no_sea_costo_exacto_positivo(entrada: object) -> None:
    """D6-A, TR-02, INV-03: sin redondear, sin punto flotante, sin números."""
    with pytest.raises(CostoInvalidoError) as error:
        validar_costo(entrada)

    assert error.value.codigo == "COSTO_INVALIDO"
    assert isinstance(error.value, DomainError)


# --- calcular_ingreso (CST-11) ------------------------------------------------


def test_un_ingreso_promedia_ponderando_por_el_stock_total_previo() -> None:
    """CST-11, `01` §6.2: (60 x 1000 + 60 x 1100) / 120."""
    resultado = calcular_ingreso(
        stock_previo=60, promedio_previo=Decimal("1000.000000"), cantidad=60, costo_ingreso="1100"
    )

    assert resultado.promedio_nuevo == Decimal("1050.000000")
    assert resultado.stock_nuevo == 120


def test_un_ingreso_con_otro_stock_y_otros_costos_triangula_la_formula() -> None:
    """Segundo caso con entradas distintas: (10 x 250 + 30 x 350) / 40 = 325."""
    resultado = calcular_ingreso(
        stock_previo=10, promedio_previo=Decimal("250.000000"), cantidad=30, costo_ingreso="350"
    )

    assert resultado.promedio_nuevo == Decimal("325.000000")
    assert resultado.stock_nuevo == 40


def test_el_resultado_del_ingreso_lleva_seis_decimales() -> None:
    resultado = calcular_ingreso(
        stock_previo=0, promedio_previo=None, cantidad=1, costo_ingreso=Decimal("5")
    )

    assert str(resultado.promedio_nuevo) == "5.000000"


def test_con_stock_previo_cero_o_negativo_el_promedio_es_el_costo_del_ingreso() -> None:
    """CST-11: si el stock total previo es cero o negativo no se pondera."""
    for stock_previo in (0, -1, -1000):
        resultado = calcular_ingreso(
            stock_previo=stock_previo,
            promedio_previo=Decimal("9999.000000"),
            cantidad=2000,
            costo_ingreso="12.345678",
        )
        assert resultado.promedio_nuevo == Decimal("12.345678")
        assert resultado.stock_nuevo == stock_previo + 2000


def test_el_promedio_previo_con_stock_previo_positivo_es_obligatorio() -> None:
    """D10: `costo_promedio` nulo solo mientras no hubo ingresos con costo; con
    stock positivo y sin promedio el estado es inconsistente y no se inventa
    un valor."""
    with pytest.raises(PromedioInconsistenteError) as error:
        calcular_ingreso(stock_previo=5, promedio_previo=None, cantidad=1, costo_ingreso="10")

    assert error.value.codigo == "PROMEDIO_INCONSISTENTE"


@pytest.mark.parametrize("cantidad", [0, -1, -60])
def test_un_ingreso_exige_cantidad_positiva(cantidad: int) -> None:
    """Un ingreso con costo es siempre de una cantidad positiva (CST-11)."""
    with pytest.raises(CantidadInvalidaError) as error:
        calcular_ingreso(
            stock_previo=0, promedio_previo=None, cantidad=cantidad, costo_ingreso="10"
        )

    assert error.value.codigo == "CANTIDAD_INVALIDA"


@pytest.mark.parametrize("cantidad", [1.5, "60", None, True])
def test_una_cantidad_que_no_es_entera_se_rechaza(cantidad: object) -> None:
    """INV-04: las cantidades base son enteras."""
    with pytest.raises(CantidadInvalidaError):
        calcular_ingreso(
            stock_previo=0,
            promedio_previo=None,
            cantidad=cantidad,  # type: ignore[arg-type]
            costo_ingreso="10",
        )


def test_un_ingreso_con_costo_invalido_no_calcula_nada() -> None:
    with pytest.raises(CostoInvalidoError):
        calcular_ingreso(stock_previo=0, promedio_previo=None, cantidad=1, costo_ingreso="0")


def test_el_stock_total_no_puede_superar_el_maximo_de_integer() -> None:
    """`integer` de PostgreSQL: el desborde es un error de dominio, no un
    error de la base."""
    with pytest.raises(StockFueraDeRangoError) as error:
        calcular_ingreso(
            stock_previo=STOCK_MAXIMO,
            promedio_previo=Decimal("1.000000"),
            cantidad=1,
            costo_ingreso="1",
        )

    assert error.value.codigo == "STOCK_FUERA_DE_RANGO"


def test_el_stock_total_puede_llegar_exacto_al_maximo() -> None:
    resultado = calcular_ingreso(
        stock_previo=STOCK_MAXIMO - 1,
        promedio_previo=Decimal("1.000000"),
        cantidad=1,
        costo_ingreso="1",
    )

    assert resultado.stock_nuevo == STOCK_MAXIMO


def test_el_promedio_ponderado_de_dos_costos_validos_nunca_desborda_numeric() -> None:
    """El promedio queda entre los dos costos: con costos dentro de
    `numeric(18,6)` el resultado también entra."""
    resultado = calcular_ingreso(
        stock_previo=1,
        promedio_previo=COSTO_MAXIMO,
        cantidad=1,
        costo_ingreso=COSTO_MAXIMO,
    )

    assert resultado.promedio_nuevo == COSTO_MAXIMO


# --- calcular_egreso (CST-12) --------------------------------------------------


def test_un_egreso_no_cambia_el_promedio_y_se_valoriza_a_ese_promedio() -> None:
    """CST-12, `01` §6.2: egreso de 72 sobre 120 a 1050."""
    resultado = calcular_egreso(
        stock_previo=120, promedio_previo=Decimal("1050.000000"), cantidad=72
    )

    assert resultado.promedio_nuevo == Decimal("1050.000000")
    assert resultado.costo_valorizacion == Decimal("1050.000000")
    assert resultado.stock_nuevo == 48


def test_un_egreso_con_otros_valores_triangula() -> None:
    resultado = calcular_egreso(stock_previo=5, promedio_previo=Decimal("12.345678"), cantidad=5)

    assert resultado.promedio_nuevo == Decimal("12.345678")
    assert resultado.costo_valorizacion == Decimal("12.345678")
    assert resultado.stock_nuevo == 0


def test_un_egreso_sin_promedio_no_valoriza_y_deja_el_promedio_nulo() -> None:
    """D10: un producto sin ingresos con costo sigue "sin costo"."""
    resultado = calcular_egreso(stock_previo=10, promedio_previo=None, cantidad=4)

    assert resultado.promedio_nuevo is None
    assert resultado.costo_valorizacion is None
    assert resultado.stock_nuevo == 6


@pytest.mark.parametrize("cantidad", [0, -1])
def test_un_egreso_exige_cantidad_positiva(cantidad: int) -> None:
    """El signo lo pone el llamador: el egreso se expresa en magnitud."""
    with pytest.raises(CantidadInvalidaError):
        calcular_egreso(stock_previo=10, promedio_previo=None, cantidad=cantidad)


def test_un_egreso_no_valida_el_stock_suficiente() -> None:
    """La condición de saldo suficiente es de `stock` (`02` §7.4, STK-05); el
    dominio de costeo solo informa el nuevo total, negativo incluido."""
    resultado = calcular_egreso(stock_previo=3, promedio_previo=Decimal("10.000000"), cantidad=5)

    assert resultado.stock_nuevo == -2


def test_un_egreso_que_baja_del_minimo_de_integer_se_rechaza() -> None:
    with pytest.raises(StockFueraDeRangoError):
        calcular_egreso(stock_previo=-STOCK_MAXIMO - 1, promedio_previo=None, cantidad=1)
