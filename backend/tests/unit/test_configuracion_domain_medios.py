"""Tareas 5.1 y 5.2 (change 17, `design.md` D13, D17): la validación de medios de pago compartida
vive en `configuracion/domain/medios.py`.

La usan el pago a un proveedor (PAG-01), el pago de contado de una compra (CMP-03) y la
cobranza (COB-02): de 1 a 20 medios de importe positivo con 2 decimales, referencia donde el
medio la exige y suma exactamente igual al importe (INV-08). Es pura: no consulta la base ni
conoce el estado de los medios (`MEDIO_PAGO_INACTIVO` e INV-21 son de la capa de servicio).

Los casos de 5.1 son los que hoy cubren `test_proveedores_domain_pagos.py` y
`test_proveedores_domain_compras.py` sobre la misma función (que `proveedores` sigue
ejerciendo); los de 5.2 son del modo sin conexión de la cobranza (`exigir_referencia=False`,
D13-C) y de la función de líneas sin referencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.errors import DomainError
from app.modules.configuracion.domain.medios import (
    ImporteInvalidoError,
    MediosInvalidosError,
    MediosNoSumanImporteError,
    ReferenciaObligatoriaError,
    posiciones_sin_referencia,
    validar_medios,
)

MAXIMO_MEDIOS = 20
"""D6: de 1 a 20 medios por pago o cobranza."""


@dataclass(frozen=True)
class Medio:
    """El medio tal como llega al dominio: importe, referencia informada y si el medio de la
    organización la exige."""

    importe: Decimal
    referencia: str | None = None
    requiere_referencia: bool = False


def medio(importe: str, *, referencia: str | None = None, exige: bool = False) -> Medio:
    return Medio(importe=Decimal(importe), referencia=referencia, requiere_referencia=exige)


def medios_de_cheques(cantidad: int, *, importe: str = "100.00") -> list[Medio]:
    return [medio(importe, referencia=f"cheque-{indice}", exige=True) for indice in range(cantidad)]


# --- 5.1: cantidad de medios (MEDIOS_INVALIDOS) --------------------------------------------


def test_un_solo_medio_que_suma_el_importe_es_valido() -> None:
    validar_medios(Decimal("152460.00"), [medio("152460.00")])


def test_sin_medios_se_rechaza_con_medios_invalidos() -> None:
    with pytest.raises(MediosInvalidosError) as error:
        validar_medios(Decimal("152460.00"), [])

    assert error.value.codigo == "MEDIOS_INVALIDOS"


def test_veinte_medios_es_valido_y_veintiuno_no() -> None:
    validar_medios(Decimal("20.00"), medios_de_cheques(MAXIMO_MEDIOS, importe="1.00"))

    with pytest.raises(MediosInvalidosError) as error:
        validar_medios(Decimal("21.00"), medios_de_cheques(MAXIMO_MEDIOS + 1, importe="1.00"))

    assert error.value.codigo == "MEDIOS_INVALIDOS"
    assert "21" in str(error.value)


def test_el_contado_de_una_compra_no_tiene_tope_de_medios() -> None:
    """CMP-03: `minimo=0, maximo=None` (la compra de contado sin medios ya es inválida por
    `MEDIOS_NO_SUMAN_IMPORTE`)."""
    validar_medios(
        Decimal("21.00"),
        medios_de_cheques(MAXIMO_MEDIOS + 1, importe="1.00"),
        minimo=0,
        maximo=None,
    )
    with pytest.raises(MediosNoSumanImporteError):
        validar_medios(Decimal("21.00"), [], minimo=0, maximo=None)


# --- 5.1: suma exacta (INV-08, MEDIOS_NO_SUMAN_IMPORTE) ------------------------------------


def test_efectivo_y_transferencia_que_suman_el_importe_son_validos() -> None:
    validar_medios(
        Decimal("152460.00"),
        [medio("100000.00"), medio("52460.00", referencia="0042", exige=True)],
    )


@pytest.mark.parametrize(
    "importes",
    [["150000.00"], ["100000.00", "52460.01"], ["152460.00", "0.01"]],
)
def test_inv08_medios_que_suman_menos_se_rechazan(importes: list[str]) -> None:
    with pytest.raises(MediosNoSumanImporteError) as error:
        validar_medios(Decimal("152460.00"), [medio(i) for i in importes])

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"


def test_inv08_medios_que_suman_mas_se_rechazan() -> None:
    """INV-08 es suma exacta, no "suma al menos"."""
    with pytest.raises(MediosNoSumanImporteError) as error:
        validar_medios(Decimal("152460.00"), [medio("100000.00"), medio("52460.00"), medio("0.01")])

    assert error.value.codigo == "MEDIOS_NO_SUMAN_IMPORTE"


def test_el_mismo_medio_puede_repetirse_con_referencias_distintas() -> None:
    validar_medios(
        Decimal("152460.00"),
        [
            medio("100000.00", referencia="0001", exige=True),
            medio("52460.00", referencia="0002", exige=True),
        ],
    )


# --- 5.1: importe del medio y del total (IMPORTE_INVALIDO, TR-01) --------------------------


@pytest.mark.parametrize("importe_medio", ["0.00", "-100.00", "100.001"])
def test_medio_con_importe_invalido_se_rechaza_indicando_cual(importe_medio: str) -> None:
    with pytest.raises(ImporteInvalidoError) as error:
        validar_medios(Decimal("100.00"), [medio("100.00"), medio(importe_medio)])

    assert error.value.codigo == "IMPORTE_INVALIDO"
    assert error.value.extension == {"medio": 1}


@pytest.mark.parametrize("importe_total", ["0.00", "-100.00", "100.001"])
def test_importe_total_invalido_se_rechaza(importe_total: str) -> None:
    with pytest.raises(ImporteInvalidoError) as error:
        validar_medios(Decimal(importe_total), [medio("100.00")])

    assert error.value.codigo == "IMPORTE_INVALIDO"


# --- 5.1: referencia obligatoria (REFERENCIA_OBLIGATORIA) ----------------------------------


@pytest.mark.parametrize("referencia", [None, "", "   "])
def test_medio_que_exige_referencia_sin_referencia_se_rechaza_indicando_cual(
    referencia: str | None,
) -> None:
    with pytest.raises(ReferenciaObligatoriaError) as error:
        validar_medios(
            Decimal("100.00"),
            [medio("40.00"), medio("60.00", referencia=referencia, exige=True)],
        )

    assert error.value.codigo == "REFERENCIA_OBLIGATORIA"
    assert error.value.extension == {"medio": 1}


def test_referencia_con_espacios_alrededor_satisface_al_medio_que_la_exige() -> None:
    validar_medios(Decimal("100.00"), [medio("100.00", referencia=" 0042 ", exige=True)])


@pytest.mark.parametrize(
    "codigo_esperado", ["MEDIOS_INVALIDOS", "IMPORTE_INVALIDO", "REFERENCIA_OBLIGATORIA"]
)
def test_los_errores_son_domain_error_422(codigo_esperado: str) -> None:
    with pytest.raises(DomainError) as error:
        if codigo_esperado == "MEDIOS_INVALIDOS":
            validar_medios(Decimal("100.00"), [])
        elif codigo_esperado == "IMPORTE_INVALIDO":
            validar_medios(Decimal("100.00"), [medio("0.00")])
        else:
            validar_medios(Decimal("100.00"), [medio("100.00", exige=True)])

    assert error.value.codigo == codigo_esperado
    assert error.value.status_http == 422


# --- 5.1: INV-08 como propiedad -----------------------------------------------------------


def _centavos_a_importe(centavos: int) -> Decimal:
    return Decimal(centavos).scaleb(-2)


@settings(max_examples=200, deadline=None)
@given(
    centavos=st.lists(
        st.integers(min_value=1, max_value=50_000_000), min_size=1, max_size=MAXIMO_MEDIOS
    )
)
def test_inv08_todo_reparto_exacto_se_acepta(centavos: list[int]) -> None:
    medios = [Medio(_centavos_a_importe(valor)) for valor in centavos]
    importe = sum((medio.importe for medio in medios), Decimal("0.00"))

    validar_medios(importe, medios)

    assert sum((medio.importe for medio in medios), Decimal("0.00")) == importe


@settings(max_examples=200, deadline=None)
@given(
    centavos=st.lists(
        st.integers(min_value=1, max_value=50_000_000), min_size=1, max_size=MAXIMO_MEDIOS
    )
)
def test_inv08_un_centavo_de_diferencia_se_rechaza_siempre(centavos: list[int]) -> None:
    medios = [Medio(_centavos_a_importe(valor + 1)) for valor in centavos]
    importe_original = sum((_centavos_a_importe(valor) for valor in centavos), Decimal("0.00"))

    with pytest.raises(MediosNoSumanImporteError):
        validar_medios(importe_original, medios)


# --- 5.2: sin exigir la referencia (cobranza sin conexión, D13-C) --------------------------


def test_sin_exigir_referencia_no_se_lanza_referencia_obligatoria() -> None:
    """D13-C: sin conexión, una referencia faltante no rechaza; se observa."""
    validar_medios(
        Decimal("100.00"),
        [medio("100.00", referencia=None, exige=True)],
        exigir_referencia=False,
    )
    validar_medios(
        Decimal("100.00"),
        [medio("60.00", referencia="  ", exige=True), medio("40.00", referencia="", exige=True)],
        exigir_referencia=False,
    )


def test_por_defecto_la_referencia_se_exige() -> None:
    with pytest.raises(ReferenciaObligatoriaError):
        validar_medios(Decimal("100.00"), [medio("100.00", referencia=None, exige=True)])
    with pytest.raises(ReferenciaObligatoriaError):
        validar_medios(
            Decimal("100.00"),
            [medio("100.00", referencia=None, exige=True)],
            exigir_referencia=True,
        )


def test_sin_exigir_referencia_sigue_rechazando_lo_malformado() -> None:
    """INV-08, TR-01 y el rango de medios no se relajan sin conexión (SYN-06)."""
    with pytest.raises(MediosNoSumanImporteError):
        validar_medios(
            Decimal("100.00"),
            [medio("90.00", referencia=None, exige=True)],
            exigir_referencia=False,
        )
    with pytest.raises(MediosInvalidosError):
        validar_medios(Decimal("100.00"), [], exigir_referencia=False)
    with pytest.raises(ImporteInvalidoError):
        validar_medios(
            Decimal("100.00"), [medio("0.00", referencia=None, exige=True)], exigir_referencia=False
        )
    with pytest.raises(ImporteInvalidoError):
        validar_medios(Decimal("0.00"), [medio("100.00")], exigir_referencia=False)


# --- 5.2: posiciones de las líneas sin la referencia exigida -------------------------------


def test_ninguna_linea_sin_referencia() -> None:
    medios = [
        medio("50.00", referencia="0042", exige=True),
        medio("50.00", referencia=None, exige=False),
    ]

    assert posiciones_sin_referencia(medios) == ()


def test_una_linea_sin_referencia_devuelve_su_posicion() -> None:
    medios = [
        medio("30.00", referencia=None, exige=False),
        medio("20.00", referencia=None, exige=True),
        medio("50.00", referencia="0042", exige=True),
    ]

    assert posiciones_sin_referencia(medios) == (1,)


def test_varias_lineas_sin_referencia_devuelven_todas_las_posiciones_en_orden() -> None:
    medios = [
        medio("10.00", referencia=None, exige=True),
        medio("10.00", referencia="0042", exige=True),
        medio("10.00", referencia="", exige=True),
        medio("10.00", referencia=None, exige=False),
        medio("10.00", referencia="   ", exige=True),
    ]

    assert posiciones_sin_referencia(medios) == (0, 2, 4)


@pytest.mark.parametrize("referencia", ["   ", "\t", " \n "])
def test_una_referencia_de_solo_espacios_cuenta_como_faltante(referencia: str) -> None:
    assert posiciones_sin_referencia([medio("10.00", referencia=referencia, exige=True)]) == (0,)


def test_un_medio_que_no_exige_referencia_nunca_cuenta() -> None:
    assert posiciones_sin_referencia([medio("10.00", referencia="  ", exige=False)]) == ()
