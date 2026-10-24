"""Esquemas HTTP de `ventas` (change 18a, tarea 7.8; `design.md` D2, D12).

La entrada refleja el contenido de `VENTA_CONFIRMAR` v1. `organizacion_id` nunca aparece (sale del
token, INV-21, TR-08): un campo extra del cuerpo se ignora y el endpoint arma el contenido campo
por campo; quien manda de verdad es `VentaConfirmarContenidoV1`, que prohíbe los extras. Los
importes viajan como string (INV-03) y las cantidades son enteros estrictos (INV-04).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr, StrictBool, StrictInt

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"


class DescuentoEsperadoRequest(BaseModel):
    """Un descuento de la línea tal como lo vio el usuario (change 18b, D1, D11): el servidor lo
    compara con el que calcula (`DESCUENTO_DIFIERE`)."""

    origen: Literal["AUTOMATICO", "MANUAL"]
    regla_id: UUID | None = None
    porcentaje: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    importe: str = Field(pattern=_PATRON_DECIMAL)


class VentaLineaRequest(BaseModel):
    """Una línea con lo que vio el usuario (D2). `descuento_manual` (fracción como texto) y
    `descuentos` (los esperados) son opcionales (change 18b, D1)."""

    linea_id: UUID
    producto_id: UUID
    presentacion_id: UUID
    cantidad: StrictInt
    lista_version_id: UUID
    precio_referencia: str = Field(pattern=_PATRON_DECIMAL)
    unidades_referencia: StrictInt
    importe_bruto: str = Field(pattern=_PATRON_DECIMAL)
    descuento_manual: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    descuentos: list[DescuentoEsperadoRequest] = Field(default_factory=list)


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


class CredencialPinRequest(BaseModel):
    """El PIN que un supervisor escribió para autorizar una excepción (change 18b, D2). Viaja
    fuera del contenido del comando: la ruta lo separa antes de armar la huella. `SecretStr` y
    ningún validador sobre el PIN (no puede citarlo en un mensaje de error)."""

    autorizador_id: UUID
    pin: SecretStr


class CreditoRequest(BaseModel):
    """El crédito de la venta (change 18b, D1): con conexión, si el usuario acepta el exceso
    (ADVERTIR) y quién autoriza (AUTORIZAR). La evaluación del dispositivo es solo del camino sin
    conexión (D7)."""

    acepta_exceso: StrictBool = False
    autorizador_id: UUID | None = None
    limite: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    saldo_considerado: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    politica: Literal["ADVERTIR", "AUTORIZAR", "BLOQUEAR"] | None = None
    resolucion: (
        Literal[
            "SIN_EXCESO",
            "ADVERTENCIA_ACEPTADA",
            "PERMISO_PROPIO",
            "PIN_SUPERVISOR",
            "TOLERANCIA_OFFLINE",
        ]
        | None
    ) = None


class VentaConfirmarRequest(BaseModel):
    """`POST /ventas`. `venta_id` y `numero` los genera quien origina la venta (`02` §9, D4).
    `credenciales` (de 0 a 2) NO forma parte del contenido ni de la huella (change 18b, D2).
    Los campos de descuentos y crédito son opcionales (D1)."""

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
    descuento_manual_general: str | None = Field(default=None, pattern=_PATRON_DECIMAL)
    motivo_descuento_id: UUID | None = None
    descuento_autorizador_id: UUID | None = None
    credito: CreditoRequest | None = None
    credenciales: list[CredencialPinRequest] = Field(default_factory=list, max_length=2)


def _texto(valor: UUID | None) -> str | None:
    return None if valor is None else str(valor)


def _linea_del_contenido(linea: VentaLineaRequest) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "linea_id": str(linea.linea_id),
        "producto_id": str(linea.producto_id),
        "presentacion_id": str(linea.presentacion_id),
        "cantidad": linea.cantidad,
        "lista_version_id": str(linea.lista_version_id),
        "precio_referencia": linea.precio_referencia,
        "unidades_referencia": linea.unidades_referencia,
        "importe_bruto": linea.importe_bruto,
    }
    if linea.descuento_manual is not None:
        cuerpo["descuento_manual"] = linea.descuento_manual
    if linea.descuentos:
        cuerpo["descuentos"] = [
            {
                "origen": descuento.origen,
                "regla_id": _texto(descuento.regla_id),
                "porcentaje": descuento.porcentaje,
                "importe": descuento.importe,
            }
            for descuento in linea.descuentos
        ]
    return cuerpo


def armar_contenido_de_venta(datos: VentaConfirmarRequest) -> dict[str, Any]:
    """El contenido de `VENTA_CONFIRMAR` v1 a partir del cuerpo de `POST /ventas`, campo por
    campo. Las `credenciales` (PIN) NO entran (change 18b, D2). Los campos opcionales de
    descuentos y crédito (D1) solo figuran si traen algo: un cuerpo sin ellos produce el mismo
    contenido, y por lo tanto la misma huella, que antes del change (INV-06, SYN-02)."""
    cobranza = datos.cobranza
    contenido: dict[str, Any] = {
        "venta_id": str(datos.venta_id),
        "numero": datos.numero,
        "cliente_id": str(datos.cliente_id),
        "ubicacion_id": _texto(datos.ubicacion_id),
        "lista_id": _texto(datos.lista_id),
        "lista_version_id": _texto(datos.lista_version_id),
        "motivo_lista_id": _texto(datos.motivo_lista_id),
        "lineas": [_linea_del_contenido(linea) for linea in datos.lineas],
        "total": datos.total,
        "cobranza": (
            None
            if cobranza is None
            else {
                "cobranza_id": str(cobranza.cobranza_id),
                "medios": [
                    {
                        "medio_pago_id": str(medio.medio_pago_id),
                        "importe": medio.importe,
                        "referencia": medio.referencia,
                    }
                    for medio in cobranza.medios
                ],
                "observacion": cobranza.observacion,
            }
        ),
    }
    if datos.descuento_manual_general is not None:
        contenido["descuento_manual_general"] = datos.descuento_manual_general
    if datos.motivo_descuento_id is not None:
        contenido["motivo_descuento_id"] = str(datos.motivo_descuento_id)
    if datos.descuento_autorizador_id is not None:
        contenido["descuento_autorizador_id"] = str(datos.descuento_autorizador_id)
    if datos.credito is not None:
        contenido["credito"] = datos.credito.model_dump(mode="json", exclude_none=True)
    return contenido


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


class VentaLineaDescuentoResponse(BaseModel):
    """Un descuento congelado de la línea (DSC-08). Porcentaje e importe como string (INV-03)."""

    origen: str
    regla_id: UUID | None
    regla_nombre: str | None
    porcentaje: str | None
    importe: str
    motivo_id: UUID | None
    motivo_nombre: str | None
    autorizador_id: UUID | None
    autorizador_nombre: str | None


class VentaCreditoResponse(BaseModel):
    """El snapshot de crédito congelado (CRE-10). Sin límite: límite, disponible y exceso nulos."""

    limite: str | None
    saldo_considerado: str | None
    disponible: str | None
    exceso: str | None
    politica: str | None
    resolucion: str
    autorizador_id: UUID | None
    autorizador_nombre: str | None


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
    descuentos: list[VentaLineaDescuentoResponse] = []


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
    credito: VentaCreditoResponse | None = None
    """Nulo en una venta anterior al change 18b."""


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
    categoria_id: UUID
    marca_id: UUID | None
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


class AlcanceDeReglaResponse(BaseModel):
    tipo: str
    entidad_id: UUID


class ReglaAplicableResponse(BaseModel):
    """Una regla activa y vigente tal como la necesita la gemela del motor (`motor.ts`, ADR-050).
    Importes y porcentajes como string (INV-03)."""

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
    alcances: list[AlcanceDeReglaResponse]


class DescuentosAplicablesResponse(BaseModel):
    """`GET /ventas/descuentos-aplicables` (change 18b, apply del 2026-10-23): por prioridad y
    antigüedad, las reglas vigentes ahora."""

    items: list[ReglaAplicableResponse]


class NumeracionResponse(BaseModel):
    """Prefijo del dispositivo de la sesión, último correlativo y el número que sigue (D4)."""

    prefijo: str
    ultimo_correlativo: int
    siguiente_numero: str


class DescuentoManualContextoResponse(BaseModel):
    """`tope`: fracción de texto (`"0.050000"` = 5 %), nula sin `DESCUENTO_MANUAL` (INV-03)."""

    habilitado: bool
    motivo_obligatorio: bool
    tiene_permiso: bool
    tope: str | None
    puede_autorizar: bool


class CreditoContextoResponse(BaseModel):
    puede_superar: bool


class MotivoContextoResponse(BaseModel):
    id: UUID
    nombre: str


class AutorizadorContextoResponse(BaseModel):
    """Nunca la derivación del PIN ni nada de ella (ADR-011)."""

    id: UUID
    nombre: str
    puede_autorizar_descuento: bool
    puede_superar_credito: bool


class ContextoDeVentaResponse(BaseModel):
    """`GET /ventas/contexto` (change 18b, D15)."""

    descuento_manual: DescuentoManualContextoResponse
    credito: CreditoContextoResponse
    motivos: list[MotivoContextoResponse]
    autorizadores: list[AutorizadorContextoResponse]


class CreditoParaVenderResponse(BaseModel):
    """`GET /ventas/credito` (change 18b, D16). Importes como string (INV-03); `limite` y
    `disponible` nulos = sin control."""

    cliente_id: UUID
    limite: str | None
    saldo: str
    disponible: str | None
    politica: str
    tolerancia_tipo: str | None
    tolerancia_valor: str | None


class VersionElegibleResponse(BaseModel):
    version_id: UUID
    numero: int
    estado: str
    vigencia_desde: datetime
    vigencia_hasta: datetime | None


class VersionesElegiblesResponse(BaseModel):
    items: list[VersionElegibleResponse]
