"""Dominio puro de la nota de venta (change 20, D4, VTA-13, CRE-02).

Sin FastAPI ni SQLAlchemy ni dominio ajeno: la fórmula del saldo es la de CRE-02 (la misma de
`clientes/domain/credito.py`), repetida acá porque un módulo no importa el dominio de otro.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.money import redondear_importe

ESTADO_ANULADA = "ANULADA"


def saldo_de_la_nota(
    muestra_saldo: bool,
    es_consumidor_final: bool,
    estado: str,
    saldo_considerado: Decimal | None,
    total: Decimal,
    cobrado: Decimal,
) -> Decimal | None:
    """El saldo resultante que imprime la nota, o `None` si se omite (D4).

    Es `saldo_considerado + total - cobrado` (CRE-02), con `saldo_considerado` el saldo que la
    venta congeló al confirmarse, de modo que la reimpresión reproduce la nota original. Un saldo
    negativo (a favor del cliente) se conserva con su signo. Se omite si la organización no lo
    pidió (`muestra_saldo`), si el cliente es el consumidor final (no tiene cuenta, CLI-03), si
    la venta no tiene snapshot (anterior al change 18b) o si está anulada (D5)."""
    if not muestra_saldo or es_consumidor_final or saldo_considerado is None:
        return None
    if estado == ESTADO_ANULADA:
        return None
    return redondear_importe(saldo_considerado + total - cobrado)
