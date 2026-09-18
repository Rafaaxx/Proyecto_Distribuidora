"""Logging estructurado en JSON (`docs/02-arquitectura.md` §17).

Cada registro es un único objeto JSON por línea. Los campos `operation_id`,
`organizacion_id`, `usuario_id` y `dispositivo_id` quedan previstos en el
formato pero ausentes (`null`) hasta que existan sesión (change 03) y bus
de comandos (change 04). Nunca se registran contraseñas, PIN ni tokens
(`02` §17, §18): este formateador no inspecciona el contenido de mensajes
o excepciones para redactar secretos — es responsabilidad de quien llama
al logger no pasarlos como argumento o mensaje.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, ClassVar

# Contexto de la petición HTTP en curso, propagado a cada registro emitido
# durante su procesamiento (`docs/02-arquitectura.md` §17).
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Campos previstos por §17 que todo registro declara, aunque estén vacíos
# hasta que exista sesión o comando asociado.
_CAMPOS_DE_CONTEXTO_PREVISTOS = (
    "operation_id",
    "organizacion_id",
    "usuario_id",
    "dispositivo_id",
)

# Atributos propios de logging.LogRecord que no son contexto de negocio y
# no deben duplicarse en la salida JSON.
_ATRIBUTOS_ESTANDAR = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)


class JsonFormatter(logging.Formatter):
    """Formatea cada `LogRecord` como un único objeto JSON por línea."""

    campos_previstos: ClassVar[tuple[str, ...]] = _CAMPOS_DE_CONTEXTO_PREVISTOS

    def format(self, record: logging.LogRecord) -> str:
        datos: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        for campo in self.campos_previstos:
            datos[campo] = getattr(record, campo, None)

        for clave, valor in record.__dict__.items():
            if clave in _ATRIBUTOS_ESTANDAR or clave in datos:
                continue
            datos[clave] = valor

        if record.exc_info:
            datos["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None

        return json.dumps(datos, default=str, ensure_ascii=False)


class RequestIdFilter(logging.Filter):
    """Inyecta el `request_id` de la petición en curso en cada registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


def configurar_logging(nivel: str = "INFO") -> None:
    """Configura el logger raíz para emitir JSON estructurado por línea."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(nivel)
