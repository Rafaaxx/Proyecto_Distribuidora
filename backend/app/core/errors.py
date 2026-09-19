"""Base de errores de dominio (`CLAUDE.md` §5: clases propias con código
estable, no excepciones genéricas).
"""

from __future__ import annotations


class DomainError(Exception):
    """Base de todo error de dominio del sistema.

    `codigo` es estable y viaja tal cual en las respuestas Problem Details
    (`docs/02-arquitectura.md` §11); no cambia entre versiones aunque el
    mensaje humano se reformule.
    """

    codigo: str = "ERROR_DE_DOMINIO"

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
