"""Change 06, tarea 6.2: normalización de nombre y CUIT de proveedor (D7).
Puro: sin acceso a datos, sin `organizacion_id` (la unicidad la valida el
servicio/repositorio, no esta capa) -- mismo criterio que
`catalogo/domain/nombres.py` (04 del 05)."""

from __future__ import annotations

import pytest

from app.modules.proveedores.domain.errores import NombreInvalidoError
from app.modules.proveedores.domain.normalizacion import normalizar_cuit, normalizar_nombre


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Bodega Andina", "Bodega Andina"),
        ("  Bodega Andina  ", "Bodega Andina"),
        ("Distribuidora Norte\n", "Distribuidora Norte"),
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
        ("30-71234567-1", "30712345671"),
        ("30712345671", "30712345671"),
        ("30 71234567 1", "30712345671"),
    ],
)
def test_normalizar_cuit_valido_a_11_digitos(entrada: str, esperado: str) -> None:
    assert normalizar_cuit(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "3071234567",  # 10 dígitos
        "307123456712",  # 12 dígitos
        "30-7123456A-1",  # letras
        "",
        "   ",
    ],
)
def test_normalizar_cuit_invalido_devuelve_none(entrada: str) -> None:
    assert normalizar_cuit(entrada) is None


def test_normalizar_cuit_none_devuelve_none() -> None:
    assert normalizar_cuit(None) is None
