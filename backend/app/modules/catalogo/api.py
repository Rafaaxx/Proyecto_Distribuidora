"""Endpoints de negocio de `catalogo` (change 05, grupo 9, `design.md` D4,
D9; tareas 9.1-9.3).

Los nueve endpoints de escritura declaran `requiere_comando_online
("GESTIONAR_CATALOGO")` (exige el encabezado `Operation-Id`, SYN-01/TR-07) y
delegan en `sync_service.procesar_comando`, igual que `identidad/api.py`
(`CLAUDE.md` §4: "Toda escritura de negocio pasa por el bus de comandos").
El import de `app.modules.catalogo.commands` (sin uso directo en este
archivo) puebla el registro de handlers al arrancar la aplicación, igual
que el de `identidad.commands` en `identidad/api.py` -- sin él, los nueve
tipos de catálogo serían tipos "nunca importados" (`app/commands/registro.py`).

A diferencia de `identidad/api.py`, los handlers de catálogo NUNCA
devuelven `"RECHAZADO"` (`commands.py`, D6): lanzan `DomainError` (incluida
`RecursoNoEncontradoError`, 404) directamente, y el manejador genérico de
`DomainError` (`app/main.py`) la traduce a Problem Details con su `codigo`
estable -- ninguna ruta de acá necesita comprobar `comando.estado`.

Las lecturas (tarea 9.2, `design.md` D9: "sin permiso nuevo") exigen el
MISMO permiso `GESTIONAR_CATALOGO` que las escrituras -- no hay un permiso
separado de solo lectura en este change.
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
    requiere_comando_online,
    requiere_permiso,
)
from app.core.clock import SystemClock
from app.modules.catalogo import commands as catalogo_commands  # noqa: F401
from app.modules.catalogo import queries as catalogo_queries
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo.domain.errores import RecursoNoEncontradoError
from app.modules.catalogo.repository import LIMITE_PAGINA_DEFAULT
from app.modules.catalogo.schemas import (
    CategoriaCrearRequest,
    CategoriaModificarRequest,
    CategoriaResponse,
    MarcaCrearRequest,
    MarcaModificarRequest,
    MarcaResponse,
    PaginaCategorias,
    PaginaMarcas,
    PaginaProductos,
    PresentacionAgregarRequest,
    PresentacionModificarRequest,
    PresentacionReferenciaCambiarRequest,
    PresentacionResponse,
    ProductoCrearRequest,
    ProductoDetalleResponse,
    ProductoModificarRequest,
    ProductoResponse,
)
from app.modules.sync import service as sync_service

router = APIRouter(prefix="/catalogo", tags=["catalogo"])

PERMISO = "GESTIONAR_CATALOGO"


def _resultado_de(comando: sync_service.Comando) -> dict[str, object]:
    assert comando.resultado is not None
    return comando.resultado


# --- categorias (tarea 9.1) -------------------------------------------------


@router.post("/categorias", response_model=CategoriaResponse, status_code=201)
def crear_categoria(
    datos: CategoriaCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> CategoriaResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"nombre": datos.nombre}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CATEGORIA_CREAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_categoria_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    categoria_id = UUID(str(_resultado_de(comando)["categoria_id"]))
    categoria = catalogo_repository.obtener_categoria_por_id(
        entrada.contexto.organizacion_id, categoria_id, sesion
    )
    assert categoria is not None
    return CategoriaResponse.model_validate(categoria)


@router.put("/categorias/{categoria_id}", response_model=CategoriaResponse)
def modificar_categoria(
    categoria_id: UUID,
    datos: CategoriaModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> CategoriaResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "categoria_id": str(categoria_id),
        "nombre": datos.nombre,
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CATEGORIA_MODIFICAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_categoria_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    categoria = catalogo_repository.obtener_categoria_por_id(
        entrada.contexto.organizacion_id, categoria_id, sesion
    )
    assert categoria is not None
    return CategoriaResponse.model_validate(categoria)


@router.get("/categorias", response_model=PaginaCategorias)
def listar_categorias(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    solo_activas: bool = False,
) -> PaginaCategorias:
    items, cursor_siguiente = catalogo_queries.listar_categorias_paginado(
        contexto.organizacion_id, sesion, limite=limite, cursor=cursor, solo_activas=solo_activas
    )
    return PaginaCategorias(
        items=[CategoriaResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )


# --- marcas (tarea 9.1) ------------------------------------------------


@router.post("/marcas", response_model=MarcaResponse, status_code=201)
def crear_marca(
    datos: MarcaCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> MarcaResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"nombre": datos.nombre}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="MARCA_CREAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_marca_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    marca_id = UUID(str(_resultado_de(comando)["marca_id"]))
    marca = catalogo_repository.obtener_marca_por_id(
        entrada.contexto.organizacion_id, marca_id, sesion
    )
    assert marca is not None
    return MarcaResponse.model_validate(marca)


@router.put("/marcas/{marca_id}", response_model=MarcaResponse)
def modificar_marca(
    marca_id: UUID,
    datos: MarcaModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> MarcaResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "marca_id": str(marca_id),
        "nombre": datos.nombre,
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="MARCA_MODIFICAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_marca_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    marca = catalogo_repository.obtener_marca_por_id(
        entrada.contexto.organizacion_id, marca_id, sesion
    )
    assert marca is not None
    return MarcaResponse.model_validate(marca)


@router.get("/marcas", response_model=PaginaMarcas)
def listar_marcas(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    solo_activas: bool = False,
) -> PaginaMarcas:
    items, cursor_siguiente = catalogo_queries.listar_marcas_paginado(
        contexto.organizacion_id, sesion, limite=limite, cursor=cursor, solo_activas=solo_activas
    )
    return PaginaMarcas(
        items=[MarcaResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )


# --- productos (tarea 9.1) ---------------------------------------------


@router.post("/productos", response_model=ProductoDetalleResponse, status_code=201)
def crear_producto(
    datos: ProductoCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ProductoDetalleResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "codigo": datos.codigo,
        "nombre": datos.nombre,
        "categoria_id": str(datos.categoria_id),
        "marca_id": str(datos.marca_id) if datos.marca_id is not None else None,
        "unidad_base": datos.unidad_base,
        "alicuota_id": str(datos.alicuota_id),
        "presentaciones": [
            {
                "nombre": presentacion.nombre,
                "unidades_base": presentacion.unidades_base,
                "usar_en_venta": presentacion.usar_en_venta,
                "usar_en_compra": presentacion.usar_en_compra,
                "es_referencia": presentacion.es_referencia,
            }
            for presentacion in datos.presentaciones
        ],
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PRODUCTO_CREAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_producto_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    producto_id = UUID(str(_resultado_de(comando)["producto_id"]))
    detalle = catalogo_queries.obtener_producto_con_presentaciones(
        entrada.contexto.organizacion_id, producto_id, sesion
    )
    assert detalle is not None
    producto, presentaciones = detalle
    return ProductoDetalleResponse(
        **ProductoResponse.model_validate(producto).model_dump(),
        presentaciones=[PresentacionResponse.model_validate(p) for p in presentaciones],
    )


@router.put("/productos/{producto_id}", response_model=ProductoResponse)
def modificar_producto(
    producto_id: UUID,
    datos: ProductoModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ProductoResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "producto_id": str(producto_id),
        "codigo": datos.codigo,
        "nombre": datos.nombre,
        "categoria_id": str(datos.categoria_id),
        "marca_id": str(datos.marca_id) if datos.marca_id is not None else None,
        "unidad_base": datos.unidad_base,
        "alicuota_id": str(datos.alicuota_id),
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PRODUCTO_MODIFICAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_producto_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    producto = catalogo_repository.obtener_producto_por_id(
        entrada.contexto.organizacion_id, producto_id, sesion
    )
    assert producto is not None
    return ProductoResponse.model_validate(producto)


@router.get("/productos", response_model=PaginaProductos)
def listar_productos(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    categoria_id: UUID | None = None,
    marca_id: UUID | None = None,
    activo: bool | None = None,
) -> PaginaProductos:
    items, cursor_siguiente = catalogo_queries.listar_productos_paginado(
        contexto.organizacion_id,
        sesion,
        limite=limite,
        cursor=cursor,
        texto=texto,
        categoria_id=categoria_id,
        marca_id=marca_id,
        activo=activo,
    )
    return PaginaProductos(
        items=[ProductoResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )


@router.get("/productos/{producto_id}", response_model=ProductoDetalleResponse)
def obtener_producto(
    producto_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ProductoDetalleResponse:
    """404 (INV-21/SEG-07) si `producto_id` no existe en
    `contexto.organizacion_id` o pertenece a otra organización."""
    detalle = catalogo_queries.obtener_producto_con_presentaciones(
        contexto.organizacion_id, producto_id, sesion
    )
    if detalle is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")
    producto, presentaciones = detalle
    return ProductoDetalleResponse(
        **ProductoResponse.model_validate(producto).model_dump(),
        presentaciones=[PresentacionResponse.model_validate(p) for p in presentaciones],
    )


# --- presentaciones (tarea 9.1) -----------------------------------------


@router.post(
    "/productos/{producto_id}/presentaciones",
    response_model=PresentacionResponse,
    status_code=201,
)
def agregar_presentacion(
    producto_id: UUID,
    datos: PresentacionAgregarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> PresentacionResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "producto_id": str(producto_id),
        "nombre": datos.nombre,
        "unidades_base": datos.unidades_base,
        "usar_en_venta": datos.usar_en_venta,
        "usar_en_compra": datos.usar_en_compra,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PRESENTACION_AGREGAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_presentacion_agregar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    presentacion_id = UUID(str(_resultado_de(comando)["presentacion_id"]))
    presentacion = catalogo_repository.obtener_presentacion_por_id(
        entrada.contexto.organizacion_id, presentacion_id, sesion
    )
    assert presentacion is not None
    return PresentacionResponse.model_validate(presentacion)


@router.put("/presentaciones/{presentacion_id}", response_model=PresentacionResponse)
def modificar_presentacion(
    presentacion_id: UUID,
    datos: PresentacionModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> PresentacionResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "presentacion_id": str(presentacion_id),
        "nombre": datos.nombre,
        "unidades_base": datos.unidades_base,
        "usar_en_venta": datos.usar_en_venta,
        "usar_en_compra": datos.usar_en_compra,
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PRESENTACION_MODIFICAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_presentacion_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    presentacion = catalogo_repository.obtener_presentacion_por_id(
        entrada.contexto.organizacion_id, presentacion_id, sesion
    )
    assert presentacion is not None
    return PresentacionResponse.model_validate(presentacion)


@router.put("/productos/{producto_id}/referencia", response_model=PresentacionResponse)
def cambiar_referencia(
    producto_id: UUID,
    datos: PresentacionReferenciaCambiarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> PresentacionResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "producto_id": str(producto_id),
        "presentacion_id": str(datos.presentacion_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PRESENTACION_REFERENCIA_CAMBIAR",
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

    def _ejecutar_handler(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_presentacion_referencia_cambiar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    nueva_referencia_id = UUID(str(_resultado_de(comando)["presentacion_id"]))
    presentacion = catalogo_repository.obtener_presentacion_por_id(
        entrada.contexto.organizacion_id, nueva_referencia_id, sesion
    )
    assert presentacion is not None
    return PresentacionResponse.model_validate(presentacion)
