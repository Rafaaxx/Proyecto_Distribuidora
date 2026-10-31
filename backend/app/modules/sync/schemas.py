"""Esquemas Pydantic del lote de sincronización (change 04, grupo 8, tarea
8.6; `02` §6.2, §6.4).

`contenido` viaja como `dict[str, object]` a propósito: el cuerpo del
comando es de forma libre por tipo (cada handler valida el suyo con su
propio esquema Pydantic vía `app.commands.registro.validar_contenido`); acá
solo se exige que sea un objeto JSON, no una lista ni un escalar. No hay
`Any` sin justificar (`CLAUDE.md` §5): `object` documenta que el contenido
todavía no se interpreta en esta capa.

Descubrimiento (change 04, grupo 8): NO se usa `ContenidoComando`
(`app.commands.huella`) acá, aunque sería el tipo más preciso -- Pydantic
no puede generar el schema de ese alias recursivo declarado con `X = A |
list["X"] | dict[str, "X"]` (sintaxis de alias implícito, no `type X = ...`
de PEP 695): entra en `RecursionError` al resolverlo. La conversión a
`ContenidoComando` se hace con un `cast` documentado en `api.py`, en el
único punto donde el valor cruza de "lo que llegó por HTTP" a "lo que el
bus espera": un `dict[str, object]` que Pydantic decodificó de un cuerpo
JSON solo puede contener las mismas formas de dato que `ContenidoComando`
admite (JSON no tiene otras), así que el `cast` no esconde ninguna
posibilidad real, solo la limitación de Pydantic para expresarlo como tipo
estático."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAXIMO_COMANDOS_POR_LOTE = 50


class ItemLoteComandoRequest(BaseModel):
    """Un comando de la cola local (`02` §13.2 `cola`), tal como el
    dispositivo lo generó. `usuario_id`/`dispositivo_id` son los que
    declaró al generarlo -- el servidor los compara contra la sesión que
    sincroniza (`ColaAjenaError`, tarea 8.5), nunca los usa tal cual para
    construir el sobre sin esa verificación.

    `extra="forbid"` (change 18b, `design.md` D2): el lote no admite credenciales efímeras; un
    ítem que traiga `credenciales` (o cualquier campo ajeno) se rechaza como malformado, sin
    guardarlo ni registrar su valor."""

    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    tipo: str
    version: int
    modo: Literal["ONLINE", "OFFLINE"]
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    secuencia: int
    app_version: str
    contenido: dict[str, object] = Field(default_factory=dict)
    jornada_id: UUID | None = None


class LoteComandosRequest(BaseModel):
    """`02` §6.4: hasta 50 comandos por lote; un lote vacío es válido
    (tarea 8.2). `max_length=50` rechaza un lote de 51 con un 422 de
    Pydantic ANTES de que la ruta se ejecute -- ninguno de sus comandos
    llega a procesarse, que es exactamente lo que pide el escenario "Un
    lote que excede el máximo se rechaza entero"."""

    items: list[ItemLoteComandoRequest] = Field(
        default_factory=list, max_length=MAXIMO_COMANDOS_POR_LOTE
    )


class ResultadoItemLoteResponse(BaseModel):
    operation_id: UUID
    estado: str
    resultado: dict[str, object] | None
    error_codigo: str | None


class LoteComandosResponse(BaseModel):
    resultados: list[ResultadoItemLoteResponse]


# --- `GET /api/v1/sync/bootstrap` (change 21, `design.md` D9) ---------------------------------
# Una sola respuesta con secciones. Importes, porcentajes y alícuotas viajan como string decimal
# (`"31250.00"`, INV-03); las cantidades en unidad base, como enteros (INV-04). Ninguna sección
# lleva costos ni márgenes (D7), ni el PIN ni la contraseña de nadie (D8).


class UsuarioBootstrap(BaseModel):
    id: UUID
    nombre: str
    usuario: str


class JornadaBootstrap(BaseModel):
    id: UUID
    ubicacion_id: UUID
    ubicacion_nombre: str | None
    abierta_en: datetime


class NumeracionBootstrap(BaseModel):
    prefijo: str
    ultimo_correlativo: int


class SesionBootstrap(BaseModel):
    usuario: UsuarioBootstrap
    permisos: list[str]
    jornada: JornadaBootstrap
    numeracion: NumeracionBootstrap


