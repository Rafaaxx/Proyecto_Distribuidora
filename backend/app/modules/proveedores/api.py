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
`/proveedores` salvo `/opciones`, que usa `GESTIONAR_CATALOGO`, `REGISTRAR_COMPRA` o
`REGISTRAR_PAGO_PROVEEDOR` (los tres abren SOLO esa lectura: el selector que consume el
alta de producto, el de compra y el de pago -- `design.md` D7 del change 12, sin ampliar
el alcance de quien solo gestiona catálogo); `EDITAR_COSTOS` para
`POST /costos`; `VER_COSTOS` para las dos lecturas de costos.

`GET /proveedores/{proveedor_id}/saldo` (change 12, `design.md` D8) es la excepción a ese
resumen: la abren `GESTIONAR_PROVEEDORES`, `REGISTRAR_PAGO_PROVEEDOR` o
`REGISTRAR_COMPRA`, porque la consumen el alta de pago, el alta de compra y la ficha del
proveedor.

Las rutas 7 y 8 (`GET .../vigente`, `GET .../historial`) resuelven el 404
de un producto inexistente o ajeno con `catalogo_service.obtener_producto`
(`02` §5.3, dirección `proveedores -> catalogo` permitida): el repositorio
de costos no distingue "producto ajeno" de "producto sin costos", ambos
devuelven una lista vacía o `None`, y la spec exige 404 para el ajeno
(INV-21)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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
)
from app.core.clock import SystemClock
from app.modules.catalogo import service as catalogo_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.cuentas_corrientes.service import EstadoDeCuentaResponse, estado_de_cuenta_response
from app.modules.identidad import service as identidad_service
from app.modules.proveedores import commands as proveedores_commands  # noqa: F401
from app.modules.proveedores import queries as proveedores_queries
from app.modules.proveedores import repository as proveedores_repository
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.domain.errores import RecursoNoEncontradoError
from app.modules.proveedores.models import Compra, CostoInformado, PagoProveedor
from app.modules.proveedores.repository import LIMITE_PAGINA_DEFAULT
from app.modules.proveedores.schemas import (
    CompraAnulacionResponse,
    CompraAnularRequest,
    CompraAnularResponse,
    CompraConfirmarRequest,
    CompraConfirmarResponse,
    CompraDetalleResponse,
    CompraLineaResponse,
    CompraMedioResponse,
    CompraPagoResponse,
    CompraResumenResponse,
    CostoDelResultadoResponse,
    CostoInformadoResponse,
    CostoInformarRequest,
    CostoInformarResponse,
    CostoVigenteResponse,
    PaginaCompras,
    PaginaCostosInformados,
    PaginaPagos,
    PaginaProveedores,
    PaginaProveedorOpciones,
    PagoAnulacionResponse,
    PagoDetalleResponse,
    PagoMedioResponse,
    PagoProveedorAnularRequest,
    PagoProveedorAnularResponse,
    PagoProveedorRegistrarRequest,
    PagoProveedorRegistrarResponse,
    PagoResumenResponse,
    ProveedorCrearRequest,
    ProveedorModificarRequest,
    ProveedorOpcionResponse,
    ProveedorResponse,
    ResumenReglaIvaResponse,
    SaldoProveedorResponse,
)
from app.modules.sync import service as sync_service

PERMISO_GESTIONAR_PROVEEDORES = "GESTIONAR_PROVEEDORES"
PERMISO_OPCIONES = "GESTIONAR_CATALOGO"
PERMISO_EDITAR_COSTOS = "EDITAR_COSTOS"
PERMISO_VER_COSTOS = "VER_COSTOS"
PERMISO_REGISTRAR_COMPRA = "REGISTRAR_COMPRA"
PERMISO_ANULAR_COMPRA = "ANULAR_COMPRA"
PERMISO_REGISTRAR_PAGO_PROVEEDOR = "REGISTRAR_PAGO_PROVEEDOR"
PERMISO_ANULAR_PAGO_PROVEEDOR = "ANULAR_PAGO_PROVEEDOR"
# D12 (change 13): el selector de alcance de una regla de margen lee las opciones de proveedor
# con solo este permiso, solo en lectura.
PERMISO_GESTIONAR_LISTAS = "GESTIONAR_LISTAS"

