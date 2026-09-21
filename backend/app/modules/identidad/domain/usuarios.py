"""Dominio puro de usuarios, dispositivos, tope de descuento, PIN de
autorización y permisos de autorización de excepciones (`03` §4, `01` §19).

Dominio puro: no importa SQLAlchemy ni FastAPI (`docs/02-arquitectura.md`
§5.2, `CLAUDE.md` §5). Cada función recibe datos y devuelve un resultado o
lanza un error de dominio con código estable.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.errors import DomainError
from app.core.money import redondear_costo

ESTADOS_USUARIO = ("ACTIVO", "INACTIVO")
ESTADOS_DISPOSITIVO = ("ACTIVO", "REVOCADO")

TOPE_DESCUENTO_MINIMO = Decimal("0.000000")
TOPE_DESCUENTO_MAXIMO = Decimal("1.000000")

PIN_AUTORIZACION_LONGITUD_MINIMA = 6

# Permisos de `01` §19 cuya presencia habilita a un rol a autorizar
# excepciones sin conexión mediante el PIN de autorización (`03` §4, spec
# `pin-de-autorizacion`).
PERMISOS_AUTORIZACION_EXCEPCION = frozenset(
    {
        "AUTORIZAR_DESCUENTO",
        "SUPERAR_CREDITO",
        "VENDER_CLIENTE_SUSPENDIDO",
        "USAR_LISTA_ANTERIOR",
    }
)

# Transiciones de estado válidas. Un estado no listado como origen, o un
# destino no presente en el conjunto de su origen, es una transición
# inválida (incluida la transición de un estado a sí mismo).
_TRANSICIONES_USUARIO: dict[str, frozenset[str]] = {
    "ACTIVO": frozenset({"INACTIVO"}),
    "INACTIVO": frozenset({"ACTIVO"}),
}

# `REVOCADO` es terminal: un dispositivo revocado no vuelve a `ACTIVO`
# (`03` §7.7); se registra un dispositivo nuevo si hace falta.
_TRANSICIONES_DISPOSITIVO: dict[str, frozenset[str]] = {
    "ACTIVO": frozenset({"REVOCADO"}),
    "REVOCADO": frozenset(),
}


class EstadoUsuarioInvalidoError(DomainError):
    codigo = "IDENTIDAD_ESTADO_USUARIO_INVALIDO"


class TransicionEstadoUsuarioInvalidaError(DomainError):
    codigo = "IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA"


class EstadoDispositivoInvalidoError(DomainError):
    codigo = "IDENTIDAD_ESTADO_DISPOSITIVO_INVALIDO"


class TransicionEstadoDispositivoInvalidaError(DomainError):
    codigo = "IDENTIDAD_TRANSICION_ESTADO_DISPOSITIVO_INVALIDA"


class TopeDescuentoFueraDeRangoError(DomainError):
    codigo = "IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO"


class PinAutorizacionInvalidoError(DomainError):
    codigo = "IDENTIDAD_PIN_AUTORIZACION_INVALIDO"


class UsuarioSinRolError(DomainError):
    codigo = "IDENTIDAD_USUARIO_SIN_ROL"


class RolConPermisoInexistenteError(DomainError):
    codigo = "IDENTIDAD_ROL_CON_PERMISO_INEXISTENTE"


class CorrelativoNoAvanzaError(DomainError):
    codigo = "IDENTIDAD_CORRELATIVO_NO_AVANZA"


class RolSinAutorizacionParaPinError(DomainError):
    codigo = "IDENTIDAD_ROL_SIN_AUTORIZACION_PARA_PIN"


class CredencialesInvalidasError(DomainError):
    """Rechazo genérico del login (tarea 8.4): usuario inexistente,
    contraseña incorrecta, usuario inactivo, organización (`slug`)
    inexistente, sin dispositivo o dispositivo revocado son, todos, este
    mismo error -- mismo código, mismo mensaje, para que ninguno revele
    cuál de esas condiciones ocurrió (SEG-01, `02` §18)."""

    codigo = "IDENTIDAD_CREDENCIALES_INVALIDAS"
    status_http = 401


class RefreshTokenInvalidoError(DomainError):
    """Rechazo genérico de renovación (tareas 8.6/8.7): token inexistente,
    de otro dispositivo, vencido, ya usado (reuso) o de una sesión cerrada.
    """

    codigo = "IDENTIDAD_REFRESH_TOKEN_INVALIDO"
    status_http = 401


class LoginBloqueadoPorIntentosError(DomainError):
    """Rate limit de login (grupo 11, `ADR-018`): demasiados intentos
    fallidos, por usuario o por IP. Mismo código y mismo mensaje sea cual
    sea el motivo del bloqueo (tarea 11.3, "el bloqueo no revela si el
    usuario existe") -- nunca dice cuál de los dos límites se alcanzó."""

    codigo = "IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS"
    status_http = 429


def validar_estado_usuario(valor: str) -> str:
    if valor not in ESTADOS_USUARIO:
        raise EstadoUsuarioInvalidoError(
            f"Estado de usuario desconocido: {valor!r}. Valores válidos: {ESTADOS_USUARIO}."
        )
    return valor


def transicionar_estado_usuario(actual: str, nuevo: str) -> str:
    validar_estado_usuario(actual)
    validar_estado_usuario(nuevo)
    if nuevo not in _TRANSICIONES_USUARIO[actual]:
        raise TransicionEstadoUsuarioInvalidaError(
            f"No se puede pasar un usuario de {actual!r} a {nuevo!r}."
        )
    return nuevo


def validar_estado_dispositivo(valor: str) -> str:
    if valor not in ESTADOS_DISPOSITIVO:
        raise EstadoDispositivoInvalidoError(
            f"Estado de dispositivo desconocido: {valor!r}. Valores válidos: {ESTADOS_DISPOSITIVO}."
        )
    return valor


def transicionar_estado_dispositivo(actual: str, nuevo: str) -> str:
    validar_estado_dispositivo(actual)
    validar_estado_dispositivo(nuevo)
    if nuevo not in _TRANSICIONES_DISPOSITIVO[actual]:
        raise TransicionEstadoDispositivoInvalidaError(
            f"No se puede pasar un dispositivo de {actual!r} a {nuevo!r}."
        )
    return nuevo


def resolver_tope_descuento_aplicable(*, tope_rol: Decimal, tope_propio: Decimal | None) -> Decimal:
    """Tope de descuento aplicable a un usuario: el propio si está definido
    (aunque sea `0`), el del rol si no (`03` §4: `tope_descuento_override`)."""
    return tope_propio if tope_propio is not None else tope_rol


def validar_tope_descuento(valor: Decimal | str) -> Decimal:
    """Valida y cuantiza un tope de descuento a 6 decimales exactos
    (TR-02). Rechaza punto flotante binario (`EntradaNoEsDineroExactoError`,
    heredada de `core/money.py`, INV-03) y valores fuera de `[0, 1]`."""
    decimal_exacto = redondear_costo(valor)
    if decimal_exacto < TOPE_DESCUENTO_MINIMO or decimal_exacto > TOPE_DESCUENTO_MAXIMO:
        raise TopeDescuentoFueraDeRangoError(
            f"El tope de descuento {decimal_exacto} está fuera de rango "
            f"[{TOPE_DESCUENTO_MINIMO}, {TOPE_DESCUENTO_MAXIMO}]."
        )
    return decimal_exacto


def validar_formato_pin_autorizacion(valor: str) -> str:
    """Valida el formato del PIN de autorización: mínimo seis caracteres,
    solo dígitos (tarea 5.4). La validación de trivialidad (secuencias,
    repeticiones) es de `ADR-019` y se implementa en el grupo 9, junto con la
    derivación PBKDF2 del servidor."""
    if len(valor) < PIN_AUTORIZACION_LONGITUD_MINIMA or not valor.isdigit():
        raise PinAutorizacionInvalidoError(
            "El PIN de autorización debe tener al menos "
            f"{PIN_AUTORIZACION_LONGITUD_MINIMA} dígitos y contener solo dígitos."
        )
    return valor


def rol_confiere_autorizacion_excepcion(permisos_rol: set[str] | frozenset[str]) -> bool:
    """`True` si el rol tiene al menos uno de los permisos que habilitan a
    autorizar excepciones sin conexión con PIN (`01` §19). El servicio que
    modifica la composición de un rol (grupo 8/9) usa esta regla para decidir
    si invalidar el PIN de autorización de los usuarios de ese rol cuando
    pierde su último permiso de autorización."""
    return not PERMISOS_AUTORIZACION_EXCEPCION.isdisjoint(permisos_rol)
