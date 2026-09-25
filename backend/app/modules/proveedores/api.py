"""Endpoints de negocio de `proveedores` (change 06, grupo 10; `design.md`
D13; `contrato-api.md`, aprobado por el usuario 2026-09-24 con las
recomendaciones P1 a P8).

Mismo criterio que `catalogo/api.py`: las escrituras (`POST /proveedores`,
`PUT /proveedores/{id}`, `POST /costos`) declaran `requiere_comando_online`
(exige `Operation-Id`, SYN-01/TR-07) y delegan en `sync_service.
procesar_comando`; las lecturas exigen `requiere_permiso` sin pasar por el
bus. El import de `app.modules.proveedores.commands` (sin uso directo en
este archivo) puebla el registro de handlers al arrancar la aplicación,
igual que `catalogo.commands` en `catalogo/api.py`.

Dos routers (`contrato-api.md` §1.1): `/proveedores` y `/costos`, combinados
en el `router` que este módulo expone. **`GET /proveedores/opciones` se
declara ANTES que `GET /proveedores/{proveedor_id}`**: si no, FastAPI
intenta interpretar `opciones` como un UUID y responde 422 en vez de 200
(D13, nota del contrato).

Permiso por ruta (D8, D12): `GESTIONAR_PROVEEDORES` para las cinco rutas de
`/proveedores` salvo `/opciones`, que usa `GESTIONAR_CATALOGO` (mismo
permiso que ya consume el selector de proveedor en el alta de producto, sin
ampliar el alcance de quien solo gestiona catálogo); `EDITAR_COSTOS` para
`POST /costos`; `VER_COSTOS` para las dos lecturas de costos.

Las rutas 7 y 8 (`GET .../vigente`, `GET .../historial`) resuelven el 404
de un producto inexistente o ajeno con `catalogo_service.obtener_producto`
(`02` §5.3, dirección `proveedores -> catalogo` permitida): el repositorio
de costos no distingue "producto ajeno" de "producto sin costos", ambos
devuelven una lista vacía o `None`, y la spec exige 404 para el ajeno
(INV-21)."""

from __future__ import annotations

from datetime import date
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
from app.modules.catalogo import service as catalogo_service
from app.modules.identidad import service as identidad_service
from app.modules.proveedores import commands as proveedores_commands  # noqa: F401
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.errores import RecursoNoEncontradoError
from app.modules.proveedores.models import CostoInformado
from app.modules.proveedores.repository import LIMITE_PAGINA_DEFAULT
from app.modules.proveedores.schemas import (
    CostoDelResultadoResponse,
    CostoInformadoResponse,
    CostoInformarRequest,
    CostoInformarResponse,
    CostoVigenteResponse,
    PaginaCostosInformados,
    PaginaProveedores,
    PaginaProveedorOpciones,
    ProveedorCrearRequest,
    ProveedorModificarRequest,
    ProveedorOpcionResponse,
    ProveedorResponse,
)
from app.modules.sync import service as sync_service

PERMISO_GESTIONAR_PROVEEDORES = "GESTIONAR_PROVEEDORES"
PERMISO_OPCIONES = "GESTIONAR_CATALOGO"
PERMISO_EDITAR_COSTOS = "EDITAR_COSTOS"
PERMISO_VER_COSTOS = "VER_COSTOS"

router_proveedores = APIRouter(prefix="/proveedores", tags=["proveedores"])
router_costos = APIRouter(prefix="/costos", tags=["proveedores"])


def _resultado_de(comando: sync_service.Comando) -> dict[str, object]:
    assert comando.resultado is not None
    return comando.resultado


# --- proveedor (D7, D5/ADR-026) ---------------------------------------------


