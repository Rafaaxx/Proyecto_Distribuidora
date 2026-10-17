"""Endpoints de lectura de `configuracion` (change 05, `design.md` D12;
tarea 9.6).

Rutas de lectura: `GET /configuracion/alicuotas` y las de medios y motivos, que no pasan por el
bus de comandos (el ratchet de cobertura del bus solo alcanza escrituras, D12). Desde el change
17b también las escrituras de medios de pago (`POST` y `PUT /configuracion/medios-pago`), que sí
pasan por el bus. `organizacion_id` sale del token
(`ContextoAutenticado`), nunca de la petición. Exige `GESTIONAR_CATALOGO`
(D12, Open Questions: mismo razonamiento que D9 de `catalogo` -- la
lectura se protege con el permiso de quien la consume; ADM y GES pueden
elegir alícuota al dar de alta productos).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    requiere_algun_permiso,
    requiere_comando_online,
    requiere_permiso,
    requiere_sesion,
)
from app.core.clock import SystemClock
from app.modules.configuracion import commands as configuracion_commands
from app.modules.configuracion import queries as configuracion_queries
from app.modules.configuracion import service as configuracion_service
from app.modules.configuracion.domain.valores import (
    AMBITOS_MOTIVO,
    AmbitoInvalidoError,
    MedioPagoNoEncontradoError,
)
from app.modules.configuracion.repository import LIMITE_PAGINA_DEFAULT
from app.modules.configuracion.schemas import (
    AlicuotaResponse,
    ListaMediosPago,
    ListaMediosPagoAdmin,
    ListaMotivos,
    MedioPagoAdminResponse,
    MedioPagoCrearRequest,
    MedioPagoModificarRequest,
    MedioPagoResponse,
    MotivoResponse,
    PaginaAlicuotas,
)
from app.modules.sync import service as sync_service

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

PERMISO = "GESTIONAR_CATALOGO"
PERMISO_MEDIOS_PAGO = "ADMIN_CONFIGURACION"  # change 17b, D1
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


# --- administración de medios de pago (change 17b, `design.md` D1, D2, D6) -----------------
#
# Escrituras por el bus (`MEDIO_PAGO_CREAR`, `MEDIO_PAGO_MODIFICAR`, solo `ONLINE`) y una
# lectura completa (activos e inactivos). Las tres exigen `ADMIN_CONFIGURACION`; la lectura de
# solo activos de arriba no cambia. Nunca hay una ruta que borre un medio (CAT-05, TR-06).


def _medio_o_404(
    organizacion_id: UUID, medio_pago_id: UUID, sesion: Session
) -> MedioPagoAdminResponse:
    medio = configuracion_service.obtener_medio_pago(organizacion_id, medio_pago_id, sesion)
    if medio is None:
        raise MedioPagoNoEncontradoError("El medio de pago no existe en esta organización.")
    return MedioPagoAdminResponse.model_validate(medio)


@router.get("/medios-pago/todos", response_model=ListaMediosPagoAdmin)
def listar_medios_pago_todos(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaMediosPagoAdmin:
    medios = configuracion_queries.listar_medios_pago_todos(contexto.organizacion_id, sesion)
    return ListaMediosPagoAdmin(
        items=[MedioPagoAdminResponse.model_validate(medio) for medio in medios]
    )


@router.post("/medios-pago", response_model=MedioPagoAdminResponse, status_code=201)
def crear_medio_pago(
    datos: MedioPagoCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> MedioPagoAdminResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "nombre": datos.nombre,
        "requiere_referencia": datos.requiere_referencia,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="MEDIO_PAGO_CREAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return configuracion_commands.manejar_medio_pago_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    medio_pago_id = UUID(str(comando.resultado["medio_pago_id"]))
    return _medio_o_404(entrada.contexto.organizacion_id, medio_pago_id, sesion)


@router.put("/medios-pago/{medio_pago_id}", response_model=MedioPagoAdminResponse)
def modificar_medio_pago(
    medio_pago_id: UUID,
    datos: MedioPagoModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> MedioPagoAdminResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "medio_pago_id": str(medio_pago_id),
        "nombre": datos.nombre,
        "requiere_referencia": datos.requiere_referencia,
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="MEDIO_PAGO_MODIFICAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entrada.contexto.organizacion_id,
        usuario_id=entrada.contexto.usuario_id,
        dispositivo_id=entrada.contexto.dispositivo_id,
        occurred_at=reloj.now(),
        secuencia=1,
        app_version="server",
        contenido=contenido,
    )
    huella = calcular_huella(sobre.contenido)
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)

    def _ejecutar_handler(
        sesion_protegida: registro.SesionDeHandler,
    ) -> sync_service.ResultadoHandler:
        return configuracion_commands.manejar_medio_pago_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return _medio_o_404(entrada.contexto.organizacion_id, medio_pago_id, sesion)


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
