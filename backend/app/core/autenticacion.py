"""Dependencia de autenticación y permisos (`design.md` D5, tareas 10.1 y
10.2).

Único camino por el que un endpoint obtiene `organizacion_id`, `usuario_id`
y `dispositivo_id`: los toma del access token, nunca del cuerpo, la
consulta ni un encabezado de la petición (`CLAUDE.md` §4, tarea 10.4). Los
permisos se cargan sin caché en cada petición (`design.md` D5): una
revocación tiene efecto inmediato en la petición siguiente con el mismo
access token (tarea 10.5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.api_v1.dependencias import _get_settings, get_session
from app.core.config import Settings
from app.core.errors import DomainError, PermisoRequeridoError
from app.core.seguridad import verificar_access_token
from app.modules.identidad import service as identidad_service

# `PermisoRequeridoError` se importa de `core/errors.py` y no se define acá, pero
# sigue siendo parte de la superficie de este módulo: los handlers del bus de
# comandos y cualquier consumidor que no pase por una ruta lo toman de
# `core.errors` directamente, que es donde puede importarse sin arrastrar
# FastAPI.


class AccessTokenAusenteError(DomainError):
    """Tarea 10.1: "Una petición sin token no llega al negocio"."""

    codigo = "IDENTIDAD_ACCESS_TOKEN_AUSENTE"
    status_http = 401


class OperationIdAusenteError(DomainError):
    """Change 04, tarea 7.1 (`02` §6.2, SYN-01, TR-07): toda escritura de
    negocio por REST DEBE llevar el encabezado `Operation-Id`. Se rechaza
    antes de tocar la base -- esta dependencia corre antes que cualquier
    handler."""

    codigo = "OPERATION_ID_REQUERIDO"
    status_http = 400


class OperationIdInvalidoError(DomainError):
    """Change 04, tarea 7.2 (SYN-06): el encabezado está presente pero no es
    un identificador válido (UUID)."""

    codigo = "OPERATION_ID_INVALIDO"
    status_http = 400


@dataclass(frozen=True)
class ContextoAutenticado:
    usuario_id: UUID
    organizacion_id: UUID
    dispositivo_id: UUID


def obtener_contexto_autenticado(
    settings: Annotated[Settings, Depends(_get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> ContextoAutenticado:
    """Extrae y verifica el access token del encabezado `Authorization:
    Bearer <token>` (tarea 10.1). `verificar_access_token` ya distingue
    firma alterada de vencimiento (`AccessTokenInvalidoError`/
    `AccessTokenExpiradoError`, ambas `DomainError` 401): esta función no
    los atrapa, los deja propagar tal cual."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise AccessTokenAusenteError("Falta el access token.")

    token = authorization.removeprefix("Bearer ").strip()
    claims = verificar_access_token(token, claves_por_kid={settings.jwt_kid: settings.jwt_secret})

    return ContextoAutenticado(
        usuario_id=claims.usuario_id,
        organizacion_id=claims.organizacion_id,
        dispositivo_id=claims.dispositivo_id,
    )


def requiere_permiso(codigo_permiso: str) -> Callable[..., ContextoAutenticado]:
    """Fábrica de dependencia (tarea 10.2): `Depends(requiere_permiso("X"))`
    en la firma de una ruta. Cada ruta de negocio DEBE declarar la suya
    (tarea 10.3, ratchet).

    `_dependencia.permiso_requerido` es el marcador que el ratchet de la
    tarea 10.3 (`tests/integration/test_ratchet_permiso_por_ruta.py`) usa
    para reconocer, recorriendo el árbol de `Dependant` de cada `APIRoute`,
    que esa ruta sí declaró un permiso -- sin depender de un nombre de
    función ni de introspección de clausura.
    """

    def _dependencia(
        contexto: Annotated[ContextoAutenticado, Depends(obtener_contexto_autenticado)],
        sesion: Annotated[Session, Depends(get_session)],
    ) -> ContextoAutenticado:
        # ADR-028 D9.1 (grupo 2 del change 06b): un usuario `INACTIVO` o con
        # rol `activo = false` se rechaza ANTES de mirar el permiso, con el
        # mismo 401 genérico que un access token inválido (D9.2-A) -- nunca
        # revela la causa (SEG-06).
        identidad_service.exigir_sesion_habilitada(
            contexto.organizacion_id, contexto.usuario_id, sesion
        )
        permisos_del_usuario = identidad_service.listar_permisos_del_usuario(
            contexto.organizacion_id, contexto.usuario_id, sesion
        )
        if codigo_permiso not in permisos_del_usuario:
            raise PermisoRequeridoError(f"Falta el permiso {codigo_permiso}.")
        return contexto

    _dependencia.permiso_requerido = codigo_permiso  # type: ignore[attr-defined]
    return _dependencia


