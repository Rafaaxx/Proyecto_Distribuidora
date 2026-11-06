"""Errores de dominio de la revisión de observaciones y rechazos (change 25, `design.md` D1, D7).

Códigos estables; viajan tal cual en Problem Details (`02` §11).
"""

from __future__ import annotations

from app.core.errors import DomainError


class ObservacionesInvalidasError(DomainError):
    """La lista de observaciones está vacía, repetida o pasa de 100 (D1, INV-01)."""

    codigo = "OBSERVACIONES_INVALIDAS"
    status_http = 422


class ComentarioInvalidoError(DomainError):
    """El comentario de la resolución, recortado, no tiene de 1 a 500 caracteres (SYN-08)."""

    codigo = "COMENTARIO_INVALIDO"
    status_http = 422


class ObservacionYaResueltaError(DomainError):
    """Alguna observación ya estaba `RESUELTA`: no se resuelve ninguna (INV-01). La extensión
    nombra las ya resueltas."""

    codigo = "OBSERVACION_YA_RESUELTA"
    status_http = 409


class RechazoYaResueltoError(DomainError):
    """El rechazo o la cuarentena ya estaba resuelto: no se resuelve otra vez (SYN-08, `01` §18)."""

    codigo = "RECHAZO_YA_RESUELTO"
    status_http = 409


class VinculoInvalidoError(DomainError):
    """El vínculo no corresponde al tipo del comando rechazado (D7)."""

    codigo = "VINCULO_INVALIDO"
    status_http = 422


class RecursoNoEncontradoError(DomainError):
    """La observación o el rechazo no existe en la organización del token (o es de otra):
    404, nunca 403 (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class CursorInvalidoError(DomainError):
    """El cursor de paginación de la bandeja está malformado."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422
