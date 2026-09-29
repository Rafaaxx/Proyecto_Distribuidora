"""Punto de entrada de la aplicación FastAPI (`docs/02-arquitectura.md` §11)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api_v1 import dependencias, sistema
from app.api_v1 import router as api_v1_router
from app.core.access_log_middleware import AccessLogMiddleware
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import DomainError
from app.core.logging import configurar_logging
from app.core.request_id_middleware import RequestIdMiddleware

# Registro de comandos. Desde la enmienda de D9 (2026-09-29) `clientes/api.py`
# también importa `clientes.commands` (mismo criterio que `catalogo`/
# `proveedores`, cada una con su ruta de escritura dedicada); este import
# queda igual de explícito para que `Base.metadata`/el registro de tipos no
# dependan de que exista un `api.py` (mismo criterio que las líneas de abajo).
from app.modules.clientes import commands as clientes_commands  # noqa: F401

# Registro de modelos. Lo importa `clientes/api.py` al armar el router de
# `app.api_v1`, pero se deja explícito para que `Base.metadata` conozca la
# tabla sin depender de que exista un `api.py` (mismo criterio que
# `catalogo/api.py` y `proveedores/api.py` con los suyos).
from app.modules.clientes import models as clientes_models  # noqa: F401


def _domain_error_a_problem_details(request: Request, exc: Exception) -> JSONResponse:
    """Traduce cualquier `DomainError` a Problem Details (RFC 9457, `02`
    §11): `codigo` es el campo de dominio estable (`PERMISO_REQUERIDO`,
    etc.); nunca se filtra el detalle interno de la excepción más allá del
    mensaje ya pensado para el usuario (`02` §17/§18: ni contraseñas, ni
    PIN, ni tokens aparecen en un mensaje de error)."""
    assert isinstance(exc, DomainError)
    content: dict[str, Any] = {
        "type": "about:blank",
        "title": exc.mensaje,
        "status": exc.status_http,
        "codigo": exc.codigo,
        "instance": str(request.url.path),
    }
    # contrato-api.md P9 (aprobado 2026-09-24): errores puntuales de fila
    # (p.ej. `COSTO_INFORMAR`) agregan `fila` vía `DomainError.extension`.
    if exc.extension:
        content.update(exc.extension)
    return JSONResponse(
        status_code=exc.status_http,
        media_type="application/problem+json",
        content=content,
    )


def crear_app(settings: Settings) -> FastAPI:
    """Construye la aplicación con la configuración dada.

    Se recibe `Settings` en vez de leerla del entorno adentro, para poder
    levantar varias instancias en pruebas con configuraciones distintas.
    """
    configurar_logging(settings.log_level)

    app = FastAPI(title="Distribuidora API", version=settings.app_version)

    engine = crear_engine(settings.database_url)
    session_factory = crear_session_factory(engine)
    app.dependency_overrides[sistema._get_engine] = lambda: engine
    app.dependency_overrides[sistema._get_settings] = lambda: settings
    app.dependency_overrides[dependencias._get_settings] = lambda: settings
    app.dependency_overrides[dependencias._get_session_factory] = lambda: session_factory

    app.add_exception_handler(DomainError, _domain_error_a_problem_details)

    # El orden de agregado importa: Starlette envuelve en orden inverso, así
    # que el último agregado queda más externo. RequestIdMiddleware debe
    # correr antes que AccessLogMiddleware para que el request_id ya esté
    # en el contexto de log cuando se emite el registro de fin de petición.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(api_v1_router, prefix="/api/v1")

    return app


def crear_app_desde_entorno() -> FastAPI:
    """Punto de entrada usado por uvicorn: lee la configuración del entorno."""
    return crear_app(Settings())  # type: ignore[call-arg]


# `app` es lo que uvicorn importa (`uvicorn app.main:app`). Se construye solo
# si `DATABASE_URL` está disponible en el entorno o en un `.env`: así importar
# este módulo desde una prueba que arma su propia `Settings` (sin variables de
# entorno globales) no falla la colección de pruebas.
app: FastAPI | None
try:
    app = crear_app_desde_entorno()
except ValidationError:
    app = None
