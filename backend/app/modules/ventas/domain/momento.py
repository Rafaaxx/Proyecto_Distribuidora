"""Momento de la venta con conexión (PRC-20, TR-05; `design.md` D9)."""

from __future__ import annotations

from datetime import datetime

from app.modules.ventas.domain.errores import MomentoFueraDeRangoError

MARGEN_POR_DEFECTO_SEGUNDOS = 300
"""Mientras la organización no defina `desvio_reloj_max_segundos` (D9)."""


def validar_momento(
    occurred_at: datetime,
    ahora: datetime,
    desvio_max_segundos: int | None,
    *,
    offline: bool,
) -> None:
    """Con conexión, `occurred_at` debe estar a lo sumo `desvio_max_segundos` (300 si es nulo)
    del reloj del servidor, hacia atrás o hacia adelante. Sin conexión no se valida."""
    if offline:
        return
    margen = MARGEN_POR_DEFECTO_SEGUNDOS if desvio_max_segundos is None else desvio_max_segundos
    if abs((occurred_at - ahora).total_seconds()) > margen:
        raise MomentoFueraDeRangoError(
            f"El momento de la venta difiere del reloj del servidor en más de {margen} segundos.",
            extension={"margen_segundos": margen},
        )
