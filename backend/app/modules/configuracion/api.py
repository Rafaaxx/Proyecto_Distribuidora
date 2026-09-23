"""Endpoints de lectura de `configuracion` (change 05, `design.md` D12;
tarea 9.6).

Única ruta por ahora: `GET /configuracion/alicuotas`, de solo lectura --
no pasa por el bus de comandos (el ratchet de cobertura del bus solo
alcanza escrituras, D12). `organizacion_id` sale del token
(`ContextoAutenticado`), nunca de la petición. Exige `GESTIONAR_CATALOGO`
(D12, Open Questions: mismo razonamiento que D9 de `catalogo` -- la
lectura se protege con el permiso de quien la consume; ADM y GES pueden
elegir alícuota al dar de alta productos).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.core.autenticacion import ContextoAutenticado, requiere_permiso
from app.modules.configuracion import queries as configuracion_queries
from app.modules.configuracion.repository import LIMITE_PAGINA_DEFAULT
from app.modules.configuracion.schemas import AlicuotaResponse, PaginaAlicuotas

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

PERMISO = "GESTIONAR_CATALOGO"


@router.get("/alicuotas", response_model=PaginaAlicuotas)
def listar_alicuotas(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> PaginaAlicuotas:
    items, cursor_siguiente = configuracion_queries.listar_alicuotas_paginado(
        contexto.organizacion_id, sesion, limite=limite, cursor=cursor
    )
    return PaginaAlicuotas(
        items=[AlicuotaResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )
