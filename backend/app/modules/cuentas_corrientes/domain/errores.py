"""Errores de dominio de `cuentas_corrientes` (`CLAUDE.md` §5): código estable,
heredan de `DomainError`.

Los códigos que las specs nombran textualmente son `TIPO_MOVIMIENTO_INVALIDO`,
`IMPORTE_INVALIDO`, `CUENTA_CON_OPERACIONES` y `CONSUMIDOR_FINAL_SIN_CUENTA`.
`CUENTA_TIPO_INVALIDO`, `SENTIDO_INVALIDO` y `SALDO_FUERA_DE_RANGO` son
defensas del servicio para quien lo llame con datos que el esquema de un
comando ya habría rechazado (y para el desborde de `numeric(14,2)` de un saldo
acumulado, `design.md` Risks).

Una entidad que no existe en la organización del token, o que pertenece a
otra, es `RecursoNoEncontradoError` (INV-21, SEG-07): 404, no 403.
"""

from __future__ import annotations

from app.core.errors import DomainError


class RecursoNoEncontradoError(DomainError):
    """El cliente o el proveedor de la cuenta no existe en la organización del
    token (o pertenece a otra) (INV-21, SEG-07, `design.md` D6, D7)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class TipoMovimientoInvalidoError(DomainError):
    """El tipo no pertenece al catálogo de la cuenta (CC-02, CC-03, D12)."""

    codigo = "TIPO_MOVIMIENTO_INVALIDO"
    status_http = 422


class CuentaTipoInvalidoError(DomainError):
    """`cuenta_tipo` distinto de `CLIENTE` y `PROVEEDOR` (CC-01, `03` §12)."""

    codigo = "CUENTA_TIPO_INVALIDO"
    status_http = 422


class SentidoInvalidoError(DomainError):
    """`sentido` distinto de `AUMENTA` y `REDUCE`, o que contradice el sentido
    fijo del tipo (CC-01, CC-05)."""

    codigo = "SENTIDO_INVALIDO"
    status_http = 422


class ImporteInvalidoError(DomainError):
    """Importe que no es positivo, tiene más de dos decimales, no es dinero
    exacto o no entra en `numeric(14,2)` (CC-01, INV-03)."""

    codigo = "IMPORTE_INVALIDO"
    status_http = 422


class SaldoFueraDeRangoError(DomainError):
    """El saldo resultante no entra en `numeric(14,2)`."""

    codigo = "SALDO_FUERA_DE_RANGO"
    status_http = 422


class CuentaConOperacionesError(DomainError):
    """La cuenta ya tiene movimientos de otro tipo: no admite más saldos
    iniciales (`design.md` D3)."""

    codigo = "CUENTA_CON_OPERACIONES"
    status_http = 409


class ConsumidorFinalSinCuentaError(DomainError):
    """El cliente consumidor final no tiene cuenta corriente (CLI-03, D4)."""

    codigo = "CONSUMIDOR_FINAL_SIN_CUENTA"
    status_http = 422


class CursorInvalidoError(DomainError):
    """El cursor de paginación del estado de cuenta está malformado."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class RangoDeFechasInvalidoError(DomainError):
    """`desde` es posterior a `hasta` en el estado de cuenta."""

    codigo = "RANGO_DE_FECHAS_INVALIDO"
    status_http = 422
