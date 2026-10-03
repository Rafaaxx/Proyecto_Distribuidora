"""Esquemas HTTP de `stock` (change 09, grupo 7; `design.md` D3, D5, D11).

Los importes y costos viajan como **string** (`"1050.000000"`, `CLAUDE.md` §4,
INV-03) y las cantidades como enteros en unidad base (INV-04). Los cuerpos de
escritura reciben `costo_unitario` como `str | int | float | None` A PROPÓSITO
(igual que `StockInicialRegistrarContenidoV1`): con `Decimal`, Pydantic aceptaría
un número JSON y lo convertiría en silencio, y el escenario pide rechazarlo con
`COSTO_INVALIDO`; lo rechaza `costeo.validar_costo`. `cantidad_base` es un entero
estricto: `1.5`, `"12"` o `true` no son cantidades.

`organizacion_id` no existe acá: sale del token (INV-21).

**Costos condicionados por `VER_COSTOS` (D3-A).** `LineaDeStockResponse.costo_promedio`
y `LineaDeKardexResponse.costo_unitario` son opcionales y, para un usuario sin
`VER_COSTOS`, `api.py` NO los establece: las rutas declaran
`response_model_exclude_unset=True`, así que la clave desaparece de la respuesta
(no viaja ni como `null`). Con el permiso, un costo sin valor (producto sin
ingresos, D10) viaja como `null` explícito.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt, field_serializer

from app.modules.stock.service import Kardex, LineaDeStock, StockDeUbicacion

TipoDeUbicacion = Literal["DEPOSITO", "VEHICULO", "OTRO"]


# --- ubicaciones ---------------------------------------------------------------


class UbicacionCrearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo: TipoDeUbicacion
    requiere_toma: bool = False


class UbicacionModificarRequest(BaseModel):
    """Reemplazo completo de los campos editables (D7, D8), igual que los `PUT`
    de los demás maestros."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo: TipoDeUbicacion
    requiere_toma: bool
    activo: bool


class UbicacionResponse(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    requiere_toma: bool
    activo: bool
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginaUbicaciones(BaseModel):
    items: list[UbicacionResponse]
    cursor_siguiente: str | None


# --- stock inicial ---------------------------------------------------------------


class LineaStockInicialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt
    costo_unitario: str | int | float | None = None


class StockInicialRegistrarRequest(BaseModel):
    """`lineas` sin cota en el esquema: el dominio la valida (1 a 200,
    `LINEAS_INVALIDAS`, D5)."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_id: UUID
    lineas: list[LineaStockInicialRequest]


class LineaStockInicialResponse(BaseModel):
    producto_id: UUID
    movimiento_id: UUID
    cantidad_base: int
    saldo: int


class StockInicialResponse(BaseModel):
    """Sale de `comando.resultado`, no de una relectura: un reenvío idempotente del
    mismo `Operation-Id` devuelve exactamente lo mismo (INV-06). No lleva costos."""

    ubicacion_id: UUID
    lineas: list[LineaStockInicialResponse]


# --- stock por ubicación ------------------------------------------------------------


class LineaDeStockResponse(BaseModel):
    producto_id: UUID
    producto_codigo: str
    producto_nombre: str
    cantidad_base: int
    unidades_referencia: int | None
    nombre_referencia: str | None
    costo_promedio: Decimal | None = None

    @field_serializer("costo_promedio")
    def _serializar_costo(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class StockDeUbicacionResponse(BaseModel):
    items: list[LineaDeStockResponse]
    cursor_siguiente: str | None


def linea_de_stock_response(linea: LineaDeStock, *, con_costos: bool) -> LineaDeStockResponse:
    """Sin `con_costos` el campo de costo no se establece y la ruta lo omite."""
    datos = {
        "producto_id": linea.producto_id,
        "producto_codigo": linea.producto_codigo,
        "producto_nombre": linea.producto_nombre,
        "cantidad_base": linea.cantidad_base,
        "unidades_referencia": linea.unidades_referencia,
        "nombre_referencia": linea.nombre_referencia,
    }
    if con_costos:
        return LineaDeStockResponse(**datos, costo_promedio=linea.costo_promedio)  # type: ignore[arg-type]
    return LineaDeStockResponse(**datos)  # type: ignore[arg-type]


def stock_de_ubicacion_response(
    stock: StockDeUbicacion, *, con_costos: bool
) -> StockDeUbicacionResponse:
    return StockDeUbicacionResponse(
        items=[linea_de_stock_response(li, con_costos=con_costos) for li in stock.lineas],
        cursor_siguiente=stock.cursor_siguiente,
    )


# --- kardex --------------------------------------------------------------------------


class LineaDeKardexResponse(BaseModel):
    id: UUID
    tipo: str
    cantidad_base: int
    origen_tipo: str
    origen_id: UUID
    occurred_at: datetime
    registered_at: datetime
    usuario_id: UUID
    operation_id: UUID
    saldo_acumulado: int
    costo_unitario: Decimal | None = None

    @field_serializer("costo_unitario")
    def _serializar_costo(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class KardexResponse(BaseModel):
    saldo_anterior: int
    saldo_actual: int
    zona_horaria: str
    producto_codigo: str
    producto_nombre: str
    unidades_referencia: int | None
    nombre_referencia: str | None
    items: list[LineaDeKardexResponse]
    cursor_siguiente: str | None


def kardex_response(kardex: Kardex, *, con_costos: bool) -> KardexResponse:
    items: list[LineaDeKardexResponse] = []
    for m in kardex.movimientos:
        datos = {
            "id": m.id,
            "tipo": m.tipo,
            "cantidad_base": m.cantidad_base,
            "origen_tipo": m.origen_tipo,
            "origen_id": m.origen_id,
            "occurred_at": m.occurred_at,
            "registered_at": m.registered_at,
            "usuario_id": m.usuario_id,
            "operation_id": m.operation_id,
            "saldo_acumulado": m.saldo_acumulado,
        }
        if con_costos:
            items.append(LineaDeKardexResponse(**datos, costo_unitario=m.costo_unitario))  # type: ignore[arg-type]
        else:
            items.append(LineaDeKardexResponse(**datos))  # type: ignore[arg-type]
    return KardexResponse(
        saldo_anterior=kardex.saldo_anterior,
        saldo_actual=kardex.saldo_actual,
        zona_horaria=kardex.zona_horaria,
        producto_codigo=kardex.producto_codigo,
        producto_nombre=kardex.producto_nombre,
        unidades_referencia=kardex.unidades_referencia,
        nombre_referencia=kardex.nombre_referencia,
        items=items,
        cursor_siguiente=kardex.cursor_siguiente,
    )
