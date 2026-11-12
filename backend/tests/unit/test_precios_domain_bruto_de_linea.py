"""Change 13, tarea 3.3: `precios/domain/bruto_de_linea.py::calcular_bruto_de_linea`
(PRC-22, `design.md` D10, `01` §7.3).

Los casos que el servidor y el dispositivo comparten corren en
`backend/tests/fixtures_compartidos/test_prc22_bruto_de_linea_fixtures.py`; acá, lo que
solo el servidor puede afirmar: que el total no se arma con el precio unitario
redondeado, el rechazo de `float` (INV-03) y de cantidades no enteras (INV-04), y la
propiedad de que `n x unidades de referencia` unidades cuestan exactamente `n x precio`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError, redondear_importe
from app.modules.precios.domain.bruto_de_linea import calcular_bruto_de_linea
from app.modules.precios.domain.errores import (
    CantidadBaseInvalidaError,
    UnidadesReferenciaInvalidasError,
)

# --- los ejemplos de `01` §7.3 ---------------------------------------------------


@pytest.mark.parametrize(
    ("precio", "unidades", "cantidad", "esperado"),
    [
        ("12500.00", 6, 15, "31250.00"),
        ("8600.00", 6, 3, "4300.00"),
        ("8600.00", 6, 1, "1433.33"),
    ],
)
def test_prc22_ejemplos_del_dominio(
    precio: str, unidades: int, cantidad: int, esperado: str
) -> None:
    assert str(calcular_bruto_de_linea(Decimal(precio), unidades, cantidad)) == esperado


def test_prc22_el_precio_puede_llegar_como_cadena_exacta() -> None:
    assert calcular_bruto_de_linea("8600.00", 6, 1) == Decimal("1433.33")


# --- un solo redondeo (TR-03) ------------------------------------------------------


def test_el_total_no_se_arma_con_el_precio_unitario_redondeado() -> None:
    """PRC-22: el unitario mostrado ($1.433,33) por 3 daría `4299.99`; el bruto correcto
    es `4300.00` porque se redondea una sola vez al final."""
    precio, unidades = Decimal("8600.00"), 6
    unitario_mostrado = calcular_bruto_de_linea(precio, unidades, 1)

    assert unitario_mostrado * 3 == Decimal("4299.99")
    assert calcular_bruto_de_linea(precio, unidades, 3) == Decimal("4300.00")


def test_el_medio_exacto_sube_y_el_resultado_tiene_dos_decimales() -> None:
    assert calcular_bruto_de_linea(Decimal("5.00"), 8, 1) == Decimal("0.63")
    assert calcular_bruto_de_linea(Decimal("5.00"), 8, 1).as_tuple().exponent == -2
    assert calcular_bruto_de_linea(Decimal("0.01"), 2, 1) == Decimal("0.01")


def test_un_cociente_periodico_no_pierde_precision_antes_del_redondeo() -> None:
    """`8600 x 5 / 6 = 7166.666...` y `8600 x 7 / 6 = 10033.333...`."""
    assert calcular_bruto_de_linea(Decimal("8600.00"), 6, 5) == Decimal("7166.67")
    assert calcular_bruto_de_linea(Decimal("8600.00"), 6, 7) == Decimal("10033.33")


# --- INV-03: sin punto flotante ----------------------------------------------------


@pytest.mark.parametrize("precio", [8600.0, 8600.5, True])
def test_inv03_rechaza_un_precio_de_punto_flotante(precio: object) -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_bruto_de_linea(precio, 6, 1)  # type: ignore[arg-type]


def test_inv03_rechaza_una_cadena_que_no_es_un_decimal() -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        calcular_bruto_de_linea("ocho mil", 6, 1)


# --- INV-04: cantidades enteras y positivas -----------------------------------------


@pytest.mark.parametrize("cantidad", [0, -1, -15])
def test_una_cantidad_base_no_positiva_se_rechaza(cantidad: int) -> None:
    with pytest.raises(CantidadBaseInvalidaError) as error:
        calcular_bruto_de_linea(Decimal("8600.00"), 6, cantidad)
    assert error.value.codigo == "CANTIDAD_BASE_INVALIDA"
    assert isinstance(error.value, DomainError)


@pytest.mark.parametrize("cantidad", [1.5, Decimal("2"), "3", True])
def test_inv04_una_cantidad_base_no_entera_se_rechaza(cantidad: object) -> None:
    with pytest.raises(CantidadBaseInvalidaError):
        calcular_bruto_de_linea(Decimal("8600.00"), 6, cantidad)  # type: ignore[arg-type]


@pytest.mark.parametrize("unidades", [0, -6])
def test_unas_unidades_de_referencia_menores_que_uno_se_rechazan(unidades: int) -> None:
    with pytest.raises(UnidadesReferenciaInvalidasError) as error:
        calcular_bruto_de_linea(Decimal("8600.00"), unidades, 3)
    assert error.value.codigo == "UNIDADES_REFERENCIA_INVALIDAS"


@pytest.mark.parametrize("unidades", [6.0, Decimal("6"), "6", False])
def test_inv04_unas_unidades_de_referencia_no_enteras_se_rechazan(unidades: object) -> None:
    with pytest.raises(UnidadesReferenciaInvalidasError):
        calcular_bruto_de_linea(Decimal("8600.00"), unidades, 3)  # type: ignore[arg-type]


# --- propiedades ---------------------------------------------------------------------

_PRECIOS = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("999999999.99"), places=2, allow_nan=False
)
_UNIDADES = st.integers(min_value=1, max_value=10_000)


@given(precio=_PRECIOS, unidades=_UNIDADES, n=st.integers(min_value=1, max_value=100_000))
def test_el_bruto_de_n_presentaciones_es_exactamente_n_por_el_precio(
    precio: Decimal, unidades: int, n: int
) -> None:
    """`n x unidades de referencia` unidades base cuestan `n x precio de referencia`, sin
    deriva de redondeo (PRC-22: ejemplo `2 cajas = 2 x $12.500 = $25.000`)."""
    assert calcular_bruto_de_linea(precio, unidades, n * unidades) == redondear_importe(precio * n)


@given(precio=_PRECIOS, unidades=_UNIDADES, cantidad=st.integers(min_value=1, max_value=1_000_000))
def test_el_bruto_es_el_exacto_redondeado_una_vez(
    precio: Decimal, unidades: int, cantidad: int
) -> None:
    """Contra una referencia exacta con aritmética entera: el bruto es
    `round_half_up(precio_centavos x cantidad / (100 x unidades))` a dos decimales."""
    centavos = int(precio * 100)
    numerador = centavos * cantidad
    # round-half-up exacto sobre enteros (los centavos del resultado).
    redondeado = (2 * numerador + unidades) // (2 * unidades)

    assert calcular_bruto_de_linea(precio, unidades, cantidad) == Decimal(redondeado) / 100
