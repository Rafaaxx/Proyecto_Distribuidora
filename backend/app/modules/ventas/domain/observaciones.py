"""Observación SYN-07 de una venta aceptada sin conexión (`design.md` D1).

El dominio solo produce el código y el detalle; el servicio la completa con la operación y la
línea (`sync` la guarda)."""

from __future__ import annotations

from dataclasses import dataclass

CODIGO_UBICACION_TOMADA_AL_SINCRONIZAR = "UBICACION_TOMADA_AL_SINCRONIZAR"
"""SYN-07, STK-09: la venta sin conexión salió de una ubicación que al sincronizar estaba tomada
por una jornada (la propia en `EN_RENDICION` o la de otro vendedor). Se acepta igual (SYN-05,
INV-17)."""


@dataclass(frozen=True)
class ObservacionDeVenta:
    codigo: str
    detalle: dict[str, object] | None
    sobre_cobranza: bool = False
    """`True` si la observación recae sobre la cobranza en el acto de la venta (`MEDIO_INACTIVO`,
    `REFERENCIA_FALTANTE`, como en el change 17) y no sobre la venta misma."""
