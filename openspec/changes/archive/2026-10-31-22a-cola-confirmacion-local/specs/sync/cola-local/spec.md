## Purpose

Confirma en el teléfono una venta de `/ruta` como una operación completa e indivisible: la venta, su cobranza, sus efectos locales sobre stock y saldo y el comando que el motor de sincronización enviará después, con número y orden asignados sin huecos ni repeticiones (`02` §13.2, §6.2, §7.7; INV-01).

## ADDED Requirements

### Requirement: Confirmar una venta local es una sola transacción

Confirmar una venta en `/ruta` DEBE escribir, en una única transacción de la base local, la venta con sus líneas calculadas, su cobranza si existe, los movimientos locales de stock y de cuenta, el comando `VENTA_CONFIRMAR` en la cola y los contadores de número y de secuencia del dispositivo. Si cualquier escritura falla, NO DEBE quedar ninguna de ellas y el carrito DEBE seguir abierto con un aviso de error. El cálculo de la venta y la verificación de credenciales DEBEN completarse antes de iniciar la transacción (`design.md` D4).

#### Scenario: Confirmación completa
- **GIVEN** `vendedor` con su jornada abierta y un carrito de 2 cajas y 3 botellas de Vino A (caja x6 a $12.500) para un cliente, con $20.000 cobrados en efectivo
- **WHEN** confirma la venta
- **THEN** la base local tiene la venta por $31.250,00, su cobranza de $20.000,00, un movimiento de stock de −15 botellas, un débito de $31.250,00 y un crédito de $20.000,00 en la cuenta local del cliente, y un comando en la cola, todos con el mismo `operation_id`
- **Regla:** INV-01; VTA-12; PRC-22; RUT-04

#### Scenario: Falla a mitad de la confirmación
- **GIVEN** un carrito listo para confirmar
- **WHEN** la escritura del comando en la cola falla después de escribir la venta
- **THEN** no queda la venta, ni la cobranza, ni ningún movimiento local, ni el comando; el número y la secuencia no avanzan; el carrito sigue abierto con un aviso de error
- **Regla:** INV-01

#### Scenario: Doble toque en confirmar
- **GIVEN** un carrito ya confirmado
- **WHEN** la confirmación se repite con el mismo carrito (doble toque o reintento tras un error)
- **THEN** hay una sola venta y un solo comando en la cola con ese `operation_id`
- **Regla:** INV-06; SYN-02

#### Scenario: Cantidades e importes exactos
- **WHEN** se confirma cualquier venta local
- **THEN** los importes quedan guardados como texto con dos decimales y las cantidades como enteros en unidad base
- **Regla:** INV-03; INV-04

### Requirement: El número de la venta lo asigna el teléfono al confirmar

El número DEBE ser el prefijo del dispositivo seguido del correlativo de seis dígitos siguiente al mayor entre el último del bootstrap y el último usado en el teléfono, y DEBE asignarse dentro de la transacción de confirmación. Un carrito descartado NO DEBE consumir número (`design.md` D4; `02` §7.7).

#### Scenario: Primera venta tras el bootstrap
- **GIVEN** un dispositivo con prefijo V03, último correlativo 141 en el bootstrap y ninguno usado en el teléfono
- **WHEN** se confirma una venta
- **THEN** su número es V03-000142
- **Regla:** VTA-06

#### Scenario: El teléfono va adelante del servidor
- **GIVEN** el teléfono ya usó V03-000145 y el bootstrap informa 141
- **WHEN** se confirma una venta
- **THEN** su número es V03-000146
- **Regla:** VTA-06; `02` §7.7

#### Scenario: Carrito descartado
- **GIVEN** la última venta fue V03-000142
- **WHEN** el vendedor descarta un carrito y confirma otro
- **THEN** el confirmado es V03-000143
- **Regla:** VTA-06

### Requirement: La cola guarda el comando completo y en orden

Cada comando de la cola DEBE tener una secuencia del dispositivo estrictamente creciente y DEBE guardar el sobre completo del lote: `operation_id` UUIDv7 generado en el teléfono, tipo `VENTA_CONFIRMAR`, versión, modo `OFFLINE`, usuario y dispositivo de la sesión local, jornada del bootstrap, `occurred_at` del momento de confirmar, secuencia, versión de la aplicación y contenido. El contenido NO DEBE llevar PIN ni credenciales y DEBE llevar el objeto de crédito con límite, saldo considerado, política y resolución. El sobre armado por el teléfono DEBE ser aceptado por el lote de sincronización del servidor (`design.md` D1, D2, D9).

#### Scenario: Orden de la cola
- **GIVEN** la cola con su última secuencia en 7
- **WHEN** se confirman dos ventas seguidas
- **THEN** sus comandos tienen las secuencias 8 y 9 en el orden en que se confirmaron
- **Regla:** SYN-03; `02` §6.4

#### Scenario: Sin credenciales en la cola
- **GIVEN** una venta con descuento autorizado por `sup01` con su PIN
- **WHEN** se encola
- **THEN** el comando lleva el autorizador y ningún PIN, derivación ni credencial
- **Regla:** ADR-056; SEG-05

#### Scenario: Contrato con el servidor
- **GIVEN** el sobre que arma el teléfono para una venta con cobranza, descuento manual y exceso de crédito por tolerancia
- **WHEN** se envía tal cual al lote de sincronización del servidor
- **THEN** el servidor lo acepta (`ACEPTADO` o `ACEPTADO_CON_OBSERVACIONES`), no como malformado
- **Regla:** SYN-01; SYN-05; CRE-09

#### Scenario: Doble envío del mismo sobre
- **GIVEN** el sobre de contrato ya aceptado por el lote
- **WHEN** se envía otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** el servidor devuelve el resultado original y no registra otra venta
- **Regla:** INV-06; SYN-02

### Requirement: El saldo y el stock locales suman lo que hizo el teléfono

Para vender, el teléfono DEBE usar como saldo del cliente el del bootstrap más los débitos y menos las cobranzas de las ventas locales de la jornada del bootstrap que no tienen resultado del servidor, y como stock disponible el del bootstrap menos lo vendido en esas mismas ventas. Las operaciones de otra jornada NO DEBEN contarse (`design.md` D5).

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

### Requirement: Las operaciones locales no se borran hasta su resultado

Una venta local, su cobranza, sus movimientos y su comando NO DEBEN borrarse por un bootstrap, por cerrar sesión, por el login de otro usuario ni por el bloqueo del PIN de desbloqueo. Cada venta local DEBE tener un estado de envío; al confirmarla es "Sin enviar" (`design.md` D13).

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
