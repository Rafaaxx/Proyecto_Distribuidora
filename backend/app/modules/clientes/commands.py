"""Handlers de comandos de `clientes` (change 07, grupo 3, tareas 3.1 a 3.5;
`design.md` D3, D4, D7, D8, D9 -- plantilla D7 del change 04: un tipo de
comando por escritura ya existente en `service.py`, un esquema de contenido
versión 1, un handler de pocas líneas que llama al servicio, sin `commit`
propio, que lo gestiona el bus).

Cuatro tipos, todos `ONLINE` y `admite_offline=False`, por el mismo motivo que
`proveedores/commands.py`: los cuatro exigen `sesion` y `reloj` como parámetros
de palabra clave obligatorios y escriben en la base del servidor.

- `CLIENTE_CREAR`, `CLIENTE_MODIFICAR` -- ficha, permiso `GESTIONAR_CLIENTES`.
- `CLIENTE_CREDITO_MODIFICAR` -- crédito, permiso `GESTIONAR_CREDITO` (D3).
- `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` -- permiso `ADMIN_CONFIGURACION` (D4).

FICHA Y CRÉDITO SON DOS COMANDOS Y NO UNO, y eso se ve en tres capas. En el
catálogo son dos tipos con dos permisos. En los esquemas, los campos de crédito
no existen en los de ficha y `extra="forbid"` convierte un `limite_credito`
mandado por error en `CONTENIDO_DE_COMANDO_INVALIDO` en vez de descartarlo en
silencio. Y en `service.py` son dos funciones con dos permisos distintos.

Mismo criterio que `catalogo/commands.py` (D6 del 05): los handlers NO atrapan
errores de dominio, los dejan subir; el bus (`sync/service.py::procesar_comando`)
revierte toda la transacción, incluida la reserva del `operation_id` y
cualquier auditoría escrita, y el comando puede reintentarse con contenido
corregido.

Los ids de clientes nuevos se generan en el servidor (UUIDv7, `core/ids.py`,
dentro de `clientes/service.py`) y se devuelven en el resultado del comando.

Sobre el permiso, que en los changes anteriores se exigía en la capa de API:
acá no hay API (change 07 grupo 4, todavía no llega) y el bus recibe lotes con
tipos distintos, así que no hay un permiso único que declarar en la ruta. El
punto donde sí se puede comprobar es el handler, que es lo que
`app/modules/sync/api.py` deja asentado para `SEG-06` (`docs/02-arquitectura.md`
§6.3 paso 4): "la validación de permisos por comando es responsabilidad del
handler resuelto por `app.commands.registro` para cada tipo". `catalogo.py` no
modela permisos y `SobreComando` no los transporta, así que se comprueba contra
`identidad_service.listar_permisos_del_usuario`, que es el único punto de
lectura de permisos del sistema y falla cerrada (conjunto vacío si el usuario
no está, está `INACTIVO` o su rol está inactivo).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.clientes import service as clientes_service
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.identidad import service as identidad_service

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler` (ver
`catalogo/commands.py` para la justificación de no importarla de `sync`)."""


def _exigir_permiso(sobre: SobreComando, sesion: object, codigo_permiso: str) -> None:
    """Falla con 403 `PERMISO_REQUERIDO` si el usuario del sobre no tiene el
    permiso (INV-01, `docs/01-dominio.md` §permisos).

    Va PRIMERO en cada handler, antes de leer o escribir nada: un rechazo de
    permiso no puede dejar un cliente creado a medias ni una configuración
    cambiada, aunque la transacción del bus llegue a revertirse."""
    permitidos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,  # type: ignore[arg-type]
    )
    if codigo_permiso not in permitidos:
        raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")


class ContenidoClienteV1(BaseModel):
    """Base de los contenidos de ficha. `extra="forbid"` es lo que hace que la
    separación de D3 sea real: Pydantic ignora por defecto lo que no
    reconoce, así que sin esto un `limite_credito` enviado por error al comando
    de ficha se perdería en silencio en vez de rechazarse."""

    model_config = ConfigDict(extra="forbid")


# --- CLIENTE_CREAR (D7, D3, CLI-01) -----------------------------------------


