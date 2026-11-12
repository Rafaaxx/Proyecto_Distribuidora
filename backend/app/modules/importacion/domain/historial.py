"""Paginación del historial de importaciones (`02` §11, spec `registro-de-
importaciones`): cursor opaco `(registered_at, id)` de la última importación de la
página; límite por defecto 50 y máximo 200.

Puro: sin acceso a datos. Un cursor ilegible, o cuyo momento no trae zona horaria
(no sería un `timestamptz`), es `CURSOR_INVALIDO`.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from app.modules.importacion.domain.errores import CursorInvalidoError

LIMITE_DEFAULT = 50
LIMITE_MAXIMO = 200


def codificar_cursor(registered_at: datetime, id_: UUID) -> str:
    """Cursor opaco `(registered_at, id)` de la última importación de la página."""
    valor = f"{registered_at.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def decodificar_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Inversa de `codificar_cursor`; ilegible o sin zona horaria es
    `CURSOR_INVALIDO`."""
    try:
        valor = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        momento_texto, id_texto = valor.rsplit("|", 1)
        momento = datetime.fromisoformat(momento_texto)
        id_ = UUID(id_texto)
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise CursorInvalidoError("El cursor de paginación no es válido.") from error
    if momento.tzinfo is None:
        raise CursorInvalidoError("El cursor de paginación no es válido.")
    return momento, id_
