"""Handlers de comandos de `identidad` (change 04, grupo 11 y grupo 14;
`design.md` D7): envuelven las cinco escrituras que quedaron fuera del bus
(`identidad/service.py::crear_usuario`, `revocar_dispositivo`,
`establecer_pin_autorizacion` -- grupo 11 -- y `cambiar_composicion_rol`,
`desbloquear_usuario` -- grupo 14, decisión del usuario 2026-09-22, ver
`tasks.md` 14.3 -- sin tocar su cuerpo más allá del parámetro `auditar`
(D7: "se cumple literalmente"; ADR-022 es la única excepción permitida).

**Plantilla de referencia para los changes 05-27** (D7): por cada
operación, un tipo de comando `ENTIDAD_ACCION` (singular, español,
mayúsculas, verbo en infinitivo), un esquema Pydantic de contenido versión
1, un handler que llama al método de servicio existente con `auditar=False`
(ADR-022: la fila de auditoría la deja el bus, `sync/service.py::
procesar_comando`, grupo 10), y `registrar_handler` + `declarar_tipo` acá.

**Nota técnica sobre la firma del handler** (gap conocido del mecanismo,
reportado, no resuelto en silencio): `app.commands.registro.HandlerFuncion`
es `Callable[[SobreComando, BaseModel], object]` -- dos argumentos, sin
`Session` ni `Clock`. Eso alcanza para el despacho genérico de
`sync.service._procesar_item_de_lote` (grupo 8, lote `OFFLINE`), que en
efecto NO pasa la sesión al handler registrado. Pero un handler real de
negocio, como los tres de este módulo, necesita la sesión (para llamar al
servicio) y el reloj (para pasárselo tal cual, sin crear uno nuevo, y que
`occurred_en`/auditoría usen el mismo momento en toda la operación). Los
tres endpoints de este módulo (`identidad/api.py`) NO pasan por
`_procesar_item_de_lote`: son escrituras `ONLINE` directas (D4) que llaman
`sync_service.procesar_comando` ellos mismos, exactamente como el arnés de
`tests/integration/test_bus_entrada_rest.py`. Por eso cada handler de este
módulo declara `sesion`/`reloj` como parámetros de palabra clave
OBLIGATORIOS (sin default): un handler real no puede ejecutar sin ellos, y
un default falso escondería el error en vez de fallar en el momento del
llamado. La llamada a `registrar_handler` (más abajo) los registra con un
`# type: ignore[arg-type]` justificado, no un `Any`: es la firma real de
la función, más específica de lo que `HandlerFuncion` modela, no menos --
mypy no puede verificarla porque el tipo genérico no la contempla, pero
ningún llamador real de este módulo pierde precisión de tipos (esta
función nunca se invoca a través de `handler_registrado.funcion` con solo
dos argumentos; los tres endpoints la importan e invocan directamente con
los cuatro). Consistente con que los tres tipos declaran
`admite_offline=False`: nunca llegarán por el lote de `/sync/comandos`,
así que el llamado de dos argumentos de `_procesar_item_de_lote` nunca se
ejercita contra estos handlers.

Si esta forma de wiring no sirviera para un change futuro que sí necesite
despachar un handler de maestros desde el lote `OFFLINE`, es señal de que
`HandlerFuncion`/`_procesar_item_de_lote` (grupos 4/8) necesitan resolver
esto de raíz -- no se ajusta acá, fuera del alcance de este grupo.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, StrictBool

from app.commands.catalogo import declarar_tipo
from app.commands.registro import SesionDeHandler, registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import PERMISOS_AUTORIZACION_EXCEPCION
from app.modules.identidad.domain.valores import computa_credito_fiscal
from app.modules.identidad.models import Rol, Usuario

ResultadoHandler = tuple[str, dict[str, object] | None, str | None]
"""Misma convención que `sync/service.py::ResultadoHandler`: `(estado,
resultado, error_codigo)`. No se importa de `sync` (`app.commands`/los
handlers de un módulo de negocio no dependen de `sync`; se declara acá,
estructuralmente idéntica, a propósito -- `commands-no-modulos` prohibiría
lo contrario si este módulo fuera `app.commands`, y aunque `identidad` SÍ
puede importar de otros módulos, evitamos el acoplamiento innecesario a
un tipo interno de `sync` por una tupla de 3 elementos)."""


# --- USUARIO_CREAR (D7, envuelve `identidad_service.crear_usuario`) --------


class UsuarioCrearContenidoV1(BaseModel):
    """Los datos del alta, SIN la contraseña (change 18b, `design.md` D2 y D23, ADR-056): la ruta
    la separa del cuerpo antes de armar el contenido y la huella y la entrega al handler por
    clausura como `SecretStr`. Así no entra a la huella (recuperable por fuerza bruta si
    estuviera), a `comando`, a `comando_cuarentena`, a la auditoría, al resultado ni al `input` de
    un error de validación. `extra="forbid"`: un contenido con `password` adentro (cliente viejo)
    es malformado."""

    model_config = ConfigDict(extra="forbid")

    usuario: str
    nombre: str
    email: str | None = None
    rol_id: UUID


def manejar_usuario_crear(
    sobre: SobreComando,
    contenido: UsuarioCrearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
    password: SecretStr,
) -> ResultadoHandler:
    """Handler de `USUARIO_CREAR` v1 (D7). `actor_id`/`dispositivo_id_actor`
    salen del sobre (contexto del token), nunca del contenido -- el
    contenido solo trae los datos propios del alta. `password` es el dato efímero de D2: llega por
    clausura desde la ruta y `.get_secret_value()` se llama UNA sola vez, donde el servicio lo
    deriva. `auditar=False` (ADR-022): la única fila de auditoría de este comando la deja
    `sync_service.procesar_comando` (grupo 10), no este handler."""
    # Change 20b, D4: el alta toma la exclusión mutua de identidad (y revalida a quien ejecuta)
    # antes de leer el rol o el nombre: un alta en un rol que se está dando de baja ve el rol
    # inactivo, y dos altas del mismo nombre se serializan.
    identidad_service.bloquear_organizacion_para_identidad(
        sobre.organizacion_id, sesion, actor_id=sobre.usuario_id
    )
    usuario = identidad_service.crear_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario=contenido.usuario,
        nombre=contenido.nombre,
        email=contenido.email,
        password=password.get_secret_value(),
        rol_id=contenido.rol_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        auditar=False,
    )
    if usuario is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


# `password` es un parámetro más que `HandlerFuncion` no modela (dato efímero por clausura, D2): el
# lote nunca invoca este handler porque el tipo se declara `exige_credenciales_efimeras`.
registrar_handler("USUARIO_CREAR", 1, UsuarioCrearContenidoV1)(
    manejar_usuario_crear  # type: ignore[arg-type]
)
declarar_tipo(
    "USUARIO_CREAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_USUARIOS",),
    exige_credenciales_efimeras=True,
)


# --- DISPOSITIVO_REVOCAR (D7, envuelve `identidad_service.revocar_dispositivo`) --


class DispositivoRevocarContenidoV1(BaseModel):
    dispositivo_id: UUID


def manejar_dispositivo_revocar(
    sobre: SobreComando,
    contenido: DispositivoRevocarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `DISPOSITIVO_REVOCAR` v1 (D7). `dispositivo_id_actor` (el
    dispositivo desde el que se autentica quien revoca) sale de
    `sobre.dispositivo_id` -- el dispositivo A REVOCAR es el del contenido,
    un dato distinto (`identidad_service.revocar_dispositivo`, docstring)."""
    dispositivo = identidad_service.revocar_dispositivo(
        sobre.organizacion_id,
        sesion,
        reloj,
        dispositivo_id=contenido.dispositivo_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        auditar=False,
    )
    if dispositivo is None:
        return "RECHAZADO", None, "DISPOSITIVO_NO_ENCONTRADO"
    return "ACEPTADO", {"dispositivo_id": str(dispositivo.id), "estado": dispositivo.estado}, None


