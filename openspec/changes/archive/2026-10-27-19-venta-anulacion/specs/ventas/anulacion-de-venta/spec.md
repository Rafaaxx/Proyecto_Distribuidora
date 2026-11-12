## Purpose

Corregir una venta confirmada anulándola por completo, con conexión, con permiso y motivo: la mercadería vuelve a su ubicación al costo congelado, la cuenta del cliente se acredita por el total y el dinero cobrado se devuelve o queda a favor (VTA-20 a VTA-22, INV-19). Escrita con las opciones recomendadas (A) de `design.md` D1 a D19, pendientes de aprobación.

## ADDED Requirements

### Requirement: Una venta se anula por comando con permiso y motivo

El sistema DEBE ofrecer el comando `VENTA_ANULAR` v1 por el bus, solo en modo `ONLINE`, por `POST /api/v1/ventas/{venta_id}/anulacion`. El contenido DEBE llevar la venta (su identificador), un motivo activo de la organización del ámbito `ANULACION_VENTA`, una observación opcional de hasta 500 caracteres y, según la regla del dinero cobrado, `devuelve_dinero`. Cualquier campo extra DEBE rechazarse como contenido inválido. DEBE exigir `ANULAR_VENTA`. El resultado DEBE traer la venta, su estado `ANULADA`, el saldo del cliente después de anular (como string), la cobranza de la venta si existía y si quedó anulada (`design.md` D1, D14).

#### Scenario: Anulación de una venta sin cobro
- **GIVEN** la venta V03-000142 a Kiosco La Esquina por $80.000, `CONFIRMADA` y sin cobranza, y el usuario `sup01` con `ANULAR_VENTA`
- **WHEN** envía `VENTA_ANULAR` con el motivo "Error de carga" y sin `devuelve_dinero`
- **THEN** la venta queda `ANULADA`, el resultado trae `"estado": "ANULADA"` y el saldo del cliente como string
- **Regla:** VTA-20; INV-03

#### Scenario: Sin permiso
- **GIVEN** el usuario `vendedor`, que tiene `VENDER` pero no `ANULAR_VENTA`
- **WHEN** intenta anular la venta
- **THEN** recibe 403 `PERMISO_REQUERIDO` y nada cambia
- **Regla:** VTA-20; SEG-06; INV-01

#### Scenario: Motivo de otro ámbito o inactivo
- **WHEN** se anula con un motivo del ámbito `ANULACION_COBRANZA`, o con uno de `ANULACION_VENTA` desactivado
- **THEN** responde 422 `MOTIVO_INVALIDO` y nada cambia
- **Regla:** VTA-20; TR-09

#### Scenario: Observación demasiado larga
- **WHEN** la observación tiene 501 caracteres
- **THEN** responde 422 `OBSERVACION_INVALIDA` y nada cambia
- **Regla:** VTA-20

#### Scenario: Modo sin conexión todavía no admitido
- **WHEN** llega `VENTA_ANULAR` en un lote de sincronización en modo `OFFLINE`
- **THEN** se rechaza como tipo que no admite ese modo y no queda ningún efecto
- **Regla:** VTA-24 (change 22c); `02` §6.5; SYN-06

#### Scenario: Venta de otra organización
- **WHEN** un Supervisor de la organización A anula una venta de la organización B, o usa un motivo de B
- **THEN** responde 404 y nada cambia en ninguna organización
- **Regla:** INV-21

### Requirement: Una venta se anula una sola vez y entera

Solo una venta `CONFIRMADA` DEBE poder anularse; una ya `ANULADA` DEBE responder `VENTA_YA_ANULADA` (409). No existe anulación parcial. La base DEBE impedir dos anulaciones de la misma venta. Anular NO DEBE borrar ni modificar ninguna fila de la venta, sus líneas, sus descuentos ni su evaluación de crédito; el único cambio sobre la venta es su estado (`design.md` D10, D11).

#### Scenario: Segunda anulación
- **GIVEN** una venta ya `ANULADA`
- **WHEN** se la anula de nuevo con otro `operation_id`
- **THEN** responde 409 `VENTA_YA_ANULADA` y no se registra ningún movimiento
- **Regla:** VTA-20; TR-06

