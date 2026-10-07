"""Change 13, tarea 4.3: redondeo del precio final (`precios/domain/redondeo.py`; spec
`precios/calculo-de-precios`; PRC-14, `design.md` D9).

Los primeros casos son los ejemplos de `01` §7.2: calculado `8571.428571` con múltiplo
`100.00` da `8600.00` (arriba), `8600.00` (más cercano) y `8500.00` (abajo).

Reglas citadas: PRC-14, TR-03 (medio hacia arriba), INV-03 (sin punto flotante).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.core.money import EntradaNoEsDineroExactoError
from app.modules.precios.domain.errores import PrecioNoPositivoError, RedondeoInvalidoError
from app.modules.precios.domain.redondeo import (
    Redondeo,
    aplicar_redondeo,
    redondear_al_multiplo,
    redondeo_aplicable,
    validar_redondeo,
)

# --- PRC-14: las tres direcciones ---------------------------------------------------------


@pytest.mark.parametrize(
    ("direccion", "esperado"),
    [("ARRIBA", "8600.00"), ("CERCANO", "8600.00"), ("ABAJO", "8500.00")],
)
def test_las_tres_direcciones_del_ejemplo(direccion: str, esperado: str) -> None:
    final = aplicar_redondeo(Decimal("8571.428571"), Decimal("100.00"), direccion)

    assert str(final) == esperado


@pytest.mark.parametrize("direccion", ["ARRIBA", "CERCANO", "ABAJO"])
def test_un_multiplo_exacto_no_cambia(direccion: str) -> None:
    assert str(aplicar_redondeo(Decimal("7800.000000"), Decimal("100.00"), direccion)) == "7800.00"


def test_el_punto_medio_en_mas_cercano_redondea_hacia_arriba() -> None:
    """TR-03: `8550.000000` está justo entre `8500` y `8600`."""
    assert str(aplicar_redondeo(Decimal("8550.000000"), Decimal("100.00"), "CERCANO")) == "8600.00"


@pytest.mark.parametrize(
    ("calculado", "esperado"),
    [
        ("8549.999999", "8500.00"),  # justo por debajo del medio
        ("8550.000001", "8600.00"),
        ("8500.000001", "8500.00"),
        ("8599.999999", "8600.00"),
    ],
)
def test_mas_cercano_a_ambos_lados_del_medio(calculado: str, esperado: str) -> None:
    assert str(aplicar_redondeo(Decimal(calculado), Decimal("100.00"), "CERCANO")) == esperado


@pytest.mark.parametrize(
    ("direccion", "esperado"),
    [("CERCANO", "8571.43"), ("ARRIBA", "8571.43"), ("ABAJO", "8571.42")],
)
def test_un_multiplo_de_un_centavo(direccion: str, esperado: str) -> None:
    final = aplicar_redondeo(Decimal("8571.428571"), Decimal("0.01"), direccion)

    assert str(final) == esperado


@pytest.mark.parametrize(
    ("calculado", "multiplo", "direccion", "esperado"),
    [
        ("8571.428571", "50.00", "ARRIBA", "8600.00"),
        ("8571.428571", "50.00", "ABAJO", "8550.00"),
        ("8571.428571", "500.00", "ARRIBA", "9000.00"),
        ("8571.428571", "0.05", "CERCANO", "8571.45"),
        ("1.000000", "7.50", "ARRIBA", "7.50"),
        ("100.000000", "7.50", "CERCANO", "97.50"),
    ],
)
def test_otros_multiplos(calculado: str, multiplo: str, direccion: str, esperado: str) -> None:
    final = aplicar_redondeo(Decimal(calculado), Decimal(multiplo), direccion)

    assert str(final) == esperado


def test_el_precio_final_siempre_tiene_dos_decimales() -> None:
    final = aplicar_redondeo(Decimal("8571.428571"), Decimal("100"), "ARRIBA")

    assert final.as_tuple().exponent == -2


# --- el redondeo aplicable: la categoría sobrescribe a la lista (D9) -------------------------


def test_la_sobrescritura_de_la_categoria_gana_a_la_de_la_lista() -> None:
    lista = Redondeo(Decimal("100.00"), "CERCANO")
    categoria = Redondeo(Decimal("500.00"), "ARRIBA")

    aplicable = redondeo_aplicable(lista, categoria)

    assert aplicable == categoria
    assert str(
        aplicar_redondeo(Decimal("8571.428571"), aplicable.multiplo, aplicable.direccion)
    ) == ("9000.00")


def test_sin_sobrescritura_rige_el_redondeo_de_la_lista() -> None:
    lista = Redondeo(Decimal("100.00"), "CERCANO")

    assert redondeo_aplicable(lista, None) == lista


# --- el resultado cero (D9) -------------------------------------------------------------------


def test_un_redondeo_que_da_cero_no_tiene_precio() -> None:
    with pytest.raises(PrecioNoPositivoError) as error:
        aplicar_redondeo(Decimal("80.000000"), Decimal("100.00"), "ABAJO")

    assert error.value.codigo == "PRECIO_NO_POSITIVO"
    assert isinstance(error.value, DomainError)


def test_el_mismo_precio_hacia_arriba_o_al_mas_cercano_si_tiene_precio() -> None:
    assert str(aplicar_redondeo(Decimal("80.000000"), Decimal("100.00"), "ARRIBA")) == "100.00"
    assert str(aplicar_redondeo(Decimal("80.000000"), Decimal("100.00"), "CERCANO")) == "100.00"


def test_redondear_al_multiplo_puede_dar_cero_sin_levantar_error() -> None:
    assert redondear_al_multiplo(Decimal("49.999999"), Decimal("100.00"), "CERCANO") == 0


# --- la validación del redondeo (PRC-14) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("multiplo", "direccion", "esperado"),
    [
        ("100", "ARRIBA", Decimal("100.00")),
        ("100.00", "CERCANO", Decimal("100.00")),
        ("0.01", "ABAJO", Decimal("0.01")),
        ("12.5", "ARRIBA", Decimal("12.50")),
        (Decimal("500"), "ARRIBA", Decimal("500.00")),
        ("999999999999.99", "ABAJO", Decimal("999999999999.99")),
    ],
)
def test_un_redondeo_valido_se_normaliza_a_dos_decimales(
    multiplo: str | Decimal, direccion: str, esperado: Decimal
) -> None:
    validado = validar_redondeo(multiplo, direccion)

    assert validado == Redondeo(esperado, direccion)
    assert str(validado.multiplo) == str(esperado)


@pytest.mark.parametrize(
    ("multiplo", "direccion"),
    [
        ("0", "ARRIBA"),
        ("0.00", "ARRIBA"),
        ("-100", "ARRIBA"),
        ("0.001", "ARRIBA"),  # tres decimales
        ("100.005", "CERCANO"),
        ("1000000000000", "ARRIBA"),  # no cabe en numeric(14,2)
        ("cien", "ARRIBA"),
        ("", "ARRIBA"),
        ("NaN", "ARRIBA"),
        ("Infinity", "ARRIBA"),
        ("100", "REDONDO"),
        ("100", "arriba"),
        ("100", ""),
    ],
)
def test_un_redondeo_invalido_se_rechaza_con_redondeo_invalido(
    multiplo: str, direccion: str
) -> None:
    with pytest.raises(RedondeoInvalidoError) as error:
        validar_redondeo(multiplo, direccion)

    assert error.value.codigo == "REDONDEO_INVALIDO"


@pytest.mark.parametrize("multiplo", [100.0, 0.5, True])
def test_inv03_un_multiplo_de_punto_flotante_se_rechaza(multiplo: object) -> None:
    with pytest.raises(EntradaNoEsDineroExactoError):
        validar_redondeo(multiplo, "ARRIBA")  # type: ignore[arg-type]
    with pytest.raises(EntradaNoEsDineroExactoError):
        aplicar_redondeo(Decimal("8571.43"), multiplo, "ARRIBA")  # type: ignore[arg-type]
    with pytest.raises(EntradaNoEsDineroExactoError):
        aplicar_redondeo(8571.43, Decimal("100"), "ARRIBA")  # type: ignore[arg-type]


def test_aplicar_redondeo_con_una_direccion_desconocida_se_rechaza() -> None:
    with pytest.raises(RedondeoInvalidoError):
        aplicar_redondeo(Decimal("8571.43"), Decimal("100"), "REDONDO")


# --- propiedades -----------------------------------------------------------------------------

_CALCULADOS = st.decimals(
    min_value=Decimal("0.000001"), max_value=Decimal("99999999.999999"), places=6
)
_MULTIPLOS = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000.00"), places=2)


@given(calculado=_CALCULADOS, multiplo=_MULTIPLOS)
def test_el_precio_final_es_multiplo_exacto_y_queda_a_menos_de_un_multiplo(
    calculado: Decimal, multiplo: Decimal
) -> None:
    """PRC-14: con cualquier dirección el resultado es múltiplo exacto del múltiplo;
    `ARRIBA >= calculado >= ABAJO`, `CERCANO` queda entre las dos y la distancia al calculado
    es menor que un múltiplo."""
    arriba = redondear_al_multiplo(calculado, multiplo, "ARRIBA")
    abajo = redondear_al_multiplo(calculado, multiplo, "ABAJO")
    cercano = redondear_al_multiplo(calculado, multiplo, "CERCANO")

    for final in (arriba, abajo, cercano):
        assert final % multiplo == 0
        assert abs(final - calculado) < multiplo
    assert arriba >= calculado >= abajo
    assert abajo <= cercano <= arriba
    assert arriba - abajo in (Decimal(0), multiplo)
    # El más cercano es el que está a menor distancia; en el medio exacto sube.
    distancia_arriba, distancia_abajo = arriba - calculado, calculado - abajo
    assert cercano == (arriba if distancia_arriba <= distancia_abajo else abajo)


@given(calculado=_CALCULADOS, multiplo=_MULTIPLOS)
def test_un_multiplo_exacto_no_cambia_con_ninguna_direccion(
    calculado: Decimal, multiplo: Decimal
) -> None:
    exacto = (calculado // multiplo) * multiplo

    for direccion in ("ARRIBA", "CERCANO", "ABAJO"):
        assert redondear_al_multiplo(exacto, multiplo, direccion) == exacto
