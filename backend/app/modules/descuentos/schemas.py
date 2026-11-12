"""Esquemas de `descuentos` (change 16, grupo 8; `design.md` D17, D18, `Enfoque técnico`).

Los `*Request` son el CUERPO HTTP de las rutas de escritura de `api.py`, distintos de los
`*ContenidoV1` de `commands.py` (el contenido AUDITADO del comando que arma cada endpoint);
mismo criterio que `precios/schemas.py`.

El umbral, el porcentaje y el importe fijo viajan como **string** en ambos sentidos (INV-03,
`CLAUDE.md` §4): en la entrada se declaran `str`, así que un número JSON se rechaza (422) en vez de
convertirse a `float`; en la salida son `str(Decimal)` con los decimales de la columna
(`"20.0000"`, `"0.050000"`, `"1000.00"`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, StrictInt

TipoReglaApi = Literal["VOLUMEN_OPERACION", "VOLUMEN_ALCANCE"]
MedidaApi = Literal["CAJAS_EQUIVALENTES", "UNIDADES_BASE", "IMPORTE_BRUTO"]
OperadorApi = Literal["GTE", "GT"]
AccionTipoApi = Literal["PORCENTAJE", "IMPORTE_FIJO"]
TipoAlcanceApi = Literal["PRODUCTO", "CATEGORIA", "MARCA"]
EstadoReglaApi = Literal["BORRADOR", "ACTIVA", "PAUSADA", "VENCIDA"]


class AlcanceReglaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoAlcanceApi
    entidad_id: UUID


class ReglaDescuentoCrearRequest(BaseModel):
    """Cuerpo de `POST /descuentos/reglas`: la regla nace en `BORRADOR`. `prioridad` admite un
    decimal solo para que la ruta lo rechace con `PRIORIDAD_INVALIDA` (un número con coma no
    puede entrar al contenido de un comando)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo: TipoReglaApi
    medida: MedidaApi
    operador: OperadorApi
    umbral: str
    accion_tipo: AccionTipoApi
    accion_valor: str
    prioridad: StrictInt | StrictFloat
    acumulable: bool
    alcances: list[AlcanceReglaRequest] = []
    vigencia_desde: AwareDatetime | None = None
    vigencia_hasta: AwareDatetime | None = None


class ReglaDescuentoModificarRequest(BaseModel):
    """Cuerpo de `PUT /descuentos/reglas/{regla_id}`. Un borrador se reemplaza con los mismos
    campos del alta; una regla activada o pausada solo admite `vigencia_hasta` (`null` quita el
    fin). Los campos que no vienen no se envían al comando."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = None
    tipo: TipoReglaApi | None = None
    medida: MedidaApi | None = None
    operador: OperadorApi | None = None
    umbral: str | None = None
    accion_tipo: AccionTipoApi | None = None
    accion_valor: str | None = None
    prioridad: StrictInt | StrictFloat | None = None
    acumulable: bool | None = None
    alcances: list[AlcanceReglaRequest] | None = None
    vigencia_desde: AwareDatetime | None = None
    vigencia_hasta: AwareDatetime | None = None


class AlcanceReglaResponse(BaseModel):
    """Un alcance con el nombre de su entidad."""

    tipo: TipoAlcanceApi
    entidad_id: UUID
    nombre: str


class ReglaDescuentoResponse(BaseModel):
    """Una regla con su condición, acción, vigencia y alcances. `estado` es el que se informa:
    `VENCIDA` (derivado, no se almacena) para una regla activa o pausada cuya vigencia hasta ya
    pasó (`01` §18). Exactamente uno de `accion_porcentaje` y `accion_importe` no es nulo."""

    id: UUID
    nombre: str
    tipo: TipoReglaApi
    medida: MedidaApi
    operador: OperadorApi
    umbral: str
    accion_tipo: AccionTipoApi
    accion_porcentaje: str | None
    accion_importe: str | None
    prioridad: int
    acumulable: bool
    vigencia_desde: datetime | None
    vigencia_hasta: datetime | None
    estado: EstadoReglaApi
    alcances: list[AlcanceReglaResponse]
    creado_en: datetime
    actualizado_en: datetime


class ReglasDescuentoResponse(BaseModel):
    """Una página del listado de reglas, de la más nueva a la más vieja; `siguiente_cursor` es
    nulo en la última página."""

    items: list[ReglaDescuentoResponse]
    siguiente_cursor: str | None
