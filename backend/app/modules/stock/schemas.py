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

from app.modules.stock.queries import (
    DetalleDeAjuste,
    DetalleDeTransferencia,
    PaginaDeAjustes,
    PaginaDeTransferencias,
)
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


# --- transferencias (change 14: STK-07, `design.md` D6) -------------------------------


class LineaTransferenciaRequest(BaseModel):
    """`cantidad_base` es un entero estricto (INV-04): `1.5`, `"12"` o `true` son un 422 de
    validación; que sea mayor que cero lo valida el dominio (`CANTIDAD_INVALIDA`)."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt


class TransferenciaCrearRequest(BaseModel):
    """`lineas` sin cota en el esquema: el dominio la valida (1 a 200, `LINEAS_INVALIDAS`,
    D6). Sin `organizacion_id` (sale del token, INV-21) y sin fecha (rige el `occurred_at`
    del sobre, TR-05)."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_origen_id: UUID
    ubicacion_destino_id: UUID
    lineas: list[LineaTransferenciaRequest]
    observacion: str | None = None


class LineaTransferenciaResponse(BaseModel):
    producto_id: UUID
    cantidad_base: int
    saldo_origen: int
    saldo_destino: int


class TransferenciaResponse(BaseModel):
    """Sale de `comando.resultado`, no de una relectura: un reenvío idempotente del mismo
    `Operation-Id` devuelve exactamente lo mismo (INV-06). No lleva costos. `observaciones`
    son los códigos de SYN-07 que dejó el comando (`STOCK_NEGATIVO`)."""

    id: UUID
    estado: str
    ubicacion_origen_id: UUID
    ubicacion_destino_id: UUID
    observacion: str | None
    lineas: list[LineaTransferenciaResponse]
    observaciones: list[str]


class TransferenciaAnularRequest(BaseModel):
    """Solo el motivo de la anulación (D6): el id de la transferencia va en la ruta y la
    organización sale del token (INV-21)."""

    model_config = ConfigDict(extra="forbid")

    motivo_id: UUID


class AnulacionDeTransferenciaResponse(BaseModel):
    motivo_id: UUID
    anulada_en: datetime
    anulada_por_id: UUID


class TransferenciaAnuladaResponse(TransferenciaResponse):
    """La transferencia ya `ANULADA`, con los datos de la anulación y los saldos que quedaron
    en origen y destino. Sale de `comando.resultado` (INV-06). No lleva costos."""

    anulacion: AnulacionDeTransferenciaResponse


# --- ajustes (change 14: STK-08, `design.md` D6) --------------------------------------


class LineaAjusteRequest(BaseModel):
    """`cantidad_base` es un entero estricto con signo (INV-04); que sea distinta de cero lo
    valida el dominio (`CANTIDAD_INVALIDA`)."""

    model_config = ConfigDict(extra="forbid")

    producto_id: UUID
    cantidad_base: StrictInt


class AjusteCrearRequest(BaseModel):
    """`lineas` sin cota en el esquema: el dominio la valida (1 a 200, `LINEAS_INVALIDAS`).
    Sin `organizacion_id` (sale del token, INV-21) y sin fecha (rige el `occurred_at` del
    sobre, TR-05)."""

    model_config = ConfigDict(extra="forbid")

    ubicacion_id: UUID
    motivo_id: UUID
    lineas: list[LineaAjusteRequest]
    observacion: str | None = None


