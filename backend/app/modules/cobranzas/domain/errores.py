"""Errores de dominio de `cobranzas` (change 17, `design.md` D2, D4, D7, D8): código estable,
heredan de `DomainError` (`CLAUDE.md` §5), mismo criterio de `status_http` que el resto
(409 conflictos de estado, 422 validaciones de contenido, 404 no encontrado). Una referencia
inexistente o de otra organización usa `RecursoNoEncontradoError` (INV-21, SEG-07: "Un recurso
de otra organización responde 404, no 403").

Los errores de medios (`MEDIOS_INVALIDOS`, `MEDIOS_NO_SUMAN_IMPORTE`, `IMPORTE_INVALIDO`,
`REFERENCIA_OBLIGATORIA`) son los de la validación compartida
(`configuracion/domain/medios.py`, D17).
"""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """Un cliente, medio de pago o cobranza que no existe en la organización del token (o que
    pertenece a otra) responde como inexistente (INV-21, SEG-07)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class CobranzaDuplicadaError(DomainError):
    """El identificador de la cobranza ya lo usa otra operación (`02` §9, SYN-06, D2)."""

    codigo = "COBRANZA_DUPLICADA"
    status_http = 409


class JornadaAjenaError(DomainError):
    """El sobre nombra una jornada que no es la del usuario y el dispositivo de la sesión
    (D8, D12)."""

    codigo = "JORNADA_AJENA"
    status_http = 409


class ConsumidorFinalSinCuentaError(DomainError):
    """No se registra una cobranza independiente al consumidor final: no tiene cuenta
    corriente (CLI-03, CC-08, D4). Es el mismo código y el mismo estado (422) que
    `cuentas_corrientes` (precisión del apply 2026-10-16)."""

    codigo = "CONSUMIDOR_FINAL_SIN_CUENTA"
    status_http = 422


class MedioPagoInactivoError(DomainError):
    """Medio de pago inactivo usado en una cobranza con conexión (TR-09, D13 punto 4). Mismo
    código y estado que el pago a proveedor."""

    codigo = "MEDIO_PAGO_INACTIVO"
    status_http = 422


class MotivoInvalidoError(DomainError):
    """Motivo inactivo o de un ámbito distinto de `ANULACION_COBRANZA` (COB-05, `03` §4)."""

    codigo = "MOTIVO_INVALIDO"
    status_http = 422


class ObservacionInvalidaError(DomainError):
    """La observación supera los 500 caracteres (D2, D7)."""

    codigo = "OBSERVACION_INVALIDA"
    status_http = 422


class CobranzaYaAnuladaError(DomainError):
    """La cobranza ya está `ANULADA`: se anula una sola vez (COB-05, D7)."""

    codigo = "COBRANZA_YA_ANULADA"
    status_http = 409


class CobranzaDeVentaError(DomainError):
    """Una cobranza de origen `VENTA` no se anula por separado: se anula con la venta
    (VTA-22, D7)."""

    codigo = "COBRANZA_DE_VENTA"
    status_http = 409


class CursorInvalidoError(DomainError):
    """El cursor de paginación del listado no se puede leer (TR-04)."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class RangoDeFechasInvalidoError(DomainError):
    """`desde` es posterior a `hasta` (TR-04)."""

    codigo = "RANGO_DE_FECHAS_INVALIDO"
    status_http = 422
