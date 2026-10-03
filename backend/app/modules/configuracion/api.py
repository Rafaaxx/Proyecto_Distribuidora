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
from app.core.autenticacion import (
    ContextoAutenticado,
    requiere_algun_permiso,
    requiere_sesion,
)
from app.modules.configuracion import queries as configuracion_queries
from app.modules.configuracion import service as configuracion_service
from app.modules.configuracion.domain.valores import AMBITOS_MOTIVO, AmbitoInvalidoError
from app.modules.configuracion.repository import LIMITE_PAGINA_DEFAULT
from app.modules.configuracion.schemas import (
    AlicuotaResponse,
    ListaMediosPago,
    ListaMotivos,
    MedioPagoResponse,
    MotivoResponse,
    PaginaAlicuotas,
)

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

PERMISO = "GESTIONAR_CATALOGO"
# La vista previa de la compra necesita la alícuota del producto (corolario de D17).
PERMISO_REGISTRAR_COMPRA = "REGISTRAR_COMPRA"


@router.get("/alicuotas", response_model=PaginaAlicuotas)
def listar_alicuotas(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_algun_permiso(PERMISO, PERMISO_REGISTRAR_COMPRA))
    ],
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


# --- medios de pago y motivos (change 11, `design.md` D2, D8, D14) -----------------------
#
# Cualquier usuario autenticado de la organización puede leerlos (D14): son catálogos que
# consumen las pantallas de compras, cobranzas y anulaciones, cada una con su propio
# permiso de negocio. Por eso estas dos rutas NO declaran `requiere_permiso` y están en la
# lista de exenciones del ratchet de permiso por ruta; sí exigen una sesión válida y
# habilitada. `organizacion_id` sale del token (INV-21).


@router.get("/medios-pago", response_model=ListaMediosPago)
def listar_medios_pago(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_sesion)],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaMediosPago:
    medios = configuracion_service.listar_medios_pago_activos(contexto.organizacion_id, sesion)
    return ListaMediosPago(
        items=[
            MedioPagoResponse.model_validate(medio)
            for medio in sorted(medios, key=lambda medio: medio.nombre)
        ]
    )


@router.get("/motivos", response_model=ListaMotivos)
def listar_motivos(
    ambito: str,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_sesion)],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaMotivos:
    if ambito not in AMBITOS_MOTIVO:
        raise AmbitoInvalidoError(
            f"El ámbito {ambito!r} no es válido. Valores válidos: {', '.join(AMBITOS_MOTIVO)}."
        )
    motivos = configuracion_service.listar_motivos_por_ambito(
        contexto.organizacion_id, sesion, ambito
    )
    return ListaMotivos(
        items=[
            MotivoResponse.model_validate(motivo)
            for motivo in sorted(motivos, key=lambda motivo: motivo.nombre)
        ]
    )
