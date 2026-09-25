"""Base de errores de dominio (`CLAUDE.md` §5: clases propias con código
estable, no excepciones genéricas).
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base de todo error de dominio del sistema.

    `codigo` es estable y viaja tal cual en las respuestas Problem Details
    (`docs/02-arquitectura.md` §11); no cambia entre versiones aunque el
    mensaje humano se reformule.
    """

    codigo: str = "ERROR_DE_DOMINIO"
    # Código HTTP con el que se traduce a Problem Details (tarea 10.2,
    # `docs/02-arquitectura.md` §11). 400 por defecto; una subclase que
    # representa una condición HTTP distinta (401, 403, 404...) lo declara.
    status_http: int = 400

    def __init__(self, mensaje: str, *, extension: dict[str, Any] | None = None) -> None:
        """`extension` (change 06, contrato-api.md P9, aprobado 2026-09-24):
        campos adicionales que un error puntual necesita exponer en el
        Problem Details (por ejemplo `fila`, el índice 0-based de la fila
        del lote de `COSTO_INFORMAR` que lo causó). Aditivo: `None` por
        defecto, no cambia el comportamiento de ningún error existente."""
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.extension = extension
