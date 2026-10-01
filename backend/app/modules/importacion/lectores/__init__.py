"""Lectores de planillas de importación (`design.md` D2): adaptadores fuera de
`domain/` que convierten un archivo en filas de texto (`FilaCruda`).

`leer_archivo` elige el lector por la extensión del nombre (`.csv` o `.xlsx`); otro
formato (un `.pdf`, un `.xls` antiguo) es `ARCHIVO_INVALIDO` y no se procesa nada.
"""

from __future__ import annotations

from app.modules.importacion.domain.errores import ArchivoInvalidoError
from app.modules.importacion.domain.planilla import FilaCruda
from app.modules.importacion.lectores.csv_lector import leer_csv
from app.modules.importacion.lectores.xlsx_lector import leer_xlsx


def leer_archivo(nombre: str, contenido: bytes) -> list[FilaCruda]:
    """Filas del archivo como `(número de fila, celdas)`. `ARCHIVO_INVALIDO` si el
    formato no es CSV ni `.xlsx`, o el archivo está vacío o dañado."""
    if not contenido:
        raise ArchivoInvalidoError("El archivo está vacío.")
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension == "csv":
        return leer_csv(contenido)
    if extension == "xlsx":
        return leer_xlsx(contenido)
    raise ArchivoInvalidoError(
        "Formato de archivo no admitido: use un CSV (.csv) o un libro de Excel (.xlsx)."
    )
