"""Middleware de `request_id` (`docs/02-arquitectura.md` §17).

Toma el encabezado `X-Request-Id` si el cliente lo envía; si no, genera uno
nuevo. Lo propaga al contexto de log de toda la petición (vía `request_id_var`)
y lo devuelve en la respuesta, para que el cliente pueda correlacionar.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.ids import nuevo_id
from app.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(nuevo_id())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
