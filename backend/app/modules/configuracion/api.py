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

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api_v1.dependencias import get_session
from app.commands import registro
from app.commands.huella import ContenidoComando, calcular_huella
from app.commands.sobre import SobreComando, construir_sobre_online
from app.core.autenticacion import (
    ContextoAutenticado,
    EntradaComandoOnline,
    requiere_algun_permiso,
    requiere_comando_online,
    requiere_permiso,
    requiere_sesion,
)
from app.core.clock import Clock, SystemClock
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
    AlicuotaCrearRequest,
    AlicuotaModificarRequest,
    AlicuotaResponse,
    ListaMediosPago,
    ListaMediosPagoAdmin,
    ListaMotivos,
    ListaMotivosAdmin,
    MedioPagoAdminResponse,
    MedioPagoCrearRequest,
    MedioPagoModificarRequest,
    MedioPagoResponse,
    MotivoAdminResponse,
    MotivoCrearRequest,
    MotivoModificarRequest,
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
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO, PERMISO_REGISTRAR_COMPRA, PERMISO_MEDIOS_PAGO)),
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


# --- administración de motivos (change 20c, `design.md` D1, D2, D12) ---------------------------
#
# Escrituras por el bus (`MOTIVO_CREAR`, `MOTIVO_MODIFICAR`, solo `ONLINE`) y una lectura
# completa (activos e inactivos). Las tres exigen `ADMIN_CONFIGURACION`; la lectura de solo
# activos por ámbito (`GET /motivos`) no cambia. Nunca hay una ruta que borre un motivo.


def _preparar_comando(
    entrada: EntradaComandoOnline,
    *,
    tipo: str,
    contenido: dict[str, ContenidoComando],
    manejar: Callable[..., sync_service.ResultadoHandler],
) -> tuple[
    Clock, SobreComando, str, Callable[[registro.SesionDeHandler], sync_service.ResultadoHandler]
]:
    """Arma el sobre `ONLINE`, su huella y el cierre que ejecuta el handler. La ruta lo pasa a
    `sync_service.procesar_comando` (el bus abre y cierra la transacción)."""
    reloj = SystemClock()
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo=tipo,
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
        return manejar(sobre, contenido_validado, sesion=sesion_protegida, reloj=reloj)

    return reloj, sobre, huella, _ejecutar_handler


def _motivo_o_404(organizacion_id: UUID, motivo_id: UUID, sesion: Session) -> MotivoAdminResponse:
    motivo = configuracion_service.obtener_motivo(organizacion_id, motivo_id, sesion)
    if motivo is None:
        raise MedioPagoNoEncontradoError("El motivo no existe en esta organización.")
    return MotivoAdminResponse.model_validate(motivo)


@router.get("/motivos/todos", response_model=ListaMotivosAdmin)
def listar_motivos_todos(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
    ambito: str | None = None,
) -> ListaMotivosAdmin:
    if ambito is not None and ambito not in AMBITOS_MOTIVO:
        raise AmbitoInvalidoError(
            f"El ámbito {ambito!r} no es válido. Valores válidos: {', '.join(AMBITOS_MOTIVO)}."
        )
    motivos = configuracion_queries.listar_motivos_todos(contexto.organizacion_id, sesion, ambito)
    return ListaMotivosAdmin(items=[MotivoAdminResponse.model_validate(m) for m in motivos])


@router.post("/motivos", response_model=MotivoAdminResponse, status_code=201)
def crear_motivo(
    datos: MotivoCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> MotivoAdminResponse:
    reloj, sobre, huella, ejecutar = _preparar_comando(
        entrada,
        tipo="MOTIVO_CREAR",
        contenido={"ambito": datos.ambito, "nombre": datos.nombre},
        manejar=configuracion_commands.manejar_motivo_crear,
    )
    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=ejecutar
    )
    assert comando.resultado is not None
    motivo_id = UUID(str(comando.resultado["motivo_id"]))
    return _motivo_o_404(entrada.contexto.organizacion_id, motivo_id, sesion)


@router.put("/motivos/{motivo_id}", response_model=MotivoAdminResponse)
def modificar_motivo(
    motivo_id: UUID,
    datos: MotivoModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> MotivoAdminResponse:
    reloj, sobre, huella, ejecutar = _preparar_comando(
        entrada,
        tipo="MOTIVO_MODIFICAR",
        contenido={"motivo_id": str(motivo_id), "nombre": datos.nombre, "activo": datos.activo},
        manejar=configuracion_commands.manejar_motivo_modificar,
    )
    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=ejecutar
    )
    return _motivo_o_404(entrada.contexto.organizacion_id, motivo_id, sesion)


# --- administración de alícuotas (change 20c, `design.md` D1, D6 a D9) --------------------------
#
# Escrituras por el bus (`ALICUOTA_CREAR`, `ALICUOTA_MODIFICAR`, solo `ONLINE`,
# `ADMIN_CONFIGURACION`). La lectura `GET /alicuotas` (arriba) admite también
# `ADMIN_CONFIGURACION`. Nunca hay una ruta que borre una alícuota.


def _alicuota_o_404(organizacion_id: UUID, alicuota_id: UUID, sesion: Session) -> AlicuotaResponse:
    alicuota = configuracion_service.obtener_alicuota_por_id(organizacion_id, alicuota_id, sesion)
    if alicuota is None:
        raise MedioPagoNoEncontradoError("La alícuota no existe en esta organización.")
    sesion.refresh(alicuota)
    return AlicuotaResponse.model_validate(alicuota)


@router.post("/alicuotas", response_model=AlicuotaResponse, status_code=201)
def crear_alicuota(
    datos: AlicuotaCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> AlicuotaResponse:
    reloj, sobre, huella, ejecutar = _preparar_comando(
        entrada,
        tipo="ALICUOTA_CREAR",
        contenido={"nombre": datos.nombre, "valor": datos.valor},
        manejar=configuracion_commands.manejar_alicuota_crear,
    )
    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=ejecutar
    )
    assert comando.resultado is not None
    alicuota_id = UUID(str(comando.resultado["alicuota_id"]))
    return _alicuota_o_404(entrada.contexto.organizacion_id, alicuota_id, sesion)


@router.put("/alicuotas/{alicuota_id}", response_model=AlicuotaResponse)
def modificar_alicuota(
    alicuota_id: UUID,
    datos: AlicuotaModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_MEDIOS_PAGO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> AlicuotaResponse:
    reloj, sobre, huella, ejecutar = _preparar_comando(
        entrada,
        tipo="ALICUOTA_MODIFICAR",
        contenido={
            "alicuota_id": str(alicuota_id),
            "nombre": datos.nombre,
            "valor": datos.valor,
            "activo": datos.activo,
        },
        manejar=configuracion_commands.manejar_alicuota_modificar,
    )
    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=ejecutar
    )
    return _alicuota_o_404(entrada.contexto.organizacion_id, alicuota_id, sesion)
