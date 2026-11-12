## MODIFIED Requirements

### Requirement: El saldo y el stock locales suman lo que hizo el teléfono

Para vender, el teléfono DEBE usar como saldo del cliente el del bootstrap más los débitos y menos las cobranzas de las ventas locales de la jornada del bootstrap, y como stock disponible el del bootstrap menos lo vendido en esas mismas ventas. Esas ventas DEBEN contarse tengan o no resultado del servidor, hasta que la conciliación con un bootstrap posterior (change 22c) las descuente. Las operaciones de otra jornada NO DEBEN contarse (`design.md` D5 del 22a; `design.md` D4 del 22b).

#### Scenario: Segunda venta al mismo cliente
- **GIVEN** un cliente con límite $200.000 y saldo $100.000 en el bootstrap, y una venta local de la jornada por $70.000 con $20.000 cobrados
- **WHEN** el vendedor arma otra venta para ese cliente
- **THEN** el saldo considerado es $150.000 y el disponible $50.000
- **Regla:** CRE-08; COB-04

#### Scenario: Stock después de vender
- **GIVEN** 63 botellas de Vino A en el bootstrap y una venta local de 15
- **WHEN** el vendedor abre el producto en otra venta
- **THEN** el disponible es 48 botellas
- **Regla:** RUT-04; STK-04

#### Scenario: Ventas de otra jornada
- **GIVEN** ventas locales sin enviar de una jornada anterior en el mismo teléfono
- **WHEN** se calcula el stock de la jornada actual
- **THEN** esas ventas no cuentan
- **Regla:** RUT-04

#### Scenario: Venta ya enviada
- **GIVEN** 63 botellas de Vino A en el bootstrap y una venta local de 15 que el servidor ya aceptó
- **WHEN** el vendedor abre el producto en otra venta, sin haber actualizado los datos
- **THEN** el disponible sigue siendo 48 botellas
- **Regla:** RUT-04; CRE-08

### Requirement: Las operaciones locales no se borran hasta su resultado

Una venta local, su cobranza, sus movimientos y su comando NO DEBEN borrarse por un bootstrap, por cerrar sesión, por el login de otro usuario, por el bloqueo del PIN de desbloqueo ni por recibir su resultado del servidor. Cada venta local DEBE tener un estado de envío: al confirmarla es «Sin enviar» y cambia a «Enviada», «Con observaciones» o «Rechazada» solo con el resultado del servidor; una venta «Rechazada» DEBE seguir visible en el teléfono (`design.md` D13 del 22a; `design.md` D3 del 22b).

#### Scenario: Bootstrap con ventas sin enviar
- **GIVEN** dos ventas sin enviar
- **WHEN** el vendedor actualiza los datos
- **THEN** las dos ventas, sus movimientos y sus comandos siguen igual
- **Regla:** SYN-09; `02` §13.4

#### Scenario: Bloqueo del PIN de desbloqueo
- **GIVEN** una venta sin enviar
- **WHEN** se superan los fallos del PIN de desbloqueo y la sesión local se bloquea
- **THEN** la venta y su comando siguen en el teléfono
- **Regla:** SEG-04

#### Scenario: Resultado recibido
- **GIVEN** una venta sin enviar con su cobranza
- **WHEN** el servidor la acepta
- **THEN** la venta queda «Enviada» y la venta, su cobranza, sus movimientos y su comando siguen en el teléfono
- **Regla:** SYN-09

#### Scenario: Venta rechazada visible
- **GIVEN** una venta que el servidor rechazó
- **WHEN** el vendedor abre «Ventas de hoy»
- **THEN** la venta aparece como «Rechazada»
- **Regla:** SYN-09; SYN-06
