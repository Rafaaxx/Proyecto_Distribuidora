"""Esquemas Pydantic de entrada/salida de `catalogo/api.py` (change 05,
grupo 9, tarea 9.1/9.2).

Los `*Request` de escritura son el CUERPO HTTP -- distintos de los
`*ContenidoV1` de `commands.py` (el contenido AUDITADO del comando): la ruta
arma el `SobreComando` a partir del cuerpo, igual que `identidad/api.py`
(`CrearUsuarioRequest` vs. `UsuarioCrearContenidoV1` no existe allá porque
identidad no tiene esa distinción, pero el criterio -- "el modelo de
transporte HTTP no es el modelo de contenido auditado" -- es el mismo:
acá SÍ son clases separadas porque `ProductoCrearContenidoV1` anida
`PresentacionInicialContenidoV1`, con el mismo shape que
`PresentacionInicialRequest` de abajo, y conviene no acoplar el contrato
HTTP a los nombres internos del comando).

`organizacion_id` nunca aparece en ningún esquema de entrada (`CLAUDE.md`
§4: sale siempre del token). Los importes no existen en este módulo (no
hay precios ni costos en `catalogo`), así que ninguna regla de dinero
aplica acá.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# --- categoria ---------------------------------------------------------


class CategoriaCrearRequest(BaseModel):
    nombre: str


class CategoriaModificarRequest(BaseModel):
    nombre: str
    activo: bool


class CategoriaResponse(BaseModel):
    id: UUID
    nombre: str
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


# --- marca ---------------------------------------------------------------


class MarcaCrearRequest(BaseModel):
    nombre: str


class MarcaModificarRequest(BaseModel):
    nombre: str
    activo: bool


class MarcaResponse(BaseModel):
    id: UUID
    nombre: str
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


# --- presentacion ----------------------------------------------------------


class PresentacionInicialRequest(BaseModel):
    """Presentación inicial dentro de un `ProductoCrearRequest` (CAT-02,
    CAT-03: el alta ya trae sus presentaciones, exactamente una de
    referencia)."""

    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    es_referencia: bool


class PresentacionAgregarRequest(BaseModel):
    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool


class PresentacionModificarRequest(BaseModel):
    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    activo: bool


class PresentacionReferenciaCambiarRequest(BaseModel):
    presentacion_id: UUID


class PresentacionResponse(BaseModel):
    id: UUID
    producto_id: UUID
    nombre: str
    unidades_base: int
    usar_en_venta: bool
    usar_en_compra: bool
    es_referencia: bool
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


# --- producto --------------------------------------------------------------


class ProductoCrearRequest(BaseModel):
    codigo: str
    nombre: str
    categoria_id: UUID
    marca_id: UUID | None = None
    unidad_base: str
    alicuota_id: UUID
    presentaciones: list[PresentacionInicialRequest]


class ProductoModificarRequest(BaseModel):
    codigo: str
    nombre: str
    categoria_id: UUID
    marca_id: UUID | None = None
    unidad_base: str
    alicuota_id: UUID
    activo: bool


class ProductoResponse(BaseModel):
    """Fila de listado (tarea 9.2): sin presentaciones -- para el detalle
    completo (incluidas sus presentaciones) ver `ProductoDetalleResponse`."""

    id: UUID
    codigo: str
    nombre: str
    categoria_id: UUID
    marca_id: UUID | None
    unidad_base: str
    alicuota_id: UUID
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class ProductoDetalleResponse(ProductoResponse):
    presentaciones: list[PresentacionResponse]


# --- paginación (tarea 9.2, `02` §11: cursor) -------------------------------


class PaginaCategorias(BaseModel):
    items: list[CategoriaResponse]
    cursor_siguiente: str | None


class PaginaMarcas(BaseModel):
    items: list[MarcaResponse]
    cursor_siguiente: str | None


class PaginaProductos(BaseModel):
    items: list[ProductoResponse]
    cursor_siguiente: str | None
