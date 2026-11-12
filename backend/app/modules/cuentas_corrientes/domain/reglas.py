"""Reglas puras de la cuenta corriente: efecto sobre el saldo (CC-04) y las
reglas de `design.md` D3 y D4 como funciones que reciben datos.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from app.modules.cuentas_corrientes.domain.catalogo import (
    AUMENTA,
    CLIENTE,
    validar_sentido,
)
from app.modules.cuentas_corrientes.domain.errores import (
    ConsumidorFinalSinCuentaError,
    CuentaConOperacionesError,
)


def efecto_sobre_saldo(sentido: str, importe: Decimal) -> Decimal:
    """`+importe` si el movimiento aumenta el saldo, `-importe` si lo reduce
    (CC-04)."""
    validar_sentido(sentido)
    return importe if sentido == AUMENTA else -importe


def saldo_de(movimientos: Iterable[tuple[str, Decimal]]) -> Decimal:
    """Saldo = lo que aumenta menos lo que reduce (CC-04), sobre pares
    `(sentido, importe)`. Es la definición contra la que se prueba INV-13; el
    saldo real se calcula con SQL sobre el libro, nunca sumando filas en Python
    (`CLAUDE.md` §4)."""
    aumenta = Decimal("0.00")
    reduce = Decimal("0.00")
    for sentido, importe in movimientos:
        if validar_sentido(sentido) == AUMENTA:
            aumenta += importe
        else:
            reduce += importe
    return aumenta - reduce


def validar_saldo_inicial_admitido(*, tiene_movimientos_de_otro_tipo: bool) -> None:
    """D3: una cuenta admite varios `SALDO_INICIAL` solo mientras no tenga
    movimientos de otro tipo."""
    if tiene_movimientos_de_otro_tipo:
        raise CuentaConOperacionesError(
            "La cuenta ya tiene movimientos de otro tipo: no admite más saldos iniciales."
        )


def validar_cuenta_con_titular(cuenta_tipo: str, *, es_consumidor_final: bool) -> None:
    """D4: el cliente consumidor final es un cliente genérico con límite cero
    (CLI-03) que no identifica a ningún deudor: no tiene cuenta corriente."""
    if cuenta_tipo == CLIENTE and es_consumidor_final:
        raise ConsumidorFinalSinCuentaError(
            "El cliente consumidor final no tiene cuenta corriente."
        )
