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

from uuid import UUID

from pydantic import BaseModel, SecretStr

from app.commands.catalogo import declarar_tipo
from app.commands.registro import registrar_handler
from app.commands.sobre import SobreComando
from app.core.clock import Clock
from app.modules.identidad import service as identidad_service

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
    usuario: str
    nombre: str
    email: str | None = None
    password: str
    rol_id: UUID


def manejar_usuario_crear(
    sobre: SobreComando,
    contenido: UsuarioCrearContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_CREAR` v1 (D7). `actor_id`/`dispositivo_id_actor`
    salen del sobre (contexto del token), nunca del contenido -- el
    contenido solo trae los datos propios del alta. `auditar=False`
    (ADR-022): la única fila de auditoría de este comando la deja
    `sync_service.procesar_comando` (grupo 10), no este handler."""
    usuario = identidad_service.crear_usuario(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        usuario=contenido.usuario,
        nombre=contenido.nombre,
        email=contenido.email,
        password=contenido.password,
        rol_id=contenido.rol_id,
        actor_id=sobre.usuario_id,
        dispositivo_id_actor=sobre.dispositivo_id,
        auditar=False,
    )
    if usuario is None:
        return "RECHAZADO", None, "ROL_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


registrar_handler("USUARIO_CREAR", 1, UsuarioCrearContenidoV1)(
    manejar_usuario_crear  # type: ignore[arg-type]
)
declarar_tipo("USUARIO_CREAR", admite_online=True, admite_offline=False)


# --- DISPOSITIVO_REVOCAR (D7, envuelve `identidad_service.revocar_dispositivo`) --


class DispositivoRevocarContenidoV1(BaseModel):
    dispositivo_id: UUID


def manejar_dispositivo_revocar(
    sobre: SobreComando,
    contenido: DispositivoRevocarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `DISPOSITIVO_REVOCAR` v1 (D7). `dispositivo_id_actor` (el
    dispositivo desde el que se autentica quien revoca) sale de
    `sobre.dispositivo_id` -- el dispositivo A REVOCAR es el del contenido,
    un dato distinto (`identidad_service.revocar_dispositivo`, docstring)."""
    dispositivo = identidad_service.revocar_dispositivo(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
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
    manejar_dispositivo_revocar  # type: ignore[arg-type]
)
declarar_tipo("DISPOSITIVO_REVOCAR", admite_online=True, admite_offline=False)


# --- PIN_AUTORIZACION_ROTAR (D7, envuelve `establecer_pin_autorizacion`) ----


class PinAutorizacionRotarContenidoV1(BaseModel):
    """`pin: SecretStr`, sin ningún validador de formato/longitud a este
    nivel (riesgo señalado del change: un `field_validator` que rechace un
    PIN inválido reintroduce la fuga, porque Pydantic reporta el
    `input_value` CRUDO -- previo al envoltorio `SecretStr` -- dentro del
    mensaje de `ValidationError`, sin importar el tipo anotado del campo;
    confirmado empíricamente antes de escribir este esquema. La validación
    de formato (longitud mínima, solo dígitos) queda, como ya estaba,
    exclusivamente en `identidad/domain/usuarios.py::
    validar_formato_pin_autorizacion`, invocada dentro de
    `establecer_pin_autorizacion` -- esa función nunca incluye el valor del
    PIN en su mensaje de error (confirmado, código existente, sin tocar).
    Consecuencia de este diseño: un PIN de longitud incorrecta pasa la
    validación de ESTE esquema (cualquier `str` es un `SecretStr` válido) y
    se rechaza más abajo, en el servicio, con un error de dominio que no
    lo expone -- nunca llega a `registro.py::validar_contenido`, que es
    donde estaba el riesgo real de fuga."""

    usuario_id: UUID
    pin: SecretStr


def manejar_pin_autorizacion_rotar(
    sobre: SobreComando,
    contenido: PinAutorizacionRotarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `PIN_AUTORIZACION_ROTAR` v1 (D7). `.get_secret_value()`
    se llama UNA sola vez, en el punto exacto en que el servicio lo
    necesita -- nunca se loguea ni se incluye en el resultado devuelto."""
    usuario = identidad_service.establecer_pin_autorizacion(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        usuario_id=contenido.usuario_id,
        pin=contenido.pin.get_secret_value(),
        actor_id=sobre.usuario_id,
        auditar=False,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


registrar_handler("PIN_AUTORIZACION_ROTAR", 1, PinAutorizacionRotarContenidoV1)(
    manejar_pin_autorizacion_rotar  # type: ignore[arg-type]
)
declarar_tipo("PIN_AUTORIZACION_ROTAR", admite_online=True, admite_offline=False)


# --- ROL_PERMISOS_CAMBIAR (grupo 14, envuelve
# `identidad_service.cambiar_composicion_rol`) --------------------------


class RolPermisosCambiarContenidoV1(BaseModel):
    rol_id: UUID
    permisos: list[str]


def manejar_rol_permisos_cambiar(
    sobre: SobreComando,
    contenido: RolPermisosCambiarContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `ROL_PERMISOS_CAMBIAR` v1 (grupo 14, D7). `auditar=False`
    (ADR-022): la única fila de auditoría de este comando la deja
    `sync_service.procesar_comando`, no este handler."""
    rol = identidad_service.cambiar_composicion_rol(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
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
    manejar_rol_permisos_cambiar  # type: ignore[arg-type]
)
declarar_tipo("ROL_PERMISOS_CAMBIAR", admite_online=True, admite_offline=False)


# --- USUARIO_DESBLOQUEAR (grupo 14, envuelve
# `identidad_service.desbloquear_usuario`) -------------------------------


class UsuarioDesbloquearContenidoV1(BaseModel):
    usuario_id: UUID


def manejar_usuario_desbloquear(
    sobre: SobreComando,
    contenido: UsuarioDesbloquearContenidoV1,
    *,
    sesion: object,
    reloj: Clock,
) -> ResultadoHandler:
    """Handler de `USUARIO_DESBLOQUEAR` v1 (grupo 14, D7, `ADR-018`).
    `auditar=False` (ADR-022): la única fila de auditoría de este comando la
    deja `sync_service.procesar_comando`, no este handler."""
    usuario = identidad_service.desbloquear_usuario(
        sobre.organizacion_id,
        sesion,  # type: ignore[arg-type]
        reloj,
        usuario_id=contenido.usuario_id,
        actor_id=sobre.usuario_id,
        auditar=False,
    )
    if usuario is None:
        return "RECHAZADO", None, "USUARIO_NO_ENCONTRADO"
    return "ACEPTADO", {"usuario_id": str(usuario.id)}, None


registrar_handler("USUARIO_DESBLOQUEAR", 1, UsuarioDesbloquearContenidoV1)(
    manejar_usuario_desbloquear  # type: ignore[arg-type]
)
declarar_tipo("USUARIO_DESBLOQUEAR", admite_online=True, admite_offline=False)
