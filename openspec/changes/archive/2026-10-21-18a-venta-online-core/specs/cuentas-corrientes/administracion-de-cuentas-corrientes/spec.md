## ADDED Requirements

### Requirement: La cuenta corriente del cliente lleva a sus ventas

En la pantalla de cuenta corriente, un movimiento `VENTA` DEBE llevar al detalle de la venta para quien tiene `VENDER` o `ANULAR_VENTA`; sin esos permisos, el movimiento se muestra sin enlace (CC-07, `design.md` D21 del change 18a).

#### Scenario: Enlace a la venta
- **GIVEN** la cuenta de Kiosco La Esquina con un débito `VENTA` de `"31250.00"` y el crédito `COBRANZA` de su cobranza
- **WHEN** un Supervisor abre la cuenta
- **THEN** el débito lleva al detalle de la venta y el crédito al de la cobranza
- **Regla:** CC-07; CC-05

#### Scenario: Sin permiso de ventas
- **WHEN** un usuario con `GESTIONAR_CLIENTES` y sin `VENDER` ni `ANULAR_VENTA` abre la misma cuenta
- **THEN** el débito se muestra sin enlace
- **Regla:** `01` §19