#### Scenario: Doble envío
- **WHEN** se reenvía el mismo `VENTA_ANULAR` con el mismo `operation_id` y la misma huella
- **THEN** se devuelve el resultado original y hay un solo juego de movimientos de anulación
- **Regla:** INV-06; SYN-02

#### Scenario: Dos anulaciones simultáneas
- **GIVEN** dos usuarios con `ANULAR_VENTA`
- **WHEN** anulan la misma venta al mismo tiempo, con transacciones confirmadas
- **THEN** una termina `ANULADA` con sus movimientos y la otra recibe `VENTA_YA_ANULADA`; hay una sola fila de anulación
- **Regla:** VTA-20; INV-05; INV-12; INV-13

#### Scenario: Valores congelados intactos
- **WHEN** se anula una venta con descuentos y evaluación de crédito
- **THEN** las líneas, los descuentos, los costos y el snapshot de crédito quedan iguales y `app_runtime` no tiene `UPDATE` sobre otra columna que `venta.estado`
- **Regla:** INV-10; INV-05

### Requirement: La anulación devuelve el stock al costo congelado

La anulación DEBE registrar, por cada línea de la venta y en su orden, un ingreso `ANULACION_VENTA` de su cantidad base en la ubicación de la venta, con origen en la venta, al costo unitario congelado de la línea, que recalcula el promedio según CST-11 y deja historia. Una línea vendida sin costo DEBE ingresar sin recalcular el promedio y sin historia, con costo nulo. El reingreso nunca deja stock negativo (`design.md` D5).

#### Scenario: Reingreso que recalcula el promedio
- **GIVEN** Vino A con la historia del ejemplo de CST-11: la venta de 72 (costo congelado $75.600,00, costo unitario $1.050,000000) y después la compra de 60 a $1.200 (stock total 108, promedio $1.133,333333)
- **WHEN** se anula la venta
- **THEN** ingresan 72 unidades a la ubicación de la venta a $1.050,000000, el promedio pasa a $1.100,000000 y queda una fila de historia con origen `ANULACION_VENTA`
- **Regla:** VTA-21; CST-11; CST-13

#### Scenario: Stock total previo en cero
- **GIVEN** Vino A con stock total 0 después de la venta de 72 a $1.050,000000
- **WHEN** se anula la venta
- **THEN** el stock total queda en 72 y el promedio en $1.050,000000
- **Regla:** VTA-21; CST-11

#### Scenario: Línea vendida sin costo
- **GIVEN** una venta recibida sin conexión con una línea de Agua B sin costo (`VENTA_SIN_COSTO`)
- **WHEN** se anula
- **THEN** ingresa la cantidad de esa línea con costo nulo, el promedio de Agua B no cambia y no queda fila de historia para ella
- **Regla:** VTA-21; CST-12; ADR-058

#### Scenario: Cajas y unidades del mismo producto
- **GIVEN** una venta con 2 cajas x6 y 3 botellas de Vino A (dos líneas)
- **WHEN** se anula
- **THEN** hay dos ingresos, de 12 y de 3 unidades base, en el orden de la venta
- **Regla:** VTA-02; VTA-21; INV-04

### Requirement: La anulación acredita el total en la cuenta del cliente

La anulación DEBE registrar un movimiento `ANULACION_VENTA` que reduce el saldo del cliente por el total de la venta, con origen en la venta, en la misma transacción que el stock (`design.md` D10).

#### Scenario: Venta sin cobro
- **GIVEN** Kiosco La Esquina con saldo $150.000 antes de una venta de $80.000 sin cobro (saldo $230.000)
- **WHEN** se anula la venta
- **THEN** se registra `ANULACION_VENTA` por $80.000 y el saldo vuelve a $150.000
- **Regla:** VTA-21; CC-02; INV-13; INV-19

### Requirement: Al anular se decide qué pasa con el dinero cobrado

