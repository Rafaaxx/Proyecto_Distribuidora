"""Catálogo de la cuenta corriente (CC-01, CC-02, CC-03, `design.md` D12).

Los tipos de la etapa 1 sin los de IVA (`IVA_FACTURA` y `ANULACION_IVA_FACTURA`
los agrega el módulo de facturación). El mismo catálogo está en el `CHECK` de la
migración: si uno cambia, cambia el otro.
"""

from __future__ import annotations

from app.modules.cuentas_corrientes.domain.errores import (
    CuentaTipoInvalidoError,
    SentidoInvalidoError,
    TipoMovimientoInvalidoError,
)

CLIENTE = "CLIENTE"
PROVEEDOR = "PROVEEDOR"
CUENTAS_TIPO = (CLIENTE, PROVEEDOR)

AUMENTA = "AUMENTA"
REDUCE = "REDUCE"
SENTIDOS = (AUMENTA, REDUCE)

SALDO_INICIAL = "SALDO_INICIAL"

TIPOS_POR_CUENTA: dict[str, frozenset[str]] = {
    CLIENTE: frozenset(
        {SALDO_INICIAL, "VENTA", "ANULACION_VENTA", "COBRANZA", "ANULACION_COBRANZA"}
    ),
    PROVEEDOR: frozenset({SALDO_INICIAL, "COMPRA", "ANULACION_COMPRA", "PAGO", "ANULACION_PAGO"}),
}

# Sentido de cada tipo: la venta y la compra aumentan lo que se debe, la
# cobranza y el pago lo reducen, y cada anulación hace lo contrario de su
# operación (CC-05, TR-06). `SALDO_INICIAL` admite los dos: la deuda previa
# puede ser a favor o en contra (`01` §21, D3), por eso no figura acá.
_SENTIDO_FIJO: dict[str, str] = {
    "VENTA": AUMENTA,
    "ANULACION_VENTA": REDUCE,
    "COBRANZA": REDUCE,
    "ANULACION_COBRANZA": AUMENTA,
    "COMPRA": AUMENTA,
    "ANULACION_COMPRA": REDUCE,
    "PAGO": REDUCE,
    "ANULACION_PAGO": AUMENTA,
}


def validar_cuenta_tipo(cuenta_tipo: str) -> str:
    if cuenta_tipo not in CUENTAS_TIPO:
        raise CuentaTipoInvalidoError(
            f"El tipo de cuenta {cuenta_tipo!r} no existe: use CLIENTE o PROVEEDOR."
        )
    return cuenta_tipo


def validar_sentido(sentido: str) -> str:
    if sentido not in SENTIDOS:
        raise SentidoInvalidoError(f"El sentido {sentido!r} no existe: use AUMENTA o REDUCE.")
    return sentido


def validar_tipo_de_movimiento(cuenta_tipo: str, tipo: str) -> str:
    """El tipo tiene que ser de la cuenta: CC-02 para clientes, CC-03 para
    proveedores (D12)."""
    validar_cuenta_tipo(cuenta_tipo)
    if tipo not in TIPOS_POR_CUENTA[cuenta_tipo]:
        raise TipoMovimientoInvalidoError(
            f"El tipo {tipo!r} no corresponde a una cuenta de {cuenta_tipo.lower()}."
        )
    return tipo


def sentido_de_tipo(tipo: str) -> str | None:
    """El sentido que le corresponde al tipo, o `None` si admite los dos
    (solo `SALDO_INICIAL`)."""
    return _SENTIDO_FIJO.get(tipo)
