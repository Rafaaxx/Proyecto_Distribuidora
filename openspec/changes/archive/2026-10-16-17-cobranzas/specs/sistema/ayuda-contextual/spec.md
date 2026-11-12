## ADDED Requirements

### Requirement: Las pantallas de cobranzas explican sus reglas

El alta de cobranza DEBE ofrecer ayuda en "Medios de pago", en el saldo resultante y en "Jornada"; el detalle, en "Jornada", junto a "Anular" y en las observaciones de sincronización. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051 y el aprobado en el change 16b (para qué sirve en una oración, palabras de todos los días, un ejemplo con nombres y montos reales, tres o cuatro oraciones) (`design.md` D20 del change 17).

#### Scenario: Medios de pago

- **GIVEN** el alta de una cobranza
- **WHEN** se abre el "(?)" de "Medios de pago"
- **THEN** explica que el importe se puede repartir en varios medios que suman justo el total y que algunos piden referencia, con un ejemplo de un pago de $50.000 repartido en $30.000 en efectivo y $20.000 por transferencia con su número
- **Regla:** COB-01, COB-02, INV-08

#### Scenario: Saldo a favor

- **GIVEN** el alta de una cobranza
- **WHEN** se abre el "(?)" del saldo resultante
- **THEN** explica que la cobranza baja la deuda total del cliente y no una venta, y que si paga de más le queda saldo a favor, con el ejemplo "debe $150.000 y paga $160.000 → le quedan $10.000 a favor"
- **Regla:** COB-03, CC-04

#### Scenario: Anular

- **GIVEN** el detalle de una cobranza confirmada, visto por quien tiene `ANULAR_COBRANZA`
- **WHEN** se abre el "(?)" junto a "Anular"
- **THEN** explica que el cliente vuelve a deber lo mismo, que la cobranza no se borra y que se anula entera
- **Regla:** COB-05, CC-02

#### Scenario: Observaciones de una cobranza sin señal

- **GIVEN** el detalle de una cobranza con `MEDIO_INACTIVO`
- **WHEN** se abre el "(?)" de las observaciones
- **THEN** explica que el pago se tomó igual porque la plata ya se cobró, y qué significan "Medio inactivo", "Falta la referencia", "Permiso revocado", "Jornada liberada" y "Cliente no habilitado" (el panel queda corto y el detalle de cada aviso va en su "Ver más", tema `cobranzas-observaciones`), con palabras de todos los días
- **Regla:** SYN-05, SYN-07, SYN-10, RUT-09
