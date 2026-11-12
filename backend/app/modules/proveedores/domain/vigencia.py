"""Referencia pura del orden de D4 para el costo vigente de un producto
(CST-03, tarea 6.5): "el de mayor vigencia desde que no supere la fecha; si
dos costos tienen la misma vigencia desde, prevalece el registrado
último". Mismo orden que `ix_costo_informado__producto_vigencia`
(`vigencia_desde DESC, creado_en DESC, id DESC`, migración `70dcb6dce507`).

Usada en una propiedad Hypothesis (grupo 7) que compara esta función contra
`obtener_vigente` de `proveedores/repository.py` (la consulta SQL real) con
los mismos datos: si algún día divergen, la propiedad lo detecta. Acá solo
vive la función pura."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CandidatoVigencia:
    """Los campos de un costo informado que el orden de D4 necesita."""

    id: UUID
    vigencia_desde: date
    creado_en: datetime
    costo_base: Decimal


def elegir_vigente(candidatos: list[CandidatoVigencia], *, fecha: date) -> CandidatoVigencia | None:
    """El costo vigente de un producto para `fecha` (CST-03, D4), o `None`
    si ningún candidato alcanza esa fecha."""
    elegibles = [candidato for candidato in candidatos if candidato.vigencia_desde <= fecha]
    if not elegibles:
        return None

    return max(
        elegibles,
        key=lambda candidato: (candidato.vigencia_desde, candidato.creado_en, candidato.id),
    )
