"""Esquemas Pydantic de salida de `configuracion/api.py` (change 05,
`design.md` D12; tarea 9.6).

`valor` viaja como **string** (`CLAUDE.md` §4: porcentajes como string,
nunca `float`) -- `field_serializer` lo convierte desde el `Decimal` del
modelo sin perder precisión (`"0.210000"`, no `"0.21"`).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_serializer


class AlicuotaResponse(BaseModel):
    id: UUID
    nombre: str
    valor: Decimal
    activo: bool

    model_config = {"from_attributes": True}

    @field_serializer("valor")
    def _serializar_valor(self, valor: Decimal) -> str:
        return str(valor)


class PaginaAlicuotas(BaseModel):
    items: list[AlicuotaResponse]
    cursor_siguiente: str | None
