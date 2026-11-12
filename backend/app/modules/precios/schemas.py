"""Esquemas de `precios` (change 13, grupo 5; `design.md` D12, `Enfoque técnico`).

Los `*Request` son el CUERPO HTTP de las rutas de escritura de `api.py`, distintos de los
`*ContenidoV1` de `commands.py` (el contenido AUDITADO del comando que arma cada endpoint);
mismo criterio que `clientes/schemas.py` y `proveedores/schemas.py`.

Los múltiplos de redondeo y los valores de margen viajan como **string** en ambos sentidos
(INV-03, `CLAUDE.md` §4): en la entrada se declaran `str`, así que un número JSON se rechaza
(422) en vez de convertirse a `float`; en la salida los `Decimal` se serializan con
`str(...)`, con los decimales que tiene la columna (`"100.00"`, `"0.300000"`). El frontend los
formatea desde el string con `lib/money.ts`, sin pasar por `number`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer

# --- listas -----------------------------------------------------------------------------


class ListaCrearRequest(BaseModel):
    """Cuerpo de `POST /precios/listas`. La lista nace activa y sin versiones."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    redondeo_multiplo: str
    redondeo_direccion: str


class ListaModificarRequest(BaseModel):
    """Cuerpo de `PUT /precios/listas/{lista_id}`: reemplaza nombre, redondeo y actividad."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    redondeo_multiplo: str
    redondeo_direccion: str
    activo: bool


class ListaResponse(BaseModel):
    """Una lista con su versión vigente (número, si la tiene) y si tiene un borrador.

    `version_vigente` es el número de la versión vigente al momento de la consulta (PRC-03);
    `tiene_borrador` dice si la lista tiene un borrador (D5: a lo sumo uno)."""

    id: UUID
    nombre: str
    redondeo_multiplo: Decimal
    redondeo_direccion: str
    activo: bool
    version_vigente: int | None
    tiene_borrador: bool
    creado_en: datetime
    actualizado_en: datetime

    @field_serializer("redondeo_multiplo")
    def _serializar_multiplo(self, valor: Decimal) -> str:
        return str(valor)


class RedondeoCategoriaResponse(BaseModel):
    id: UUID
    categoria_id: UUID
    categoria_nombre: str | None
    multiplo: Decimal
    direccion: str
    activo: bool

    @field_serializer("multiplo")
    def _serializar_multiplo(self, valor: Decimal) -> str:
        return str(valor)


class ListaDetalleResponse(ListaResponse):
    """El detalle de una lista: además de lo de `ListaResponse`, sus sobrescrituras de
    redondeo por categoría."""

    redondeos_categoria: list[RedondeoCategoriaResponse]


class ListasResponse(BaseModel):
    items: list[ListaResponse]


class ListaOpcionResponse(BaseModel):
    """Lectura reducida de una lista activa: identificador y nombre (`design.md` D12)."""

    id: UUID
    nombre: str


class ListaOpcionesResponse(BaseModel):
    items: list[ListaOpcionResponse]


# --- reglas de margen -------------------------------------------------------------------


class ReglaCrearRequest(BaseModel):
    """Cuerpo de `POST /precios/listas/{lista_id}/reglas`: `valor` es una fracción en string
    (30% = `"0.300000"`); `alcance_id` va solo con un alcance que no es `LISTA`."""

    model_config = ConfigDict(extra="forbid")

    tipo: str
    valor: str
    alcance_tipo: str
    alcance_id: UUID | None = None


class ReglaModificarRequest(BaseModel):
    """Cuerpo de `PUT /precios/listas/{lista_id}/reglas/{regla_id}`: tipo, valor y actividad;
    el alcance y la lista no cambian."""

    model_config = ConfigDict(extra="forbid")

    tipo: str
    valor: str
    activo: bool


class ReglaResponse(BaseModel):
    """Una regla con su alcance (tipo, entidad y nombre de la entidad), tipo, valor y
    actividad. `alcance_nombre` es nulo en el alcance `LISTA` (no tiene entidad)."""

    id: UUID
    lista_id: UUID
    alcance_tipo: str
    alcance_id: UUID | None
    alcance_nombre: str | None
    tipo: str
    valor: Decimal
    activo: bool
    creado_en: datetime
    actualizado_en: datetime

    @field_serializer("valor")
    def _serializar_valor(self, valor: Decimal) -> str:
        return str(valor)


class ReglasResponse(BaseModel):
    items: list[ReglaResponse]


# --- redondeo por categoría -------------------------------------------------------------


class RedondeoCategoriaDefinirRequest(BaseModel):
    """Cuerpo de `PUT /precios/listas/{lista_id}/redondeos-categoria/{categoria_id}`."""

    model_config = ConfigDict(extra="forbid")

    multiplo: str
    direccion: str
    activo: bool = True


# --- borrador, precios y versiones (change 13, grupos 7 y 8) --------------------------------


class ProductoSinPrecioResponse(BaseModel):
    """Un producto activo que el borrador no tiene y la causa (`SIN_PRESENTACION_DE_REFERENCIA`,
    `SIN_COSTO`, `SIN_REGLA`, `PRECIO_NO_POSITIVO`, o `SIN_CALCULAR` si hoy podría calcularse y
    hay que regenerar)."""

    producto_id: UUID
    producto_nombre: str | None
    causa: str


class GeneracionResponse(BaseModel):
    """Resultado de `LISTA_GENERAR_BORRADOR`: el borrador, cuántos precios tiene, los productos
    sin precio y cuántos precios llevan las señales de costo (D2, D3)."""

    version_id: UUID
    numero: int
    regenerado: bool
    cantidad_precios: int
    productos_sin_precio: list[ProductoSinPrecioResponse]
    precios_con_otra_regla_iva: int
    precios_con_costos_distintos: int


class PrecioFijarRequest(BaseModel):
    """Cuerpo de `PUT /precios/listas/{lista_id}/versiones/{version_id}/precios/{producto_id}`.

    `precio_final` es obligatorio y puede ser nulo: un importe en string lo fija a mano, `null`
    quita la marca manual y el precio vuelve a calcularse (D7). Un número JSON se rechaza
    (INV-03)."""

    model_config = ConfigDict(extra="forbid")

    precio_final: str | None


class PrecioFijadoResponse(BaseModel):
    """El precio que quedó en el borrador; `precio_final` es nulo si al quitar la marca manual
    el producto no pudo calcularse y quedó sin precio."""

    version_id: UUID
    producto_id: UUID
    precio_final: str | None
    manual: bool


class SenalesResponse(BaseModel):
    """Las señales de un precio del borrador (D2, D3, D7) y, si salió de un costo, de qué
    presentación."""

    sin_costo: bool
    margen_menor: bool
    costo_otra_regla_iva: bool
    costos_distintos_por_presentacion: bool
    presentacion_del_costo_id: UUID | None
    presentacion_del_costo_nombre: str | None


class PresentacionDeVentaResponse(BaseModel):
    """Nombre y unidades base de una presentación activa de venta del producto, para mostrar
    el precio por presentación (PRC-22). Sin costos ni precios."""

    nombre: str
    unidades_base: int


class PrecioDeVersionResponse(BaseModel):
    """Un precio de una versión. Los campos de costo (`costo_referencia`, `tipo_margen`,
    `valor_margen`, `precio_calculado`) van en nulo sin `VER_COSTOS` (D12). `relacion` y
    `precio_version_base` comparan con la versión base (PRC-17); `senales` solo en un
    borrador; `presentaciones` son las activas de venta del producto, de menos unidades a más.
    Importes, costos y márgenes viajan como string."""

    producto_id: UUID
    producto_nombre: str | None
    unidades_referencia: int
    precio_final: str
    manual: bool
    precio_version_base: str | None
    relacion: str | None
    senales: SenalesResponse | None
    presentaciones: list[PresentacionDeVentaResponse]
    costo_referencia: str | None
    tipo_margen: str | None
    valor_margen: str | None
    precio_calculado: str | None


class VersionResponse(BaseModel):
    """Una versión de lista con su estado almacenado (`BORRADOR`, `PUBLICADA`, `ANULADA`) y,
    si está publicada, el derivado de las fechas (`PROGRAMADA`, `VIGENTE`, `HISTORICA`; PRC-03).
    Los autores van con su nombre."""

    id: UUID
    lista_id: UUID
    numero: int
    estado: str
    estado_derivado: str | None
    vigencia_desde: datetime | None
    vigencia_hasta: datetime | None
    version_base_id: UUID | None
    generado_en: datetime | None
    creado_por_id: UUID
    creado_por_nombre: str | None
    creado_en: datetime
    publicado_por_id: UUID | None
    publicado_por_nombre: str | None
    publicado_en: datetime | None
    anulado_por_id: UUID | None
    anulado_por_nombre: str | None
    anulado_en: datetime | None


class PreciosDeVersionResponse(BaseModel):
    """Los precios de una versión paginados por cursor (`siguiente_cursor` es nulo en la
    última página)."""

    version: VersionResponse
    precios: list[PrecioDeVersionResponse]
    siguiente_cursor: str | None


class BorradorResponse(PreciosDeVersionResponse):
    """El borrador de una lista: sus precios y, aparte, los productos activos sin precio."""

    productos_sin_precio: list[ProductoSinPrecioResponse]


class PublicarRequest(BaseModel):
    """Cuerpo de `POST /precios/listas/{lista_id}/versiones/{version_id}/publicar`. Las
    vigencias son instantes con zona horaria; sin `vigencia_desde` rige el momento de la
    publicación y nunca puede ser anterior a él (D6)."""

    model_config = ConfigDict(extra="forbid")

    vigencia_desde: AwareDatetime | None = None
    vigencia_hasta: AwareDatetime | None = None


class VersionesResponse(BaseModel):
    """Las versiones de una lista, de la más nueva a la más antigua."""

    items: list[VersionResponse]


class PrecioVigenteResponse(BaseModel):
    """El precio de referencia de un producto en la versión vigente (string) y las unidades de
    referencia guardadas en el precio (entero, D1)."""

    producto_id: UUID
    precio_final: str
    unidades_referencia: int


class PreciosVigentesResponse(BaseModel):
    """`GET /precios/listas/{id}/vigente`: la versión vigente a un momento y los precios
    pedidos (todos los de la versión si no se pidió ningún producto). `productos_sin_precio`
    son los pedidos que la versión no tiene (PRC-10)."""

    version_id: UUID
    numero: int
    vigencia_desde: datetime
    vigencia_hasta: datetime | None
    precios: list[PrecioVigenteResponse]
    productos_sin_precio: list[UUID]


class ListaPredeterminadaDefinirRequest(BaseModel):
    """Cuerpo de `PUT /precios/lista-predeterminada`: la lista elegida, que tiene que estar
    activa. `organizacion_id` no se acepta: sale del token (INV-21)."""

    model_config = ConfigDict(extra="forbid")

    lista_id: UUID


class ListaPredeterminadaResponse(BaseModel):
    """La lista predeterminada de la organización (`01` §4), o todo en nulo si no tiene."""

    lista_id: UUID | None
    lista_nombre: str | None
    activa: bool | None
