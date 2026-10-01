"""Filas con la misma clave natural dentro de un archivo (`FILA_DUPLICADA`,
`design.md` D6).

Puro. Dos filas del mismo archivo con la misma clave natural dan `FILA_DUPLICADA` en
la SEGUNDA (y siguientes), citando la primera aparición. Se detecta ANTES de llamar
al servicio: si no, la segunda fila chocaría con la primera ya escrita en la misma
transacción y daría el error de duplicado de la entidad, que no distingue "ya existía"
de "está repetida en el archivo".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.modules.importacion.domain.informe import ErrorDeFila, error_de_fila_duplicada
from app.modules.importacion.domain.planilla import FilaPlanilla

Claves = Callable[[FilaPlanilla], Sequence[tuple[str, str]]]
"""`(columna, clave)` de una fila; una clave vacía no cuenta."""


def marcar_duplicadas(filas: Sequence[FilaPlanilla], claves: Claves) -> dict[int, ErrorDeFila]:
    """Error de duplicado por número de fila. Una fila duplicada NO registra sus
    demás claves (no es "dueña" de ellas); se informa una sola vez por fila, con la
    primera clave repetida."""
    vistas: dict[tuple[str, str], int] = {}
    duplicadas: dict[int, ErrorDeFila] = {}
    for fila in filas:
        de_la_fila = [(columna, clave) for columna, clave in claves(fila) if clave != ""]
        repetida = next(
            ((columna, clave) for columna, clave in de_la_fila if (columna, clave) in vistas),
            None,
        )
        if repetida is not None:
            duplicadas[fila.fila] = error_de_fila_duplicada(
                fila=fila.fila, columna=repetida[0], fila_original=vistas[repetida]
            )
            continue
        for clave in de_la_fila:
            vistas[clave] = fila.fila
    return duplicadas
