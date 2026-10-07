"""Esquemas de `clientes` (change 07, grupo 4; `design.md` D9, enmienda
2026-09-29).

Las cuatro escrituras de este módulo tienen ahora una ruta dedicada cada una
en `api.py` (D9, enmienda 2026-09-29: el despacho genérico de
`POST /sync/comandos` no ejecuta hoy ningún handler `ONLINE`, deuda
nominada al change 17). Los `*Request` de abajo son el CUERPO HTTP de esas
rutas, distintos de los `*ContenidoV1` de `commands.py` (el contenido
AUDITADO del comando que arma cada endpoint) -- mismo criterio que
`proveedores/schemas.py` y `catalogo/schemas.py`.

Los importes se declaran `Decimal` y salen por `field_serializer` como
**string**, igual que `CostoInformadoResponse` (`proveedores/schemas.py`):
INV-03 y `CLAUDE.md` §4 prohíben el `float` en el camino, y el frontend los
formatea desde el string con `lib/money.ts` sin convertirlos a número
(spec `administracion-de-clientes`, escenario "Guardar el crédito y ver el
resultado").

Los tres campos de crédito viajan en la lectura aunque el permiso de quien
consulta sea `GESTIONAR_CLIENTES` y no `GESTIONAR_CREDITO` (D3): la ficha
los muestra en solo lectura y quien no puede editarlos tiene que poder
**verlos** (spec `administracion-de-clientes`, escenario "La ficha muestra el
crédito en solo lectura"). Lo que separa los dos permisos es la escritura,
que va por el bus, no la lectura de la fila.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"


class ClienteResponse(BaseModel):
    """La fila de `cliente` tal como la expone la API.

    No expone `disponible`, `exceso` ni `política aplicada`: los calcula el
    módulo que confirma la venta resolviendo la herencia de la organización
    en el momento de evaluar (CRE-03, CRE-06, D8). Este change guarda el
    crédito como datos y no como resultado.

    Tampoco expone `actualizado_por_id`: no hay ninguna pantalla que lo
    consulte hoy, y agregarlo "porque el modelo lo tiene" sería superficie
    sin consumidor (D9, mismo criterio que `ProveedorResponse`).
    """

    id: UUID
    codigo: str | None
    nombre: str
    razon_social: str | None
    documento_tipo: str | None
    documento_numero: str | None
    direccion: str
    contacto: str
    telefono: str | None
    email: str | None
    lista_precio_id: UUID | None
    """La lista de precios asignada (CLI-01, change 13, D11); `None` = la predeterminada de
    la organización (PRC-20)."""
    limite_credito: Decimal | None
    politica_credito: str | None
    tolerancia_offline_tipo: str | None
    tolerancia_offline_valor: Decimal | None
    estado_facturacion_default: str | None
    es_consumidor_final: bool
    estado: str
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}

    @field_serializer("limite_credito", "tolerancia_offline_valor")
    def _serializar_decimal(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class PaginaClientes(BaseModel):
    """Paginada por cursor: el listado pagina por `(nombre, id)` y devuelve
    el cursor de la próxima página, no un offset (`02` §11; el listado no
    puede traer filas a Python para(sumarlas, `CLAUDE.md` §4)."""

    items: list[ClienteResponse]
    cursor_siguiente: str | None


class ClienteCrearRequest(BaseModel):
    """Cuerpo de `POST /clientes` (D9). Sin `estado` (nace `ACTIVO`, D7) y sin
    `es_consumidor_final` (solo lo pone `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`,
    CLI-03). `lista_precio_id` es la lista asignada, opcional (change 13, D11)."""

    nombre: str
    direccion: str
    contacto: str
    razon_social: str | None = None
    documento_tipo: str | None = None
    documento_numero: str | None = None
    telefono: str | None = None
    email: str | None = None
    codigo: str | None = None
    estado_facturacion_default: str | None = None
    lista_precio_id: UUID | None = None


class ClienteModificarRequest(BaseModel):
    """Cuerpo de `PUT /clientes/{cliente_id}` (D9). `PUT` reemplaza el estado
    completo de la ficha, igual que `ProveedorModificarRequest`: un opcional
    ausente o `null` se guarda como `null` (salvo `lista_precio_id`). `estado` es obligatorio porque
    modificar la ficha y cambiar el estado son la misma escritura (D7). Sin
    campos de crédito (D3) ni de consumidor final (CLI-03). `lista_precio_id` es la
    excepción (change 13, D11, ajuste A): ausente conserva la lista asignada, `null`
    explícito la quita y un id la asigna; se distingue con `model_fields_set`."""

    nombre: str
    direccion: str
    contacto: str
    estado: str
    razon_social: str | None = None
    documento_tipo: str | None = None
    documento_numero: str | None = None
    telefono: str | None = None
    email: str | None = None
    codigo: str | None = None
    estado_facturacion_default: str | None = None
    lista_precio_id: UUID | None = None


class ClienteCreditoModificarRequest(BaseModel):
    """Cuerpo de `PUT /clientes/{cliente_id}/credito` (D3, D9). Los tres
    campos son opcionales porque `None` significa HEREDAR de la organización
    (CRE-03, CRE-06, D8), no "dejar como está" -- misma semántica que
    `ClienteCreditoModificarContenidoV1` en `commands.py`. Los importes viajan
    como **string** estricto (mismo patrón que `CostoDelLoteRequest` en
    `proveedores/schemas.py`): la huella canónica del comando (`commands/
    huella.py`) no admite `Decimal`, así que el tipo se convierte recién en
    `ClienteCreditoModificarContenidoV1` al validar el contenido, nunca acá
    (`CLAUDE.md` §4, INV-03)."""

    limite_credito: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    politica_credito: str | None = None
    tolerancia_offline_tipo: str | None = None
    tolerancia_offline_valor: str | None = Field(default=None, pattern=_PATRON_DECIMAL)


class ConsumidorFinalConfigurarRequest(BaseModel):
    """Cuerpo de `POST /clientes/consumidor-final` (D4, ADR-029). Solo el
    nombre: la dirección y el contacto son genéricos y el cliente lo crea
    este mismo comando (nunca un `cliente_id` existente, CLI-03)."""

    nombre: str = "Consumidor final"


class ConsumidorFinalResponse(BaseModel):
    """`GET /clientes/consumidor-final` (spec `consumidor-final`,
    escenarios "Organización sin consumidor final" y "Organización con
    consumidor final").

    **No es 404 cuando la organización no lo habilitó**: 200 con
    `habilitado: false` y `cliente: null`. El 404 queda para el cliente de
    otra organización o inexistente por id en `GET /clientes/{cliente_id}`
    (INV-21), no para un estado legítimo de esta organización. Por eso este
    esquema NO declara `from_attributes`: se arma explícito en `api.py` y no
    sale de `model_validate` de una fila.
    """

    habilitado: bool
    cliente: ClienteResponse | None
