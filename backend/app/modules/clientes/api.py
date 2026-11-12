"""Endpoints de `clientes` (change 07, grupo 4; `design.md` D9, enmienda
2026-09-29).

Cuatro escrituras y tres lecturas. Las escrituras (`POST /clientes`,
`PUT /clientes/{id}`, `PUT /clientes/{id}/credito`,
`POST /clientes/consumidor-final`) tienen cada una su propia ruta dedicada,
mismo criterio que `proveedores/api.py` y `catalogo/api.py`: declaran
`requiere_comando_online` (exige `Operation-Id`, SYN-01/TR-07) y delegan en
`sync_service.procesar_comando`. El texto original de D9 decía "escrituras:
los cuatro comandos" asumiendo que el despacho genérico de
`POST /sync/comandos` podía ejecutarlas; se confirmó que no: `sync/
service.py::_procesar_item_de_lote` llama a los handlers con solo dos
argumentos posicionales, y los cuatro de `clientes/commands.py` exigen
`sesion`/`reloj` como parámetros de palabra clave (deuda nominada al change
17, ver `catalogo/commands.py`). El import de `app.modules.clientes.commands`
(sin uso directo salvo por las funciones `manejar_*`) puebla el registro de
handlers al arrancar la aplicación, igual que en `proveedores/api.py`.

Un solo router con prefijo `/clientes` (D9: siete rutas, no varios routers).

**`/consumidor-final` se declara ANTES que `/{cliente_id}`** en ambos
métodos: si no, FastAPI intenta interpretar `consumidor-final` como un UUID
y responde 422 en vez de 200/201. Mismo criterio que `/proveedores/opciones`
en `proveedores/api.py` (D13 del change 06, nota del contrato).

Permiso por ruta: `GESTIONAR_CLIENTES` para las tres lecturas, `POST
/clientes` y `PUT /clientes/{id}` (D3, ADR-028); `GESTIONAR_CREDITO` para
`PUT /clientes/{id}/credito` (D3); `ADMIN_CONFIGURACION` para `POST
/clientes/consumidor-final` (D4, ADR-029). Las lecturas no exigen
`GESTIONAR_CREDITO`: la ficha devuelve los tres campos de crédito también a
quien no puede editarlos (spec `administracion-de-clientes`, escenario "La
ficha muestra el crédito en solo lectura"). Y `GESTIONAR_CREDITO` sin
`GESTIONAR_CLIENTES` no habilita la sección (escenario "Permiso de crédito
sin permiso de clientes").

`organizacion_id` sale siempre del token (`ContextoAutenticado`/`sobre`),
nunca de la petición (INV-02). Un recurso de otra organización responde
**404, no 403** (`CLAUDE.md` §4, INV-21): tanto las lecturas como los
`repository.obtener_cliente_por_id*` que resuelven la escritura filtran por
organización, así que un id ajeno es indistinguible de uno inexistente."""

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
from app.modules.clientes import commands as clientes_commands  # noqa: F401
from app.modules.clientes import repository as clientes_repository
from app.modules.clientes import service as clientes_service
from app.modules.clientes.domain.errores import RecursoNoEncontradoError
from app.modules.clientes.models import Cliente
from app.modules.clientes.repository import LIMITE_PAGINA_DEFAULT
from app.modules.clientes.schemas import (
    ClienteCrearRequest,
    ClienteCreditoModificarRequest,
    ClienteModificarRequest,
    ClienteOpcionResponse,
    ClienteResponse,
    ClienteSaldoResponse,
    ClienteVendedorAsignarRequest,
    ClienteVendedorAsignarResponse,
    ConsumidorFinalConfigurarRequest,
    ConsumidorFinalResponse,
    PaginaClientes,
    PaginaOpcionesDeClientes,
    VendedorElegibleResponse,
)
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.cuentas_corrientes.service import EstadoDeCuentaResponse, estado_de_cuenta_response
from app.modules.sync import service as sync_service

PERMISO = "GESTIONAR_CLIENTES"
PERMISO_CREDITO = "GESTIONAR_CREDITO"
PERMISO_CONFIGURACION = "ADMIN_CONFIGURACION"
PERMISO_REGISTRAR_COBRANZA = "REGISTRAR_COBRANZA"
PERMISO_VENDER = "VENDER"

router = APIRouter(prefix="/clientes", tags=["clientes"])


def _resultado_de(comando: sync_service.Comando) -> dict[str, object]:
    assert comando.resultado is not None
    return comando.resultado


