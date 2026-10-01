"""Tarea 4.3 (change 10): `leer_archivo` elige el lector por la extensión del nombre
(`design.md` D2). Un formato no admitido (`.pdf`, `.xls` antiguo, sin extensión) es
`ARCHIVO_INVALIDO` y no se procesa nada (INV-01)."""

from __future__ import annotations

import pytest

from app.modules.importacion.domain.errores import ArchivoInvalidoError
from app.modules.importacion.lectores import leer_archivo


@pytest.mark.parametrize("nombre", ["datos.csv", "DATOS.CSV", "mis datos.v2.Csv"])
def test_un_csv_se_lee_con_el_lector_de_csv_sin_importar_las_mayusculas(nombre: str) -> None:
    assert leer_archivo(nombre, b"nombre\nA\n") == [(1, ["nombre"]), (2, ["A"])]


@pytest.mark.parametrize(
    "nombre", ["informe.pdf", "viejo.xls", "datos", "datos.csv.exe", ".csv.zip"]
)
def test_un_formato_no_admitido_es_archivo_invalido(nombre: str) -> None:
    with pytest.raises(ArchivoInvalidoError) as error:
        leer_archivo(nombre, b"nombre\nA\n")

    assert error.value.codigo == "ARCHIVO_INVALIDO"
    assert "CSV" in error.value.mensaje


def test_un_archivo_vacio_es_archivo_invalido_aunque_la_extension_sea_valida() -> None:
    with pytest.raises(ArchivoInvalidoError):
        leer_archivo("datos.csv", b"")


def test_un_xlsx_que_no_es_un_zip_es_archivo_invalido() -> None:
    with pytest.raises(ArchivoInvalidoError):
        leer_archivo("datos.xlsx", b"nombre\nA\n")
