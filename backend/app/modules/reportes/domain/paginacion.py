"""Paginación de las listas de los reportes (change 26, `design.md` D14), pura.

El tamaño es fijo en el servidor: no hay parámetro `tamano`, así nadie pide páginas sin límite.
Una página posterior a la última no es error: devuelve `filas` vacías con los totales reales.
"""

from __future__ import annotations

from dataclasses import dataclass

TAMANO_DE_PAGINA = 50


@dataclass(frozen=True)
class Sobre[T]:
    """Una página de una lista: sus filas y dónde está dentro del total."""

    filas: list[T]
    pagina: int
    tamano: int
    total_filas: int
    paginas: int


def desplazamiento_de(pagina: int) -> int:
    """El `OFFSET` de una página (la primera es la 1)."""
    return (pagina - 1) * TAMANO_DE_PAGINA


def armar_sobre[T](filas: list[T], *, pagina: int, total_filas: int) -> Sobre[T]:
    """El sobre de la página pedida; `paginas` es el techo de `total_filas / 50` (0 sin filas)."""
    return Sobre(
        filas=filas,
        pagina=pagina,
        tamano=TAMANO_DE_PAGINA,
        total_filas=total_filas,
        paginas=-(-total_filas // TAMANO_DE_PAGINA),
    )
