"""Sobre del comando (`02` §6.2, `design.md` D3, D4).

Estructura inmutable que representa el sobre completo de un comando: los
campos de identidad de la operación (`operation_id`, tipo, versión, modo),
los campos de contexto (organización, usuario, dispositivo, jornada), los
campos de secuencia y versión de aplicación, y el contenido propiamente
dicho.

La propiedad de seguridad que exige la spec ("El contenido no puede elegir
la organización", INV-21, TR-08) se cumple por construcción: `organizacion_
id`, `usuario_id` y `dispositivo_id` son parámetros explícitos del
constructor, separados de `contenido` (un `dict` de forma libre). Ningún
código de este módulo lee esos tres campos DESDE `contenido`; quien arma
el sobre (la dependencia REST del grupo 7, o el endpoint de sincronización
del grupo 8) los toma del contexto de sesión (token JWT) y se los pasa acá
como argumentos separados. Si `contenido` informa una organización, un
usuario o un dispositivo distinto, ese valor queda dentro de `contenido`
como cualquier otro dato de negocio: nunca sobreescribe los campos del
sobre.

No importa FastAPI ni SQLAlchemy (`design.md` D3): es mecanismo puro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.commands.huella import ContenidoComando
from app.core.errors import DomainError


@dataclass(frozen=True)
class SobreComando:
    """Sobre inmutable de un comando (`03` §13, `02` §6.2)."""

    operation_id: UUID
    tipo: str
    version: int
    modo: str
    organizacion_id: UUID
    usuario_id: UUID
    dispositivo_id: UUID
    occurred_at: datetime
    secuencia: int
    app_version: str
    contenido: dict[str, ContenidoComando]
    jornada_id: UUID | None = None


class ModoNoAdmitidoPorRestError(DomainError):
    """Un endpoint REST directo intentó declarar un comando en un modo
    distinto de `ONLINE` (ADR-012, `02` §6.2, `design.md` D4): el modo
    `OFFLINE` solo se admite por el punto de entrada de sincronización
    (`POST /sync/comandos`, grupo 8). Se rechaza en vez de sobreescribirse
    en silencio -- a diferencia de organización/usuario/dispositivo, que
    siempre viajan por un canal separado y confiable (el token) y por eso
    SÍ se sobreescriben sin aviso: `modo` es un campo que un ensamblador de
    sobre genérico podría reenviar tal cual desde una fuente del cliente si
    nada lo frena."""

    codigo = "MODO_NO_ADMITIDO_POR_REST"
    status_http = 400


def construir_sobre_online(
    *,
    operation_id: UUID,
    tipo: str,
    version: int,
    modo: str,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    occurred_at: datetime,
    secuencia: int,
    app_version: str,
    contenido: dict[str, ContenidoComando],
    jornada_id: UUID | None = None,
) -> SobreComando:
    """Arma el sobre para un endpoint REST directo (`design.md` D4,
    ADR-012, tarea 7.4). `modo` DEBE ser `"ONLINE"`: cualquier otro valor se
    rechaza explícitamente (escenario "Un endpoint REST directo no acepta
    modo OFFLINE") en vez de forzarse a `ONLINE` en silencio, para que un
    ensamblador de sobre que reenvíe un `modo` ajeno desde el cliente no
    esconda el error."""
    if modo != "ONLINE":
        raise ModoNoAdmitidoPorRestError(
            f"Un endpoint REST directo no admite modo {modo!r}; solo ONLINE."
        )
    return SobreComando(
        operation_id=operation_id,
        tipo=tipo,
        version=version,
        modo=modo,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=occurred_at,
        secuencia=secuencia,
        app_version=app_version,
        contenido=contenido,
        jornada_id=jornada_id,
    )
