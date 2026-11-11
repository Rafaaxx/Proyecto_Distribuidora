## ADDED Requirements

### Requirement: Las anulaciones de compra y de pago a proveedor guardan su motivo en la auditoría

El registro de auditoría de `COMPRA_ANULAR` y de `PAGO_PROVEEDOR_ANULAR` aceptados DEBE guardar el motivo elegido en la anulación, igual que los comandos de stock que ya lo copian. Un comando rechazado NO DEBE dejar motivo (AUD-02; deuda del change 14, parte 1; ADR-070, deuda 2; `design.md` D1).

#### Scenario: Anulación de compra con motivo
- **GIVEN** una compra confirmada y un motivo activo de la organización
- **WHEN** se anula la compra con ese motivo
- **THEN** el registro de auditoría de `COMPRA_ANULAR` tiene ese motivo
- **Regla:** AUD-02

#### Scenario: Anulación de pago con motivo
- **GIVEN** un pago a proveedor confirmado y un motivo activo
- **WHEN** se anula el pago con ese motivo
- **THEN** el registro de auditoría de `PAGO_PROVEEDOR_ANULAR` tiene ese motivo
- **Regla:** AUD-02

#### Scenario: Una anulación rechazada no deja motivo
- **GIVEN** una compra ya anulada
- **WHEN** se intenta anularla de nuevo con un motivo
- **THEN** el comando se rechaza y ningún registro de auditoría aceptado de esa compra lleva el motivo del intento
- **Regla:** AUD-02; INV-01

#### Scenario: Doble envío de la anulación
- **GIVEN** una anulación de pago aceptada
- **WHEN** se reenvía con el mismo `operation_id`
- **THEN** se devuelve el resultado original y existe un solo registro de auditoría con el motivo
- **Regla:** INV-06
