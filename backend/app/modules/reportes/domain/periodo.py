"""Período de un reporte (TR-04, REP-02; `design.md` D1 del change 26). Puro.

Convierte las fechas de negocio del filtro (inclusivas, en la zona de la organización) en el
intervalo de instantes `[inicio, fin)` con la misma regla que `rango_de_instantes` de
`cobranzas` (copiada: `reportes` no importa el dominio de otros módulos).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.modules.reportes.domain.errores import (
    PeriodoDemasiadoLargoError,
    RangoDeFechasInvalidoError,
)

TOPE_DE_DIAS = 366


@dataclass(frozen=True)
class Periodo:
    """El período aplicado: fechas de negocio inclusivas y su intervalo `[inicio, fin)`."""

    desde: date
    hasta: date
    zona_horaria: str
    inicio: datetime
    fin: datetime


def resolver_periodo(
    desde: date | None, hasta: date | None, *, hoy: date, zona_horaria: str
) -> Periodo:
    """Completa lo que falta con el mes en curso y valida el rango.

    Sin `desde` ni `hasta`: del día 1 del mes de `hoy` hasta `hoy`. Con solo `desde`, hasta
    `hoy`; con solo `hasta`, desde el día 1 de ese mes. `desde > hasta` es
    `RANGO_DE_FECHAS_INVALIDO`; más de `TOPE_DE_DIAS` días, `PERIODO_DEMASIADO_LARGO`.
    """
    hasta_aplicado = hasta if hasta is not None else hoy
    desde_aplicado = desde if desde is not None else hasta_aplicado.replace(day=1)
    if desde_aplicado > hasta_aplicado:
        raise RangoDeFechasInvalidoError(
            f"El rango {desde_aplicado} a {hasta_aplicado} está invertido."
        )
    if (hasta_aplicado - desde_aplicado).days + 1 > TOPE_DE_DIAS:
        raise PeriodoDemasiadoLargoError(f"El período no puede superar los {TOPE_DE_DIAS} días.")
    zona = ZoneInfo(zona_horaria)
    return Periodo(
        desde=desde_aplicado,
        hasta=hasta_aplicado,
        zona_horaria=zona_horaria,
        inicio=datetime.combine(desde_aplicado, time.min, tzinfo=zona),
        fin=datetime.combine(hasta_aplicado + timedelta(days=1), time.min, tzinfo=zona),
    )
