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


class PermisoRequeridoError(DomainError):
    """Falta el permiso que la operación exige: 403.

    Vive acá y no en `core/autenticacion.py` aunque lo inventara el change 05
    (tarea 10.2), porque no es un error de la capa HTTP: es un `DomainError`
    como cualquier otro y lo lanza cualquier consumidor que deba comprobar un
    permiso, no sólo una ruta. En particular lo necesitan los handlers del bus
    de comandos (`clientes/commands.py`, `docs/02-arquitectura.md` §6.3 paso 4:
    el permiso se valida por comando, y un lote de sincronización trae tipos
    distintos, así que no hay un permiso único que declarar en la ruta), y esos
    handlers no pueden importar `core/autenticacion.py` porque ese módulo
    depende de `api_v1.dependencias` y el ciclo de imports lo rompe.

    El código `PERMISO_REQUERIDO` y el 403 son los mismos de siempre: esta clase
    se mudó de módulo, no se redefinió.
    """

    codigo = "PERMISO_REQUERIDO"
    status_http = 403
