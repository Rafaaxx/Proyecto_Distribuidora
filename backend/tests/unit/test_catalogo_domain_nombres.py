"""Change 05, tarea 4.2: normalización y validación de nombre y código
(CAT-01, spec categorias-y-marcas y productos-y-presentaciones)."""

from __future__ import annotations

import pytest

from app.modules.catalogo.domain.errores import CodigoInvalidoError, NombreInvalidoError
from app.modules.catalogo.domain.nombres import normalizar_codigo, normalizar_nombre


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Vinos", "Vinos"),
        ("  Vinos  ", "Vinos"),
        ("Bodega Norte\n", "Bodega Norte"),
    ],
)
def test_normalizar_nombre_recorta_espacios(entrada: str, esperado: str) -> None:
    assert normalizar_nombre(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "\t\n"])
def test_normalizar_nombre_vacio_o_solo_espacios_es_invalido(entrada: str) -> None:
    with pytest.raises(NombreInvalidoError):
        normalizar_nombre(entrada)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("VA-001", "VA-001"),
        ("  VA-001  ", "VA-001"),
    ],
)
def test_normalizar_codigo_recorta_espacios(entrada: str, esperado: str) -> None:
    assert normalizar_codigo(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   "])
def test_normalizar_codigo_vacio_o_solo_espacios_es_invalido(entrada: str) -> None:
    with pytest.raises(CodigoInvalidoError):
        normalizar_codigo(entrada)
