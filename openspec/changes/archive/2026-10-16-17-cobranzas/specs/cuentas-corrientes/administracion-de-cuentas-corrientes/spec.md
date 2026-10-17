## ADDED Requirements

### Requirement: La cuenta corriente del cliente lleva a sus cobranzas

La pantalla de cuenta corriente de un cliente DEBE ofrecer "Registrar cobranza", con el cliente precargado, a quien tiene `REGISTRAR_COBRANZA`, salvo para el consumidor final. Cada movimiento `COBRANZA` y `ANULACION_COBRANZA` DEBE enlazar al detalle de su cobranza para quien tiene `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA`; sin esos permisos, el movimiento se ve sin enlace (`design.md` D19 del change 17, ADR-027).

#### Scenario: Registrar desde la cuenta
- **GIVEN** un usuario con `GESTIONAR_CLIENTES` y `REGISTRAR_COBRANZA` en la cuenta de `Kiosco La Esquina`
- **WHEN** elige "Registrar cobranza"
- **THEN** se abre el alta con el cliente precargado y el saldo "Nos debe $ 150.000,00"
- **Regla:** COB-01; CC-07

#### Scenario: Enlace al detalle
- **GIVEN** la cuenta con un movimiento `COBRANZA` de `"50000.00"`
- **WHEN** el usuario con `ANULAR_COBRANZA` elige ese movimiento
- **THEN** se abre el detalle de la cobranza
- **Regla:** CC-01; ADR-027

#### Scenario: Sin permiso de cobranzas
- **GIVEN** un usuario con solo `GESTIONAR_CLIENTES`
- **WHEN** abre la cuenta
- **THEN** ve los movimientos `COBRANZA` sin enlace y no ve "Registrar cobranza"
- **Regla:** ADR-027

#### Scenario: Consumidor final
- **WHEN** se abre la cuenta del consumidor final
- **THEN** no se ofrece "Registrar cobranza"
- **Regla:** CLI-03; `design.md` D4 del change 17
