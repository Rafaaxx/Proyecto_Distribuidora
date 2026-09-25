"""Router agregador de la API versión 1 (`docs/02-arquitectura.md` §11).

Los módulos de negocio (`app/modules/<modulo>/api.py`) se agregan aquí a
medida que existan.
"""

from fastapi import APIRouter

from app.api_v1 import auth, sistema
from app.modules.catalogo import api as catalogo_api
from app.modules.configuracion import api as configuracion_api
from app.modules.identidad import api as identidad_api
from app.modules.proveedores import api as proveedores_api
from app.modules.sync import api as sync_api

router = APIRouter()
router.include_router(sistema.router)
router.include_router(auth.router)
router.include_router(identidad_api.router)
router.include_router(catalogo_api.router)
router.include_router(configuracion_api.router)
router.include_router(proveedores_api.router)
router.include_router(sync_api.router)
