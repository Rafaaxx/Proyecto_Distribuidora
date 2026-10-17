"""Reglas puras de las consultas de `cobranzas` (change 17, tarea 10.1; `design.md` D14).

Sin infraestructura (`CLAUDE.md` §4): el cursor opaco del listado y la conversión de las fechas de
negocio (en la zona horaria de la organización, TR-04) a un intervalo de instantes.
"""

from __future__ import annotations

import base64
import binascii
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.cobranzas.domain.errores import CursorInvalidoError, RangoDeFechasInvalidoError

LIMITE_MINIMO_DE_PAGINA = 1
LIMITE_MAXIMO_DE_PAGINA = 200
LIMITE_DEFAULT_DE_PAGINA = 50


def acotar_limite(limite: int | None) -> int:
    """El límite pedido, dentro de 1 a 200 (la API responde 422 fuera de rango; acá solo se
    acota por seguridad); `None` es el valor por defecto."""
    pedido = LIMITE_DEFAULT_DE_PAGINA if limite is None else limite
    return min(max(pedido, LIMITE_MINIMO_DE_PAGINA), LIMITE_MAXIMO_DE_PAGINA)


def codificar_cursor(occurred_at: datetime, id_: UUID) -> str:
    """Cursor opaco `(momento, id)` de la última cobranza de la página."""
    valor = f"{occurred_at.isoformat()}|{id_}"
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


def rango_de_instantes(
    desde: date | None, hasta: date | None, zona_horaria: str
) -> tuple[datetime | None, datetime | None]:
    """Convierte las fechas de negocio del filtro (TR-04, en la zona de la organización) en un
    intervalo de instantes `[desde, hasta)`: `desde` es el inicio de ese día y `hasta`, que se
    incluye entero, es el inicio del día siguiente. `desde` posterior a `hasta` es
    `RANGO_DE_FECHAS_INVALIDO`."""
    if desde is not None and hasta is not None and desde > hasta:
        raise RangoDeFechasInvalidoError(f"El rango {desde} a {hasta} está invertido.")
    zona = ZoneInfo(zona_horaria)
    inicio = None if desde is None else datetime.combine(desde, time.min, tzinfo=zona)
    fin = (
        None
        if hasta is None
        else datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=zona)
    )
    return inicio, fin
