"""Tarea 5.3 (change 18a; spec `ventas/confirmacion-de-venta`, requisito de número;
`design.md` D4): formato `PPP-NNNNNN`, prefijo del dispositivo y correlativo que nunca
retrocede.

Reglas citadas: VTA-06 (ADR-008).
"""

from __future__ import annotations

import pytest

from app.modules.ventas.domain.errores import NumeroInvalidoError
from app.modules.ventas.domain.numero import (
    armar_numero,
    correlativo_de,
    nuevo_ultimo_correlativo,
)


@pytest.mark.parametrize(
    ("numero", "prefijo", "esperado"),
    [
        ("V01-000042", "V01", 42),
        ("V03-000142", "V03", 142),
        ("V01-000001", "V01", 1),
        ("V01-999999", "V01", 999999),
        ("V01-1000000", "V01", 1000000),  # el formato admite más dígitos (Open Questions)
    ],
)
def test_vta06_el_numero_valido_devuelve_su_correlativo(
    numero: str, prefijo: str, esperado: int
) -> None:
    assert correlativo_de(numero, prefijo) == esperado


@pytest.mark.parametrize(
    ("numero", "prefijo"),
    [
        ("V02-000001", "V01"),  # prefijo de otro dispositivo
        ("v01-000001", "V01"),  # distinto de mayúsculas
        ("V01000001", "V01"),  # sin guion
        ("V01-42", "V01"),  # menos de seis dígitos
        ("V01-00004a", "V01"),
        ("V01-000000", "V01"),  # el correlativo empieza en 1
        ("V01-000001 ", "V01"),
        (" V01-000001", "V01"),
        ("V01--00001", "V01"),
        ("", "V01"),
        ("V01-", "V01"),
        ("-000001", "V01"),
        ("V011-000001", "V01"),
    ],
)
def test_vta06_un_numero_mal_formado_o_de_otro_dispositivo_se_rechaza(
    numero: str, prefijo: str
) -> None:
    with pytest.raises(NumeroInvalidoError) as error:
        correlativo_de(numero, prefijo)
    assert error.value.codigo == "NUMERO_INVALIDO"
    assert error.value.status_http == 422


@pytest.mark.parametrize(
    ("actual", "propuesto", "esperado"),
    [(41, 42, 42), (50, 45, 50), (50, 50, 50), (0, 1, 1)],
)
def test_vta06_el_ultimo_correlativo_es_el_mayor_y_nunca_retrocede(
    actual: int, propuesto: int, esperado: int
) -> None:
    """Un número menor (una venta sin conexión más vieja) no retrocede el correlativo."""
    assert nuevo_ultimo_correlativo(actual, propuesto) == esperado


@pytest.mark.parametrize(
    ("prefijo", "correlativo", "esperado"),
    [("V01", 42, "V01-000042"), ("V03", 142, "V03-000142"), ("V01", 1234567, "V01-1234567")],
)
def test_vta06_el_numero_se_arma_con_seis_digitos_como_minimo(
    prefijo: str, correlativo: int, esperado: str
) -> None:
    assert armar_numero(prefijo, correlativo) == esperado
    assert correlativo_de(esperado, prefijo) == correlativo