@router_proveedores.post("", response_model=ProveedorResponse, status_code=201)
def crear_proveedor(
    datos: ProveedorCrearRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_PROVEEDORES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ProveedorResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "nombre": datos.nombre,
        "cuit": datos.cuit,
        "contacto": datos.contacto,
        "telefono": datos.telefono,
        "email": datos.email,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PROVEEDOR_CREAR",
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
        return proveedores_commands.manejar_proveedor_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    proveedor_id = UUID(str(_resultado_de(comando)["proveedor_id"]))
    proveedor = proveedores_repository.obtener_proveedor_por_id(
        entrada.contexto.organizacion_id, proveedor_id, sesion
    )
    assert proveedor is not None
    return ProveedorResponse.model_validate(proveedor)


@router_proveedores.put("/{proveedor_id}", response_model=ProveedorResponse)
def modificar_proveedor(
    proveedor_id: UUID,
    datos: ProveedorModificarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_GESTIONAR_PROVEEDORES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ProveedorResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "proveedor_id": str(proveedor_id),
        "nombre": datos.nombre,
        "cuit": datos.cuit,
        "contacto": datos.contacto,
        "telefono": datos.telefono,
        "email": datos.email,
        "activo": datos.activo,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PROVEEDOR_MODIFICAR",
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
        return proveedores_commands.manejar_proveedor_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    proveedor = proveedores_repository.obtener_proveedor_por_id(
        entrada.contexto.organizacion_id, proveedor_id, sesion
    )
    assert proveedor is not None
    return ProveedorResponse.model_validate(proveedor)


@router_proveedores.get("", response_model=PaginaProveedores)
def listar_proveedores(
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_GESTIONAR_PROVEEDORES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    activo: bool | None = None,
) -> PaginaProveedores:
    items, cursor_siguiente = proveedores_service.listar_proveedores(
        contexto.organizacion_id, sesion, limite=limite, cursor=cursor, texto=texto, activo=activo
    )
    return PaginaProveedores(
        items=[ProveedorResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )


@router_proveedores.get("/opciones", response_model=PaginaProveedorOpciones)
def listar_opciones_de_proveedores(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_OPCIONES))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> PaginaProveedorOpciones:
    items, cursor_siguiente = proveedores_service.listar_opciones_de_proveedores(
        contexto.organizacion_id, sesion, limite=limite, cursor=cursor
    )
    return PaginaProveedorOpciones(
        items=[ProveedorOpcionResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )


@router_proveedores.get("/{proveedor_id}", response_model=ProveedorResponse)
def obtener_proveedor(
    proveedor_id: UUID,
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_GESTIONAR_PROVEEDORES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ProveedorResponse:
    proveedor = proveedores_service.obtener_proveedor(
        contexto.organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    return ProveedorResponse.model_validate(proveedor)


# --- costos informados (D3, D4, D12, D14) ------------------------------------


def _costo_informado_response(
    organizacion_id: UUID, costo: CostoInformado, sesion: Session, *, usuario_nombre: str
) -> CostoInformadoResponse:
    """P4 (aprobado 2026-09-24): suma `proveedor_nombre` (tabla propia) y
    `presentacion_nombre` (vía `catalogo_service`, dirección permitida).
    P10 (enmienda aprobada en la verificación manual 13.5): suma también
    `usuario_nombre`, que el llamador ya resolvió por lote (vía
    `identidad_service.obtener_nombres_de_usuarios`) para no consultar una
    vez por fila."""
    proveedor = proveedores_repository.obtener_proveedor_por_id(
        organizacion_id, costo.proveedor_id, sesion
    )
    assert proveedor is not None  # la FK de costo_informado garantiza su existencia.
    presentacion = catalogo_service.obtener_presentacion(
        organizacion_id, costo.presentacion_id, sesion
    )
    assert presentacion is not None  # idem.
    return CostoInformadoResponse(
        id=costo.id,
        proveedor_id=costo.proveedor_id,
        producto_id=costo.producto_id,
        presentacion_id=costo.presentacion_id,
        valor=costo.valor,
        incluye_iva=costo.incluye_iva,
        bonificacion=costo.bonificacion,
        alicuota_aplicada=costo.alicuota_aplicada,
        costo_base=costo.costo_base,
        vigencia_desde=costo.vigencia_desde,
        observacion=costo.observacion,
        usuario_id=costo.usuario_id,
        operation_id=costo.operation_id,
        creado_en=costo.creado_en,
        proveedor_nombre=proveedor.nombre,
        presentacion_nombre=presentacion.nombre,
        usuario_nombre=usuario_nombre,
    )


@router_costos.post("", response_model=CostoInformarResponse, status_code=201)
def informar_costos(
    datos: CostoInformarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_EDITAR_COSTOS))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CostoInformarResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "proveedor_id": str(datos.proveedor_id),
        "costos": [
            {
                "producto_id": str(costo.producto_id),
                "presentacion_id": str(costo.presentacion_id),
                "valor": costo.valor,
                "incluye_iva": costo.incluye_iva,
                "bonificacion": costo.bonificacion,
                "vigencia_desde": costo.vigencia_desde.isoformat(),
                "observacion": costo.observacion,
            }
            for costo in datos.costos
        ],
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="COSTO_INFORMAR",
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
        return proveedores_commands.manejar_costo_informar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    resultado = _resultado_de(comando)
    costo_ids = resultado["costo_ids"]
    costos_base = resultado["costos_base"]
    assert isinstance(costo_ids, list) and isinstance(costos_base, list)
    return CostoInformarResponse(
        costos=[
            CostoDelResultadoResponse(id=UUID(str(costo_id)), costo_base=str(costo_base))
            for costo_id, costo_base in zip(costo_ids, costos_base, strict=True)
        ]
    )


@router_costos.get("/productos/{producto_id}/vigente", response_model=CostoVigenteResponse)
def obtener_costo_vigente(
    producto_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_COSTOS))],
    sesion: Annotated[Session, Depends(get_session)],
    fecha: date | None = None,
) -> CostoVigenteResponse:
    """P7 (aprobado 2026-09-24): 200 con `costo: null` si el producto no
    tiene costo vigente para `fecha`; 404 solo si `producto_id` no existe
    en la organización o es ajeno (INV-21).

    P11 (`contrato-api.md`, aprobado en la verificación manual 13.5,
    opción B): suma `por_presentacion` -- el último costo informado (D4)
    de CADA presentación con costo a `fecha`, resuelto con la única
    consulta de `proveedores_service.listar_ultimo_costo_por_presentacion`
    (nunca trayendo el historial completo a Python). Los nombres de
    usuario se resuelven por lote junto con los del costo vigente (evita
    N+1); la lista se ordena por `presentacion_nombre` una vez resueltos
    los nombres para mostrar (mismo patrón que P4)."""
    producto = catalogo_service.obtener_producto(contexto.organizacion_id, producto_id, sesion)
    if producto is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")

    fecha_efectiva = fecha
    if fecha_efectiva is None:
        fecha_efectiva = identidad_service.fecha_de_negocio(
            contexto.organizacion_id, sesion, SystemClock()
        )
        assert fecha_efectiva is not None  # la organización del token siempre existe.

    costo = proveedores_service.obtener_costo_informado_vigente(
        contexto.organizacion_id, producto_id, fecha_efectiva, sesion
    )
    costos_por_presentacion = proveedores_service.listar_ultimo_costo_por_presentacion(
        contexto.organizacion_id, producto_id, fecha_efectiva, sesion
    )

    ids_usuarios = {item.usuario_id for item in costos_por_presentacion}
    if costo is not None:
        ids_usuarios.add(costo.usuario_id)
    nombres_de_usuarios = (
        identidad_service.obtener_nombres_de_usuarios(
            contexto.organizacion_id, ids_usuarios, sesion
        )
        if ids_usuarios
        else {}
    )

    respuestas_por_presentacion = [
        _costo_informado_response(
            contexto.organizacion_id,
            item,
            sesion,
            usuario_nombre=nombres_de_usuarios[item.usuario_id],
        )
        for item in costos_por_presentacion
    ]
    respuestas_por_presentacion.sort(key=lambda respuesta: respuesta.presentacion_nombre)

    return CostoVigenteResponse(
        fecha=fecha_efectiva,
        costo=(
            _costo_informado_response(
                contexto.organizacion_id,
                costo,
                sesion,
                usuario_nombre=nombres_de_usuarios[costo.usuario_id],
            )
            if costo is not None
            else None
        ),
        por_presentacion=respuestas_por_presentacion,
    )


@router_costos.get("/productos/{producto_id}/historial", response_model=PaginaCostosInformados)
def listar_historial_de_costos(
    producto_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO_VER_COSTOS))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
) -> PaginaCostosInformados:
    producto = catalogo_service.obtener_producto(contexto.organizacion_id, producto_id, sesion)
    if producto is None:
        raise RecursoNoEncontradoError(f"El producto {producto_id} no existe en esta organización.")

    items, cursor_siguiente = proveedores_service.listar_historial_costos(
        contexto.organizacion_id, producto_id, sesion, limite=limite, cursor=cursor
    )
    # P10 (enmienda aprobada en la verificación manual 13.5): un único
    # llamado por lote a `identidad_service`, no uno por fila (evita N+1).
    nombres_de_usuarios = identidad_service.obtener_nombres_de_usuarios(
        contexto.organizacion_id, {item.usuario_id for item in items}, sesion
    )
    return PaginaCostosInformados(
        items=[
            _costo_informado_response(
                contexto.organizacion_id,
                item,
                sesion,
                usuario_nombre=nombres_de_usuarios[item.usuario_id],
            )
            for item in items
        ],
        cursor_siguiente=cursor_siguiente,
    )


router = APIRouter()
router.include_router(router_proveedores)
router.include_router(router_costos)
