## MODIFIED Requirements

### Requirement: El saldo y el stock locales suman lo que hizo el teléfono

Para vender y para las pantallas de consulta, el teléfono DEBE usar como saldo del cliente el del bootstrap más los débitos y menos las cobranzas de las operaciones locales de la jornada del bootstrap que el bootstrap todavía no incluye, y como stock disponible el del bootstrap menos lo vendido en esas mismas operaciones. Una operación local está incluida en el bootstrap cuando su secuencia es menor o igual que la secuencia procesada que informó ese bootstrap; esas NO DEBEN contarse. Las demás DEBEN contarse tengan o no resultado del servidor. Una venta «Rechazada» DEBE seguir contando en su jornada, cualquiera sea su secuencia. Un bootstrap sin secuencia procesada DEBE tratarse como si no incluyera ninguna operación local. Las operaciones de otra jornada NO DEBEN contarse. El bootstrap NO DEBE modificar los movimientos locales (`design.md` D1 y D2; D5 del 22a; D4 del 22b).

#### Scenario: Segunda venta al mismo cliente
- **GIVEN** un cliente con límite $200.000 y saldo $100.000 en el bootstrap, y una venta local de la jornada por $70.000 con $20.000 cobrados que el bootstrap no incluye
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

#### Scenario: Venta ya enviada, después de actualizar los datos
- **GIVEN** una venta local de 15 botellas de Vino A con secuencia 7 que el servidor aceptó, y un bootstrap posterior con 48 botellas y secuencia procesada 7
- **WHEN** el vendedor abre el producto en otra venta
- **THEN** el disponible es 48 botellas, no 33
- **Regla:** RUT-04; CRE-08; SYN-11

#### Scenario: Respuesta del lote perdida
- **GIVEN** una venta local de 15 botellas con secuencia 7 que el servidor procesó pero cuya respuesta no llegó, de modo que en el teléfono sigue «Sin enviar»
- **WHEN** llega un bootstrap con 48 botellas y secuencia procesada 7
- **THEN** el disponible es 48 botellas y la venta sigue «Sin enviar» hasta el reenvío
- **Regla:** CRE-08; INV-06

#### Scenario: Venta posterior a la foto
- **GIVEN** un bootstrap con secuencia procesada 7 y dos ventas locales de la jornada con secuencias 7 y 8
- **WHEN** se calcula el saldo del cliente
- **THEN** solo cuenta la de secuencia 8
- **Regla:** CRE-08

#### Scenario: Venta rechazada
- **GIVEN** una venta local de 15 botellas con secuencia 7 que el servidor rechazó, y un bootstrap con secuencia procesada 9
- **WHEN** se calcula el stock de la jornada
- **THEN** la venta rechazada sigue descontando sus 15 botellas
- **Regla:** RUT-04; SYN-06; SYN-09

#### Scenario: Bootstrap sin secuencia procesada
- **GIVEN** un bootstrap descargado antes de este cambio, sin secuencia procesada, y una venta aceptada de la jornada
- **WHEN** se calcula el stock
- **THEN** la venta cuenta, como antes
- **Regla:** CRE-08

#### Scenario: Doble sincronización
- **GIVEN** una venta aceptada e incluida en el bootstrap
- **WHEN** se sincroniza otra vez y el servidor devuelve el mismo resultado
- **THEN** el saldo y el stock locales no cambian
- **Regla:** INV-06; SYN-02

#### Scenario: El bootstrap no toca los movimientos
- **GIVEN** tres movimientos locales de la jornada
- **WHEN** se aplica un bootstrap con secuencia procesada
- **THEN** los tres movimientos siguen igual en el teléfono
- **Regla:** SYN-09; `02` §13.4
