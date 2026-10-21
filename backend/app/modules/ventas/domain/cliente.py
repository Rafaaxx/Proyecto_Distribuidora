"""Cliente habilitado y consumidor final de contado (CLI-02, CLI-03, SYN-05, SYN-07;
`design.md` D5)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.modules.ventas.domain.errores import (
    ClienteInactivoError,
    ClienteSuspendidoError,
    ConsumidorFinalContadoError,
)
from app.modules.ventas.domain.observaciones import ObservacionDeVenta

CODIGO_CLIENTE_NO_HABILITADO = "CLIENTE_NO_HABILITADO"
# Decisión del usuario del 2026-10-19 (D5): el consumidor final que llega sin conexión con una
# cobranza distinta del total se acepta con este código propio.
CODIGO_CONSUMIDOR_FINAL_CON_DEUDA = "CONSUMIDOR_FINAL_CON_DEUDA"

_ACTIVO = "ACTIVO"
_SUSPENDIDO = "SUSPENDIDO"


def evaluar_cliente(
    *,
    cliente_id: UUID,
    estado: str,
    es_consumidor_final: bool,
    puede_vender_suspendido: bool,
    total: Decimal,
    cobranza: Decimal | None,
    offline: bool,
) -> ObservacionDeVenta | None:
    """Con conexión rechaza: `CLIENTE_INACTIVO`, `CLIENTE_SUSPENDIDO` sin el permiso y
    `CONSUMIDOR_FINAL_CONTADO` si la cobranza en el acto no es igual al total. Sin conexión
    nunca rechaza (INV-17): el estado no habilitado devuelve `CLIENTE_NO_HABILITADO` y el
    consumidor final con cobranza distinta del total, `CONSUMIDOR_FINAL_CON_DEUDA`. Devuelve
    `None` si el cliente está habilitado."""
    estado_no_habilitado = estado != _ACTIVO and not (
        estado == _SUSPENDIDO and puede_vender_suspendido
    )
    consumidor_final_a_credito = es_consumidor_final and cobranza != total
    if not (estado_no_habilitado or consumidor_final_a_credito):
        return None

    if offline:
        if estado_no_habilitado:
            return ObservacionDeVenta(
                CODIGO_CLIENTE_NO_HABILITADO,
                {"cliente_id": str(cliente_id), "estado": estado},
            )
        return ObservacionDeVenta(
            CODIGO_CONSUMIDOR_FINAL_CON_DEUDA,
            {
                "cliente_id": str(cliente_id),
                "total": str(total),
                "cobranza": None if cobranza is None else str(cobranza),
            },
        )
    if estado_no_habilitado:
        if estado == _SUSPENDIDO:
            raise ClienteSuspendidoError("El cliente está suspendido (CLI-02).")
        raise ClienteInactivoError("El cliente está inactivo (CLI-02).")
    raise ConsumidorFinalContadoError(
        "Al consumidor final se le vende solo de contado: la cobranza debe ser igual al total."
    )
