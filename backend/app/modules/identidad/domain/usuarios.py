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
    status_http = 422


class PinAutorizacionInvalidoError(DomainError):
    codigo = "IDENTIDAD_PIN_AUTORIZACION_INVALIDO"


class SinAdministradorError(DomainError):
    """Un cambio de permisos dejaría a la organización sin nadie que administre usuarios y roles
    (change 17b, D8, ADR-053, TR-10)."""

    codigo = "IDENTIDAD_SIN_ADMINISTRADOR"
    status_http = 409


class UsuarioSinRolError(DomainError):
    codigo = "IDENTIDAD_USUARIO_SIN_ROL"


class RolConPermisoInexistenteError(DomainError):
    codigo = "IDENTIDAD_ROL_CON_PERMISO_INEXISTENTE"


class CorrelativoNoAvanzaError(DomainError):
    codigo = "IDENTIDAD_CORRELATIVO_NO_AVANZA"


class PinIncorrectoError(DomainError):
    """El PIN no valida (change 18b, D2/D3, SEG-05). Un PIN equivocado, un autorizador sin PIN y
    uno con el PIN invalidado responden exactamente igual (mismo código, estado y mensaje): no se
    revela cuál es el caso."""

    codigo = "PIN_INCORRECTO"
    status_http = 403


class ContrasenaIncorrectaError(DomainError):
    """La contraseña actual de "Mi PIN" no es correcta (change 18b, D21 punto 4). 403 y no 401:
    la interfaz trata el 401 como sesión terminada."""

    codigo = "IDENTIDAD_CONTRASENA_INCORRECTA"
    status_http = 403


class PinBloqueadoError(DomainError):
    """Demasiados fallos del PIN de un autorizador (change 18b, D3 revisada, SEG-04): por par
    (quien intenta, autorizador) o general por autorizador. Mismo código y mensaje en los dos
    casos: no se revela cuál de los dos límites se alcanzó ni cuánto falta."""

    codigo = "PIN_BLOQUEADO"
    status_http = 429


class AutorizadorSinPermisoError(DomainError):
    """El autorizador no tiene el permiso que la autorización exige (change 18b, D3 revisada,
    punto 5): se revisa ANTES del PIN y no cuenta como fallo. Mismo código que el de
    `clientes` y `descuentos`."""

    codigo = "AUTORIZADOR_SIN_PERMISO"
    status_http = 403


class AutorizadorNoEncontradoError(DomainError):
    """El autorizador no existe en la organización (o es de otra): 404 como todo recurso ajeno
    (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


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


def _es_pin_trivial(valor: str) -> bool:
    """ADR-019 (precisado en el change 18b, D21 punto 6): trivial es todo PIN de dígitos
    iguales (`000000`) o una escalera de paso 1, ascendente o descendente, sin vuelta
    (`123456`, `456789`, `987654`; `901234` no lo es porque se corta en 9 -> 0)."""
    digitos = [int(caracter) for caracter in valor]
    pasos = {
        siguiente - anterior for anterior, siguiente in zip(digitos, digitos[1:], strict=False)
    }
    return pasos in ({0}, {1}, {-1})


def validar_formato_pin_autorizacion(valor: str) -> str:
    """Valida el formato del PIN de autorización: mínimo seis caracteres, solo dígitos (tarea
    5.4) y no trivial (todos los dígitos iguales o una escalera de paso 1 sin vuelta, ADR-019;
    change 18b, tarea 6.4). El mensaje nunca incluye el valor. Solo se controla al DEFINIR el
    PIN: uno trivial ya definido sigue validando."""
    if len(valor) < PIN_AUTORIZACION_LONGITUD_MINIMA or not valor.isdigit():
        raise PinAutorizacionInvalidoError(
            "El PIN de autorización debe tener al menos "
            f"{PIN_AUTORIZACION_LONGITUD_MINIMA} dígitos y contener solo dígitos."
        )
    if _es_pin_trivial(valor):
        raise PinAutorizacionInvalidoError(
            "El PIN de autorización no puede ser trivial: ni todos los dígitos iguales ni una "
            "secuencia consecutiva ascendente o descendente (ADR-019)."
        )
    return valor


def rol_confiere_autorizacion_excepcion(permisos_rol: set[str] | frozenset[str]) -> bool:
    """`True` si el rol tiene al menos uno de los permisos que habilitan a
    autorizar excepciones sin conexión con PIN (`01` §19). El servicio que
    modifica la composición de un rol (grupo 8/9) usa esta regla para decidir
    si invalidar el PIN de autorización de los usuarios de ese rol cuando
    pierde su último permiso de autorización."""
    return not PERMISOS_AUTORIZACION_EXCEPCION.isdisjoint(permisos_rol)


def validar_queda_administrador(
    *,
    administradores_en_otros_roles: int,
    conserva_el_permiso: bool,
    rol_activo: bool,
    usuarios_activos_del_rol: int,
) -> None:
    """Regla pura (ADR-053): después del cambio queda al menos un usuario ACTIVO de un rol activo
    con `ADMIN_USUARIOS`. Recibe conteos hechos en SQL: los usuarios activos de roles activos,
    distintos del editado, que lo tienen; y los usuarios activos del rol editado. El rol editado
    solo cuenta si conserva el permiso, está activo y tiene al menos un usuario activo."""
    if administradores_en_otros_roles >= 1:
        return
    if conserva_el_permiso and rol_activo and usuarios_activos_del_rol >= 1:
        return
    raise SinAdministradorError(
        "La organización se quedaría sin nadie que administre usuarios y roles"
    )
