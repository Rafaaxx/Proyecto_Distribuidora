"""Esquemas Pydantic de entrada y salida de `cobranzas` (change 17; `design.md` D2, D14).

Los importes viajan como string (INV-03, `CLAUDE.md` §4): un número JSON ya degradado por
`float` en el cliente se rechaza con 422.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.cobranzas.domain.cobranza import MAXIMO_OBSERVACION

_PATRON_DECIMAL = r"^-?\d+(\.\d+)?$"


class CobranzaMedioRequest(BaseModel):
    """Un medio de la cobranza (D2). `importe` como string estricto (INV-03)."""

    medio_pago_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    referencia: str | None = None


class CobranzaRegistrarRequest(BaseModel):
    """`POST /cobranzas`. `organizacion_id` nunca aparece (sale del token, INV-21/TR-08).
    `cobranza_id` lo genera quien registra (UUIDv7, `02` §9). `medios` no declara `min_length`:
    una lista vacía la rechaza el dominio con `MEDIOS_INVALIDOS` y su código estable, no un 422
    genérico de Pydantic (D2).

    Sin `extra="forbid"`: el endpoint arma el `contenido` del comando campo por campo, así que un
    campo extra del cuerpo se ignora y nunca llega al bus. Quien manda de verdad es
    `CobranzaRegistrarContenidoV1`, que sí lo prohíbe."""

    cobranza_id: UUID
    cliente_id: UUID
    importe: str = Field(pattern=_PATRON_DECIMAL)
    medios: list[CobranzaMedioRequest]
    observacion: str | None = Field(default=None, max_length=MAXIMO_OBSERVACION)


class CobranzaRegistrarResponse(BaseModel):
    """Sale de `comando.resultado`, no de una relectura: un reenvío idempotente del mismo
    `Operation-Id` devuelve exactamente lo mismo (INV-06). `saldo` es el saldo resultante del
    cliente (CC-04), que la pantalla muestra como "saldo después de la cobranza"; negativo es
    saldo a favor (COB-03). `jornada_id` es la jornada que recibió la cobranza (D8)."""

    cobranza_id: UUID
    estado: str
    importe: str
    saldo: str
    jornada_id: UUID | None


class CobranzaAnularRequest(BaseModel):
    """`POST /cobranzas/{id}/anulacion` (COB-05). `cobranza_id` va en la ruta y la organización
    sale del token (INV-21). La observación es opcional y de hasta 500 caracteres (D7)."""

    motivo_id: UUID
    observacion: str | None = Field(default=None, max_length=MAXIMO_OBSERVACION)


class CobranzaAnularResponse(BaseModel):
    """Sale de `comando.resultado` (INV-06). `saldo` es el saldo del cliente después de devolver
    el importe (CC-04); los importes viajan como string (INV-03)."""

    cobranza_id: UUID
    estado: str
    importe: str
    saldo: str


class CobranzaResumenResponse(BaseModel):
    """Una fila del listado (D14). Los importes viajan como string (INV-03)."""

    cobranza_id: UUID
    occurred_at: datetime
    cliente_id: UUID
    cliente_nombre: str | None
    importe: str
    estado: str
    origen: str
    venta_id: UUID | None
    usuario_id: UUID
    usuario_nombre: str | None
    jornada_id: UUID | None


class PaginaCobranzas(BaseModel):
    items: list[CobranzaResumenResponse]
    cursor_siguiente: str | None


class CobranzaMedioResponse(BaseModel):
    medio_pago_id: UUID
    medio_nombre: str | None
    importe: str
    referencia: str | None


class CobranzaAnulacionResponse(BaseModel):
    motivo_id: UUID
    motivo_nombre: str | None
    observacion: str | None
    usuario_id: UUID
    usuario_nombre: str | None
    anulada_en: datetime


class CobranzaObservacionResponse(BaseModel):
    """Una observación de sincronización de la cobranza (SYN-07). `detalle` es el JSON del
    detalle tal cual se guardó (línea, medio e importe en `MEDIO_INACTIVO` y
    `REFERENCIA_FALTANTE`)."""

    codigo: str
    estado: str
    detalle: dict[str, object] | None


class CobranzaDetalleResponse(CobranzaResumenResponse):
    observacion: str | None
    registered_at: datetime
    medios: list[CobranzaMedioResponse]
    anulacion: CobranzaAnulacionResponse | None
    observaciones: list[CobranzaObservacionResponse]
