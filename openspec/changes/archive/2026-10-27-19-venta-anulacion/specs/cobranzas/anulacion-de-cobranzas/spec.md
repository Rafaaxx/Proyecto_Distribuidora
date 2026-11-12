## ADDED Requirements

### Requirement: La cobranza de una venta se anula con su venta

Una cobranza de origen `VENTA` DEBE anularse solo al anular su venta con devolución del dinero (VTA-22): queda `ANULADA`, su anulación lleva el motivo y la observación de la anulación de la venta (ámbito `ANULACION_VENTA`) y se registra `ANULACION_COBRANZA` por su importe completo, en la misma transacción que la venta. `COBRANZA_ANULAR` DEBE seguir rechazándola con `COBRANZA_DE_VENTA` (409) mientras esté `CONFIRMADA`; si ya quedó `ANULADA` con su venta, responde `COBRANZA_YA_ANULADA` (409), porque la regla de estado va antes que la de origen. La base DEBE seguir impidiendo dos anulaciones de la misma cobranza (`design.md` D9).

#### Scenario: Anulada con la venta
- **GIVEN** la cobranza de $20.000 de una venta de $80.000
- **WHEN** se anula la venta con devolución
- **THEN** la cobranza queda `ANULADA` con una anulación cuyo motivo es el de la venta y se registra `ANULACION_COBRANZA` por $20.000
- **Regla:** VTA-22; COB-05; CC-02

#### Scenario: Por su propio comando
- **WHEN** se envía `COBRANZA_ANULAR` sobre la cobranza de una venta confirmada o anulada sin devolución
- **THEN** responde 409 `COBRANZA_DE_VENTA` y nada cambia
- **Regla:** COB-05; VTA-22

#### Scenario: Anulación de la venta sin devolución
- **WHEN** se anula la venta sin devolución
- **THEN** la cobranza sigue `CONFIRMADA` y sin anulación
- **Regla:** VTA-22

#### Scenario: Concurrencia con la cobranza
- **WHEN** se anula una venta con devolución mientras otra transacción envía `COBRANZA_ANULAR` sobre su cobranza, ambas confirmadas
- **THEN** la cobranza tiene una sola anulación, la de la venta, y `COBRANZA_ANULAR` responde `COBRANZA_DE_VENTA` si llega antes de que la venta se anule o `COBRANZA_YA_ANULADA` si llega después
- **Regla:** INV-05; INV-13; `02` §7.3