class LineaAjusteResponse(BaseModel):
    """`costo_unitario` solo existe con `VER_COSTOS`: sin el permiso la ruta no lo establece
    y la clave desaparece de la respuesta (`response_model_exclude_unset`, ADR-036)."""

    producto_id: UUID
    cantidad_base: int
    saldo: int
    costo_unitario: Decimal | None = None

    @field_serializer("costo_unitario")
    def _serializar_costo(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class AjusteResponse(BaseModel):
    """Sale de `comando.resultado` (un reenvío idempotente devuelve lo mismo, INV-06); la
    ruta le agrega el costo de cada línea, leído del ajuste, si el usuario tiene `VER_COSTOS`."""

    id: UUID
    estado: str
    ubicacion_id: UUID
    motivo_id: UUID
    observacion: str | None
    lineas: list[LineaAjusteResponse]


class AjusteAnularRequest(BaseModel):
    """Solo el motivo de la anulación (D6): el id del ajuste va en la ruta."""

    model_config = ConfigDict(extra="forbid")

    motivo_id: UUID


class AnulacionDeAjusteResponse(BaseModel):
    motivo_id: UUID
    anulado_en: datetime
    anulado_por_id: UUID


class AjusteAnuladoResponse(AjusteResponse):
    """El ajuste ya `ANULADA`: `motivo_id` sigue siendo el del ajuste y `anulacion.motivo_id`
    el de la anulación. Cada línea trae su cantidad ORIGINAL y el saldo que dejó la anulación;
    `observaciones` lista `STOCK_NEGATIVO` si la anulación dejó un saldo bajo cero."""

    anulacion: AnulacionDeAjusteResponse
    observaciones: list[str]


def _lineas_de_ajuste_response(
    resultado: dict[str, object], costos: dict[UUID, Decimal | None] | None
) -> list[LineaAjusteResponse]:
    lineas: list[LineaAjusteResponse] = []
    for dato in resultado["lineas"]:  # type: ignore[attr-defined]
        base = {
            "producto_id": UUID(str(dato["producto_id"])),
            "cantidad_base": dato["cantidad_base"],
            "saldo": dato["saldo"],
        }
        if costos is None:
            lineas.append(LineaAjusteResponse(**base))
        else:
            lineas.append(
                LineaAjusteResponse(**base, costo_unitario=costos.get(base["producto_id"]))
            )
    return lineas


def ajuste_response(
    resultado: dict[str, object], *, costos: dict[UUID, Decimal | None] | None
) -> AjusteResponse:
    """Arma la respuesta desde el resultado guardado del comando. Con `costos` (el usuario
    tiene `VER_COSTOS`) cada línea trae su `costo_unitario`; sin él la clave se omite."""
    return AjusteResponse(
        id=UUID(str(resultado["ajuste_id"])),
        estado=str(resultado["estado"]),
        ubicacion_id=UUID(str(resultado["ubicacion_id"])),
        motivo_id=UUID(str(resultado["motivo_id"])),
        observacion=None if resultado["observacion"] is None else str(resultado["observacion"]),
        lineas=_lineas_de_ajuste_response(resultado, costos),
    )


def ajuste_anulado_response(
    resultado: dict[str, object], *, costos: dict[UUID, Decimal | None] | None
) -> AjusteAnuladoResponse:
    """Como `ajuste_response`, para el resultado de `STOCK_AJUSTE_ANULAR`."""
    anulacion: dict[str, object] = resultado["anulacion"]  # type: ignore[assignment]
    return AjusteAnuladoResponse(
        id=UUID(str(resultado["ajuste_id"])),
        estado=str(resultado["estado"]),
        ubicacion_id=UUID(str(resultado["ubicacion_id"])),
        motivo_id=UUID(str(resultado["motivo_id"])),
        observacion=None if resultado["observacion"] is None else str(resultado["observacion"]),
        lineas=_lineas_de_ajuste_response(resultado, costos),
        anulacion=AnulacionDeAjusteResponse(
            motivo_id=UUID(str(anulacion["motivo_id"])),
            anulado_en=datetime.fromisoformat(str(anulacion["anulado_en"])),
            anulado_por_id=UUID(str(anulacion["anulado_por_id"])),
        ),
        observaciones=[str(codigo) for codigo in resultado["observaciones"]],  # type: ignore[attr-defined]
    )


# --- lecturas de transferencias y ajustes (change 14, tareas 10.1 y 10.2, D7) ------------------


class TransferenciaDelListadoResponse(BaseModel):
    id: UUID
    estado: str
    ubicacion_origen_id: UUID
    ubicacion_origen_nombre: str
    ubicacion_destino_id: UUID
    ubicacion_destino_nombre: str
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    cantidad_de_lineas: int


class PaginaDeTransferenciasResponse(BaseModel):
    items: list[TransferenciaDelListadoResponse]
    cursor_siguiente: str | None


class LineaDelDetalleDeTransferenciaResponse(BaseModel):
    """Sin costo: una transferencia no lo muestra a nadie (ADR-036)."""

    orden: int
    producto_id: UUID
    producto_codigo: str | None
    producto_nombre: str | None
    cantidad_base: int
    unidades_referencia: int | None
    nombre_referencia: str | None


class DetalleDeAnulacionDeTransferenciaResponse(BaseModel):
    motivo_id: UUID
    motivo_nombre: str | None
    anulada_en: datetime
    anulada_por_id: UUID
    anulada_por_nombre: str | None


class DetalleDeTransferenciaResponse(BaseModel):
    id: UUID
    estado: str
    ubicacion_origen_id: UUID
    ubicacion_origen_nombre: str
    ubicacion_destino_id: UUID
    ubicacion_destino_nombre: str
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    registered_at: datetime
    lineas: list[LineaDelDetalleDeTransferenciaResponse]
    anulacion: DetalleDeAnulacionDeTransferenciaResponse | None


def pagina_de_transferencias_response(
    pagina: PaginaDeTransferencias,
) -> PaginaDeTransferenciasResponse:
    return PaginaDeTransferenciasResponse(
        items=[
            TransferenciaDelListadoResponse(**vars(transferencia))
            for transferencia in pagina.transferencias
        ],
        cursor_siguiente=pagina.cursor_siguiente,
    )


def detalle_de_transferencia_response(
    detalle: DetalleDeTransferencia,
) -> DetalleDeTransferenciaResponse:
    anulacion = detalle.anulacion
    return DetalleDeTransferenciaResponse(
        id=detalle.id,
        estado=detalle.estado,
        ubicacion_origen_id=detalle.ubicacion_origen_id,
        ubicacion_origen_nombre=detalle.ubicacion_origen_nombre,
        ubicacion_destino_id=detalle.ubicacion_destino_id,
        ubicacion_destino_nombre=detalle.ubicacion_destino_nombre,
        observacion=detalle.observacion,
        usuario_id=detalle.usuario_id,
        usuario_nombre=detalle.usuario_nombre,
        occurred_at=detalle.occurred_at,
        registered_at=detalle.registered_at,
        lineas=[
            LineaDelDetalleDeTransferenciaResponse(
                orden=linea.orden,
                producto_id=linea.producto_id,
                producto_codigo=linea.producto_codigo,
                producto_nombre=linea.producto_nombre,
                cantidad_base=linea.cantidad_base,
                unidades_referencia=linea.unidades_referencia,
                nombre_referencia=linea.nombre_referencia,
            )
            for linea in detalle.lineas
        ],
        anulacion=None
        if anulacion is None
        else DetalleDeAnulacionDeTransferenciaResponse(
            motivo_id=anulacion.motivo_id,
            motivo_nombre=anulacion.motivo_nombre,
            anulada_en=anulacion.momento,
            anulada_por_id=anulacion.usuario_id,
            anulada_por_nombre=anulacion.usuario_nombre,
        ),
    )


class AjusteDelListadoResponse(BaseModel):
    id: UUID
    estado: str
    ubicacion_id: UUID
    ubicacion_nombre: str
    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    cantidad_de_lineas: int


class PaginaDeAjustesResponse(BaseModel):
    items: list[AjusteDelListadoResponse]
    cursor_siguiente: str | None


class LineaDelDetalleDeAjusteResponse(BaseModel):
    """`costo_unitario` solo existe con `VER_COSTOS`: sin el permiso la ruta no lo establece y
    la clave desaparece de la respuesta (`response_model_exclude_unset`, ADR-036)."""

    orden: int
    producto_id: UUID
    producto_codigo: str | None
    producto_nombre: str | None
    cantidad_base: int
    unidades_referencia: int | None
    nombre_referencia: str | None
    costo_unitario: Decimal | None = None

    @field_serializer("costo_unitario")
    def _serializar_costo(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class DetalleDeAnulacionDeAjusteResponse(BaseModel):
    motivo_id: UUID
    motivo_nombre: str | None
    anulado_en: datetime
    anulado_por_id: UUID
    anulado_por_nombre: str | None


class DetalleDeAjusteResponse(BaseModel):
    id: UUID
    estado: str
    ubicacion_id: UUID
    ubicacion_nombre: str
    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    occurred_at: datetime
    registered_at: datetime
    lineas: list[LineaDelDetalleDeAjusteResponse]
    anulacion: DetalleDeAnulacionDeAjusteResponse | None


def pagina_de_ajustes_response(pagina: PaginaDeAjustes) -> PaginaDeAjustesResponse:
    return PaginaDeAjustesResponse(
        items=[AjusteDelListadoResponse(**vars(ajuste)) for ajuste in pagina.ajustes],
        cursor_siguiente=pagina.cursor_siguiente,
    )


def detalle_de_ajuste_response(
    detalle: DetalleDeAjuste, *, con_costos: bool
) -> DetalleDeAjusteResponse:
    """Sin `con_costos` el campo de costo de cada línea no se establece y la ruta lo omite."""
    anulacion = detalle.anulacion
    lineas: list[LineaDelDetalleDeAjusteResponse] = []
    for linea in detalle.lineas:
        datos = {
            "orden": linea.orden,
            "producto_id": linea.producto_id,
            "producto_codigo": linea.producto_codigo,
            "producto_nombre": linea.producto_nombre,
            "cantidad_base": linea.cantidad_base,
            "unidades_referencia": linea.unidades_referencia,
            "nombre_referencia": linea.nombre_referencia,
        }
        if con_costos:
            lineas.append(
                LineaDelDetalleDeAjusteResponse(**datos, costo_unitario=linea.costo_unitario)  # type: ignore[arg-type]
            )
        else:
            lineas.append(LineaDelDetalleDeAjusteResponse(**datos))  # type: ignore[arg-type]
    return DetalleDeAjusteResponse(
        id=detalle.id,
        estado=detalle.estado,
        ubicacion_id=detalle.ubicacion_id,
        ubicacion_nombre=detalle.ubicacion_nombre,
        motivo_id=detalle.motivo_id,
        motivo_nombre=detalle.motivo_nombre,
        observacion=detalle.observacion,
        usuario_id=detalle.usuario_id,
        usuario_nombre=detalle.usuario_nombre,
        occurred_at=detalle.occurred_at,
        registered_at=detalle.registered_at,
        lineas=lineas,
        anulacion=None
        if anulacion is None
        else DetalleDeAnulacionDeAjusteResponse(
            motivo_id=anulacion.motivo_id,
            motivo_nombre=anulacion.motivo_nombre,
            anulado_en=anulacion.momento,
            anulado_por_id=anulacion.usuario_id,
            anulado_por_nombre=anulacion.usuario_nombre,
        ),
    )


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
    motivo_nombre: str | None = None
    estado_origen: str | None = None
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
            "motivo_nombre": m.motivo_nombre,
            "estado_origen": m.estado_origen,
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
