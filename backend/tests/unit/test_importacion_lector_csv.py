"""Tarea 3.3 (change 10): lector de CSV (`design.md` D2).

Adaptador fuera de `domain/`: convierte los bytes de un CSV en filas de texto con
su número de fila (`FilaCruda`). UTF-8 con o sin BOM y, si no decodifica,
Windows-1252; separador `,` o `;` detectado en el encabezado (Excel en español
guarda con `;`); comillas dobles.

Reglas citadas: INV-01 (un archivo ilegible se rechaza completo), `design.md` D2
y los escenarios "CSV en UTF-8 aceptado" y "CSV guardado por Excel en español" de
`specs/importacion/planillas`.
"""

from __future__ import annotations

import pytest

from app.modules.importacion.domain.errores import ArchivoInvalidoError
from app.modules.importacion.lectores.csv_lector import leer_csv

ENCABEZADO = "nombre,cuit,contacto,telefono,email"


def test_un_csv_utf8_con_dos_filas_se_lee_con_su_numero_de_fila() -> None:
    """Escenario "CSV en UTF-8 aceptado"."""
    datos = f"{ENCABEZADO}\nBodega Sur,30712345678,Ana,,\nCervecería Norte,,,,\n".encode()

    filas = leer_csv(datos)

    assert filas[0] == (1, ["nombre", "cuit", "contacto", "telefono", "email"])
    assert filas[1] == (2, ["Bodega Sur", "30712345678", "Ana", "", ""])
    assert filas[2] == (3, ["Cervecería Norte", "", "", "", ""])
    assert len(filas) == 3


def test_el_bom_de_utf8_se_descarta_y_no_ensucia_el_primer_encabezado() -> None:
    datos = b"\xef\xbb\xbf" + f"{ENCABEZADO}\nA,,,,\n".encode()

    filas = leer_csv(datos)

    assert filas[0][1][0] == "nombre"


def test_un_csv_de_excel_en_espanol_windows_1252_con_punto_y_coma_se_lee_bien() -> None:
    """Escenario "CSV guardado por Excel en español": Windows-1252, `;`, Ñ y tildes
    (que en UTF-8 no decodifican)."""
    texto = "nombre;cuit;contacto;telefono;email\r\nCervecería Ñandú;;;;\r\n"
    datos = texto.encode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        datos.decode("utf-8")  # el caso es realmente "no UTF-8"

    filas = leer_csv(datos)

    assert filas[0][1] == ["nombre", "cuit", "contacto", "telefono", "email"]
    assert filas[1] == (2, ["Cervecería Ñandú", "", "", "", ""])


def test_el_separador_se_detecta_en_el_encabezado_coma_o_punto_y_coma() -> None:
    con_coma = leer_csv(b"nombre,cuit\nA,1\n")
    con_punto_y_coma = leer_csv(b"nombre;cuit\nA;1\n")

    assert con_coma == con_punto_y_coma == [(1, ["nombre", "cuit"]), (2, ["A", "1"])]


def test_un_archivo_de_una_sola_columna_se_lee_sin_separador() -> None:
    assert leer_csv(b"nombre\nA\nB\n") == [(1, ["nombre"]), (2, ["A"]), (3, ["B"])]


def test_una_coma_dentro_de_comillas_no_separa_cuando_el_separador_es_punto_y_coma() -> None:
    datos = b'nombre;contacto\n"Sur, Bodega";"Ana ""la jefa"""\n'

    filas = leer_csv(datos)

    assert filas[1] == (2, ["Sur, Bodega", 'Ana "la jefa"'])


def test_un_salto_de_linea_dentro_de_comillas_es_una_sola_fila() -> None:
    """El número de fila es el de la planilla (un registro), no el de la línea de
    texto."""
    datos = 'nombre,contacto\n"Sur","línea 1\nlínea 2"\nNorte,x\n'.encode()

    filas = leer_csv(datos)

    assert filas[1] == (2, ["Sur", "línea 1\nlínea 2"])
    assert filas[2] == (3, ["Norte", "x"])


def test_las_lineas_vacias_conservan_el_numero_de_fila_de_las_siguientes() -> None:
    filas = leer_csv(b"nombre,cuit\nA,1\n\nB,2\n")

    assert [numero for numero, _ in filas] == [1, 2, 3, 4]
    assert filas[2] == (3, [])
    assert filas[3] == (4, ["B", "2"])


def test_los_finales_de_linea_de_windows_y_la_falta_de_salto_final_se_toleran() -> None:
    filas = leer_csv(b"nombre,cuit\r\nA,1\r\nB,2")

    assert filas == [(1, ["nombre", "cuit"]), (2, ["A", "1"]), (3, ["B", "2"])]


@pytest.mark.parametrize(
    "datos",
    [
        b"",
        b"   \n  \n",
        b"\xef\xbb\xbf",
        b"nombre,cuit\n\x00A,1\n",  # byte nulo: no es texto
        b"nombre,cuit\n\x81A,1\n",  # no es UTF-8 ni Windows-1252 (0x81 no está definido)
        b"%PDF-1.7\n\x00\x00binary",
    ],
)
def test_un_archivo_vacio_o_que_no_es_texto_es_archivo_invalido(datos: bytes) -> None:
    with pytest.raises(ArchivoInvalidoError) as error:
        leer_csv(datos)

    assert error.value.codigo == "ARCHIVO_INVALIDO"


def test_un_campo_gigante_es_archivo_invalido_y_no_un_error_interno() -> None:
    datos = b"nombre\n" + b"x" * 200_000 + b"\n"

    with pytest.raises(ArchivoInvalidoError):
        leer_csv(datos)