class ClienteCrearContenidoV1(ContenidoClienteV1):
    """La ficha mínima de `CLI-01`. `estado` NO se acepta: el cliente nace
    `ACTIVO` (D7) y la transición de estado se pide en `CLIENTE_MODIFICAR`.
    `es_consumidor_final` tampoco: esa marca solo la pone
    `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` (CLI-03), que además es el único que
    puede hacerlo porque escribe la configuración de la organización.

    `lista_precio_id` NO está, aunque la columna exista (D2): la tabla
    `lista_precio` no se crea hasta el change 13, así que el valor no se puede
    validar y la mitigación de D2 es que la columna "no se ofrece en ningún
    formulario" hasta que exista la FK compuesta. Un `uuid` sin destino sería
    un dato que el usuario escribe y nadie puede confirmar."""

    nombre: str
    direccion: str
    contacto: str
    razon_social: str | None = None
    documento_tipo: str | None = None
    documento_numero: str | None = None
    telefono: str | None = None
    email: str | None = None
    codigo: str | None = None
    estado_facturacion_default: str | None = None


def manejar_cliente_crear(
    sobre: SobreComando, contenido: ClienteCrearContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, "GESTIONAR_CLIENTES")
    cliente = clientes_service.crear_cliente(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        direccion=contenido.direccion,
        contacto=contenido.contacto,
        razon_social=contenido.razon_social,
        documento_tipo=contenido.documento_tipo,
        documento_numero=contenido.documento_numero,
        telefono=contenido.telefono,
        email=contenido.email,
        codigo=contenido.codigo,
        estado_facturacion_default=contenido.estado_facturacion_default,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"cliente_id": str(cliente.id)}, None


registrar_handler("CLIENTE_CREAR", 1, ClienteCrearContenidoV1)(
    manejar_cliente_crear  # type: ignore[arg-type]
)
declarar_tipo("CLIENTE_CREAR", admite_online=True, admite_offline=False)


# --- CLIENTE_MODIFICAR (D7, máquina de estados de `docs/01` §18) -----------


class ClienteModificarContenidoV1(ContenidoClienteV1):
    """`estado` es obligatorio porque modificar la ficha y cambiar el estado
    son la misma escritura: el cliente tiene que poder quedar `INACTIVO` en el
    mismo comando que le corrige la dirección. Lo que NO va aquí es el crédito
    (D3) ni la marca de consumidor final (CLI-03).

    Tampoco `lista_precio_id`, por la misma mitigación de D2 que en el alta."""

    cliente_id: UUID
    nombre: str
    direccion: str
    contacto: str
    estado: str
    razon_social: str | None = None
    documento_tipo: str | None = None
    documento_numero: str | None = None
    telefono: str | None = None
    email: str | None = None
    codigo: str | None = None
    estado_facturacion_default: str | None = None


def manejar_cliente_modificar(
    sobre: SobreComando, contenido: ClienteModificarContenidoV1, *, sesion: object, reloj: Clock
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, "GESTIONAR_CLIENTES")
    cliente = clientes_service.modificar_cliente(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        cliente_id=contenido.cliente_id,
        nombre=contenido.nombre,
        direccion=contenido.direccion,
        contacto=contenido.contacto,
        estado=contenido.estado,
        razon_social=contenido.razon_social,
        documento_tipo=contenido.documento_tipo,
        documento_numero=contenido.documento_numero,
        telefono=contenido.telefono,
        email=contenido.email,
        codigo=contenido.codigo,
        estado_facturacion_default=contenido.estado_facturacion_default,
        actor_id=sobre.usuario_id,
        # CLI-06 activo (change 08, D8): un cliente tiene operaciones si su
        # cuenta corriente tiene algun movimiento. Se consulta dentro del
        # servicio, con la fila del cliente ya bloqueada.
        verificar_operaciones=lambda: cuentas_corrientes_service.cuenta_tiene_movimientos(
            sobre.organizacion_id,
            sesion,  # type: ignore[arg-type]
            cuenta_tipo="CLIENTE",
            entidad_id=contenido.cliente_id,
        ),
    )
    return "ACEPTADO", {"cliente_id": str(cliente.id)}, None


