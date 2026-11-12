"""Esquemas HTTP de `cuentas_corrientes` (change 08, grupo 6; `design.md` D5, D9).

Los importes viajan como **string** (`"150000.00"`, `CLAUDE.md` §4, INV-03): las
respuestas los serializan con `str()` y el cuerpo de la escritura los recibe como
`str | int | float` a propósito, igual que `SaldoInicialRegistrarContenidoV1`, para
que un número JSON llegue hasta `domain/importe.py` y se rechace con
`IMPORTE_INVALIDO` en vez de convertirse en silencio.

`SaldoInicialRegistrarRequest` es el CUERPO HTTP de la ruta dedicada; el contenido
auditado del comando lo arma `api.py` (mismo criterio que `proveedores/schemas.py`).
`organizacion_id` no existe acá: sale del token (INV-21).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

from app.modules.cuentas_corrientes.domain.estado_de_cuenta import EstadoDeCuenta


class SaldoInicialRegistrarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cuenta_tipo: Literal["CLIENTE", "PROVEEDOR"]
    entidad_id: UUID
    importe: str | int | float
    sentido: Literal["AUMENTA", "REDUCE"]


class SaldoInicialResponse(BaseModel):
    """Sale de `comando.resultado`, no de una relectura: un reenvío idempotente
    del mismo `Operation-Id` devuelve exactamente lo mismo (INV-06)."""

    movimiento_id: UUID
    saldo: str


class MovimientoEstadoDeCuentaResponse(BaseModel):
    """Un movimiento del estado de cuenta con su saldo acumulado real (CC-07)."""

    id: UUID
    tipo: str
    sentido: str
    importe: Decimal
    origen_tipo: str
    origen_id: UUID
    occurred_at: datetime
    registered_at: datetime
    usuario_id: UUID
    operation_id: UUID
    saldo_acumulado: Decimal

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("importe", "saldo_acumulado")
    def _serializar_decimal(self, valor: Decimal) -> str:
        return str(valor)


class EstadoDeCuentaResponse(BaseModel):
    saldo_anterior: Decimal
    saldo_actual: Decimal
    zona_horaria: str
    items: list[MovimientoEstadoDeCuentaResponse]
    cursor_siguiente: str | None

    @field_serializer("saldo_anterior", "saldo_actual")
    def _serializar_decimal(self, valor: Decimal) -> str:
        return str(valor)


def estado_de_cuenta_response(estado: EstadoDeCuenta) -> EstadoDeCuentaResponse:
    """Convierte el resultado del servicio en la respuesta HTTP. Lo comparten las
    rutas de clientes y de proveedores: el estado de cuenta es el mismo."""
    return EstadoDeCuentaResponse(
        saldo_anterior=estado.saldo_anterior,
        saldo_actual=estado.saldo_actual,
        zona_horaria=estado.zona_horaria,
        items=[MovimientoEstadoDeCuentaResponse.model_validate(m) for m in estado.movimientos],
        cursor_siguiente=estado.cursor_siguiente,
    )