class NotaBootstrap(BaseModel):
    domicilio: str | None
    telefono: str | None
    muestra_saldo: bool


class ConfiguracionBootstrap(BaseModel):
    organizacion_id: UUID
    nombre: str
    cuit: str | None
    moneda: str
    zona_horaria: str
    condicion_iva: str
    modo_impositivo: str
    politica_credito: str
    tolerancia_tipo: str | None
    tolerancia_valor: str | None
    permite_consumidor_final: bool | None
    consumidor_final_id: UUID | None
    estado_facturacion_default: str
    intentos_pin_max: int
    motivo_obligatorio_lista: bool
    nota: NotaBootstrap


class DescuentoManualBootstrap(BaseModel):
    habilitado: bool
    motivo_obligatorio: bool
    tiene_permiso: bool
    tope: str | None
    puede_autorizar: bool


class ContextoVentaBootstrap(BaseModel):
    descuento_manual: DescuentoManualBootstrap
    puede_superar_credito: bool


class MedioPagoBootstrap(BaseModel):
    id: UUID
    nombre: str
    requiere_referencia: bool


class MotivoBootstrap(BaseModel):
    id: UUID
    ambito: str
    nombre: str


class AlicuotaBootstrap(BaseModel):
    id: UUID
    nombre: str
    valor: str


class CatalogosBootstrap(BaseModel):
    medios_pago: list[MedioPagoBootstrap]
    motivos: list[MotivoBootstrap]
    alicuotas: list[AlicuotaBootstrap]


class PresentacionBootstrap(BaseModel):
    id: UUID
    nombre: str
    unidades_base: int
    es_referencia: bool


class ProductoBootstrap(BaseModel):
    id: UUID
    codigo: str
    nombre: str
    categoria_id: UUID
    marca_id: UUID | None
    alicuota_id: UUID
    alicuota_valor: str
    presentacion_referencia_id: UUID | None
    presentaciones: list[PresentacionBootstrap]


class CreditoBootstrap(BaseModel):
    limite: str | None
    politica: str
    tolerancia_tipo: str | None
    tolerancia_valor: str | None


class ClienteBootstrap(BaseModel):
    id: UUID
    codigo: str | None
    nombre: str
    razon_social: str | None
    documento_tipo: str | None
    documento_numero: str | None
    direccion: str
    telefono: str | None
    estado: str
    lista_precio_id: UUID | None
    es_consumidor_final: bool
    en_cartera: bool
    saldo: str
    credito: CreditoBootstrap


class PrecioBootstrap(BaseModel):
    producto_id: UUID
    precio_referencia: str
    unidades_referencia: int


class VersionBootstrap(BaseModel):
    id: UUID
    numero: int
    estado: str
    vigencia_desde: datetime
    vigencia_hasta: datetime | None
    precios: list[PrecioBootstrap]


class ListaBootstrap(BaseModel):
    id: UUID
    nombre: str
    es_predeterminada: bool
    versiones: list[VersionBootstrap]


class AlcanceBootstrap(BaseModel):
    tipo: str
    entidad_id: UUID


class ReglaDescuentoBootstrap(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    medida: str
    operador: str
    umbral: str
    accion_tipo: str
    accion_porcentaje: str | None
    accion_importe: str | None
    acumulable: bool
    prioridad: int
    vigencia_desde: datetime
    vigencia_hasta: datetime | None
    alcances: list[AlcanceBootstrap]


class StockBootstrap(BaseModel):
    producto_id: UUID
    cantidad_base: int


class AutorizadorBootstrap(BaseModel):
    """La derivación PBKDF2 del PIN de un autorizador (`02` §12.4, ADR-011): nunca el PIN."""

    id: UUID
    nombre: str
    permisos: list[str]
    pin_hash: str
    pin_sal: str
    iteraciones: int


class BootstrapResponse(BaseModel):
    generado_en: datetime
    sesion: SesionBootstrap
    configuracion: ConfiguracionBootstrap
    contexto_venta: ContextoVentaBootstrap | None
    catalogos: CatalogosBootstrap
    productos: list[ProductoBootstrap]
    clientes: list[ClienteBootstrap]
    listas: list[ListaBootstrap]
    reglas_descuento: list[ReglaDescuentoBootstrap]
    stock: list[StockBootstrap]
    autorizadores: list[AutorizadorBootstrap]