registrar_handler("DISPOSITIVO_REVOCAR", 1, DispositivoRevocarContenidoV1)(
    manejar_dispositivo_revocar
)
declarar_tipo(
    "DISPOSITIVO_REVOCAR",
    admite_online=True,
    admite_offline=False,
    permisos=("GESTIONAR_DISPOSITIVOS",),
)


# --- PIN_AUTORIZACION_ROTAR (D7, envuelve `establecer_pin_autorizacion`) ----


class PinAutorizacionRotarContenidoV1(BaseModel):
    """El contenido lleva solo `usuario_id`. El PIN NO está acá (change 18b, `design.md` D2 y
    D21): la ruta lo separa del cuerpo antes de armar el contenido y la huella y lo entrega al
    handler por clausura como `SecretStr`. Así no entra a la huella (recuperable por fuerza bruta
    si estuviera), a `comando`, a `comando_cuarentena`, a la auditoría, al resultado ni al
    `input` de un error de validación. `extra="forbid"`: un contenido con `pin` adentro (cliente
    viejo) es malformado. La validación de formato del PIN (longitud, solo dígitos, no trivial)
    vive en `identidad/domain/usuarios.py::validar_formato_pin_autorizacion` y nunca incluye el
    valor en su mensaje; ningún `field_validator` sobre el secreto (lección del change 04)."""

    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID


def manejar_pin_autorizacion_rotar(
    sobre: SobreComando,
    contenido: PinAutorizacionRotarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
    pin: SecretStr,
) -> ResultadoHandler:
    """Handler de `PIN_AUTORIZACION_ROTAR` v1 (D7). `pin` es el dato efímero de D2: llega por
    clausura desde la ruta, `.get_secret_value()` se llama UNA sola vez, en el punto exacto en
    que el servicio lo necesita, y nunca se loguea ni se incluye en el resultado."""
    usuario = identidad_service.establecer_pin_autorizacion(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        pin=pin.get_secret_value(),
        actor_id=sobre.usuario_id,
        auditar=False,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


# `pin` es un parámetro más que `HandlerFuncion` no modela (dato efímero por clausura, D2): el
# lote nunca invoca este handler porque el tipo se declara `exige_credenciales_efimeras`.
registrar_handler("PIN_AUTORIZACION_ROTAR", 1, PinAutorizacionRotarContenidoV1)(
    manejar_pin_autorizacion_rotar  # type: ignore[arg-type]
)
declarar_tipo(
    "PIN_AUTORIZACION_ROTAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_USUARIOS",),
    exige_credenciales_efimeras=True,
)


