## ADDED Requirements

### Requirement: Un producto con stock no se desactiva

`PRODUCTO_MODIFICAR` que pasa un producto de activo a inactivo DEBE rechazarse con `PRODUCTO_CON_STOCK` (409), sin cambiar nada, si el producto tiene algún saldo de stock **distinto de cero** en cualquier ubicación de la organización, incluidos los saldos negativos; se mira cada saldo, no el stock total (CAT-05, ADR-038 puntos 4 y 5, `design.md` D4 del change 14). Reactivar un producto, o guardar uno que ya estaba inactivo sin cambiar su estado, NO DEBE disparar la comprobación. El catálogo DEBE consultar el stock sin depender del módulo de stock, por un verificador que ese módulo registra al arrancar; sin verificador registrado, la desactivación DEBE fallar con un error de configuración y NO DEBE aceptarse sin comprobar (`design.md` D4.1; ADR-023, ADR-025). La desactivación DEBE tomar el producto con bloqueo exclusivo, para serializarse con un movimiento de stock simultáneo: nunca DEBE quedar un producto inactivo con stock recién ingresado (`design.md` D4.2). Los productos que ya estaban inactivos con stock antes de esta regla NO se modifican: para vaciarlos se reactivan, se vacían y se vuelven a desactivar.

#### Scenario: Desactivar un producto con stock

- **GIVEN** "Vino Rosado" activo con 18 unidades en "Camioneta 1" y 0 en el depósito
- **WHEN** se envía `PRODUCTO_MODIFICAR` con `activo` falso
- **THEN** se rechaza con `PRODUCTO_CON_STOCK` (409) y el producto sigue activo
- **Regla:** CAT-05; ADR-038; `design.md` D4

#### Scenario: Desactivar un producto sin stock

- **GIVEN** "Vino Rosado" activo, con movimientos en el libro y todos sus saldos en 0
- **WHEN** se envía `PRODUCTO_MODIFICAR` con `activo` falso
- **THEN** se acepta y el producto queda inactivo
- **Regla:** CAT-05; `design.md` D4

#### Scenario: Saldos que se compensan

- **GIVEN** un producto activo con +5 en el depósito y −5 en "Camioneta 1" (stock total 0)
- **WHEN** se lo desactiva
- **THEN** se rechaza con `PRODUCTO_CON_STOCK`
- **Regla:** STK-04; `design.md` D4

#### Scenario: Saldo negativo

- **GIVEN** un producto activo con −12 en el depósito
- **WHEN** se lo desactiva
- **THEN** se rechaza con `PRODUCTO_CON_STOCK`
- **Regla:** STK-05; `design.md` D4

#### Scenario: Modificar otros datos de un producto con stock

- **GIVEN** un producto activo con stock
- **WHEN** se envía `PRODUCTO_MODIFICAR` cambiando el nombre y dejando `activo` verdadero
- **THEN** se acepta
- **Regla:** CAT-05; `design.md` D4

#### Scenario: Producto ya inactivo con stock

- **GIVEN** "Vino Blanco" inactivo desde antes de esta regla, con 6 unidades en el depósito
- **WHEN** se envía `PRODUCTO_MODIFICAR` dejándolo inactivo, y después otro reactivándolo
- **THEN** ambos se aceptan; ya activo, no puede volver a desactivarse hasta que su saldo sea 0
- **Regla:** CAT-05; `design.md` D4

#### Scenario: Sin verificador de stock registrado

- **GIVEN** el catálogo sin ningún verificador de stock registrado
- **WHEN** se desactiva un producto
- **THEN** la operación falla con un error de configuración y el producto sigue activo
- **Regla:** TR-10; ADR-025; `design.md` D4.1

#### Scenario: Stock de otra organización

- **GIVEN** un producto de la organización A sin stock y un producto de la organización B con stock
- **WHEN** la organización A desactiva el suyo
- **THEN** se acepta: solo cuentan los saldos de su organización
- **Regla:** INV-21; SEG-07

#### Scenario: Desactivación e ingreso simultáneos

- **GIVEN** un producto activo sin stock, su desactivación y, a la vez, una transferencia que le ingresa 6 unidades en "Camioneta 1"
- **WHEN** las dos transacciones confirman
- **THEN** o la desactivación falla con `PRODUCTO_CON_STOCK`, o la transferencia falla con `PRODUCTO_INACTIVO`; nunca queda un producto inactivo con stock
- **Regla:** CAT-05; ADR-038; `design.md` D4.2
