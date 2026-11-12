"""Tarea 3.1 (change 10): conversión exacta de texto a decimal, entero, booleano y
fecha de la planilla (`specs/importacion/planillas`, `design.md` D3 y D12).

Funciones puras: ninguna toca la base ni importa infraestructura. El separador
decimal es la coma, sin separador de miles, y el punto se rechaza (D12): `1.500`
es ambiguo y se lee en silencio como 1,5 o como 1500 según quien lo mire. Ningún
valor pasa por `float`.

Reglas citadas: INV-03 (ningún valor con punto flotante), INV-04 (cantidades
enteras), TR-01, TR-02, `design.md` D12.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.importacion.domain.errores import (
    CantidadInvalidaError,
    FechaInvalidaError,
    NumeroInvalidoError,
    ValorInvalidoError,
)
from app.modules.importacion.domain.valores import (
    a_booleano,
    a_decimal,
    a_entero,
    a_fecha,
)

# --- decimales (D12) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("18000,00", "18000.00"),
        ("18000,50", "18000.50"),
        ("0,000001", "0.000001"),
        ("18000", "18000"),
        ("  1239,669421 ", "1239.669421"),
        ("-12,5", "-12.5"),
    ],
)
def test_un_decimal_con_coma_se_lee_exacto_y_conserva_su_escala(texto: str, esperado: str) -> None:
    """Escenario "Coma decimal": `18000,00` es exactamente `"18000.00"` (TR-01)."""
    valor = a_decimal(texto, columna="valor")

    assert isinstance(valor, Decimal)
    assert str(valor) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "1.500",  # punto ambiguo (escenario "Punto ambiguo rechazado")
        "1.234,56",  # separador de miles (escenario "Separador de miles rechazado")
        "1,234,56",  # más de un separador
        "18000.50",  # el punto no es decimal en texto (D12)
        "abc",
        "",
        "   ",
        ",5",
        "5,",
        "1e3",
        "NaN",
        "Infinity",
        "--5",
        "1 000",
        "$1000",
    ],
)
def test_un_decimal_mal_escrito_da_numero_invalido_con_su_columna(texto: str) -> None:
    with pytest.raises(NumeroInvalidoError) as error:
        a_decimal(texto, columna="importe")

    assert error.value.codigo == "NUMERO_INVALIDO"
    assert error.value.columna == "importe"
    assert error.value.status_http == 422


def test_un_decimal_demasiado_largo_se_rechaza_sin_intentar_leerlo() -> None:
    """Un texto absurdo no llega a la base (desbordaría la columna `NUMERIC`)."""
    with pytest.raises(NumeroInvalidoError):
        a_decimal("9" * 60, columna="valor")


@given(
    entero=st.integers(min_value=0, max_value=10**12),
    decimales=st.integers(min_value=0, max_value=999_999),
    cantidad_de_decimales=st.integers(min_value=1, max_value=6),
    negativo=st.booleans(),
)
def test_inv03_todo_decimal_con_hasta_seis_decimales_escrito_con_coma_vuelve_igual(
    entero: int, decimales: int, cantidad_de_decimales: int, negativo: bool
) -> None:
    """INV-03: la lectura es exacta, sin pasar por binario. Se arma el texto con
    coma y se compara contra el `Decimal` de partida."""
    parte_decimal = str(decimales).zfill(6)[:cantidad_de_decimales]
    signo = "-" if negativo else ""
    original = Decimal(f"{signo}{entero}.{parte_decimal}")

    leido = a_decimal(f"{signo}{entero},{parte_decimal}", columna="costo")

    assert leido == original
    assert str(leido) == str(original)  # misma escala, sin ceros de más ni de menos


# --- enteros (INV-04) --------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("10", 10), ("-12", -12), ("0", 0), (" 60 ", 60), ("10,0", 10), ("10,00", 10)],
)
def test_un_entero_se_lee_exacto_y_admite_decimales_en_cero(texto: str, esperado: int) -> None:
    valor = a_entero(texto, columna="cantidad_base")

    assert valor == esperado
    assert type(valor) is int


@pytest.mark.parametrize(
    "texto",
    [
        "10,5",  # escenario "Cantidad con decimales"
        "1.500",
        "abc",
        "",
        "2147483648",  # fuera del rango de `integer`
        "-2147483649",
        "10,5,1",
    ],
)
def test_inv04_una_cantidad_con_decimales_o_no_numerica_da_cantidad_invalida(
    texto: str,
) -> None:
    with pytest.raises(CantidadInvalidaError) as error:
        a_entero(texto, columna="cantidad_base")

    assert error.value.codigo == "CANTIDAD_INVALIDA"
    assert error.value.columna == "cantidad_base"


def test_el_entero_en_el_limite_de_integer_se_acepta() -> None:
    assert a_entero("2147483647", columna="cantidad_base") == 2_147_483_647
    assert a_entero("-2147483648", columna="cantidad_base") == -2_147_483_648


# --- booleanos ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("S", True),
        ("s", True),
        ("SI", True),
        ("Sí", True),
        ("SÍ", True),
        (" si ", True),
        ("N", False),
        ("n", False),
        ("NO", False),
        ("no", False),
    ],
)
def test_los_booleanos_aceptan_s_si_n_no_sin_distinguir_mayusculas(
    texto: str, esperado: bool
) -> None:
    assert a_booleano(texto, columna="incluye_iva") is esperado


@pytest.mark.parametrize("texto", ["quizás", "true", "1", "", "SII", "X"])
def test_un_booleano_distinto_de_los_admitidos_da_valor_invalido(texto: str) -> None:
    """Escenario "Booleano inválido"."""
    with pytest.raises(ValorInvalidoError) as error:
        a_booleano(texto, columna="incluye_iva")

    assert error.value.codigo == "VALOR_INVALIDO"
    assert error.value.columna == "incluye_iva"


# --- fechas ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2026-10-01", date(2026, 10, 1)),
        ("01/10/2026", date(2026, 10, 1)),  # escenario "Fecha en formato local"
        ("1/2/2026", date(2026, 2, 1)),
        ("29/02/2028", date(2028, 2, 29)),
        (" 31/12/2026 ", date(2026, 12, 31)),
    ],
)
def test_las_fechas_aceptan_iso_y_dia_mes_anio(texto: str, esperado: date) -> None:
    assert a_fecha(texto, columna="vigencia_desde") == esperado


@pytest.mark.parametrize(
    "texto",
    ["2026/10/01", "10-01-2026", "31/02/2026", "2026-13-01", "ayer", "", "01/10/26", "01-10-2026"],
)
def test_una_fecha_con_otra_forma_o_inexistente_da_fecha_invalida(texto: str) -> None:
    with pytest.raises(FechaInvalidaError) as error:
        a_fecha(texto, columna="vigencia_desde")

    assert error.value.codigo == "FECHA_INVALIDA"
    assert error.value.columna == "vigencia_desde"