# --- PIN_AUTORIZACION_PROPIO_DEFINIR ("Mi PIN", change 18b, D21 parte B) ---------------------


class PinAutorizacionPropioDefinirContenidoV1(BaseModel):
    """Contenido VACÍO (`extra="forbid"`): el usuario sale del token, nunca del cuerpo, y el PIN y
    la contraseña actual viajan como dato efímero por clausura (D2, D21 punto 3), así que no
    están en la huella, `comando`, la auditoría, el resultado ni los registros. Ningún
    `field_validator` sobre los secretos (lección del change 04)."""

    model_config = ConfigDict(extra="forbid")


def manejar_pin_autorizacion_propio_definir(
    sobre: SobreComando,
    contenido: PinAutorizacionPropioDefinirContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
    password_actual: SecretStr,
    pin: SecretStr,
    ip: str,
) -> ResultadoHandler:
    """Handler de `PIN_AUTORIZACION_PROPIO_DEFINIR` v1. `password_actual`, `pin` e `ip` llegan por
    clausura desde la ruta (`POST /api/v1/yo/pin-autorizacion`). El servicio verifica la
    contraseña con el límite del login, valida el PIN y lo deriva; todo rechazo lanza una
    excepción de dominio (nunca devuelve `RECHAZADO`). El resultado no lleva secretos."""
    usuario = identidad_service.definir_pin_propio(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=sobre.usuario_id,
        password_actual=password_actual.get_secret_value(),
        pin=pin.get_secret_value(),
        ip=ip,
        dispositivo_id=sobre.dispositivo_id,
    )
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


# Como `PIN_AUTORIZACION_ROTAR`: parámetros efímeros que `HandlerFuncion` no modela; el lote
# rechaza el tipo (`exige_credenciales_efimeras`). Solo `ONLINE`.
registrar_handler("PIN_AUTORIZACION_PROPIO_DEFINIR", 1, PinAutorizacionPropioDefinirContenidoV1)(
    manejar_pin_autorizacion_propio_definir  # type: ignore[arg-type]
)
declarar_tipo(
    "PIN_AUTORIZACION_PROPIO_DEFINIR",
    admite_online=True,
    admite_offline=False,
    permisos=tuple(sorted(PERMISOS_AUTORIZACION_EXCEPCION)),
    exige_credenciales_efimeras=True,
)


# --- ROL_PERMISOS_CAMBIAR (grupo 14, envuelve
# `identidad_service.cambiar_composicion_rol`) --------------------------


class RolPermisosCambiarContenidoV1(BaseModel):
    rol_id: UUID
    permisos: list[str]


