## ADDED Requirements

### Requirement: Registrar una cobranza local es una sola transacción

Registrar una cobranza en el teléfono DEBE escribir, en una sola transacción de la base local, la cobranza (identificador, cliente, importe, medios, observación, jornada, momento, origen `INDEPENDIENTE`, estado «Sin enviar» y `operation_id` propio), un movimiento local de crédito por el importe en la cuenta del cliente y el comando `COBRANZA_REGISTRAR` en modo `OFFLINE` con la siguiente secuencia de la cola, y avanzar la última secuencia; si algo falla NO DEBE quedar nada y la secuencia NO DEBE avanzar. Confirmar otra vez la misma cobranza NO DEBE crear otra cobranza ni otro comando (`design.md` D1, D5).

#### Scenario: Cobranza local
- **GIVEN** Kiosco La Esquina en los datos del día y la última secuencia 7
- **WHEN** el vendedor registra una cobranza de $50.000 con $30.000 en efectivo y $20.000 por transferencia n.º 0042
- **THEN** quedan la cobranza «Sin enviar», un crédito de $50.000 al cliente y el comando `COBRANZA_REGISTRAR` con secuencia 8, todo con el `operation_id` de la cobranza
- **Regla:** COB-01; COB-04; INV-01; SYN-01

#### Scenario: Falla a mitad de la cobranza
- **WHEN** la escritura del comando falla después de escribir la cobranza y el movimiento
- **THEN** no queda la cobranza, ni el movimiento, ni el comando, y la última secuencia no avanza
- **Regla:** INV-01

#### Scenario: Doble toque
- **GIVEN** una cobranza ya registrada en el teléfono
- **WHEN** se confirma otra vez el mismo formulario
- **THEN** no se escribe nada nuevo y se muestra la cobranza existente
- **Regla:** INV-06; SYN-02

#### Scenario: Cobranza después de una venta sin enviar
- **GIVEN** una venta «Sin enviar» con secuencia 7
- **WHEN** el vendedor cobra al mismo cliente
- **THEN** la cobranza queda con secuencia 8 y las dos se envían en ese orden
- **Regla:** SYN-03

### Requirement: La cobranza local cuenta en el saldo local

El crédito de una cobranza local DEBE contar en el saldo local del cliente por la misma regla que una venta: desde que se confirma y hasta que un bootstrap con secuencia procesada mayor o igual que la suya la incluya. Una cobranza independiente «Rechazada» NO DEBE contar. El cobro en el momento de una venta DEBE seguir la regla de su venta, sin cambios (`design.md` D6).

#### Scenario: Crédito después de cobrar
- **GIVEN** Kiosco La Esquina con límite $200.000 y saldo $150.000 en el bootstrap
- **WHEN** el vendedor le cobra $50.000 en el teléfono
- **THEN** el saldo considerado es $100.000 y el disponible $100.000
- **Regla:** CRE-08; CRE-01; COB-04

#### Scenario: Cobranza incluida en el bootstrap
- **GIVEN** la cobranza de $50.000 con secuencia 8 aceptada y un bootstrap con saldo $100.000 y secuencia procesada 8
- **WHEN** se calcula el saldo
- **THEN** el saldo considerado es $100.000, no $50.000
- **Regla:** CRE-08; INV-06; SYN-11

#### Scenario: Cobranza pendiente después de actualizar los datos
- **GIVEN** un bootstrap con saldo $150.000 y secuencia procesada 7, y la cobranza de $50.000 con secuencia 8 sin enviar
- **WHEN** se calcula el saldo
- **THEN** el saldo considerado es $100.000
- **Regla:** CRE-08; SYN-11

#### Scenario: Cobranza rechazada
- **GIVEN** la cobranza de $50.000 rechazada por el servidor y el saldo del bootstrap en $150.000
- **WHEN** se calcula el saldo
- **THEN** la cobranza no cuenta y el saldo considerado es $150.000
- **Regla:** CRE-08; SYN-06; SYN-09

#### Scenario: El cobro de una venta rechazada sigue con su venta
- **GIVEN** una venta rechazada con su cobro en el momento
- **WHEN** se calcula el saldo
- **THEN** la venta y su cobro siguen contando completos, como hasta ahora
- **Regla:** CRE-08; ADR-065

#### Scenario: Saldo a favor
- **GIVEN** Kiosco La Esquina debe $150.000 en el bootstrap
- **WHEN** el vendedor le cobra $160.000
- **THEN** el saldo considerado es −$10.000: $10.000 a favor del cliente
- **Regla:** COB-01; CC-04

#### Scenario: Doble sincronización
- **GIVEN** una cobranza aceptada e incluida en el bootstrap
- **WHEN** se sincroniza otra vez y el servidor devuelve el mismo resultado
- **THEN** el saldo local no cambia
- **Regla:** INV-06
