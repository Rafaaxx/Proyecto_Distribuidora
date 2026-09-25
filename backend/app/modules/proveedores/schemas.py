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

from pydantic import BaseModel, Field, field_serializer

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