def manejar_rol_permisos_cambiar(
    sobre: SobreComando,
    contenido: RolPermisosCambiarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_PERMISOS_CAMBIAR` v1 (grupo 14, D7). `auditar=False`
    (ADR-022): la única fila de auditoría de este comando la deja
    `sync_service.procesar_comando`, no este handler."""
    rol = identidad_service.cambiar_composicion_rol(
        sobre.organizacion_id,
        sesion,
        reloj,
        rol_id=contenido.rol_id,
        permisos_nuevos=frozenset(contenido.permisos),
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        auditar=False,
    )
    if rol is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return "ACEPTADO", {"rol_id": str(rol.id)}, None


registrar_handler("ROL_PERMISOS_CAMBIAR", 1, RolPermisosCambiarContenidoV1)(
    manejar_rol_permisos_cambiar
)
declarar_tipo(
    "ROL_PERMISOS_CAMBIAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- USUARIO_DESBLOQUEAR (grupo 14, envuelve
# `identidad_service.desbloquear_usuario`) -------------------------------


class UsuarioDesbloquearContenidoV1(BaseModel):
    usuario_id: UUID


def manejar_usuario_desbloquear(
    sobre: SobreComando,
    contenido: UsuarioDesbloquearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_DESBLOQUEAR` v1 (grupo 14, D7, `ADR-018`).
    `auditar=False` (ADR-022): la única fila de auditoría de este comando la
    deja `sync_service.procesar_comando`, no este handler."""
    usuario = identidad_service.desbloquear_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        actor_id=sobre.usuario_id,
        auditar=False,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


registrar_handler("USUARIO_DESBLOQUEAR", 1, UsuarioDesbloquearContenidoV1)(
    manejar_usuario_desbloquear
)
declarar_tipo(
    "USUARIO_DESBLOQUEAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- ORGANIZACION_CONDICION_IVA_CAMBIAR (11b, D7, CST-06, envuelve
# `identidad_service.cambiar_condicion_iva`) --------------------------------


class OrganizacionCondicionIvaCambiarContenidoV1(BaseModel):
    """Solo la condición nueva. `organizacion_id` sale del sobre (token), nunca del
    contenido. Es un `str`: el dominio cerrado lo valida `validar_condicion_iva` con su
    error de dominio (422)."""

    condicion_iva: str


def manejar_organizacion_condicion_iva_cambiar(
    sobre: SobreComando,
    contenido: OrganizacionCondicionIvaCambiarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ORGANIZACION_CONDICION_IVA_CAMBIAR` v1 (D7). El permiso se exige acá,
    PRIMERO (`ADMIN_CONFIGURACION`, mismo criterio que `CLIENTE_CONSUMIDOR_FINAL_
    CONFIGURAR`: lo que se toca es la organización, SEG-06). El resultado lleva la
    configuración fiscal vigente tras el cambio: un reenvío idempotente devuelve exactamente
    esto (INV-06)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,
    )
    if "ADMIN_CONFIGURACION" not in permisos:
        raise PermisoRequeridoError("Falta el permiso ADMIN_CONFIGURACION.")

    configuracion = identidad_service.cambiar_condicion_iva(
        sobre.organizacion_id,
        sesion,
        reloj,
        condicion_nueva=contenido.condicion_iva,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if configuracion is None:
        return "RECHAZADO", None, "ORGANIZACION_NO_ENCONTRADA"
    return (
        "ACEPTADO",
        {
            "condicion_iva": configuracion.condicion_iva,
            "computa_credito_fiscal": computa_credito_fiscal(configuracion.condicion_iva),
            "modo_impositivo": configuracion.modo_impositivo,
            "modalidad_iva_default": configuracion.modalidad_iva_default,
        },
        None,
    )


registrar_handler(
    "ORGANIZACION_CONDICION_IVA_CAMBIAR", 1, OrganizacionCondicionIvaCambiarContenidoV1
)(manejar_organizacion_condicion_iva_cambiar)
declarar_tipo(
    "ORGANIZACION_CONDICION_IVA_CAMBIAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)


# --- ROL_TOPE_DESCUENTO_DEFINIR (change 16, D13, DSC-06, envuelve
# `identidad_service.definir_tope_descuento_de_rol`) -----------------------


class RolTopeDescuentoDefinirContenidoV1(BaseModel):
    """El rol y su tope nuevo. `organizacion_id` sale del sobre (token), nunca del contenido. El
    tope es un `str`: un número JSON no es válido (INV-03) y el rango lo valida el dominio con su
    error (422)."""

    rol_id: UUID
    tope_descuento: str


def manejar_rol_tope_descuento_definir(
    sobre: SobreComando,
    contenido: RolTopeDescuentoDefinirContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_TOPE_DESCUENTO_DEFINIR` v1 (D13). El permiso se exige acá, PRIMERO
    (`ADMIN_USUARIOS`, el de la composición de roles; SEG-06). `auditar` no existe: la auditoría
    con valor anterior y nuevo es la del servicio (mismo patrón que `cambiar_condicion_iva`). El
    resultado lleva el rol tal como quedó: un reenvío idempotente devuelve exactamente esto
    (INV-06)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id,
        sobre.usuario_id,
        sesion,
    )
    if "ADMIN_USUARIOS" not in permisos:
        raise PermisoRequeridoError("Falta el permiso ADMIN_USUARIOS.")

    rol = identidad_service.definir_tope_descuento_de_rol(
        sobre.organizacion_id,
        sesion,
        reloj,
        rol_id=contenido.rol_id,
        tope_nuevo=contenido.tope_descuento,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if rol is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return (
        "ACEPTADO",
        {
            "rol_id": str(rol.id),
            "nombre": rol.nombre,
            "activo": rol.activo,
            "tope_descuento": f"{rol.tope_descuento:.6f}",
        },
        None,
    )


registrar_handler("ROL_TOPE_DESCUENTO_DEFINIR", 1, RolTopeDescuentoDefinirContenidoV1)(
    manejar_rol_tope_descuento_definir
)
declarar_tipo(
    "ROL_TOPE_DESCUENTO_DEFINIR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_USUARIOS",),
)


# --- DESCUENTO_MANUAL_CONFIGURAR (change 18b, D13, DSC-06, envuelve
# `identidad_service.configurar_descuento_manual`) ---------------------------


class DescuentoManualConfigurarContenidoV1(BaseModel):
    """Los dos booleanos, obligatorios y estrictos: un texto, un número o un nulo no son un
    booleano (DSC-06). `organizacion_id` sale del sobre (token), nunca del contenido, y
    `extra="forbid"` rechaza cualquier campo que el comando no define."""

    model_config = ConfigDict(extra="forbid")

    habilitado: StrictBool
    motivo_obligatorio: StrictBool


def manejar_descuento_manual_configurar(
    sobre: SobreComando,
    contenido: DescuentoManualConfigurarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `DESCUENTO_MANUAL_CONFIGURAR` v1 (D13). El permiso se exige acá, PRIMERO
    (`ADMIN_CONFIGURACION`, SEG-06). La auditoría con valor anterior y nuevo es la del servicio.
    El resultado lleva lo que quedó: un reenvío idempotente devuelve exactamente esto (INV-06)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if "ADMIN_CONFIGURACION" not in permisos:
        raise PermisoRequeridoError("Falta el permiso ADMIN_CONFIGURACION.")

    configuracion = identidad_service.configurar_descuento_manual(
        sobre.organizacion_id,
        sesion,
        reloj,
        habilitado=contenido.habilitado,
        motivo_obligatorio=contenido.motivo_obligatorio,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if configuracion is None:
        return "RECHAZADO", None, "ORGANIZACION_NO_ENCONTRADA"
    return (
        "ACEPTADO",
        {
            "habilitado": configuracion.descuento_manual_habilitado,
            "motivo_obligatorio": bool(configuracion.motivo_obligatorio_descuento),
        },
        None,
    )


registrar_handler("DESCUENTO_MANUAL_CONFIGURAR", 1, DescuentoManualConfigurarContenidoV1)(
    manejar_descuento_manual_configurar
)
declarar_tipo(
    "DESCUENTO_MANUAL_CONFIGURAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)


# --- CREDITO_ORGANIZACION_CONFIGURAR (change 18b, D14, CRE-03, CRE-06, envuelve
# `identidad_service.configurar_credito_organizacion`) -----------------------


class CreditoOrganizacionConfigurarContenidoV1(BaseModel):
    """Política por defecto y tolerancia sin conexión de la organización. Los tres campos son
    obligatorios (la tolerancia vacía se expresa con `null` en los dos): así un comando nunca
    borra la tolerancia por omisión. El valor viaja como texto (INV-03); la política y el tipo
    fuera del catálogo se rechazan como contenido inválido, y la pareja a medias o el valor
    inválido, en el dominio con `TOLERANCIA_OFFLINE_INVALIDA`."""

    model_config = ConfigDict(extra="forbid")

    politica: Literal["ADVERTIR", "AUTORIZAR", "BLOQUEAR"]
    tolerancia_tipo: Literal["IMPORTE", "PORCENTAJE"] | None
    tolerancia_valor: str | None


def manejar_credito_organizacion_configurar(
    sobre: SobreComando,
    contenido: CreditoOrganizacionConfigurarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `CREDITO_ORGANIZACION_CONFIGURAR` v1 (D14). Permiso `ADMIN_CONFIGURACION`
    primero (SEG-06). El resultado lleva la configuración vigente tras el cambio (INV-06)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if "ADMIN_CONFIGURACION" not in permisos:
        raise PermisoRequeridoError("Falta el permiso ADMIN_CONFIGURACION.")

    configuracion = identidad_service.configurar_credito_organizacion(
        sobre.organizacion_id,
        sesion,
        reloj,
        politica=contenido.politica,
        tolerancia_tipo=contenido.tolerancia_tipo,
        tolerancia_valor=contenido.tolerancia_valor,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if configuracion is None:
        return "RECHAZADO", None, "ORGANIZACION_NO_ENCONTRADA"
    valor = configuracion.tolerancia_offline_valor
    return (
        "ACEPTADO",
        {
            "politica": configuracion.politica_credito_default,
            "tolerancia_tipo": configuracion.tolerancia_offline_tipo,
            "tolerancia_valor": None if valor is None else f"{valor:.2f}",
        },
        None,
    )


registrar_handler("CREDITO_ORGANIZACION_CONFIGURAR", 1, CreditoOrganizacionConfigurarContenidoV1)(
    manejar_credito_organizacion_configurar
)
declarar_tipo(
    "CREDITO_ORGANIZACION_CONFIGURAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)


# --- NOTA_VENTA_CONFIGURAR (change 20, D10, VTA-13, envuelve
# `identidad_service.configurar_nota_de_venta`) --------------------------------


class NotaVentaConfigurarContenidoV1(BaseModel):
    """Parámetros de la nota de venta. Los tres campos son obligatorios (domicilio y teléfono
    vacíos se expresan con `null` o con texto en blanco, que se normaliza a nulo): así un comando
    nunca borra un dato por omisión. `muestra_saldo` es booleano estricto."""

    model_config = ConfigDict(extra="forbid")

    muestra_saldo: StrictBool
    domicilio: str | None
    telefono: str | None


def manejar_nota_venta_configurar(
    sobre: SobreComando,
    contenido: NotaVentaConfigurarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `NOTA_VENTA_CONFIGURAR` v1 (D10). Permiso `ADMIN_CONFIGURACION` primero
    (SEG-06). El resultado lleva la configuración vigente tras el cambio (INV-06)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if "ADMIN_CONFIGURACION" not in permisos:
        raise PermisoRequeridoError("Falta el permiso ADMIN_CONFIGURACION.")

    configuracion = identidad_service.configurar_nota_de_venta(
        sobre.organizacion_id,
        sesion,
        reloj,
        muestra_saldo=contenido.muestra_saldo,
        domicilio=contenido.domicilio,
        telefono=contenido.telefono,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if configuracion is None:
        return "RECHAZADO", None, "ORGANIZACION_NO_ENCONTRADA"
    return (
        "ACEPTADO",
        {
            "muestra_saldo": configuracion.nota_venta_muestra_saldo,
            "domicilio": configuracion.nota_venta_domicilio,
            "telefono": configuracion.nota_venta_telefono,
        },
        None,
    )


registrar_handler("NOTA_VENTA_CONFIGURAR", 1, NotaVentaConfigurarContenidoV1)(
    manejar_nota_venta_configurar
)
declarar_tipo(
    "NOTA_VENTA_CONFIGURAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)


# --- ORGANIZACION_DATOS_CONFIGURAR (change 20, D15, VTA-13, envuelve
# `identidad_service.configurar_datos_de_organizacion`) -----------------------


class OrganizacionDatosConfigurarContenidoV1(BaseModel):
    """Nombre y CUIT de la organización. Ambos son obligatorios en el contenido (el CUIT vacío
    se expresa con `null` o con texto en blanco, que se normaliza a nulo): así un comando nunca
    borra un dato por omisión. `organizacion_id` sale del sobre (token), nunca del contenido."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    cuit: str | None


def manejar_organizacion_datos_configurar(
    sobre: SobreComando,
    contenido: OrganizacionDatosConfigurarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ORGANIZACION_DATOS_CONFIGURAR` v1 (D15). Permiso `ADMIN_CONFIGURACION`
    primero (SEG-06). El resultado lleva el nombre y el CUIT vigentes tras el cambio (INV-06)."""
    permisos = identidad_service.listar_permisos_del_usuario(
        sobre.organizacion_id, sobre.usuario_id, sesion
    )
    if "ADMIN_CONFIGURACION" not in permisos:
        raise PermisoRequeridoError("Falta el permiso ADMIN_CONFIGURACION.")

    organizacion = identidad_service.configurar_datos_de_organizacion(
        sobre.organizacion_id,
        sesion,
        reloj,
        nombre=contenido.nombre,
        cuit=contenido.cuit,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if organizacion is None:
        return "RECHAZADO", None, "ORGANIZACION_NO_ENCONTRADA"
    return "ACEPTADO", {"nombre": organizacion.nombre, "cuit": organizacion.cuit}, None


registrar_handler("ORGANIZACION_DATOS_CONFIGURAR", 1, OrganizacionDatosConfigurarContenidoV1)(
    manejar_organizacion_datos_configurar
)
declarar_tipo(
    "ORGANIZACION_DATOS_CONFIGURAR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_CONFIGURACION",),
)


# --- Administración de usuarios (change 20b, D1): un comando por acción -------------------------
#
# Todos `ONLINE`, `ADMIN_USUARIOS` (el bus lo exige en todo camino, ADR-056). `organizacion_id` y
# quien ejecuta salen del sobre (token), nunca del contenido. La auditoría de entidad con antes y
# después la escribe el servicio; la fila genérica del comando, el bus (ADR-022). Un usuario que
# no está en la organización responde `RECHAZADO` y la ruta lo traduce a 404 (INV-21, SEG-07).


def _resultado_de_usuario(usuario: Usuario) -> dict[str, object]:
    """Lo que devuelven los comandos de usuario: el usuario tal como quedó, sin `password_hash` ni
    PIN. Un reenvío idempotente devuelve exactamente esto (INV-06)."""
    tope = usuario.tope_descuento_override
    return {
        "usuario_id": str(usuario.id),
        "usuario": usuario.usuario,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol_id": str(usuario.rol_id),
        "estado": usuario.estado,
        "tope_descuento_override": None if tope is None else f"{tope:.6f}",
    }


# --- USUARIO_BAJA (D2, D3, D4, D5) --------------------------------------------------------------


class UsuarioBajaContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    observacion: str | None = None


def manejar_usuario_baja(
    sobre: SobreComando,
    contenido: UsuarioBajaContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_BAJA` v1."""
    usuario = identidad_service.dar_de_baja_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        observacion=contenido.observacion,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_usuario(usuario), None


registrar_handler("USUARIO_BAJA", 1, UsuarioBajaContenidoV1)(manejar_usuario_baja)
declarar_tipo(
    "USUARIO_BAJA", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- USUARIO_REACTIVAR (D2) ---------------------------------------------------------------------


class UsuarioReactivarContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID


def manejar_usuario_reactivar(
    sobre: SobreComando,
    contenido: UsuarioReactivarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_REACTIVAR` v1."""
    usuario = identidad_service.reactivar_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_usuario(usuario), None


registrar_handler("USUARIO_REACTIVAR", 1, UsuarioReactivarContenidoV1)(manejar_usuario_reactivar)
declarar_tipo(
    "USUARIO_REACTIVAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- Administración de roles (change 20b, D10, D11): crear, renombrar, baja y reactivación ------
#
# Todos `ONLINE`, `ADMIN_USUARIOS` (el bus lo exige en todo camino, ADR-056). `organizacion_id` y
# quien ejecuta salen del sobre (token). La auditoría de entidad la escribe el servicio; la fila
# genérica del comando, el bus (ADR-022). Un rol que no está en la organización responde
# `RECHAZADO` y la ruta lo traduce a 404 (INV-21, SEG-07).


def _resultado_de_rol(
    sobre: SobreComando, sesion: SesionDeHandler, rol: Rol, permisos: list[str] | None = None
) -> dict[str, object]:
    """Lo que devuelven los comandos de rol: el rol tal como quedó. Un reenvío idempotente devuelve
    exactamente esto (INV-06)."""
    if permisos is None:
        permisos = sorted(
            identidad_service.listar_permisos_de_un_rol(sobre.organizacion_id, rol.id, sesion)
        )
    return {
        "rol_id": str(rol.id),
        "nombre": rol.nombre,
        "activo": rol.activo,
        "tope_descuento": f"{rol.tope_descuento:.6f}",
        "permisos": permisos,
    }


class RolCrearContenidoV1(BaseModel):
    """Nombre, permisos y tope del rol nuevo (D10). El tope es un `str` (INV-03); por defecto 0."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    permisos: list[str]
    tope_descuento: str = "0"


def manejar_rol_crear(
    sobre: SobreComando,
    contenido: RolCrearContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_CREAR` v1."""
    rol, permisos = identidad_service.crear_rol_nuevo(
        sobre.organizacion_id,
        sesion,
        reloj,
        nombre=contenido.nombre,
        permisos=frozenset(contenido.permisos),
        tope_descuento=contenido.tope_descuento,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", _resultado_de_rol(sobre, sesion, rol, permisos), None


registrar_handler("ROL_CREAR", 1, RolCrearContenidoV1)(manejar_rol_crear)
declarar_tipo("ROL_CREAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",))


class RolRenombrarContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol_id: UUID
    nombre: str


def manejar_rol_renombrar(
    sobre: SobreComando,
    contenido: RolRenombrarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_RENOMBRAR` v1."""
    rol = identidad_service.renombrar_rol(
        sobre.organizacion_id,
        sesion,
        reloj,
        rol_id=contenido.rol_id,
        nombre=contenido.nombre,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if rol is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_rol(sobre, sesion, rol), None


registrar_handler("ROL_RENOMBRAR", 1, RolRenombrarContenidoV1)(manejar_rol_renombrar)
declarar_tipo(
    "ROL_RENOMBRAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


class RolBajaContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol_id: UUID


def manejar_rol_baja(
    sobre: SobreComando,
    contenido: RolBajaContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_BAJA` v1."""
    rol = identidad_service.dar_de_baja_rol(
        sobre.organizacion_id,
        sesion,
        reloj,
        rol_id=contenido.rol_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if rol is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_rol(sobre, sesion, rol), None


registrar_handler("ROL_BAJA", 1, RolBajaContenidoV1)(manejar_rol_baja)
declarar_tipo("ROL_BAJA", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",))


class RolReactivarContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol_id: UUID


def manejar_rol_reactivar(
    sobre: SobreComando,
    contenido: RolReactivarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_REACTIVAR` v1."""
    rol = identidad_service.reactivar_rol(
        sobre.organizacion_id,
        sesion,
        reloj,
        rol_id=contenido.rol_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if rol is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_rol(sobre, sesion, rol), None


registrar_handler("ROL_REACTIVAR", 1, RolReactivarContenidoV1)(manejar_rol_reactivar)
declarar_tipo(
    "ROL_REACTIVAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- USUARIO_MODIFICAR (D9) ---------------------------------------------------------------------


class UsuarioModificarContenidoV1(BaseModel):
    """Reemplazo completo de nombre y email. El nombre de inicio de sesión no se edita: un
    contenido que lo traiga es malformado (`extra="forbid"`)."""

    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    nombre: str
    email: str | None


def manejar_usuario_modificar(
    sobre: SobreComando,
    contenido: UsuarioModificarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_MODIFICAR` v1."""
    usuario = identidad_service.modificar_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        nombre=contenido.nombre,
        email=contenido.email,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_usuario(usuario), None


registrar_handler("USUARIO_MODIFICAR", 1, UsuarioModificarContenidoV1)(manejar_usuario_modificar)
declarar_tipo(
    "USUARIO_MODIFICAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- USUARIO_ROL_CAMBIAR (D7) -------------------------------------------------------------------


class UsuarioRolCambiarContenidoV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    rol_id: UUID


def manejar_usuario_rol_cambiar(
    sobre: SobreComando,
    contenido: UsuarioRolCambiarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_ROL_CAMBIAR` v1. Un rol que no es de la organización lanza
    `RolNoEncontradoError` (404) desde el servicio."""
    usuario = identidad_service.cambiar_rol_de_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        rol_id=contenido.rol_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_usuario(usuario), None


registrar_handler("USUARIO_ROL_CAMBIAR", 1, UsuarioRolCambiarContenidoV1)(
    manejar_usuario_rol_cambiar
)
declarar_tipo(
    "USUARIO_ROL_CAMBIAR", admite_online=True, admite_offline=False, permisos=("ADMIN_USUARIOS",)
)


# --- USUARIO_CONTRASENA_RESTABLECER (D8-A) ------------------------------------------------------


class UsuarioContrasenaRestablecerContenidoV1(BaseModel):
    """Solo el usuario. La contraseña NO está acá (ADR-056): la ruta la separa del cuerpo antes de
    armar el contenido y la huella y la entrega al handler por clausura como `SecretStr`. Así no
    entra a la huella, a `comando`, a `comando_cuarentena`, a la auditoría, al resultado ni al
    `input` de un error de validación. `extra="forbid"`: un contenido con `contrasena` adentro es
    malformado. Ningún `field_validator` sobre el secreto."""

    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID


def manejar_usuario_contrasena_restablecer(
    sobre: SobreComando,
    contenido: UsuarioContrasenaRestablecerContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
    password_nueva: SecretStr,
) -> ResultadoHandler:
    """Handler de `USUARIO_CONTRASENA_RESTABLECER` v1. `.get_secret_value()` se llama UNA vez,
    donde el servicio la deriva. El resultado no lleva secretos."""
    usuario = identidad_service.restablecer_contrasena_de_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        password_nueva=password_nueva.get_secret_value(),
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


# Dato efímero por clausura que `HandlerFuncion` no modela: el lote nunca invoca este handler
# porque el tipo se declara `exige_credenciales_efimeras`.
registrar_handler("USUARIO_CONTRASENA_RESTABLECER", 1, UsuarioContrasenaRestablecerContenidoV1)(
    manejar_usuario_contrasena_restablecer  # type: ignore[arg-type]
)
declarar_tipo(
    "USUARIO_CONTRASENA_RESTABLECER",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_USUARIOS",),
    exige_credenciales_efimeras=True,
)


# --- CONTRASENA_PROPIA_CAMBIAR ("Mi contraseña", D20) -------------------------------------------


class ContrasenaPropiaCambiarContenidoV1(BaseModel):
    """Contenido VACÍO (`extra="forbid"`): el usuario sale del token, nunca del cuerpo, y las dos
    contraseñas viajan como dato efímero por clausura (ADR-056), así que no están en la huella,
    `comando`, la auditoría, el resultado ni los registros. Ningún `field_validator` sobre los
    secretos."""

    model_config = ConfigDict(extra="forbid")


def manejar_contrasena_propia_cambiar(
    sobre: SobreComando,
    contenido: ContrasenaPropiaCambiarContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
    password_actual: SecretStr,
    password_nueva: SecretStr,
    ip: str,
) -> ResultadoHandler:
    """Handler de `CONTRASENA_PROPIA_CAMBIAR` v1. `password_actual`, `password_nueva` e `ip` llegan
    por clausura desde la ruta (`POST /api/v1/yo/contrasena`). Todo rechazo lanza una excepción de
    dominio (nunca devuelve `RECHAZADO`). El resultado no lleva secretos."""
    usuario = identidad_service.cambiar_contrasena_propia(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=sobre.usuario_id,
        password_actual=password_actual.get_secret_value(),
        password_nueva=password_nueva.get_secret_value(),
        ip=ip,
        dispositivo_id=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


# Como `PIN_AUTORIZACION_PROPIO_DEFINIR`: parámetros efímeros que `HandlerFuncion` no modela; el
# lote rechaza el tipo (`exige_credenciales_efimeras`). Solo `ONLINE`. Cualquier usuario
# autenticado y activo puede cambiar SU contraseña: el bus ya exige sesión válida y usuario activo
# y el tipo solo actúa sobre el usuario del token, así que es la única salida justificada de
# `permisos` (D20, ADR-056; nunca en un tipo `OFFLINE`).
registrar_handler("CONTRASENA_PROPIA_CAMBIAR", 1, ContrasenaPropiaCambiarContenidoV1)(
    manejar_contrasena_propia_cambiar  # type: ignore[arg-type]
)
declarar_tipo(
    "CONTRASENA_PROPIA_CAMBIAR",
    admite_online=True,
    admite_offline=False,
    sin_permiso=(
        "Cualquier usuario autenticado y activo cambia su propia contraseña, confirmando la "
        "actual; solo actúa sobre el usuario del token (D20)."
    ),
    exige_credenciales_efimeras=True,
)


# --- USUARIO_TOPE_DESCUENTO_DEFINIR (D12) -------------------------------------------------------


class UsuarioTopeDescuentoDefinirContenidoV1(BaseModel):
    """El usuario y su tope propio nuevo. El tope es un `str` (un número JSON no es válido, INV-03)
    o `null` para volver al del rol; el rango lo valida el dominio con su error (422)."""

    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    tope_descuento: str | None


def manejar_usuario_tope_descuento_definir(
    sobre: SobreComando,
    contenido: UsuarioTopeDescuentoDefinirContenidoV1,
    *,
    sesion: SesionDeHandler,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_TOPE_DESCUENTO_DEFINIR` v1."""
    usuario = identidad_service.definir_tope_descuento_de_usuario(
        sobre.organizacion_id,
        sesion,
        reloj,
        usuario_id=contenido.usuario_id,
        tope_nuevo=contenido.tope_descuento,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        operation_id=sobre.operation_id,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", _resultado_de_usuario(usuario), None


registrar_handler("USUARIO_TOPE_DESCUENTO_DEFINIR", 1, UsuarioTopeDescuentoDefinirContenidoV1)(
    manejar_usuario_tope_descuento_definir
)
declarar_tipo(
    "USUARIO_TOPE_DESCUENTO_DEFINIR",
    admite_online=True,
    admite_offline=False,
    permisos=("ADMIN_USUARIOS",),
)