registrar_handler("CLIENTE_MODIFICAR", 1, ClienteModificarContenidoV1)(
    manejar_cliente_modificar  # type: ignore[arg-type]
)
declarar_tipo("CLIENTE_MODIFICAR", admite_online=True, admite_offline=False)


# --- CLIENTE_CREDITO_MODIFICAR (D3, D8, CRE-01, CRE-03, CRE-06, AUD-01) ---


class ClienteCreditoModificarContenidoV1(ContenidoClienteV1):
    """Sólo los tres campos de crédito más el cliente al que se aplican. Los
    importes viajan como string y Pydantic los valida como `Decimal` sin pasar
    por `float` (`CLAUDE.md` §4).

    Los tres son opcionales porque `None` significa HEREDAR (CRE-03, CRE-06),
    no "dejar como está": un comando con los tres en `None` deja el crédito
    delegando en la organización. Para no cambiar nada hay que mandar el
    contenido con el `cliente_id` solo... lo cual no limpia el crédito sino que
    lo deja heredando. Es la semántica de D8 y por eso los tres son opcionales
    y ninguno tiene valor por defecto distinto de `None`."""

    cliente_id: UUID
    limite_credito: Decimal | None = None
    politica_credito: str | None = None
    tolerancia_offline_tipo: str | None = None
    tolerancia_offline_valor: Decimal | None = None


def manejar_cliente_credito_modificar(
    sobre: SobreComando,
    contenido: ClienteCreditoModificarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    _exigir_permiso(sobre, sesion, "GESTIONAR_CREDITO")
    cliente = clientes_service.modificar_credito_cliente(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        cliente_id=contenido.cliente_id,
        limite_credito=contenido.limite_credito,
        politica_credito=contenido.politica_credito,
        tolerancia_offline_tipo=contenido.tolerancia_offline_tipo,
        tolerancia_offline_valor=contenido.tolerancia_offline_valor,
        actor_id=sobre.usuario_id,
        operation_id=sobre.operation_id,
        dispositivo_id=sobre.dispositivo_id,
    )
    return "ACEPTADO", {"cliente_id": str(cliente.id)}, None


registrar_handler("CLIENTE_CREDITO_MODIFICAR", 1, ClienteCreditoModificarContenidoV1)(
    manejar_cliente_credito_modificar  # type: ignore[arg-type]
)
declarar_tipo("CLIENTE_CREDITO_MODIFICAR", admite_online=True, admite_offline=False)


# --- CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR (D4, ADR-029) --------------------


class ClienteConsumidorFinalConfigurarContenidoV1(ContenidoClienteV1):
    """Sólo el nombre, y por un motivo concreto: el consumidor final es un
    cliente de la organización, no un cliente que el usuario elige
    (ADR-029). No se manda `direccion` ni `contacto` porque se completan con
    valores genéricos que son dato de la organización, y no se manda
    `cliente_id` porque el cliente lo crea este mismo comando: aceptar un id
    haría que la segunda invocación apuntara a un cliente existente en vez de
    rechazarse con `CONSUMIDOR_FINAL_YA_HABILITADO`."""

    nombre: str


def manejar_cliente_consumidor_final_configurar(
    sobre: SobreComando,
    contenido: ClienteConsumidorFinalConfigurarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    # D4: `ADMIN_CONFIGURACION` y no `GESTIONAR_CLIENTES` porque este comando
    # no solo crea un cliente, además escribe `configuracion_organizacion`. Es
    # la misma razón por la que subir el límite de crédito de toda la
    # organización es otro permiso: lo que se toca es la organización.
    _exigir_permiso(sobre, sesion, "ADMIN_CONFIGURACION")
    cliente = clientes_service.configurar_consumidor_final(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        nombre=contenido.nombre,
        actor_id=sobre.usuario_id,
    )
    return "ACEPTADO", {"cliente_id": str(cliente.id)}, None


registrar_handler(
    "CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR", 1, ClienteConsumidorFinalConfigurarContenidoV1
)(
    manejar_cliente_consumidor_final_configurar  # type: ignore[arg-type]
)
declarar_tipo("CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR", admite_online=True, admite_offline=False)
