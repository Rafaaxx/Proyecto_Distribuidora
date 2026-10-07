"""Endpoints de `precios` (change 13, grupo 5; `design.md` D8, D9, D12, `Enfoque técnico`).

Cinco escrituras y cinco lecturas bajo `/api/v1/precios`. Las escrituras tienen cada una su
ruta dedicada, mismo criterio que `clientes/api.py` y `proveedores/api.py`: declaran
`requiere_comando_online` (exige `Operation-Id`, SYN-01/TR-07) y delegan en
`sync_service.procesar_comando`. Cada función de ruta referencia `procesar_comando` ella
misma (no a través de un auxiliar): es lo que el ratchet de cobertura del bus inspecciona.

- `POST /precios/listas` (`LISTA_PRECIO_CREAR`) y `PUT /precios/listas/{lista_id}`
  (`LISTA_PRECIO_MODIFICAR`).
- `POST /precios/listas/{lista_id}/reglas` (`REGLA_MARGEN_CREAR`) y
  `PUT /precios/listas/{lista_id}/reglas/{regla_id}` (`REGLA_MARGEN_MODIFICAR`).
- `PUT /precios/listas/{lista_id}/redondeos-categoria/{categoria_id}`
  (`REDONDEO_CATEGORIA_DEFINIR`): `PUT` porque definir de nuevo la misma categoría actualiza
  la existente (a lo sumo una sobrescritura por lista y categoría).

Permisos (`01` §19, `design.md` D12): las escrituras exigen `GESTIONAR_LISTAS`; las lecturas
de listas, detalle y reglas, `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`; la lectura reducida de
listas activas (`/precios/listas/opciones`), además `GESTIONAR_CLIENTES` o
`ADMIN_CONFIGURACION`. **`/listas/opciones` se declara ANTES que `/listas/{lista_id}`**: si no,
FastAPI intenta interpretar `opciones` como un UUID y responde 422 (mismo criterio que
`/proveedores/opciones`).

`organizacion_id` sale siempre del token, nunca de la petición (INV-02, INV-21); un recurso de
otra organización responde 404, no 403 (`CLAUDE.md` §4).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel
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
)
from app.core.clock import Clock, SystemClock
from app.modules.identidad import service as identidad_service
from app.modules.precios import commands as precios_commands
from app.modules.precios import queries
from app.modules.precios.schemas import (
    BorradorResponse,
    GeneracionResponse,
    ListaCrearRequest,
    ListaDetalleResponse,
    ListaModificarRequest,
    ListaOpcionesResponse,
    ListaPredeterminadaDefinirRequest,
    ListaPredeterminadaResponse,
    ListaResponse,
    ListasResponse,
    PrecioFijadoResponse,
    PrecioFijarRequest,
    PreciosDeVersionResponse,
    PreciosVigentesResponse,
    PublicarRequest,
    RedondeoCategoriaDefinirRequest,
    RedondeoCategoriaResponse,
    ReglaCrearRequest,
    ReglaModificarRequest,
    ReglaResponse,
    ReglasResponse,
    VersionesResponse,
    VersionResponse,
)
from app.modules.sync import service as sync_service

PERMISO_GESTIONAR_LISTAS = "GESTIONAR_LISTAS"
PERMISO_PUBLICAR_LISTAS = "PUBLICAR_LISTAS"
PERMISO_GESTIONAR_CLIENTES = "GESTIONAR_CLIENTES"
PERMISO_ADMIN_CONFIGURACION = "ADMIN_CONFIGURACION"
PERMISO_VER_COSTOS = "VER_COSTOS"

router = APIRouter(prefix="/precios", tags=["precios"])


def _preparar(
    entrada: EntradaComandoOnline, tipo: str, contenido: dict[str, ContenidoComando], reloj: Clock
) -> tuple[SobreComando, str, BaseModel]:
    """El sobre del comando, su huella y el contenido validado contra el esquema del handler
    registrado: lo común a las cinco escrituras. Quien llama pasa los tres a
    `sync_service.procesar_comando`."""
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
    handler_registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(handler_registrado, sobre.contenido)
    return sobre, calcular_huella(sobre.contenido), contenido_validado


# --- escrituras ---------------------------------------------------------------------------


@router.post("/listas", response_model=ListaResponse, status_code=201)
def crear_lista(
    datos: ListaCrearRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "LISTA_PRECIO_CREAR",
        {
            "nombre": datos.nombre,
            "redondeo_multiplo": datos.redondeo_multiplo,
            "redondeo_direccion": datos.redondeo_direccion,
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_precio_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return queries.obtener_lista(
        entrada.contexto.organizacion_id,
        UUID(str(comando.resultado["lista_id"])),
        sesion,
        ahora=reloj.now(),
    )


@router.put("/listas/{lista_id}", response_model=ListaResponse)
def modificar_lista(
    lista_id: UUID,
    datos: ListaModificarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "LISTA_PRECIO_MODIFICAR",
        {
            "lista_id": str(lista_id),
            "nombre": datos.nombre,
            "redondeo_multiplo": datos.redondeo_multiplo,
            "redondeo_direccion": datos.redondeo_direccion,
            "activo": datos.activo,
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_precio_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_lista(
        entrada.contexto.organizacion_id, lista_id, sesion, ahora=reloj.now()
    )


@router.post("/listas/{lista_id}/reglas", response_model=ReglaResponse, status_code=201)
def crear_regla(
    lista_id: UUID,
    datos: ReglaCrearRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "REGLA_MARGEN_CREAR",
        {
            "lista_id": str(lista_id),
            "tipo": datos.tipo,
            "valor": datos.valor,
            "alcance_tipo": datos.alcance_tipo,
            "alcance_id": None if datos.alcance_id is None else str(datos.alcance_id),
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_regla_margen_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return queries.obtener_regla(
        entrada.contexto.organizacion_id,
        lista_id,
        UUID(str(comando.resultado["regla_id"])),
        sesion,
    )


@router.put("/listas/{lista_id}/reglas/{regla_id}", response_model=ReglaResponse)
def modificar_regla(
    lista_id: UUID,
    regla_id: UUID,
    datos: ReglaModificarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglaResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "REGLA_MARGEN_MODIFICAR",
        {
            "lista_id": str(lista_id),
            "regla_id": str(regla_id),
            "tipo": datos.tipo,
            "valor": datos.valor,
            "activo": datos.activo,
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_regla_margen_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_regla(entrada.contexto.organizacion_id, lista_id, regla_id, sesion)


@router.put(
    "/listas/{lista_id}/redondeos-categoria/{categoria_id}",
    response_model=RedondeoCategoriaResponse,
)
def definir_redondeo_de_categoria(
    lista_id: UUID,
    categoria_id: UUID,
    datos: RedondeoCategoriaDefinirRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> RedondeoCategoriaResponse:
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "REDONDEO_CATEGORIA_DEFINIR",
        {
            "lista_id": str(lista_id),
            "categoria_id": str(categoria_id),
            "multiplo": datos.multiplo,
            "direccion": datos.direccion,
            "activo": datos.activo,
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_redondeo_categoria_definir(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_redondeo_de_categoria(
        entrada.contexto.organizacion_id, lista_id, categoria_id, sesion
    )


# --- lecturas -----------------------------------------------------------------------------


@router.get("/listas", response_model=ListasResponse)
def listar_listas(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListasResponse:
    """Las listas de la organización con su redondeo, su actividad, su versión vigente (si la
    tiene) y si tienen un borrador. Los múltiplos viajan como string."""
    return queries.listar_listas(contexto.organizacion_id, sesion, ahora=SystemClock().now())


@router.get("/listas/opciones", response_model=ListaOpcionesResponse)
def listar_opciones_de_listas(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(
            requiere_algun_permiso(
                PERMISO_GESTIONAR_LISTAS,
                PERMISO_PUBLICAR_LISTAS,
                PERMISO_GESTIONAR_CLIENTES,
                PERMISO_ADMIN_CONFIGURACION,
            )
        ),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaOpcionesResponse:
    """Lectura reducida de las listas activas (identificador y nombre) para los selectores
    de la ficha del cliente y de la configuración (`design.md` D12)."""
    return queries.listar_opciones_de_listas(contexto.organizacion_id, sesion)


@router.get("/listas/{lista_id}", response_model=ListaDetalleResponse)
def obtener_lista(
    lista_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaDetalleResponse:
    """El detalle de una lista con sus sobrescrituras de redondeo por categoría. 404 para una
    lista de otra organización (INV-21, SEG-07)."""
    return queries.obtener_detalle_de_lista(
        contexto.organizacion_id, lista_id, sesion, ahora=SystemClock().now()
    )


@router.get("/listas/{lista_id}/reglas", response_model=ReglasResponse)
def listar_reglas(
    lista_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ReglasResponse:
    """Las reglas de una lista con su alcance (tipo, entidad y nombre de la entidad), tipo,
    valor como string y actividad. 404 para una lista de otra organización."""
    return queries.listar_reglas(contexto.organizacion_id, lista_id, sesion)


# --- borrador: generar, fijar precio y consultar (change 13, grupo 7) ------------------------


@router.post("/listas/{lista_id}/borrador", response_model=GeneracionResponse)
def generar_borrador(
    lista_id: UUID,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> GeneracionResponse:
    """`LISTA_GENERAR_BORRADOR`: crea el borrador de la lista o regenera el que tiene (un
    solo borrador por lista, D5), conservando los precios manuales. Informa cuántos precios
    tiene y los productos sin precio con su causa."""
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada, "LISTA_GENERAR_BORRADOR", {"lista_id": str(lista_id)}, reloj
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_generar_borrador(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return queries.respuesta_de_generacion(
        entrada.contexto.organizacion_id, comando.resultado, sesion
    )


@router.put(
    "/listas/{lista_id}/versiones/{version_id}/precios/{producto_id}",
    response_model=PrecioFijadoResponse,
)
def fijar_precio_manual(
    lista_id: UUID,
    version_id: UUID,
    producto_id: UUID,
    datos: PrecioFijarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> PrecioFijadoResponse:
    """`LISTA_BORRADOR_PRECIO_FIJAR`: fija a mano el precio de un producto en el borrador, o
    -con `precio_final` nulo- quita la marca manual y lo vuelve a calcular (D7). `PUT` porque
    fijar de nuevo el mismo producto reemplaza su precio."""
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "LISTA_BORRADOR_PRECIO_FIJAR",
        {
            "lista_id": str(lista_id),
            "version_id": str(version_id),
            "producto_id": str(producto_id),
            "precio_final": datos.precio_final,
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_borrador_precio_fijar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    assert comando.resultado is not None
    return queries.respuesta_de_precio_fijado(comando.resultado)


def _tiene_ver_costos(contexto: ContextoAutenticado, sesion: Session) -> bool:
    permisos = identidad_service.listar_permisos_del_usuario(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    return PERMISO_VER_COSTOS in permisos


@router.get("/listas/{lista_id}/borrador", response_model=BorradorResponse)
def obtener_borrador(
    lista_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BorradorResponse:
    """El borrador de la lista: sus precios paginados por cursor (con el precio de la versión
    base, la relación con ella y las señales) y, aparte, los productos sin precio con su
    causa. El costo de referencia, el margen y el precio calculado solo viajan con
    `VER_COSTOS` (D12); sin él van en nulo. 404 si la lista es ajena o no tiene borrador."""
    return queries.obtener_borrador(
        contexto.organizacion_id,
        lista_id,
        sesion,
        ver_costos=_tiene_ver_costos(contexto, sesion),
        limite=limite,
        cursor=cursor,
    )


# --- versiones: publicar, anular y consultar (change 13, grupo 8) -----------------------------


@router.post("/listas/{lista_id}/versiones/{version_id}/publicar", response_model=VersionResponse)
def publicar_version(
    lista_id: UUID,
    version_id: UUID,
    datos: PublicarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_PUBLICAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> VersionResponse:
    """`LISTA_PUBLICAR`: publica el borrador con su vigencia (PRC-02). Sin `vigencia_desde`
    rige desde el momento de la publicación; nunca puede ser anterior a él (D6). Exige
    `PUBLICAR_LISTAS` (PRC-06)."""
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "LISTA_PUBLICAR",
        {
            "lista_id": str(lista_id),
            "version_id": str(version_id),
            "vigencia_desde": (
                None if datos.vigencia_desde is None else datos.vigencia_desde.isoformat()
            ),
            "vigencia_hasta": (
                None if datos.vigencia_hasta is None else datos.vigencia_hasta.isoformat()
            ),
        },
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_publicar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_version(
        entrada.contexto.organizacion_id, lista_id, version_id, sesion, ahora=reloj.now()
    )


@router.post("/listas/{lista_id}/versiones/{version_id}/anular", response_model=VersionResponse)
def anular_version(
    lista_id: UUID,
    version_id: UUID,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_PUBLICAR_LISTAS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> VersionResponse:
    """`LISTA_ANULAR_VERSION`: anula una versión publicada cuya vigencia aún no comenzó
    (PRC-05). Sus precios no se borran ni cambian. Exige `PUBLICAR_LISTAS`."""
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "LISTA_ANULAR_VERSION",
        {"lista_id": str(lista_id), "version_id": str(version_id)},
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_anular_version(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_version(
        entrada.contexto.organizacion_id, lista_id, version_id, sesion, ahora=reloj.now()
    )


@router.get("/listas/{lista_id}/versiones", response_model=VersionesResponse)
def listar_versiones(
    lista_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> VersionesResponse:
    """Las versiones de la lista, de la más nueva a la más antigua, con su estado almacenado
    y derivado (`PROGRAMADA`, `VIGENTE`, `HISTORICA`), sus vigencias y sus autores."""
    return queries.listar_versiones(
        contexto.organizacion_id, lista_id, sesion, ahora=SystemClock().now()
    )


@router.get(
    "/listas/{lista_id}/versiones/{version_id}/precios", response_model=PreciosDeVersionResponse
)
def listar_precios_de_version(
    lista_id: UUID,
    version_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PreciosDeVersionResponse:
    """Los precios de cualquier versión -también histórica o anulada- paginados por cursor.
    Los campos de costo solo viajan con `VER_COSTOS` (D12)."""
    return queries.obtener_precios_de_version(
        contexto.organizacion_id,
        lista_id,
        version_id,
        sesion,
        ahora=SystemClock().now(),
        ver_costos=_tiene_ver_costos(contexto, sesion),
        limite=limite,
        cursor=cursor,
    )


@router.get("/listas/{lista_id}/vigente", response_model=PreciosVigentesResponse)
def obtener_precios_vigentes(
    lista_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    momento: AwareDatetime | None = None,
    producto_id: Annotated[list[UUID] | None, Query()] = None,
) -> PreciosVigentesResponse:
    """La versión vigente de la lista a `momento` (ahora si se omite; con zona horaria) y sus
    precios de referencia con las unidades de referencia de cada precio (PRC-20, D1). Con
    `producto_id` repetido solo esos productos, y los que la versión no tiene van en
    `productos_sin_precio`. Sin versión vigente, 409 `LISTA_SIN_VERSION_VIGENTE`."""
    return queries.obtener_precios_vigentes(
        contexto.organizacion_id,
        lista_id,
        sesion,
        momento=SystemClock().now() if momento is None else momento,
        producto_ids=producto_id,
    )


@router.put("/lista-predeterminada", response_model=ListaPredeterminadaResponse)
def definir_lista_predeterminada(
    datos: ListaPredeterminadaDefinirRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_ADMIN_CONFIGURACION))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaPredeterminadaResponse:
    """`LISTA_PRECIO_PREDETERMINADA_DEFINIR`: define la lista de precios predeterminada de la
    organización (solo una lista activa, PRC-20). Exige `ADMIN_CONFIGURACION`."""
    reloj = SystemClock()
    sobre, huella, contenido_validado = _preparar(
        entrada,
        "LISTA_PRECIO_PREDETERMINADA_DEFINIR",
        {"lista_id": str(datos.lista_id)},
        reloj,
    )

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return precios_commands.manejar_lista_precio_predeterminada_definir(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return queries.obtener_lista_predeterminada(entrada.contexto.organizacion_id, sesion)


@router.get("/lista-predeterminada", response_model=ListaPredeterminadaResponse)
def obtener_lista_predeterminada(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(
            requiere_algun_permiso(
                PERMISO_ADMIN_CONFIGURACION, PERMISO_GESTIONAR_LISTAS, PERMISO_PUBLICAR_LISTAS
            )
        ),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ListaPredeterminadaResponse:
    """La lista predeterminada de la organización, o todo en nulo si no definió una. Se lee
    con `ADMIN_CONFIGURACION`, `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS` (D11)."""
    return queries.obtener_lista_predeterminada(contexto.organizacion_id, sesion)