router_proveedores = APIRouter(prefix="/proveedores", tags=["proveedores"])
router_costos = APIRouter(prefix="/costos", tags=["proveedores"])
router_compras = APIRouter(prefix="/compras", tags=["proveedores"])
router_pagos = APIRouter(prefix="/pagos-proveedores", tags=["proveedores"])


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
    contexto: Annotated[
        ContextoAutenticado,
        Depends(
            requiere_algun_permiso(
                PERMISO_OPCIONES,
                PERMISO_REGISTRAR_COMPRA,
                PERMISO_REGISTRAR_PAGO_PROVEEDOR,
                PERMISO_GESTIONAR_LISTAS,
            )
        ),
    ],
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


@router_proveedores.get("/{proveedor_id}/cuenta-corriente", response_model=EstadoDeCuentaResponse)
def obtener_cuenta_corriente_de_proveedor(
    proveedor_id: UUID,
    contexto: Annotated[
        ContextoAutenticado, Depends(requiere_permiso(PERMISO_GESTIONAR_PROVEEDORES))
    ],
    sesion: Annotated[Session, Depends(get_session)],
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EstadoDeCuentaResponse:
    """Estado de cuenta del proveedor (change 08, tarea 6.2; CC-07, `design.md`
    D2 y D9). Permiso `GESTIONAR_PROVEEDORES`, el de la ficha. Mismas reglas que
    `clientes/api.py`: fechas de negocio en la zona de la organización, `limite`
    mayor que 200 es 422 y un proveedor ajeno o inexistente responde 404 antes de
    leer el libro (INV-21, SEG-07)."""
    proveedor = proveedores_service.obtener_proveedor(
        contexto.organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    estado = cuentas_corrientes_service.estado_de_cuenta(
        contexto.organizacion_id,
        sesion,
        cuenta_tipo="PROVEEDOR",
        entidad_id=proveedor_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return estado_de_cuenta_response(estado)


@router_proveedores.get("/{proveedor_id}/saldo", response_model=SaldoProveedorResponse)
def obtener_saldo_de_proveedor(
    proveedor_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(
            requiere_algun_permiso(
                PERMISO_GESTIONAR_PROVEEDORES,
                PERMISO_REGISTRAR_PAGO_PROVEEDOR,
                PERMISO_REGISTRAR_COMPRA,
            )
        ),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> SaldoProveedorResponse:
    """Saldo actual del proveedor (change 12, tarea 6.2; `design.md` D8; CC-04, INV-03).

    Es la lectura liviana que consume el alta de pago (saldo actual y resultante) y el aviso
    del alta de compra: sale del `service.py` de `cuentas_corrientes` (dirección permitida,
    ADR-043 punto 15), que lo calcula en SQL sobre `saldo_cuenta` y da `"0.00"` si la cuenta
    no tiene movimientos. Un proveedor ajeno o inexistente responde 404 antes de leer el
    saldo (INV-21, SEG-07)."""
    proveedor = proveedores_service.obtener_proveedor(
        contexto.organizacion_id, proveedor_id, sesion
    )
    if proveedor is None:
        raise RecursoNoEncontradoError(
            f"El proveedor {proveedor_id} no existe en esta organización."
        )
    saldo = cuentas_corrientes_service.obtener_saldo(
        contexto.organizacion_id,
        sesion,
        cuenta_tipo="PROVEEDOR",
        entidad_id=proveedor_id,
    )
    return SaldoProveedorResponse(saldo=str(saldo))


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
        computa_credito_fiscal=costo.computa_credito_fiscal,
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


@router_costos.get("/resumen-regla-iva", response_model=ResumenReglaIvaResponse)
def resumir_costos_por_regla_de_iva(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso("ADMIN_CONFIGURACION", PERMISO_EDITAR_COSTOS)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    fecha: date | None = None,
) -> ResumenReglaIvaResponse:
    """11b, D10 (CST-03, CST-06): cuántos costos informados vigentes a `fecha` (por defecto,
    la fecha de negocio de hoy) se registraron computando crédito fiscal y cuántos sin
    computarlo. Lo usa la pantalla de cambio de condición para avisar cuántos costos conviene
    volver a informar. La organización sale del token (INV-21)."""
    fecha_efectiva = fecha
    if fecha_efectiva is None:
        fecha_efectiva = identidad_service.fecha_de_negocio(
            contexto.organizacion_id, sesion, SystemClock()
        )
        assert fecha_efectiva is not None  # la organización del token siempre existe.
    resumen = proveedores_queries.resumir_costos_vigentes_por_regla_de_iva(
        contexto.organizacion_id, fecha_efectiva, sesion
    )
    return ResumenReglaIvaResponse(
        fecha=resumen.fecha,
        con_credito_fiscal=resumen.con_credito_fiscal,
        sin_credito_fiscal=resumen.sin_credito_fiscal,
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


# --- compras (change 11: CMP-01 a CMP-04, CMP-08; `design.md` D1 a D7, D14) ------------


@router_compras.post("", response_model=CompraConfirmarResponse, status_code=201)
def confirmar_compra(
    datos: CompraConfirmarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_REGISTRAR_COMPRA))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CompraConfirmarResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "proveedor_id": str(datos.proveedor_id),
        "fecha": datos.fecha.isoformat(),
        "ubicacion_id": str(datos.ubicacion_id),
        "condicion": datos.condicion,
        "total_factura": datos.total_factura,
        "numero_comprobante": datos.numero_comprobante,
        "observacion": datos.observacion,
        "lineas": [
            {
                "producto_id": str(linea.producto_id),
                "presentacion_id": str(linea.presentacion_id),
                "cantidad": linea.cantidad,
                "valor": linea.valor,
                "incluye_iva": linea.incluye_iva,
                "bonificacion": linea.bonificacion,
            }
            for linea in datos.lineas
        ],
        "medios": [
            {
                "medio_pago_id": str(medio.medio_pago_id),
                "importe": medio.importe,
                "referencia": medio.referencia,
            }
            for medio in datos.medios
        ],
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="COMPRA_CONFIRMAR",
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
        return proveedores_commands.manejar_compra_confirmar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return CompraConfirmarResponse.model_validate(_resultado_de(comando))


@router_compras.post("/{compra_id}/anulacion", response_model=CompraAnularResponse)
def anular_compra(
    compra_id: UUID,
    datos: CompraAnularRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_ANULAR_COMPRA))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CompraAnularResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "compra_id": str(compra_id),
        "motivo_id": str(datos.motivo_id),
        "devuelve_pago": datos.devuelve_pago,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="COMPRA_ANULAR",
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
        sesion_protegida: object,
    ) -> sync_service.ResultadoHandler | sync_service.ResultadoHandlerConObservaciones:
        return proveedores_commands.manejar_compra_anular(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return CompraAnularResponse.model_validate(_resultado_de(comando))


# --- pagos a proveedor (change 12: PAG-01, PAG-02; `design.md` D2 a D6, D10, D14) ---------


@router_pagos.post("", response_model=PagoProveedorRegistrarResponse, status_code=201)
def registrar_pago_proveedor(
    datos: PagoProveedorRegistrarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_REGISTRAR_PAGO_PROVEEDOR))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> PagoProveedorRegistrarResponse:
    """`POST /pagos-proveedores` (change 12, tarea 4.3). El resultado sale de
    `comando.resultado`, no de una relectura: un reenvío idempotente del mismo
    `Operation-Id` devuelve exactamente lo mismo (INV-06). Los importes viajan y vuelven
    como string (INV-03) y los errores de medio traen su índice 0-based en el Problem
    Details (`02` §11, PAG-01)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "proveedor_id": str(datos.proveedor_id),
        "fecha": datos.fecha.isoformat(),
        "importe": datos.importe,
        "medios": [
            {
                "medio_pago_id": str(medio.medio_pago_id),
                "importe": medio.importe,
                "referencia": medio.referencia,
            }
            for medio in datos.medios
        ],
        "observacion": datos.observacion,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PAGO_PROVEEDOR_REGISTRAR",
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
        return proveedores_commands.manejar_pago_proveedor_registrar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return PagoProveedorRegistrarResponse.model_validate(_resultado_de(comando))


@router_pagos.post("/{pago_id}/anulacion", response_model=PagoProveedorAnularResponse)
def anular_pago_proveedor(
    pago_id: UUID,
    datos: PagoProveedorAnularRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_ANULAR_PAGO_PROVEEDOR))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> PagoProveedorAnularResponse:
    """`POST /pagos-proveedores/{id}/anulacion` (change 12, PAG-03, tarea 5.4).

    El resultado sale de `comando.resultado`, no de una relectura: un reenvío idempotente
    del mismo `Operation-Id` devuelve exactamente lo mismo (INV-06). El saldo es el que
    queda DESPUÉS de la anulación (CC-04) y viaja como string (INV-03).

    El endpoint no dice si el pago es de una compra vigente (D2), si ya estaba anulado
    (PAG-03) ni si el motivo es de otro ámbito (D1): eso lo decide el servicio con su
    código estable y el Problem Details lotranslate (`02` §11)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "pago_id": str(pago_id),
        "motivo_id": str(datos.motivo_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="PAGO_PROVEEDOR_ANULAR",
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
        return proveedores_commands.manejar_pago_proveedor_anular(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return PagoProveedorAnularResponse.model_validate(_resultado_de(comando))


def _resumen_de_pago(pago: PagoProveedor, proveedor_nombre: str) -> PagoResumenResponse:
    return PagoResumenResponse(
        pago_id=pago.id,
        fecha=pago.fecha,
        proveedor_id=pago.proveedor_id,
        proveedor_nombre=proveedor_nombre,
        importe=str(pago.importe),
        origen=pago.origen,
        estado=pago.estado,
        compra_id=pago.compra_id,
    )


@router_pagos.get("", response_model=PaginaPagos)
def listar_pagos(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(
            requiere_algun_permiso(PERMISO_REGISTRAR_PAGO_PROVEEDOR, PERMISO_ANULAR_PAGO_PROVEEDOR)
        ),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    proveedor_id: UUID | None = None,
    estado: Literal["CONFIRMADA", "ANULADA"] | None = None,
    origen: Literal["COMPRA", "INDEPENDIENTE"] | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaPagos:
    """Pagos de la organización del más reciente al más viejo, por cursor (change 12, tarea
    6.1; PAG-01, TR-04, `design.md` D7 y D11): `REGISTRAR_PAGO_PROVEEDOR` o
    `ANULAR_PAGO_PROVEEDOR`. `desde` y `hasta` son fechas de pago inclusivas; un `limite`
    fuera de 1 a 200, un rango invertido (`RANGO_DE_FECHAS_INVALIDO`), un cursor ilegible
    (`CURSOR_INVALIDO`) o un `estado`/`origen` desconocido son 422, no un recorte ni un
    filtro ignorado.

    Incluye los pagos de origen `COMPRA` con su `compra_id` (D11), así que el listado es
    el de "todos los pagos de la semana" del ejemplo de D11."""
    pagina = proveedores_queries.listar_pagos(
        contexto.organizacion_id,
        sesion,
        proveedor_id=proveedor_id,
        estado=estado,
        origen=origen,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return PaginaPagos(
        items=[_resumen_de_pago(item.pago, item.proveedor_nombre) for item in pagina.pagos],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router_pagos.get("/{pago_id}", response_model=PagoDetalleResponse)
def obtener_pago(
    pago_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(
            requiere_algun_permiso(PERMISO_REGISTRAR_PAGO_PROVEEDOR, PERMISO_ANULAR_PAGO_PROVEEDOR)
        ),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> PagoDetalleResponse:
    """Detalle de un pago con sus medios (nombre, importe y referencia), la observación, el
    estado de su compra si es de origen `COMPRA` y, si está anulado, el motivo, el usuario
    y el momento (PAG-01, PAG-03). 404 si es de otra organización o no existe (INV-21),
    igual que un id inexistente."""
    detalle = proveedores_queries.obtener_detalle_de_pago(contexto.organizacion_id, pago_id, sesion)
    anulacion = detalle.anulacion
    # Mismo mecanismo que el historial de costos: el nombre sale de `identidad_service`.
    respuesta_anulacion = (
        None
        if anulacion is None
        else PagoAnulacionResponse(
            motivo_id=anulacion.motivo_id,
            motivo_nombre=anulacion.motivo_nombre,
            anulado_en=anulacion.anulado_en,
            anulado_por_id=anulacion.anulado_por_id,
            anulado_por_nombre=identidad_service.obtener_nombres_de_usuarios(
                contexto.organizacion_id, {anulacion.anulado_por_id}, sesion
            )[anulacion.anulado_por_id],
        )
    )
    return PagoDetalleResponse(
        **_resumen_de_pago(detalle.pago, detalle.proveedor_nombre).model_dump(),
        observacion=detalle.pago.observacion,
        compra_estado=detalle.compra_estado,
        medios=[
            PagoMedioResponse(
                medio_pago_id=medio.medio_pago_id,
                medio_nombre=medio.medio_nombre,
                importe=str(medio.importe),
                referencia=medio.referencia,
            )
            for medio in detalle.medios
        ],
        anulacion=respuesta_anulacion,
    )


def _resumen_de(compra: Compra, proveedor_nombre: str) -> CompraResumenResponse:
    return CompraResumenResponse(
        id=compra.id,
        fecha=compra.fecha,
        proveedor_id=compra.proveedor_id,
        proveedor_nombre=proveedor_nombre,
        condicion=compra.condicion,
        total_neto=str(compra.total_neto),
        total_factura=str(compra.total_factura),
        estado=compra.estado,
        numero_comprobante=compra.numero_comprobante,
    )


@router_compras.get("", response_model=PaginaCompras)
def listar_compras(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_REGISTRAR_COMPRA, PERMISO_ANULAR_COMPRA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    proveedor_id: UUID | None = None,
    estado: Literal["CONFIRMADA", "ANULADA"] | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    numero_comprobante: str | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaCompras:
    """Compras de la organización de la más reciente a la más vieja, por cursor
    (`design.md` D14: `REGISTRAR_COMPRA` o `ANULAR_COMPRA`). `desde` y `hasta` son fechas
    de comprobante inclusivas; un `limite` fuera de 1 a 200 es 422, no un recorte."""
    pagina = proveedores_queries.listar_compras(
        contexto.organizacion_id,
        sesion,
        proveedor_id=proveedor_id,
        estado=estado,
        desde=desde,
        hasta=hasta,
        numero_comprobante=numero_comprobante,
        cursor=cursor,
        limite=limite,
    )
    return PaginaCompras(
        items=[_resumen_de(item.compra, item.proveedor_nombre) for item in pagina.compras],
        cursor_siguiente=pagina.cursor_siguiente,
    )


@router_compras.get("/{compra_id}", response_model=CompraDetalleResponse)
def obtener_compra(
    compra_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO_REGISTRAR_COMPRA, PERMISO_ANULAR_COMPRA)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> CompraDetalleResponse:
    """Detalle de una compra con líneas, pago y anulación. 404 si es de otra organización
    o no existe (INV-21)."""
    detalle = proveedores_queries.obtener_detalle_de_compra(
        contexto.organizacion_id, compra_id, sesion
    )
    resumen = _resumen_de(detalle.compra, detalle.proveedor_nombre)
    return CompraDetalleResponse(
        **resumen.model_dump(),
        ubicacion_id=detalle.compra.ubicacion_id,
        observacion=detalle.compra.observacion,
        lineas=[
            CompraLineaResponse(
                orden=linea.orden,
                producto_id=linea.producto_id,
                producto_codigo=linea.producto_codigo,
                producto_nombre=linea.producto_nombre,
                presentacion_id=linea.presentacion_id,
                presentacion_nombre=linea.presentacion_nombre,
                unidades_presentacion=linea.unidades_presentacion,
                unidades_referencia=linea.unidades_referencia,
                nombre_referencia=linea.nombre_referencia,
                cantidad=str(linea.cantidad),
                cantidad_base=linea.cantidad_base,
                valor_presentacion=str(linea.valor_presentacion),
                incluye_iva=linea.incluye_iva,
                computa_credito_fiscal=linea.computa_credito_fiscal,
                bonificacion=str(linea.bonificacion),
                alicuota_aplicada=str(linea.alicuota_aplicada),
                costo_base=str(linea.costo_base),
                importe_neto=str(linea.importe_neto),
            )
            for linea in detalle.lineas
        ],
        pago=(
            None
            if detalle.pago is None
            else CompraPagoResponse(
                id=detalle.pago.id,
                fecha=detalle.pago.fecha,
                importe=str(detalle.pago.importe),
                estado=detalle.pago.estado,
                anulado_en=detalle.pago.anulado_en,
                medios=[
                    CompraMedioResponse(
                        medio_pago_id=medio.medio_pago_id,
                        medio_nombre=medio.medio_nombre,
                        importe=str(medio.importe),
                        referencia=medio.referencia,
                    )
                    for medio in detalle.pago.medios
                ],
            )
        ),
        anulacion=(
            None
            if detalle.anulacion is None
            else CompraAnulacionResponse(
                motivo_id=detalle.anulacion.motivo_id,
                motivo_nombre=detalle.anulacion.motivo_nombre,
                anulada_en=detalle.anulacion.anulada_en,
                anulada_por_id=detalle.anulacion.anulada_por_id,
            )
        ),
    )


router = APIRouter()
router.include_router(router_proveedores)
router.include_router(router_costos)
router.include_router(router_compras)
router.include_router(router_pagos)
