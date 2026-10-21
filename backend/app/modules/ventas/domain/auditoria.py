"""Textos de la auditoría de una venta (change 18a, tarea 10.1; `design.md` D20).

Puro, sin infraestructura (`02` §5.3). La venta que usó otra lista que la que le corresponde al
cliente, o una versión que no es la vigente, deja en su única fila de auditoría el motivo y esta
observación (AUD-01, AUD-02, PRC-21).
"""

from __future__ import annotations


def observacion_de_lista(
    *, lista_nombre: str, version_numero: int, otra_lista: bool, version_no_vigente: bool
) -> str | None:
    """`Lista "<nombre>", versión <n>: <razones>`; `None` si la venta usó la lista y la versión
    que le correspondían (no hay nada que observar)."""
    razones: list[str] = []
    if otra_lista:
        razones.append("lista distinta de la que le corresponde al cliente")
    if version_no_vigente:
        razones.append("versión no vigente")
    if not razones:
        return None
    return f'Lista "{lista_nombre}", versión {version_numero}: {" y ".join(razones)}'
