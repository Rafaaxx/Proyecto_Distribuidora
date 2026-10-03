"""Esquemas Pydantic de entrada/salida de `proveedores/api.py` (change 06,
grupo 10; `contrato-api.md`, aprobado por el usuario 2026-09-24 con las
recomendaciones P1 a P8).

Mismo criterio que `catalogo/schemas.py`: los `*Request` de escritura son
el CUERPO HTTP, distintos de los `*ContenidoV1` de `commands.py` (el
contenido AUDITADO del comando). `organizacion_id` nunca aparece en ningún
esquema de entrada (`CLAUDE.md` §4: sale siempre del token).

Decimales (`CLAUDE.md` §4, `contrato-api.md` P3): `valor` y `bonificacion`
viajan como **string** estricto, con un patrón que rechaza un número JSON
ya degradado por `float` en el cliente (`02` §10.2 es un DEBE). El patrón
no limita la cantidad de decimales -- esa validación es del dominio
(`domain/lote.py`, `VALOR_INVALIDO`/`BONIFICACION_INVALIDA`), para no
duplicar la regla ni fallar con un 422 genérico de Pydantic en vez del
código estable que la spec exige. La salida usa `field_serializer` sobre
el `Decimal` del modelo, igual que `configuracion/schemas.py::
AlicuotaResponse` -- conserva la escala de la columna (`"0.210000"`, no
`"0.21"`)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"

# --- proveedor (D7) ----------------------------------------------------------


class ProveedorCrearRequest(BaseModel):
    nombre: str
    cuit: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None


class ProveedorModificarRequest(BaseModel):
    """`PUT` reemplaza el estado completo (spec, `contrato-api.md` §2.1):
    un opcional ausente o `null` se guarda como `null`."""

    nombre: str
    cuit: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    activo: bool


class ProveedorResponse(BaseModel):
    id: UUID
    nombre: str
    cuit: str | None
    contacto: str | None
    telefono: str | None
    email: str | None
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class ProveedorOpcionResponse(BaseModel):
    """`GET /proveedores/opciones` (D8): solo proveedores activos, sin
    CUIT ni contacto."""

    id: UUID
    nombre: str

    model_config = {"from_attributes": True}


class PaginaProveedores(BaseModel):
    items: list[ProveedorResponse]
    cursor_siguiente: str | None


class PaginaProveedorOpciones(BaseModel):
    """Paginada (`contrato-api.md` P2, aprobado 2026-09-24)."""

    items: list[ProveedorOpcionResponse]
    cursor_siguiente: str | None


# --- costos informados (D12) -------------------------------------------------


class CostoDelLoteRequest(BaseModel):
    """Un costo dentro del lote de `POST /costos` (D12). `valor` y
    `bonificacion` viajan como string estricto (P3); la cantidad de
    decimales la valida el dominio, no el patrón de este campo."""

    producto_id: UUID
    presentacion_id: UUID
    valor: str = Field(pattern=_PATRON_DECIMAL)
    incluye_iva: bool
    bonificacion: str = Field(default="0", pattern=_PATRON_DECIMAL)
    vigencia_desde: date
    observacion: str | None = None


class ResumenReglaIvaResponse(BaseModel):
    """`GET /costos/resumen-regla-iva` (11b, D10): cuántos costos vigentes a `fecha` se
    registraron con y sin crédito fiscal. Insumo de la confirmación del cambio de condición."""

    fecha: date
    con_credito_fiscal: int
    sin_credito_fiscal: int


class CostoInformarRequest(BaseModel):
    proveedor_id: UUID
    costos: list[CostoDelLoteRequest] = Field(min_length=1, max_length=200)


class CostoDelResultadoResponse(BaseModel):
    """Un elemento de la respuesta de `POST /costos` (P6, aprobado
    2026-09-24): sale de `comando.resultado`, no de una relectura de las
    filas -- un reenvío idempotente del mismo `Operation-Id` devuelve
    exactamente lo mismo."""

    id: UUID
    costo_base: str


class CostoInformarResponse(BaseModel):
    costos: list[CostoDelResultadoResponse]


class CostoInformadoResponse(BaseModel):
    """Respuesta de `GET .../vigente` y `GET .../historial` (`contrato-
    api.md` §2.2). `proveedor_nombre` y `presentacion_nombre` (P4, aprobado
    2026-09-24) se resuelven en `api.py`, no vienen de `model_validate`
    directo del modelo `CostoInformado` -- por eso este esquema NO declara
    `from_attributes`: `api.py` arma cada instancia explícitamente."""

    id: UUID
    proveedor_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    valor: Decimal
    incluye_iva: bool
    computa_credito_fiscal: bool
    bonificacion: Decimal
    alicuota_aplicada: Decimal
    costo_base: Decimal
    vigencia_desde: date
    observacion: str | None
    usuario_id: UUID
    operation_id: UUID
    creado_en: datetime
    proveedor_nombre: str
    presentacion_nombre: str
    usuario_nombre: str
    """Nombre para mostrar de quien registró el costo (`contrato-api.md`
    P10, enmienda aprobada en la verificación manual 13.5): se resuelve en
    `api.py` vía `identidad.service.obtener_nombres_de_usuarios`, por lote
    -- mismo criterio que `proveedor_nombre`/`presentacion_nombre`."""

    @field_serializer("valor", "bonificacion", "alicuota_aplicada", "costo_base")
    def _serializar_decimal(self, valor: Decimal) -> str:
        return str(valor)


class PaginaCostosInformados(BaseModel):
    items: list[CostoInformadoResponse]
    cursor_siguiente: str | None


class CostoVigenteResponse(BaseModel):
    """`GET .../vigente` (P7, aprobado 2026-09-24): 200 siempre que el
    producto exista en la organización, con `costo: null` cuando no hay
    costo vigente para `fecha` -- el 404 queda solo para un producto
    inexistente o ajeno (INV-21)."""

    fecha: date
    costo: CostoInformadoResponse | None
    por_presentacion: list[CostoInformadoResponse]
    """P11 (`contrato-api.md`, aprobado en la verificación manual 13.5,
    opción B): el último costo informado (D4) de CADA presentación del
    producto con costo a `fecha` (una presentación sin costo se omite),
    ordenado por `presentacion_nombre` -- cambio aditivo, no toca `costo`.
    Puramente informativo: el precio (PRC-11) sigue calculándose solo con
    `costo` (el costo vigente del producto)."""


# --- compras (change 11, `design.md` D1 a D7) ------------------------------------------


class CompraLineaRequest(BaseModel):
    """Una línea de `POST /compras` (D5). `cantidad`, `valor` y `bonificacion` viajan
    como string estricto (INV-03); la cantidad de decimales la valida el dominio con su
    código estable (`CANTIDAD_INVALIDA`, `VALOR_INVALIDO`, `BONIFICACION_INVALIDA`)."""

    producto_id: UUID
    presentacion_id: UUID
    cantidad: str = Field(pattern=_PATRON_DECIMAL)
    valor: str = Field(pattern=_PATRON_DECIMAL)
    incluye_iva: bool
    bonificacion: str = Field(default="0", pattern=_PATRON_DECIMAL)


class CompraMedioRequest(BaseModel):
    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class CompraConfirmarRequest(BaseModel):
    """`organizacion_id` nunca aparece (sale del token). `lineas` no declara
    `min_length`: una compra sin líneas la rechaza el dominio con `COMPRA_SIN_LINEAS`
    (INV-07), no un 422 genérico de Pydantic. `condicion` es `CONTADO` o `CREDITO`:
    cualquier otro valor lo rechaza el dominio con `CONDICION_INVALIDA`."""

    proveedor_id: UUID
    fecha: date
    ubicacion_id: UUID
    condicion: str
    total_factura: str = Field(pattern=_PATRON_DECIMAL)
    numero_comprobante: str | None = None
    observacion: str | None = None
    lineas: list[CompraLineaRequest]
    medios: list[CompraMedioRequest] = Field(default_factory=list)


class DiferenciaDeCostoResponse(BaseModel):
    """CMP-04, D7: una línea cuyo costo base difiere del costo informado vigente (o no
    tiene vigente, `costo_base_vigente: null`). Informativa: la compra nunca registra un
    costo informado."""

    linea: int
    producto_id: UUID
    costo_base_compra: str
    costo_base_vigente: str | None


class CompraConfirmarResponse(BaseModel):
    """Sale de `comando.resultado`, no de una relectura: un reenvío idempotente del mismo
    `Operation-Id` devuelve exactamente lo mismo (INV-06). Importes como string."""

    compra_id: UUID
    total_neto: str
    total_factura: str
    pago_id: UUID | None
    diferencias_de_costo: list[DiferenciaDeCostoResponse]


class CompraAnularRequest(BaseModel):
    """`POST /compras/{id}/anulacion`. `devuelve_pago` es obligatorio en una compra de
    contado y prohibido en una a crédito (D3): lo decide el servicio con
    `CONDICION_INVALIDA`, que conoce la condición. `organizacion_id` nunca aparece
    (sale del token)."""

    model_config = ConfigDict(extra="forbid")

    motivo_id: UUID
    devuelve_pago: bool | None = None


class CompraAnularResponse(BaseModel):
    """Sale de `comando.resultado` (INV-06). `observaciones` son los códigos de SYN-07
    que dejó la anulación (`ANULACION_COMPRA_SIN_RECALCULO`, `STOCK_NEGATIVO`)."""

    compra_id: UUID
    estado: str
    pago_anulado: bool
    observaciones: list[str]


class CompraResumenResponse(BaseModel):
    """Una fila del listado de compras. Importes como string (INV-03)."""

    id: UUID
    fecha: date
    proveedor_id: UUID
    proveedor_nombre: str
    condicion: str
    total_neto: str
    total_factura: str
    estado: str
    numero_comprobante: str | None


class PaginaCompras(BaseModel):
    items: list[CompraResumenResponse]
    cursor_siguiente: str | None


class CompraLineaResponse(BaseModel):
    """Una línea del detalle. `unidades_referencia` permite mostrar la cantidad en cajas
    + unidades (CAT-08); `None` si el producto no tiene presentación de referencia."""

    orden: int
    producto_id: UUID
    producto_codigo: str | None
    producto_nombre: str | None
    presentacion_id: UUID
    presentacion_nombre: str | None
    unidades_presentacion: int
    unidades_referencia: int | None
    nombre_referencia: str | None
    cantidad: str
    cantidad_base: int
    valor_presentacion: str
    incluye_iva: bool
    computa_credito_fiscal: bool
    bonificacion: str
    alicuota_aplicada: str
    costo_base: str
    importe_neto: str


class CompraMedioResponse(BaseModel):
    medio_pago_id: UUID
    medio_nombre: str | None
    importe: str
    referencia: str | None


class CompraPagoResponse(BaseModel):
    id: UUID
    fecha: date
    importe: str
    estado: str
    anulado_en: datetime | None
    medios: list[CompraMedioResponse]


class CompraAnulacionResponse(BaseModel):
    motivo_id: UUID
    motivo_nombre: str | None
    anulada_en: datetime
    anulada_por_id: UUID


class CompraDetalleResponse(CompraResumenResponse):
    ubicacion_id: UUID
    observacion: str | None
    lineas: list[CompraLineaResponse]
    pago: CompraPagoResponse | None
    anulacion: CompraAnulacionResponse | None
