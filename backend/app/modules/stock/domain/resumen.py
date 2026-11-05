"""Tipos del dinero del resumen de una jornada (RUT-07; change 24, `design.md` D4).

`stock` no importa `ventas` ni `cobranzas` (contratos de import-linter): son ellos quienes, al
importar su `service.py`, registran en el de `stock` el lector de lo suyo (mismo patrón que ADR-025
y ADR-028 D9.3-B) y lo devuelven con estos tipos, que `stock/service.py` reexporta. Datos puros,
sin infraestructura (`02` §5.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class TotalDeVentas:
    """Cantidad de ventas y su total (string en la API, INV-03)."""

    cantidad: int
    total: Decimal


@dataclass(frozen=True)
class VentasDeJornada:
    """Las ventas de una jornada para su resumen: vigentes y anuladas (por la jornada de la
    anulación, aunque la jornada se haya liberado, ADR-066) y, aparte, las registradas después de
    la rendición."""

    vigentes: TotalDeVentas
    anuladas: TotalDeVentas
    vigentes_tardias: TotalDeVentas
    anuladas_tardias: TotalDeVentas


@dataclass(frozen=True)
class TotalDeMedio:
    """Lo cobrado con un medio de pago: su identificador, su nombre (`None` si ya no se puede
    resolver) y el importe."""

    medio_pago_id: UUID
    nombre: str | None
    total: Decimal


@dataclass(frozen=True)
class CobranzasDeJornada:
    """Las cobranzas de una jornada de un estado: cuántas, su importe y lo cobrado por medio de
    pago, ordenado por nombre."""

    cantidad: int
    total: Decimal
    por_medio: list[TotalDeMedio]
