"""Punto de entrada de la aplicación FastAPI (`docs/02-arquitectura.md` §11)."""

from fastapi import FastAPI
from pydantic import ValidationError

from app.api_v1 import router as api_v1_router
from app.api_v1 import sistema
from app.core.access_log_middleware import AccessLogMiddleware
from app.core.config import Settings
from app.core.db import crear_engine
from app.core.logging import configurar_logging
from app.core.request_id_middleware import RequestIdMiddleware


def crear_app(settings: Settings) -> FastAPI:
    """Construye la aplicación con la configuración dada.

    Se recibe `Settings` en vez de leerla del entorno adentro, para poder
    levantar varias instancias en pruebas con configuraciones distintas.
    """
    configurar_logging(settings.log_level)

    app = FastAPI(title="Distribuidora API", version=settings.app_version)

    engine = crear_engine(settings.database_url)
    app.dependency_overrides[sistema._get_engine] = lambda: engine
    app.dependency_overrides[sistema._get_settings] = lambda: settings

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
