"""Primitivas de seguridad: hash de contraseña, access token JWT y refresh
token opaco (`03` §7, ADR-017, `design.md` D4).

Módulo de infraestructura pura: no accede a base de datos ni a FastAPI. La
inyección del reloj (`core/clock.py`) queda en manos de quien llama
(`identidad/service.py`, grupo 8) para las operaciones que necesitan "ahora";
las funciones de acá reciben el momento como parámetro explícito cuando
importa para la prueba (emisión y verificación de expiración), lo que las
mantiene puras y fáciles de probar sin mockear el reloj global.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.errors import DomainError

ACCESS_TOKEN_TTL_MINUTOS = 15
ALGORITMO_ACCESS_TOKEN = "HS256"

# Longitud en bytes de entropía del refresh token opaco antes de codificar
# (`secrets.token_urlsafe` documenta ~1.3 caracteres por byte de entropía).
_REFRESH_TOKEN_BYTES = 32

_password_hasher = PasswordHasher()


class AccessTokenInvalidoError(DomainError):
    codigo = "IDENTIDAD_ACCESS_TOKEN_INVALIDO"
    status_http = 401


class AccessTokenExpiradoError(DomainError):
    codigo = "IDENTIDAD_ACCESS_TOKEN_EXPIRADO"
    status_http = 401


@dataclass(frozen=True)
class ClaimsAccessToken:
    """Lo único que el access token afirma (`design.md` D5: los permisos
    nunca viajan acá, se cargan sin caché en cada petición)."""

    usuario_id: UUID
    organizacion_id: UUID
    dispositivo_id: UUID


def hashear_password(password: str) -> str:
    """Deriva `password` con Argon2id. Cada llamada usa una sal aleatoria
    nueva: dos derivaciones de la misma contraseña no coinciden como cadena
    (`03` §7.1)."""
    return _password_hasher.hash(password)


def verificar_password(password: str, hash_almacenado: str) -> bool:
    """`True` si `password` deriva a `hash_almacenado`. Nunca lanza sobre una
    contraseña incorrecta: la distingue devolviendo `False`."""
    try:
        return _password_hasher.verify(hash_almacenado, password)
    except VerifyMismatchError:
        return False


def emitir_access_token(
    *,
    usuario_id: UUID,
    organizacion_id: UUID,
    dispositivo_id: UUID,
    secreto: str,
    kid: str,
    emitido_en: datetime,
) -> str:
    """Emite un access token HS256 que vence a los 15 minutos
    (`ACCESS_TOKEN_TTL_MINUTOS`), con el secreto activo identificado por
    `kid` en el encabezado (`design.md` D4)."""
    payload = {
        "usuario_id": str(usuario_id),
        "organizacion_id": str(organizacion_id),
        "dispositivo_id": str(dispositivo_id),
        "iat": int(emitido_en.timestamp()),
        "exp": int((emitido_en + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTOS)).timestamp()),
    }
    return jwt.encode(payload, secreto, algorithm=ALGORITMO_ACCESS_TOKEN, headers={"kid": kid})


def verificar_access_token(
    token: str,
    *,
    claves_por_kid: dict[str, str],
    ahora: datetime | None = None,
) -> ClaimsAccessToken:
    """Verifica firma y vencimiento y devuelve los datos del contexto.

    Rechaza (`AccessTokenInvalidoError`): token malformado, firma alterada,
    `kid` ausente o desconocido. Rechaza (`AccessTokenExpiradoError`): token
    vencido con firma válida, para que quien llama pueda distinguir "hay que
    renovar" de "el token es ilegítimo".
    """
    try:
        encabezado = jwt.get_unverified_header(token)
    except jwt.PyJWTError as error:
        raise AccessTokenInvalidoError("El access token está malformado.") from error

    kid = encabezado.get("kid")
    secreto = claves_por_kid.get(kid) if kid is not None else None
    if secreto is None:
        raise AccessTokenInvalidoError(f"El access token declara un kid desconocido: {kid!r}.")

    momento_referencia = ahora if ahora is not None else datetime.now(UTC)
    try:
        # `verify_exp=False`: la firma y la estructura del payload se
        # verifican acá igual, pero el vencimiento se compara a mano contra
        # `momento_referencia` en vez del reloj real del proceso, para que
        # quien llama (`identidad/service.py`) pueda inyectar el reloj
        # (`core/clock.py`) en vez de depender del reloj del sistema.
        payload = jwt.decode(
            token,
            secreto,
            algorithms=[ALGORITMO_ACCESS_TOKEN],
            options={"require": ["exp", "iat"], "verify_exp": False},
        )
        if payload["exp"] < int(momento_referencia.timestamp()):
            raise AccessTokenExpiradoError("El access token venció.")
    except AccessTokenExpiradoError:
        raise
    except jwt.PyJWTError as error:
        raise AccessTokenInvalidoError(f"El access token no verifica: {error}.") from error

    return ClaimsAccessToken(
        usuario_id=UUID(payload["usuario_id"]),
        organizacion_id=UUID(payload["organizacion_id"]),
        dispositivo_id=UUID(payload["dispositivo_id"]),
    )


def generar_refresh_token() -> str:
    """Genera el valor en claro de un refresh token opaco, con entropía
    suficiente (256 bits) y sin ninguna estructura interpretable (ADR-017)."""
    return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)


def derivar_hash_refresh_token(token_claro: str) -> str:
    """Deriva el valor almacenable de un refresh token. El servidor nunca
    guarda `token_claro`: solo esta derivación, que no permite reconstruirlo
    (`03` §4: `sesion_refresh.token_hash`)."""
    return hashlib.sha256(token_claro.encode("utf-8")).hexdigest()


# PBKDF2-HMAC-SHA256 con sal aleatoria de 32 bytes (`ADR-019`). El número de
# iteraciones sigue la recomendación mínima de OWASP (2023) para
# PBKDF2-HMAC-SHA256; se guarda junto con cada derivación (`usuario.
# pin_autorizacion_iteraciones`, `03` §4) para poder subirlo a futuro sin
# invalidar las derivaciones ya guardadas con un valor menor.
PIN_AUTORIZACION_ITERACIONES_DEFAULT = 600_000
_PIN_AUTORIZACION_SAL_BYTES = 32


def derivar_pin_autorizacion(
    pin: str, *, iteraciones: int = PIN_AUTORIZACION_ITERACIONES_DEFAULT
) -> tuple[str, str, int]:
    """Deriva `pin` con PBKDF2-HMAC-SHA256 y una sal aleatoria nueva.
    Devuelve `(hash_hex, sal_hex, iteraciones)`, los tres valores que
    `03` §4 guarda por usuario (`ADR-019`, tarea 9.1)."""
    sal = secrets.token_bytes(_PIN_AUTORIZACION_SAL_BYTES)
    derivado = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), sal, iteraciones)
    return derivado.hex(), sal.hex(), iteraciones


def verificar_pin_autorizacion(
    pin: str, *, hash_almacenado: str, sal: str, iteraciones: int
) -> bool:
    """`True` si `pin` deriva a `hash_almacenado` con `sal` e `iteraciones`
    (mismo criterio con el que el bootstrap valida sin conexión, `02`
    §12.4)."""
    derivado = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(sal), iteraciones)
    return secrets.compare_digest(derivado.hex(), hash_almacenado)
