"""Estado de cuenta: página, cursor y rango de fechas de negocio (CC-07,
`design.md` D9, TR-04), más los tipos de lectura que devuelven el repositorio y
el servicio.

Todo es puro: el saldo acumulado y la suma del libro los calcula la base con SQL
(`CLAUDE.md` §4); acá solo se decide cuántas filas, desde dónde y entre qué
instantes.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.cuentas_corrientes.domain.errores import (
    CursorInvalidoError,
    RangoDeFechasInvalidoError,
)

LIMITE_DEFAULT = 50
LIMITE_MAXIMO = 200


@dataclass(frozen=True)
class LineaDeEstadoDeCuenta:
    """Un movimiento del estado de cuenta con su saldo acumulado real (el de la
    cuenta completa, no el de la página, D9)."""

    id: UUID
    tipo: str
    sentido: str
    importe: Decimal
    origen_tipo: str
    origen_id: UUID
    occurred_at: datetime
    registered_at: datetime
    usuario_id: UUID
    operation_id: UUID
    saldo_acumulado: Decimal


@dataclass(frozen=True)
class DiferenciaDeSaldo:
    """Una cuenta cuyo saldo materializado no coincide con la suma de su libro
    (INV-13, `02` §7.6). Se informa, no se corrige (ADR-015)."""

    cuenta_tipo: str
    entidad_id: UUID
    saldo_materializado: Decimal
    suma_del_libro: Decimal


@dataclass(frozen=True)
class EstadoDeCuenta:
    """Respuesta del estado de cuenta (D9): saldo con el que arranca el período,
    saldo actual, zona horaria de la organización (TR-04, con la que la pantalla
    muestra las fechas), la página de movimientos en orden `(occurred_at, id)` y el
    cursor de la página siguiente (`None` si es la última)."""

    saldo_anterior: Decimal
    saldo_actual: Decimal
    zona_horaria: str
    movimientos: list[LineaDeEstadoDeCuenta]
    cursor_siguiente: str | None


def limite_efectivo(limite: int | None) -> int:
    """`None` es el límite por defecto; el resto se acota entre 1 y el
    máximo."""
    if limite is None:
        return LIMITE_DEFAULT
    return min(max(limite, 1), LIMITE_MAXIMO)


def codificar_cursor(occurred_at: datetime, id_: UUID) -> str:
    """Cursor opaco `(occurred_at, id)` del último movimiento de la página."""
    valor = f"{occurred_at.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(valor.encode("utf-8")).decode("ascii")


def decodificar_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Inversa de `codificar_cursor`. Un cursor que no se puede leer, o cuyo
    momento no trae zona horaria (no sería un `timestamptz`), es
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


def rango_de_instantes(
    desde: date | None, hasta: date | None, zona_horaria: str
) -> tuple[datetime | None, datetime | None]:
    """Convierte las fechas de negocio del filtro (TR-04, en la zona de la
    organización) en un intervalo de instantes `[desde, hasta)`: `desde` es el
    inicio de ese día y `hasta`, que se incluye entero, es el inicio del día
    siguiente."""
    if desde is not None and hasta is not None and desde > hasta:
        raise RangoDeFechasInvalidoError("`desde` no puede ser posterior a `hasta`.")
    zona = ZoneInfo(zona_horaria)
    inicio = None if desde is None else datetime.combine(desde, time.min, tzinfo=zona)
    fin = (
        None
        if hasta is None
        else datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=zona)
    )
    return inicio, fin
