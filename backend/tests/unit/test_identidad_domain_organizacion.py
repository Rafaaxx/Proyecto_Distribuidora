"""Tarea 12.1 (change 20; `design.md` D15; spec `organizacion/parametros-de-organizacion`):
normalización pura del nombre y del CUIT de la organización.

Reglas citadas: VTA-13, CLI-05.
"""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.identidad.domain.organizacion import (
    NOMBRE_DE_ORGANIZACION_MAXIMO,
    CuitInvalidoError,
    NombreDeOrganizacionInvalidoError,
    normalizar_cuit_de_organizacion,
    normalizar_nombre_de_organizacion,
)

# --- nombre -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Distribuidora Sur", "Distribuidora Sur"),
        ("  Distribuidora Sur \n", "Distribuidora Sur"),
        ("x", "x"),
        ("n" * NOMBRE_DE_ORGANIZACION_MAXIMO, "n" * NOMBRE_DE_ORGANIZACION_MAXIMO),
        (f" {'n' * NOMBRE_DE_ORGANIZACION_MAXIMO} ", "n" * NOMBRE_DE_ORGANIZACION_MAXIMO),
    ],
    ids=["normal", "bordes", "una_letra", "tope_200", "tope_200_con_bordes"],
)
def test_vta13_el_nombre_valido_se_recorta(texto: str, esperado: str) -> None:
    assert normalizar_nombre_de_organizacion(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    ["", "   ", "\n\t ", "n" * (NOMBRE_DE_ORGANIZACION_MAXIMO + 1)],
    ids=["vacio", "espacios", "blancos", "tope_mas_uno"],
)
def test_vta13_el_nombre_vacio_o_demasiado_largo_se_rechaza(texto: str) -> None:
    with pytest.raises(NombreDeOrganizacionInvalidoError) as error:
        normalizar_nombre_de_organizacion(texto)

    assert error.value.codigo == "NOMBRE_DE_ORGANIZACION_INVALIDO"
    assert error.value.status_http == 422
    assert isinstance(error.value, DomainError)


# --- CUIT -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("30-71234567-8", "30712345678"),
        ("30 71234567 8", "30712345678"),
        ("  20345678901 ", "20345678901"),
        ("27-12345678-4", "27123456784"),
    ],
    ids=["guiones", "espacios", "bordes", "otro"],
)
def test_cli05_el_cuit_valido_se_normaliza_a_once_digitos(texto: str, esperado: str) -> None:
    assert normalizar_cuit_de_organizacion(texto) == esperado


@pytest.mark.parametrize("vacio", [None, "", "   ", "\t\n"])
def test_cli05_el_cuit_vacio_pasa_a_nulo(vacio: str | None) -> None:
    assert normalizar_cuit_de_organizacion(vacio) is None


@pytest.mark.parametrize(
    "texto",
    ["3071234567", "307123456789", "30-7123456A-8", "30.71234567.8", "abc"],
    ids=["diez", "doce", "letra", "puntos", "letras"],
)
def test_cli05_el_cuit_invalido_se_rechaza(texto: str) -> None:
    with pytest.raises(CuitInvalidoError) as error:
        normalizar_cuit_de_organizacion(texto)

    assert error.value.codigo == "CUIT_INVALIDO"
    assert error.value.status_http == 422
