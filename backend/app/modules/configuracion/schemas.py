"""Esquemas Pydantic de salida de `configuracion/api.py` (change 05,
`design.md` D12; tarea 9.6).

`valor` viaja como **string** (`CLAUDE.md` §4: porcentajes como string,
nunca `float`) -- `field_serializer` lo convierte desde el `Decimal` del
modelo sin perder precisión (`"0.210000"`, no `"0.21"`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


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


class AlicuotaCrearRequest(BaseModel):
    """Cuerpo de `POST /configuracion/alicuotas` (change 20c, D6): el valor es un string decimal
    (INV-03, un número JSON se rechaza); nace activa y la organización sale del token."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    valor: str


class AlicuotaModificarRequest(BaseModel):
    """Reemplazo completo de `PUT /configuracion/alicuotas/{id}` (D6): el valor debe ser el
    guardado (`VALOR_NO_MODIFICABLE` si no)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    valor: str
    activo: bool


class MedioPagoResponse(BaseModel):
    """Un medio de pago activo con su indicador de referencia obligatoria."""

    id: UUID
    nombre: str
    requiere_referencia: bool

    model_config = {"from_attributes": True}


class ListaMediosPago(BaseModel):
    items: list[MedioPagoResponse]


class MedioPagoAdminResponse(BaseModel):
    """Un medio de pago activo o no, para la administración (change 17b, D2, D6)."""

    id: UUID
    nombre: str
    requiere_referencia: bool
    activo: bool
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class ListaMediosPagoAdmin(BaseModel):
    items: list[MedioPagoAdminResponse]


class MedioPagoCrearRequest(BaseModel):
    """Cuerpo de `POST /configuracion/medios-pago`: el medio nace activo y la organización sale
    del token (`extra="forbid"`)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    requiere_referencia: bool


class MedioPagoModificarRequest(BaseModel):
    """Reemplazo completo de los campos editables (D2), igual que los `PUT` de los demás
    maestros."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    requiere_referencia: bool
    activo: bool


class MotivoResponse(BaseModel):
    id: UUID
    nombre: str

    model_config = {"from_attributes": True}


class ListaMotivos(BaseModel):
    items: list[MotivoResponse]


class MotivoAdminResponse(BaseModel):
    """Un motivo activo o no, con su ámbito, para la administración (change 20c, D12)."""

    id: UUID
    ambito: str
    nombre: str
    activo: bool
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class ListaMotivosAdmin(BaseModel):
    items: list[MotivoAdminResponse]


class MotivoCrearRequest(BaseModel):
    """Cuerpo de `POST /configuracion/motivos`: el motivo nace activo y la organización sale del
    token (`extra="forbid"`)."""

    model_config = ConfigDict(extra="forbid")

    ambito: str
    nombre: str


class MotivoModificarRequest(BaseModel):
    """Reemplazo de nombre y estado (D2). El ámbito no se modifica: un campo `ambito` se rechaza."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    activo: bool
