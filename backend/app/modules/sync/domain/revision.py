"""Reglas puras de la revisión de observaciones y de rechazos (change 25, `design.md` D1, D7;
SYN-08, INV-01). Sin infraestructura: reciben datos y devuelven resultados o lanzan errores de
dominio.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from app.modules.sync.domain.errores import (
    ComentarioInvalidoError,
    CursorInvalidoError,
    ObservacionesInvalidasError,
    ObservacionYaResueltaError,
    RechazoYaResueltoError,
    VinculoInvalidoError,
)

MAXIMO_DE_OBSERVACIONES = 100
MAXIMO_DEL_COMENTARIO = 500

PENDIENTE = "PENDIENTE"
RESUELTA = "RESUELTA"

VINCULO_VENTA = "VENTA"
VINCULO_COBRANZA = "COBRANZA"

# D7: el vínculo que admite cada tipo de comando rechazado. Los demás tipos (incluida la
# anulación, precisión del 2026-11-06) no admiten vínculo.
_VINCULO_POR_COMANDO = {
    "VENTA_CONFIRMAR": VINCULO_VENTA,
    "COBRANZA_REGISTRAR": VINCULO_COBRANZA,
}


def validar_observaciones(ids: Sequence[UUID]) -> tuple[UUID, ...]:
    """De 1 a 100 identificadores distintos; los devuelve ordenados por `id`, el orden en que el
    caso de uso las bloquea (`FOR UPDATE`) para no cruzarse con otra resolución."""
    if not 1 <= len(ids) <= MAXIMO_DE_OBSERVACIONES:
        raise ObservacionesInvalidasError(
            f"Hay que indicar de 1 a {MAXIMO_DE_OBSERVACIONES} observaciones."
        )
    if len(set(ids)) != len(ids):
        raise ObservacionesInvalidasError("Una observación está repetida en la lista.")
    return tuple(sorted(ids))


def validar_comentario(comentario: str) -> str:
    """Devuelve el comentario sin espacios en los extremos; debe tener de 1 a 500 caracteres."""
    recortado = comentario.strip()
    if not 1 <= len(recortado) <= MAXIMO_DEL_COMENTARIO:
        raise ComentarioInvalidoError(
            f"El comentario debe tener de 1 a {MAXIMO_DEL_COMENTARIO} caracteres."
        )
    return recortado


def validar_pendientes(estados: Mapping[UUID, str]) -> None:
    """INV-01: si alguna observación ya está `RESUELTA`, no se resuelve ninguna."""
    resueltas = sorted(id_ for id_, estado in estados.items() if estado == RESUELTA)
    if resueltas:
        raise ObservacionYaResueltaError(
            "Alguna de las observaciones ya estaba resuelta.",
            extension={"observaciones": [str(id_) for id_ in resueltas]},
        )


def vinculo_admitido(tipo_comando: str) -> str | None:
    """Tipo de vínculo que admite el comando, o `None` si no admite ninguno."""
    return _VINCULO_POR_COMANDO.get(tipo_comando)


def validar_rechazo_pendiente(pendiente: bool) -> None:
    """SYN-08, `01` §18: un rechazo o una cuarentena resuelto no se resuelve otra vez."""
    if not pendiente:
        raise RechazoYaResueltoError("El rechazo ya estaba resuelto.")


def validar_tipo_de_vinculo(tipo_comando: str, vinculo_tipo: str | None) -> None:
    """Sin vínculo siempre es válido; con vínculo, debe ser del tipo que admite el comando
    (`VINCULO_INVALIDO`). Se evalúa ANTES de leer la operación vinculada."""
    if vinculo_tipo is not None and vinculo_tipo != vinculo_admitido(tipo_comando):
        raise VinculoInvalidoError(f"Un rechazo de {tipo_comando} no admite ese vínculo.")


def codificar_cursor(registered_at: datetime, operacion_id: UUID) -> str:
    """Cursor opaco `(registered_at, operacion_id)` de la última operación de la página."""
    valor = f"{registered_at.isoformat()}|{operacion_id}"
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def decodificar_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Inversa de `codificar_cursor`; uno ilegible es `CURSOR_INVALIDO`."""
    try:
        valor = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        momento_texto, id_texto = valor.rsplit("|", 1)
        momento = datetime.fromisoformat(momento_texto)
        if momento.tzinfo is None:
            raise ValueError("el cursor lleva un momento sin zona")
        return momento, UUID(id_texto)
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise CursorInvalidoError("El cursor de paginación no es válido.") from error