def requiere_sesion(
    contexto: Annotated[ContextoAutenticado, Depends(obtener_contexto_autenticado)],
    sesion: Annotated[Session, Depends(get_session)],
) -> ContextoAutenticado:
    """Dependencia de una ruta que exige una sesión válida y habilitada pero NINGÚN
    permiso en particular (change 11, `design.md` D14: medios de pago y motivos los lee
    cualquier usuario autenticado). Mismo rechazo que `requiere_permiso` ante un usuario
    o rol inactivo (ADR-028 D9.1). No lleva el marcador `permiso_requerido`: las rutas que
    la usan figuran en la lista de exenciones del ratchet de permiso por ruta."""
    identidad_service.exigir_sesion_habilitada(
        contexto.organizacion_id, contexto.usuario_id, sesion
    )
    return contexto


def requiere_algun_permiso(*codigos_permiso: str) -> Callable[..., ContextoAutenticado]:
    """Como `requiere_permiso`, pero alcanza con tener CUALQUIERA de los permisos
    (change 11, `design.md` D14: leer compras exige `REGISTRAR_COMPRA` o
    `ANULAR_COMPRA`). El marcador `permiso_requerido` lleva los códigos unidos con
    ` o `, así el ratchet de permiso por ruta la reconoce igual."""
    assert codigos_permiso, "requiere_algun_permiso necesita al menos un permiso."

    def _dependencia(
        contexto: Annotated[ContextoAutenticado, Depends(obtener_contexto_autenticado)],
        sesion: Annotated[Session, Depends(get_session)],
    ) -> ContextoAutenticado:
        identidad_service.exigir_sesion_habilitada(
            contexto.organizacion_id, contexto.usuario_id, sesion
        )
        permisos_del_usuario = identidad_service.listar_permisos_del_usuario(
            contexto.organizacion_id, contexto.usuario_id, sesion
        )
        if not any(codigo in permisos_del_usuario for codigo in codigos_permiso):
            raise PermisoRequeridoError(
                f"Falta alguno de los permisos {', '.join(codigos_permiso)}."
            )
        return contexto

    _dependencia.permiso_requerido = " o ".join(codigos_permiso)  # type: ignore[attr-defined]
    return _dependencia


@dataclass(frozen=True)
class EntradaComandoOnline:
    """Contexto autenticado más el `operation_id` ya validado (change 04,
    `design.md` D4): lo que un endpoint de escritura necesita para armar su
    `SobreComando` con `app.commands.sobre.construir_sobre_online` -- el
    resto del sobre (tipo, versión, contenido, `occurred_at`, secuencia,
    `app_version`) es propio de cada endpoint y no de esta dependencia."""

    contexto: ContextoAutenticado
    operation_id: UUID


def requiere_comando_online(codigo_permiso: str) -> Callable[..., EntradaComandoOnline]:
    """Fábrica de dependencia (tarea 7.3, `design.md` D4): compone
    `requiere_permiso` (que ya resuelve `ContextoAutenticado` desde el
    access token) con la exigencia y validación del encabezado
    `Operation-Id`, sin reescribir la lógica de permisos existente.

    Ausencia del encabezado -> `OperationIdAusenteError` (400, tarea 7.1).
    Encabezado que no es un UUID válido -> `OperationIdInvalidoError` (400,
    tarea 7.2). Ambas antes de que la petición toque la base: la dependencia
    de permisos ya se resolvió, pero ningún handler llegó a ejecutarse.

    Nota técnica: `contexto` usa `Depends(...)` como VALOR por defecto
    (`= Depends(dependencia_permiso)`), no dentro de un `Annotated[...]`.
    Con `from __future__ import annotations` (vigente en este módulo), toda
    anotación se guarda como texto y FastAPI la evalúa recién al construir
    las rutas -- si `Depends(requiere_permiso(codigo_permiso))` viviera
    DENTRO de la anotación, esa evaluación tardía fallaría con
    `NameError: codigo_permiso no está definido` (`codigo_permiso` es una
    variable local de esta fábrica, invisible en los globals del módulo
    donde se evalúa el texto). Los valores por defecto, en cambio, se
    evalúan de inmediato -- por eso `dependencia_permiso` se resuelve acá
    arriba, antes de definir `_dependencia`, capturado por clausura.
    """
    dependencia_permiso = requiere_permiso(codigo_permiso)

    def _dependencia(
        contexto: ContextoAutenticado = Depends(dependencia_permiso),  # noqa: B008
        operation_id: Annotated[str | None, Header(alias="Operation-Id")] = None,
    ) -> EntradaComandoOnline:
        if operation_id is None:
            raise OperationIdAusenteError(
                "Falta el encabezado Operation-Id, obligatorio en toda escritura (SYN-01, TR-07)."
            )
        try:
            operation_id_uuid = UUID(operation_id)
        except ValueError as error:
            raise OperationIdInvalidoError(
                f"El encabezado Operation-Id no es un identificador válido: {operation_id!r}."
            ) from error
        return EntradaComandoOnline(contexto=contexto, operation_id=operation_id_uuid)

    _dependencia.permiso_requerido = codigo_permiso  # type: ignore[attr-defined]
    return _dependencia
