"""Esquemas HTTP de `ventas` (change 18a, tarea 7.8; `design.md` D2, D12).

La entrada refleja el contenido de `VENTA_CONFIRMAR` v1. `organizacion_id` nunca aparece (sale del
token, INV-21, TR-08): un campo extra del cuerpo se ignora y el endpoint arma el contenido campo
por campo; quien manda de verdad es `VentaConfirmarContenidoV1`, que prohíbe los extras. Los
importes viajan como string (INV-03) y las cantidades son enteros estrictos (INV-04).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"


class VentaLineaRequest(BaseModel):
    """Una línea con lo que vio el usuario (D2)."""

    linea_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    cantidad: StrictInt
    lista_version_id: UUID
    precio_referencia: str = Field(pattern=_PATRON_DECIMAL)
    unidades_referencia: StrictInt
    importe_bruto: str = Field(pattern=_PATRON_DECIMAL)


class VentaCobranzaMedioRequest(BaseModel):
    """Un medio de la cobranza en el acto (D12)."""

    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class VentaCobranzaRequest(BaseModel):
    """La cobranza en el acto; su importe es la suma de los medios (INV-08)."""

    cobranza_id: UUID
    medios: list[VentaCobranzaMedioRequest]
    observacion: str | None = None


class VentaConfirmarRequest(BaseModel):
    """`POST /ventas`. `venta_id` y `numero` los genera quien origina la venta (`02` §9, D4)."""

    venta_id: UUID
    numero: str
    cliente_id: UUID
    ubicacion_id: UUID | None = None
    lista_id: UUID | None = None
    lista_version_id: UUID | None = None
    motivo_lista_id: UUID | None = None
    lineas: list[VentaLineaRequest]
    total: str = Field(pattern=_PATRON_DECIMAL)
    cobranza: VentaCobranzaRequest | None = None


class VentaConfirmarResponse(BaseModel):
    """Sale de `comando.resultado`, no de una relectura: un reenvío idempotente del mismo
    `Operation-Id` devuelve exactamente lo mismo (INV-06). `saldo` es el saldo resultante del
    cliente, con la cobranza en el acto ya aplicada; negativo es saldo a favor."""

    venta_id: UUID
    numero: str
    estado: str
    total: str
    saldo: str
    cobranza_id: UUID | None


# --- lecturas (change 18a, tareas 9.1 y 9.2; `design.md` D19) ---------------------------------


class VentaResumenResponse(BaseModel):
    """Una venta del listado. Los importes viajan como string (INV-03)."""

    venta_id: UUID
    numero: str
    occurred_at: datetime
    cliente_id: UUID
    cliente_nombre: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    ubicacion_id: UUID
    ubicacion_nombre: str | None
    jornada_id: UUID | None
    total: str
    estado: str
    estado_facturacion: str
    modo_confirmacion: str


class PaginaVentas(BaseModel):
    items: list[VentaResumenResponse]
    cursor_siguiente: str | None


class VentaLineaResponse(BaseModel):
    """Una línea congelada. `costo_unitario` y `costo_total` van en nulo sin `VER_COSTOS`
    (VTA-05, `01` §19). Sin utilidad: es de los reportes (REP-04)."""

    linea_id: UUID
    orden: int
    producto_id: UUID
    producto_nombre: str | None
    presentacion_id: UUID
    presentacion_nombre: str | None
    lista_version_id: UUID
    unidades_presentacion: int
    cantidad: int
    cantidad_base: int
    precio_referencia: str
    unidades_referencia: int
    importe_bruto: str
    importe_descuento: str
    importe_neto: str
    alicuota: str
    importe_iva: str
    costo_unitario: str | None
    costo_total: str | None


class VentaCobranzaResponse(BaseModel):
    cobranza_id: UUID
    importe: str
    estado: str


class VentaMotivoResponse(BaseModel):
    motivo_id: UUID
    nombre: str | None


class VentaObservacionResponse(BaseModel):
    codigo: str
    estado: str
    detalle: dict[str, object]


class VentaDetalleResponse(VentaResumenResponse):
    """La venta como quedó congelada (VTA-03, VTA-12)."""

    registered_at: datetime
    dispositivo_id: UUID
    lista_id: UUID
    lista_nombre: str | None
    version_id: UUID
    version_numero: int | None
    motivo_lista: VentaMotivoResponse | None
    modo_impositivo: str
    total_neto: str
    total_iva: str
    importe_facturado: str
    cobranza: VentaCobranzaResponse | None
    lineas: list[VentaLineaResponse]
    observaciones: list[VentaObservacionResponse]


class PresentacionParaVenderResponse(BaseModel):
    presentacion_id: UUID
    nombre: str
    unidades_base: int
    es_referencia: bool


class ProductoParaVenderResponse(BaseModel):
    """Un producto activo con su precio en la versión (nulo y `sin_precio` si no tiene, D7) y el
    stock de la ubicación pedida (nulo si no se pidió). Nunca lleva costos ni márgenes."""

    producto_id: UUID
    codigo: str
    nombre: str
    precio_referencia: str | None
    unidades_referencia: int | None
    sin_precio: bool
    stock_base: int | None
    presentaciones: list[PresentacionParaVenderResponse]


class PreciosParaVenderResponse(BaseModel):
    lista_id: UUID
    lista_nombre: str
    version_id: UUID
    version_numero: int
    ubicacion_id: UUID | None
    items: list[ProductoParaVenderResponse]
    cursor_siguiente: str | None


class NumeracionResponse(BaseModel):
    """Prefijo del dispositivo de la sesión, último correlativo y el número que sigue (D4)."""

    prefijo: str
    ultimo_correlativo: int
    siguiente_numero: str


class VersionElegibleResponse(BaseModel):
    version_id: UUID
    numero: int
    estado: str
    vigencia_desde: datetime
    vigencia_hasta: datetime | None


class VersionesElegiblesResponse(BaseModel):
    items: list[VersionElegibleResponse]
