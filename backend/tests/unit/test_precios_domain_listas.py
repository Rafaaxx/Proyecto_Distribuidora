"""Change 13, tarea 5.1: normalización del nombre de una lista (`precios/domain/listas.py`;
spec `precios/listas-de-precios`; PRC-01, TR-10)."""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.precios.domain.errores import (
    NombreDuplicadoError,
    NombreInvalidoError,
    RecursoNoEncontradoError,
    ReglaDuplicadaError,
)
from app.modules.precios.domain.listas import normalizar_nombre


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("General", "General"),
        ("  General  ", "General"),
        ("\tMayorista\n", "Mayorista"),
        ("Lista de verano", "Lista de verano"),
    ],
)
def test_el_nombre_se_guarda_recortado(nombre: str, esperado: str) -> None:
    assert normalizar_nombre(nombre) == esperado


@pytest.mark.parametrize("nombre", ["", "   ", "\t\n"])
def test_un_nombre_vacio_o_de_solo_espacios_se_rechaza(nombre: str) -> None:
    with pytest.raises(NombreInvalidoError) as error:
        normalizar_nombre(nombre)

    assert error.value.codigo == "NOMBRE_INVALIDO"


@pytest.mark.parametrize(
    ("clase", "codigo", "status"),
    [
        (NombreInvalidoError, "NOMBRE_INVALIDO", 422),
        (NombreDuplicadoError, "NOMBRE_DUPLICADO", 409),
        (ReglaDuplicadaError, "REGLA_DUPLICADA", 409),
        (RecursoNoEncontradoError, "RECURSO_NO_ENCONTRADO", 404),
    ],
)
def test_los_errores_de_listas_tienen_codigo_estable_y_estado_http(
    clase: type[DomainError], codigo: str, status: int
) -> None:
    error = clase("mensaje")

    assert (error.codigo, error.status_http) == (codigo, status)
