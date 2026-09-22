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

from pydantic import BaseModel, Field

MAXIMO_COMANDOS_POR_LOTE = 50


class ItemLoteComandoRequest(BaseModel):
    """Un comando de la cola local (`02` §13.2 `cola`), tal como el
    dispositivo lo generó. `usuario_id`/`dispositivo_id` son los que
    declaró al generarlo -- el servidor los compara contra la sesión que
    sincroniza (`ColaAjenaError`, tarea 8.5), nunca los usa tal cual para
    construir el sobre sin esa verificación."""

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
