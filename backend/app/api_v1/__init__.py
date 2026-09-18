"""Router agregador de la API versión 1 (`docs/02-arquitectura.md` §11).

Los módulos de negocio (`app/modules/<modulo>/api.py`) se agregan aquí a
medida que existan. Este change solo monta los endpoints de sistema.
"""

from fastapi import APIRouter

from app.api_v1 import sistema

router = APIRouter()
router.include_router(sistema.router)
