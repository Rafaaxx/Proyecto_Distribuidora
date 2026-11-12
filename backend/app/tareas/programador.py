"""Cuándo corre la tarea diaria (change 28, D6): funciones puras, sin dormir ni leer el reloj."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.tareas.configuracion import ConfiguracionInvalidaError

_HORA = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


def parsear_hora(texto: str) -> time:
    """`HH:MM` entre 00:00 y 23:59, o `ConfiguracionInvalidaError` que nombra `TAREAS_HORA`."""
    encontrada = _HORA.fullmatch(texto)
    if encontrada is None:
        raise ConfiguracionInvalidaError(
            "TAREAS_HORA debe tener la forma HH:MM entre 00:00 y 23:59"
        )
    return time(int(encontrada.group(1)), int(encontrada.group(2)))


def proxima_corrida(ahora: datetime, hora: time, zona: ZoneInfo) -> datetime:
    """El próximo momento (en UTC) en que son las `hora` en `zona`, estrictamente posterior a
    `ahora`: antes de la hora corre hoy; a la hora exacta o después, mañana. El día lo decide la
    fecha local de la zona (no UTC) y respeta los cambios de hora de verano."""
    local = ahora.astimezone(zona)
    dia = local.date()
    objetivo = datetime.combine(dia, hora, tzinfo=zona)
    if objetivo.astimezone(UTC) <= ahora:
        objetivo = datetime.combine(dia + timedelta(days=1), hora, tzinfo=zona)
    return objetivo.astimezone(UTC)