def _con_vendedor(
    organizacion_id: UUID, sesion: Session, clientes: list[Cliente]
) -> list[ClienteResponse]:
    """Las respuestas de `clientes` con el nombre y la validez de su vendedor (change 20b, D6,
    D15), resueltos por lote a través de `clientes/service.py`."""
    datos = clientes_service.datos_de_vendedores(
        organizacion_id,
        {c.vendedor_id for c in clientes if c.vendedor_id is not None},
        sesion,
    )
    respuestas = [ClienteResponse.model_validate(cliente) for cliente in clientes]
    for respuesta in respuestas:
        vendedor = None if respuesta.vendedor_id is None else datos.get(respuesta.vendedor_id)
        if vendedor is not None:
            respuesta.vendedor_nombre = vendedor.nombre
            respuesta.vendedor_valido = vendedor.valido
    return respuestas


def _cliente_o_404(organizacion_id: UUID, cliente_id: UUID, sesion: Session) -> ClienteResponse:
    cliente = clientes_repository.obtener_cliente_por_id(organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")
    return _con_vendedor(organizacion_id, sesion, [cliente])[0]


# --- escrituras (D9, enmienda 2026-09-29) ------------------------------------


@router.post("", response_model=ClienteResponse, status_code=201)
def crear_cliente(
    datos: ClienteCrearRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "nombre": datos.nombre,
        "direccion": datos.direccion,
        "contacto": datos.contacto,
        "razon_social": datos.razon_social,
        "documento_tipo": datos.documento_tipo,
        "documento_numero": datos.documento_numero,
        "telefono": datos.telefono,
        "email": datos.email,
        "codigo": datos.codigo,
        "estado_facturacion_default": datos.estado_facturacion_default,
        "lista_precio_id": None if datos.lista_precio_id is None else str(datos.lista_precio_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CLIENTE_CREAR",
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
        return clientes_commands.manejar_cliente_crear(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    cliente_id = UUID(str(_resultado_de(comando)["cliente_id"]))
    return _cliente_o_404(entrada.contexto.organizacion_id, cliente_id, sesion)


@router.put("/{cliente_id}", response_model=ClienteResponse)
def modificar_cliente(
    cliente_id: UUID,
    datos: ClienteModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "cliente_id": str(cliente_id),
        "nombre": datos.nombre,
        "direccion": datos.direccion,
        "contacto": datos.contacto,
        "estado": datos.estado,
        "razon_social": datos.razon_social,
        "documento_tipo": datos.documento_tipo,
        "documento_numero": datos.documento_numero,
        "telefono": datos.telefono,
        "email": datos.email,
        "codigo": datos.codigo,
        "estado_facturacion_default": datos.estado_facturacion_default,
    }
    if "lista_precio_id" in datos.model_fields_set:
        # Ausente conserva la lista asignada; nulo explícito la quita (ajuste A, change 13).
        contenido["lista_precio_id"] = (
            None if datos.lista_precio_id is None else str(datos.lista_precio_id)
        )
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CLIENTE_MODIFICAR",
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
        return clientes_commands.manejar_cliente_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return _cliente_o_404(entrada.contexto.organizacion_id, cliente_id, sesion)


@router.put("/{cliente_id}/credito", response_model=ClienteResponse)
def modificar_credito_cliente(
    cliente_id: UUID,
    datos: ClienteCreditoModificarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_CREDITO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "cliente_id": str(cliente_id),
        "limite_credito": datos.limite_credito,
        "politica_credito": datos.politica_credito,
        "tolerancia_offline_tipo": datos.tolerancia_offline_tipo,
        "tolerancia_offline_valor": datos.tolerancia_offline_valor,
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CLIENTE_CREDITO_MODIFICAR",
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
        return clientes_commands.manejar_cliente_credito_modificar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return _cliente_o_404(entrada.contexto.organizacion_id, cliente_id, sesion)


@router.post("/vendedor", response_model=ClienteVendedorAsignarResponse)
def asignar_vendedor(
    datos: ClienteVendedorAsignarRequest,
    entrada: Annotated[EntradaComandoOnline, Depends(requiere_comando_online(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteVendedorAsignarResponse:
    """Change 20b (D15): asigna un vendedor a uno o varios clientes, o lo quita con `null`
    (`CLIENTE_VENDEDOR_ASIGNAR`, `GESTIONAR_CLIENTES`, solo con conexión, todo o nada)."""
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {
        "cliente_ids": [str(cliente_id) for cliente_id in datos.cliente_ids],
        "vendedor_id": None if datos.vendedor_id is None else str(datos.vendedor_id),
    }
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CLIENTE_VENDEDOR_ASIGNAR",
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
        return clientes_commands.manejar_cliente_vendedor_asignar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    return ClienteVendedorAsignarResponse.model_validate(_resultado_de(comando))


@router.post("/consumidor-final", response_model=ClienteResponse, status_code=201)
def configurar_consumidor_final(
    datos: ConsumidorFinalConfigurarRequest,
    entrada: Annotated[
        EntradaComandoOnline, Depends(requiere_comando_online(PERMISO_CONFIGURACION))
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteResponse:
    reloj = SystemClock()
    contenido: dict[str, ContenidoComando] = {"nombre": datos.nombre}
    sobre = construir_sobre_online(
        operation_id=entrada.operation_id,
        tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
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
        return clientes_commands.manejar_cliente_consumidor_final_configurar(
            sobre,
            contenido_validado,  # type: ignore[arg-type]
            sesion=sesion_protegida,
            reloj=reloj,
        )

    comando = sync_service.procesar_comando(
        sesion, reloj, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar_handler
    )
    cliente_id = UUID(str(_resultado_de(comando)["cliente_id"]))
    return _cliente_o_404(entrada.contexto.organizacion_id, cliente_id, sesion)


# --- lecturas -----------------------------------------------------------------


@router.get("", response_model=PaginaClientes)
def listar_clientes(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
    limite: int = LIMITE_PAGINA_DEFAULT,
    cursor: str | None = None,
    texto: str | None = None,
    estado: str | None = None,
    vendedor_id: UUID | None = None,
    sin_vendedor: bool = False,
) -> PaginaClientes:
    """Listado paginado por cursor con filtro por texto y por estado (spec
    `administracion-de-clientes`, escenarios "Buscar un cliente por texto" y
    "Filtrar por estado suspendido"). El `estado` se valida contra el
    catálogo cerrado en `domain/estado.py` y lo repite el `CHECK` de la base.

    Change 20b (D15): cada cliente trae su vendedor (`vendedor_id`, `vendedor_nombre`,
    `vendedor_valido`) y el listado filtra por `vendedor_id` o por `sin_vendedor=true`.
    """
    items, cursor_siguiente = clientes_service.listar_clientes(
        contexto.organizacion_id,
        sesion,
        limite=limite,
        cursor=cursor,
        texto=texto,
        estado=estado,
        vendedor_id=vendedor_id,
        sin_vendedor=sin_vendedor,
    )
    return PaginaClientes(
        items=_con_vendedor(contexto.organizacion_id, sesion, items),
        cursor_siguiente=cursor_siguiente,
    )


@router.get("/opciones", response_model=PaginaOpcionesDeClientes)
def listar_opciones_de_clientes(
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO, PERMISO_REGISTRAR_COBRANZA, PERMISO_VENDER)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
    texto: str | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=100)] = LIMITE_PAGINA_DEFAULT,
    incluir_consumidor_final: bool = False,
    alcance: Literal["todos"] | None = None,
) -> PaginaOpcionesDeClientes:
    """Selector liviano de clientes para quien cobra (change 17, `design.md` D14, tabla de
    permisos aprobada por el usuario el 2026-10-16): `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`;
    desde el change 18a (D19, aprobada el 2026-10-20), también `VENDER`, solo lectura.
    Devuelve identificador, nombre, código, estado y la marca `es_consumidor_final`, sin crédito
    ni documento; solo clientes `ACTIVO` y `SUSPENDIDO`, y el consumidor final únicamente con
    `incluir_consumidor_final=true` (la pantalla de venta, CLI-03; aprobado el 2026-10-20).
    Se declara antes de `/{cliente_id}`.

    Change 20b (D14): quien no tiene `GESTIONAR_CLIENTES` y tiene clientes asignados recibe sus
    clientes; `alcance=todos` ("Buscar en todos los clientes") trae todos. Sin cartera, o con
    `GESTIONAR_CLIENTES`, siempre todos (ADR-052)."""
    items, cursor_siguiente = clientes_service.listar_opciones(
        contexto.organizacion_id,
        sesion,
        limite=limite,
        cursor=cursor,
        texto=texto,
        incluir_consumidor_final=incluir_consumidor_final,
        usuario_id=contexto.usuario_id,
        pide_todos=alcance == "todos",
    )
    return PaginaOpcionesDeClientes(
        items=[ClienteOpcionResponse.model_validate(item) for item in items],
        cursor_siguiente=cursor_siguiente,
    )


@router.get("/vendedores", response_model=list[VendedorElegibleResponse])
def listar_vendedores_elegibles(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> list[VendedorElegibleResponse]:
    """Change 20b (D15): los usuarios que se pueden elegir como vendedor de un cliente (activos,
    con rol activo y con `VENDER` o `REGISTRAR_COBRANZA`), para quien administra clientes sin
    administrar usuarios. Solo `id` y `nombre`, de la organización del token. Se declara antes de
    `/{cliente_id}`."""
    return [
        VendedorElegibleResponse(id=usuario_id, nombre=nombre)
        for usuario_id, nombre in clientes_service.listar_vendedores_elegibles(
            contexto.organizacion_id, sesion
        )
    ]


@router.get("/consumidor-final", response_model=ConsumidorFinalResponse)
def obtener_consumidor_final(
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ConsumidorFinalResponse:
    """El consumidor final de la organización que consulta (spec
    `consumidor-final`).

    200 con `habilitado: false` cuando la organización no lo habilitó, y
    200 con el cliente cuando sí: la ausencia del consumidor final es un
    estado normal de la organización, no un recurso inexistente, así que no
    es 404.

    El aislamiento (INV-21) es por construcción: se resuelve por
    `clientes_consumidor_final_id` de la configuración de A, que es de A, y
    el cliente sale del mismo filtro por `organizacion_id`. El de B no se
    puede pedir por esta ruta, porque el identificador sale de la
    configuración de A, no de un parámetro de la petición.
    """
    cliente = clientes_service.obtener_consumidor_final(contexto.organizacion_id, sesion)
    if cliente is None:
        return ConsumidorFinalResponse(habilitado=False, cliente=None)
    return ConsumidorFinalResponse(habilitado=True, cliente=ClienteResponse.model_validate(cliente))


@router.get("/{cliente_id}", response_model=ClienteResponse)
def obtener_cliente(
    cliente_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteResponse:
    """La ficha de un cliente, con sus tres campos de crédito en solo lectura
    para quien no tiene `GESTIONAR_CREDITO` (D3).

    404 para un cliente de otra organización (INV-21, SEG-07): la respuesta
    no distingue "ajeno" de "no existe", para que el 404 no confirme la
    existencia del recurso de otra organización.
    """
    cliente = clientes_service.obtener_cliente_por_id(contexto.organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")
    return _con_vendedor(contexto.organizacion_id, sesion, [cliente])[0]


@router.get("/{cliente_id}/saldo", response_model=ClienteSaldoResponse)
def obtener_saldo_de_cliente(
    cliente_id: UUID,
    contexto: Annotated[
        ContextoAutenticado,
        Depends(requiere_algun_permiso(PERMISO, PERMISO_REGISTRAR_COBRANZA, PERMISO_VENDER)),
    ],
    sesion: Annotated[Session, Depends(get_session)],
) -> ClienteSaldoResponse:
    """Saldo actual del cliente, desde `saldo_cuenta` (change 17, D14, aprobada por el usuario el
    2026-10-16): `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`; desde el change 18a (D19, aprobada
    el 2026-10-20), también `VENDER`, solo lectura. Sin movimientos es `"0.00"` (CC-04).
    404 para un cliente de otra organización o inexistente, antes de leer el saldo (INV-21)."""
    cliente = clientes_service.obtener_cliente_por_id(contexto.organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")
    saldo = cuentas_corrientes_service.obtener_saldo(
        contexto.organizacion_id, sesion, cuenta_tipo="CLIENTE", entidad_id=cliente_id
    )
    return ClienteSaldoResponse(cliente_id=cliente_id, saldo=str(saldo))


@router.get("/{cliente_id}/cuenta-corriente", response_model=EstadoDeCuentaResponse)
def obtener_cuenta_corriente_de_cliente(
    cliente_id: UUID,
    contexto: Annotated[ContextoAutenticado, Depends(requiere_permiso(PERMISO))],
    sesion: Annotated[Session, Depends(get_session)],
    desde: date | None = None,
    hasta: date | None = None,
    cursor: str | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EstadoDeCuentaResponse:
    """Estado de cuenta del cliente (change 08, tarea 6.2; CC-07, `design.md`
    D2 y D9). Permiso `GESTIONAR_CLIENTES`, el mismo de la ficha: quien puede ver
    al cliente puede ver su cuenta. `desde`/`hasta` son fechas de negocio en la
    zona de la organización; un `limite` mayor que 200 es un error de validación
    (422), no un recorte silencioso.

    404 para un cliente de otra organización o inexistente (INV-21, SEG-07): se
    comprueba ANTES de leer el libro, así que la respuesta no revela saldo ni
    movimientos ajenos."""
    cliente = clientes_service.obtener_cliente_por_id(contexto.organizacion_id, cliente_id, sesion)
    if cliente is None:
        raise RecursoNoEncontradoError(f"El cliente {cliente_id} no existe en esta organización.")
    estado = cuentas_corrientes_service.estado_de_cuenta(
        contexto.organizacion_id,
        sesion,
        cuenta_tipo="CLIENTE",
        entidad_id=cliente_id,
        desde=desde,
        hasta=hasta,
        cursor=cursor,
        limite=limite,
    )
    return estado_de_cuenta_response(estado)
