"""Registro de fin de petición (`docs/02-arquitectura.md` §17, §18).

Emite un registro con método, ruta, código de estado y duración al terminar
cada petición. Nunca incluye el cuerpo, los encabezados ni el detalle del
error: solo su tipo, para no filtrar credenciales, tokens ni cadenas de
conexión (`02` §18).
"""

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inicio = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duracion_ms = (time.perf_counter() - inicio) * 1000
            logger.error(
                "Error no manejado procesando la petición",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round(duracion_ms, 2),
                    "error_type": type(exc).__name__,
                },
            )
            raise

        duracion_ms = (time.perf_counter() - inicio) * 1000
        logger.info(
            "Petición procesada",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duracion_ms, 2),
            },
        )
        return response
