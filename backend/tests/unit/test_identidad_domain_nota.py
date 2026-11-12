"""Tarea 5.1 (change 20; `design.md` D10; spec `organizacion/parametros-de-organizacion`):
normalización pura de los textos de la nota de venta (domicilio y teléfono).

Reglas citadas: VTA-13, AUD-01.
"""

from __future__ import annotations

import pytest

from app.core.errors import DomainError
from app.modules.identidad.domain.nota import (
    DOMICILIO_MAXIMO,
    TELEFONO_MAXIMO,
    DatoDeNotaInvalidoError,
    normalizar_datos_de_nota,
)


def test_vta13_recorta_los_espacios_de_los_extremos() -> None:
    assert normalizar_datos_de_nota("  Av. San Martín 1234  ", "\t261 555-0000\n") == (
        "Av. San Martín 1234",
        "261 555-0000",
    )


@pytest.mark.parametrize("vacio", [None, "", "   ", "\n\t "])
def test_vta13_vacio_o_solo_espacios_pasa_a_nulo(vacio: str | None) -> None:
    assert normalizar_datos_de_nota(vacio, vacio) == (None, None)


def test_vta13_cada_campo_se_normaliza_por_separado() -> None:
    assert normalizar_datos_de_nota("Calle 1", None) == ("Calle 1", None)
    assert normalizar_datos_de_nota("  ", "123") == (None, "123")


def test_vta13_el_largo_maximo_se_mide_despues_de_recortar() -> None:
    domicilio = "d" * DOMICILIO_MAXIMO
    telefono = "t" * TELEFONO_MAXIMO
    assert normalizar_datos_de_nota(f" {domicilio} ", f" {telefono} ") == (domicilio, telefono)
    assert (DOMICILIO_MAXIMO, TELEFONO_MAXIMO) == (200, 50)


@pytest.mark.parametrize(
    ("domicilio", "telefono"),
    [("d" * 201, None), (None, "t" * 51), ("d" * 201, "t" * 51)],
    ids=["domicilio_largo", "telefono_largo", "ambos_largos"],
)
def test_vta13_un_texto_demasiado_largo_se_rechaza(
    domicilio: str | None, telefono: str | None
) -> None:
    with pytest.raises(DatoDeNotaInvalidoError) as error:
        normalizar_datos_de_nota(domicilio, telefono)

    assert error.value.codigo == "DATO_DE_NOTA_INVALIDO"
    assert error.value.status_http == 422
    assert isinstance(error.value, DomainError)
