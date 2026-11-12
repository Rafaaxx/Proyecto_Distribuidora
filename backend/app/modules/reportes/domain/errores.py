"""Errores de dominio de `reportes` (código estable, `CLAUDE.md` §5)."""

from __future__ import annotations

from app.core.errors import DomainError


class RangoDeFechasInvalidoError(DomainError):
    """`desde` es posterior a `hasta` (TR-04).

    Mismo código y mismo HTTP que el error homónimo de `cobranzas` y `cuentas_corrientes`:
    `reportes` no importa el dominio de otros módulos (`design.md` D1 y D6 del change 26).
    """

    codigo = "RANGO_DE_FECHAS_INVALIDO"
    status_http = 422


class PeriodoDemasiadoLargoError(DomainError):
    """El período pedido supera el tope de días de un reporte (`design.md` D1)."""

    codigo = "PERIODO_DEMASIADO_LARGO"
    status_http = 422


class RecursoNoEncontradoError(DomainError):
    """Un recurso (jornada, organización) que no existe en la organización del token, o que
    pertenece a otra, responde como inexistente (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404
