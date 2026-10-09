"""Kardex: página, cursor y rango de fechas de negocio (STK-04, `design.md`
D11, TR-04), más los tipos de lectura que devuelven el repositorio y el
servicio.

Todo es puro: el saldo acumulado y las sumas las calcula la base con SQL
(`CLAUDE.md` §4); acá solo se decide cuántas filas, desde dónde y entre qué
instantes. Mismo contrato que el estado de cuenta (ADR-034 punto 6).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.stock.domain.errores import CursorInvalidoError, RangoDeFechasInvalidoError

LIMITE_DEFAULT = 50
LIMITE_MAXIMO = 200


@dataclass(frozen=True)
class LineaDeKardex:
    """Un movimiento del kardex con su saldo acumulado real (el de la historia
    completa del producto en la ubicación, no el de la página, D11).
    `costo_unitario` es `None` en un movimiento sin costo. `motivo_id` lo llena el repositorio;
    `motivo_nombre` y `estado_origen` los completa el servicio (change 14)."""

    id: UUID
    tipo: str
    cantidad_base: int
    costo_unitario: Decimal | None
    origen_tipo: str
    origen_id: UUID
    occurred_at: datetime
    registered_at: datetime
    usuario_id: UUID
    operation_id: UUID
    saldo_acumulado: int
    motivo_id: UUID | None = None
    motivo_nombre: str | None = None
    """Solo en un movimiento `AJUSTE` (STK-08, change 14, D7): el motivo del ajuste, o el de su
    anulación en el inverso."""
    estado_origen: str | None = None
    """Solo en un movimiento con origen `TRANSFERENCIA` o `AJUSTE_STOCK`: el estado de esa
    operación (`CONFIRMADA` o `ANULADA`)."""


@dataclass(frozen=True)
class DiferenciaDeStock:
    """Un producto y ubicación cuyo saldo no coincide con la suma de su libro, o
    un producto cuyo `stock_total` no coincide con la suma de sus saldos (INV-12,
    `02` §7.6). En una diferencia de `stock_total`, `ubicacion_id` es `None`. Se
    informa, no se corrige (ADR-015)."""

    producto_id: UUID
    ubicacion_id: UUID | None
    valor_materializado: int
    valor_esperado: int


@dataclass(frozen=True)
class Kardex:
    """Respuesta del kardex (D11): saldo con el que arranca el período, saldo
    actual, zona horaria de la organización, el producto (código, nombre y
    unidades de su presentación de referencia, `None` si no tiene una: la
    pantalla muestra las cantidades en cajas + unidades, CAT-08), la página de movimientos en orden
    `(occurred_at, id)` y el cursor de la página siguiente (`None` si es la
    última)."""

    saldo_anterior: int
    saldo_actual: int
    zona_horaria: str
    producto_codigo: str
    producto_nombre: str
    unidades_referencia: int | None
    nombre_referencia: str | None
    movimientos: list[LineaDeKardex]
    cursor_siguiente: str | None


def limite_efectivo(limite: int | None) -> int:
    """`None` es el límite por defecto; el resto se acota entre 1 y el máximo. La
    API rechaza con 422 lo que sale de rango antes de llegar acá (D11)."""
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


def codificar_cursor_de_id(id_: UUID) -> str:
    """Cursor opaco de una lista ordenada por `id`: la página siguiente sigue en
    el id que viene después del último de la página (D11)."""
    return base64.urlsafe_b64encode(str(id_).encode("ascii")).decode("ascii")


def decodificar_cursor_de_id(cursor: str) -> UUID:
    """Inversa de `codificar_cursor_de_id`; un cursor ilegible es
    `CURSOR_INVALIDO`."""
    try:
        return UUID(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise CursorInvalidoError("El cursor de paginación no es válido.") from error


def codificar_cursor_de_producto(producto_id: UUID) -> str:
    """Cursor del stock por ubicación (D11): ordena por `producto_id`."""
    return codificar_cursor_de_id(producto_id)


def decodificar_cursor_de_producto(cursor: str) -> UUID:
    """Inversa de `codificar_cursor_de_producto`."""
    return decodificar_cursor_de_id(cursor)


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
