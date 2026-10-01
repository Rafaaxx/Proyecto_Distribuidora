"""Lector de CSV de planillas de importación (`design.md` D2).

Adaptador fuera de `domain/`: convierte los bytes de un CSV en filas de texto con
su número de fila (`FilaCruda`). La conversión de cada celda a decimal, entero,
booleano o fecha NO ocurre acá: el texto llega tal cual a `domain/valores.py`
(INV-03).

- Codificación: UTF-8 (con o sin BOM) y, si no decodifica, Windows-1252, que es lo
  que Excel en español guarda al exportar a CSV.
- Separador: `,` o `;`, el que más aparezca en el encabezado fuera de comillas
  (Excel en español guarda con `;`).
- Número de fila: el del registro, como lo ve el usuario en su planilla; una línea
  vacía ocupa su número y un salto de línea dentro de comillas no cuenta.
"""

from __future__ import annotations

import csv
import io

from app.modules.importacion.domain.errores import ArchivoInvalidoError
from app.modules.importacion.domain.planilla import FilaCruda

_BOM_UTF8 = b"\xef\xbb\xbf"


def _decodificar(contenido: bytes) -> str:
    """UTF-8 estricto y, si falla, Windows-1252 estricto. Un byte nulo no es texto."""
    if b"\x00" in contenido:
        raise ArchivoInvalidoError("El archivo no es un CSV de texto.")
    if contenido.startswith(_BOM_UTF8):
        contenido = contenido[len(_BOM_UTF8) :]
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return contenido.decode("cp1252")
    except UnicodeDecodeError as error:
        raise ArchivoInvalidoError(
            "El archivo no está codificado en UTF-8 ni en Windows-1252."
        ) from error


def _detectar_separador(texto: str) -> str:
    """El separador más frecuente en la primera línea, fuera de comillas. Si no hay
    ninguno (una sola columna) o empatan, la coma."""
    comas = 0
    puntos_y_comas = 0
    entre_comillas = False
    for caracter in texto:
        if caracter == '"':
            entre_comillas = not entre_comillas
        elif not entre_comillas:
            if caracter in "\r\n":
                break
            if caracter == ",":
                comas += 1
            elif caracter == ";":
                puntos_y_comas += 1
    return ";" if puntos_y_comas > comas else ","


def leer_csv(contenido: bytes) -> list[FilaCruda]:
    """Filas del CSV como `(número de fila, celdas)`. `ARCHIVO_INVALIDO` si el
    archivo está vacío, no es texto o tiene un campo de tamaño absurdo."""
    texto = _decodificar(contenido)
    if texto.strip() == "":
        raise ArchivoInvalidoError("El archivo está vacío.")
    separador = _detectar_separador(texto)
    lector = csv.reader(io.StringIO(texto, newline=""), delimiter=separador, quotechar='"')
    try:
        return [(numero, list(celdas)) for numero, celdas in enumerate(lector, start=1)]
    except csv.Error as error:
        raise ArchivoInvalidoError(f"El CSV no se pudo leer: {error}.") from error
