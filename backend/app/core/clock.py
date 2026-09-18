"""Reloj inyectable (`docs/02-arquitectura.md` §9).

El backend nunca llama `datetime.now()` directamente: siempre pasa por un
`Clock`, para poder fijar la hora en pruebas.
"""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Reloj real: devuelve el momento actual en UTC (`timestamptz`)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Reloj fijo para pruebas: siempre devuelve el mismo momento."""

    def __init__(self, momento: datetime) -> None:
        self._momento = momento

    def now(self) -> datetime:
        return self._momento