Si la venta tiene su cobranza `CONFIRMADA`, `devuelve_dinero` DEBE indicarse; si no la tiene, DEBE omitirse; en otro caso `DEVOLUCION_INVALIDA` (422). Con devolución, la cobranza DEBE quedar `ANULADA`, con su anulación registrada con el motivo y la observación de la venta, y un movimiento `ANULACION_COBRANZA` por su importe completo. Sin devolución, la cobranza DEBE quedar como estaba y su importe como saldo a favor. En una venta al consumidor final, `devuelve_dinero` falso DEBE rechazarse con `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409) (`design.md` D2, D3, D4, D9).

#### Scenario: Con devolución
- **GIVEN** Kiosco La Esquina con saldo $150.000, una venta de $80.000 con cobranza de $20.000 (saldo $210.000)
- **WHEN** se anula con `devuelve_dinero` verdadero
- **THEN** se registran `ANULACION_VENTA` por $80.000 y `ANULACION_COBRANZA` por $20.000, la cobranza queda `ANULADA` y el saldo vuelve a $150.000
- **Regla:** VTA-22; COB-05; INV-19

#### Scenario: Sin devolución
- **GIVEN** el mismo caso
- **WHEN** se anula con `devuelve_dinero` falso
- **THEN** se registra solo `ANULACION_VENTA` por $80.000, la cobranza sigue `CONFIRMADA` y el saldo queda en $130.000
- **Regla:** VTA-22; CC-05; ADR-058

#### Scenario: Cobranza mayor que el total
- **GIVEN** una venta de $80.000 con cobranza de $100.000
- **WHEN** se anula con devolución
- **THEN** se anula la cobranza completa ($100.000) y el saldo queda como antes de la venta
- **Regla:** VTA-11; VTA-22

#### Scenario: Falta o sobra la indicación
- **WHEN** se anula una venta con cobranza sin `devuelve_dinero`, o una venta sin cobranza con `devuelve_dinero`
- **THEN** responde 422 `DEVOLUCION_INVALIDA` y nada cambia
- **Regla:** VTA-22; ADR-058

#### Scenario: Consumidor final
- **GIVEN** una venta de $4.300 al consumidor final cobrada entera
- **WHEN** se anula con `devuelve_dinero` falso
- **THEN** responde 409 `CONSUMIDOR_FINAL_SIN_DEVOLUCION`; con `devuelve_dinero` verdadero la venta y la cobranza quedan `ANULADA` y su cuenta vuelve a cero
- **Regla:** CLI-03; VTA-22; ADR-058

### Requirement: Anular deja el stock y el saldo como si la venta no se hubiera registrado

Después de anular con devolución, el stock de cada producto en cada ubicación y el saldo del cliente DEBEN ser iguales a los anteriores a la venta, y ninguna fila DEBE haberse borrado. Sin devolución, el stock DEBE ser igual y el saldo DEBE diferir solo en el importe de la cobranza (`design.md` D4).

#### Scenario: Propiedad con SQL
- **GIVEN** ventas generadas al azar (líneas, presentaciones, cobranza nula, parcial, total o mayor)
- **WHEN** se confirma cada venta y se la anula con devolución
- **THEN** la suma de movimientos por producto y ubicación y la suma del libro del cliente, calculadas con SQL, son iguales a las de antes de la venta, y la cantidad de filas de los libros solo creció
- **Regla:** INV-19; INV-12; INV-13; INV-05

### Requirement: La mercadería vuelve a la ubicación original con la regla de toma

El reingreso DEBE ir a la ubicación de la venta. Si está tomada por una jornada que no es la del comando, DEBE aceptarse solo para quien tiene `LIBERAR_UBICACION` (el movimiento sin jornada y la jornada nombrada en la auditoría); en otro caso `UBICACION_TOMADA` (409). Una ubicación inactiva DEBE rechazar la anulación con `UBICACION_INACTIVA` (409). Si el usuario y el dispositivo del comando tienen una jornada `ABIERTA` sobre esa ubicación, el reingreso y la anulación DEBEN llevar esa jornada; si no, quedan sin jornada. Una venta de una jornada cerrada o liberada DEBE poder anularse con conexión (`design.md` D6, D8).

#### Scenario: Camioneta tomada por otro vendedor
- **GIVEN** una venta de Juan desde la camioneta 2, que hoy tiene Pedro en una jornada `ABIERTA`
- **WHEN** `ges01` (sin `LIBERAR_UBICACION`) la anula
- **THEN** responde 409 `UBICACION_TOMADA` y nada cambia
- **Regla:** STK-09; VTA-21; ADR-058

#### Scenario: Supervisor con `LIBERAR_UBICACION`
- **WHEN** `sup01` anula la misma venta
- **THEN** la mercadería vuelve a la camioneta 2 sin jornada en el movimiento y la auditoría nombra la jornada de Pedro
- **Regla:** STK-09; AUD-01

#### Scenario: Jornada propia abierta
- **GIVEN** un usuario con `ANULAR_VENTA` y una jornada `ABIERTA` en la camioneta 2 en su dispositivo
- **WHEN** anula desde ese dispositivo una venta de la camioneta 2
- **THEN** el reingreso y la anulación llevan su jornada
- **Regla:** RUT-04; STK-09

#### Scenario: Venta de una jornada cerrada con la ubicación libre
- **GIVEN** una venta de una jornada ya `CERRADA` y la camioneta sin jornada
- **WHEN** un Supervisor la anula
- **THEN** se anula y la anulación queda sin jornada
- **Regla:** VTA-20; STK-09

#### Scenario: Ubicación inactiva
- **WHEN** se anula una venta cuya ubicación fue desactivada
- **THEN** responde 409 `UBICACION_INACTIVA` y nada cambia
- **Regla:** STK-02; ADR-058

### Requirement: Se anula aunque los maestros se hayan desactivado

Una venta DEBE poder anularse aunque su cliente esté suspendido o inactivo o su producto o presentación estén inactivos (`design.md` D7).

#### Scenario: Producto desactivado
- **GIVEN** una venta de Vino A y Vino A desactivado después
- **WHEN** se anula
- **THEN** se anula y Vino A queda con el stock reingresado
- **Regla:** CAT-05; VTA-21; ADR-058

#### Scenario: Cliente inactivo
- **WHEN** se anula una venta de un cliente que hoy está `INACTIVO`
- **THEN** se anula y el movimiento queda en su cuenta
- **Regla:** CLI-02; VTA-20

### Requirement: La anulación es atómica y respeta el orden de bloqueo

Venta, stock, costo, cuenta, cobranza, estado y auditoría DEBEN registrarse en una sola transacción: si algo falla, nada queda. La venta y después su cobranza DEBEN tomarse antes de `saldo_cuenta`, y el resto en el orden global de `02` §7.3. La precedencia de rechazos DEBE ser: contenido, venta (404, `VENTA_YA_ANULADA`), motivo, dinero cobrado, ubicación (`design.md` D10).

#### Scenario: Falla inyectada
- **WHEN** se inyecta una falla después de cada efecto (stock, costo, cuenta, cobranza, estado, auditoría)
- **THEN** en cada caso la venta sigue `CONFIRMADA`, la cobranza como estaba y los libros sin filas nuevas, y el mismo `operation_id` puede reintentarse
- **Regla:** INV-01; `02` §6.3

#### Scenario: Anulación y venta del mismo producto a la vez
- **WHEN** se anula una venta de Vino A mientras se confirma otra venta de Vino A al mismo cliente, con transacciones confirmadas
- **THEN** ambas terminan sin interbloqueo y el stock y el saldo son iguales a la suma de sus movimientos
- **Regla:** INV-12; INV-13; `02` §7.3

#### Scenario: Precedencia
- **WHEN** se anula una venta ya `ANULADA` con un motivo inválido
- **THEN** responde `VENTA_YA_ANULADA`
- **Regla:** ADR-058

### Requirement: La anulación queda auditada con su motivo

El comando DEBE dejar una sola fila de auditoría con el motivo y, en su observación, la cobranza anulada si la hubo y la constancia de la ubicación tomada si se usó la excepción. No DEBE emitir observaciones nuevas de SYN-07; las observaciones pendientes de la venta siguen pendientes (`design.md` D15).

#### Scenario: Auditoría con devolución
- **WHEN** se anula con devolución la venta con cobranza de $20.000
- **THEN** hay una fila de auditoría `VENTA_ANULAR` con el motivo, el usuario, el dispositivo, el `operation_id` y una observación que nombra la cobranza anulada
- **Regla:** AUD-01; AUD-02

#### Scenario: Observaciones de la venta
- **GIVEN** una venta con `STOCK_NEGATIVO` pendiente
- **WHEN** se anula
- **THEN** la observación sigue `PENDIENTE` y no se crea ninguna nueva
- **Regla:** SYN-08
