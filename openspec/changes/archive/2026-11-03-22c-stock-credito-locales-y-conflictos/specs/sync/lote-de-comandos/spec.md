## MODIFIED Requirements

### Requirement: El servidor devuelve un resultado por comando

El servidor DEBE responder un resultado por cada comando procesado, identificado por su `operation_id`, con el estado final, el código de error cuando corresponda y la lista de observaciones del comando (código, tipo e identificador de la operación observada y detalle; vacía si no hay). El reenvío de un comando ya procesado DEBE devolver las mismas observaciones. Un resultado `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO` NO DEBE detener el procesamiento del resto del lote. Las observaciones DEBEN ser solo las del propio comando (`02` §6.4, SYN-04, SYN-07, SYN-09; `design.md` D3).

#### Scenario: Un rechazo no detiene el lote

- **GIVEN** un lote de tres comandos cuyo segundo se rechaza por una regla
- **WHEN** el servidor lo procesa
- **THEN** los tres tienen resultado y el tercero fue procesado
- **Regla:** `02` §6.4, SYN-04

#### Scenario: Cada resultado se identifica por su comando

- **GIVEN** un lote de varios comandos
- **WHEN** el servidor responde
- **THEN** cada resultado indica el identificador de operación al que corresponde
- **Regla:** SYN-09 (el dispositivo no elimina una operación local hasta recibir su resultado)

#### Scenario: Venta sin conexión con observaciones

- **GIVEN** una venta sin conexión que deja stock negativo de un producto y se cobra con un medio desactivado
- **WHEN** el servidor la acepta
- **THEN** el resultado es `ACEPTADO_CON_OBSERVACIONES` y trae `STOCK_NEGATIVO` sobre la venta con el producto en el detalle y `MEDIO_INACTIVO` sobre la cobranza con la línea, el medio y el importe
- **Regla:** SYN-04; SYN-07

#### Scenario: Resultado sin observaciones

- **GIVEN** una venta aceptada sin observaciones y otra rechazada
- **WHEN** el servidor responde
- **THEN** las dos traen la lista de observaciones vacía
- **Regla:** SYN-04

#### Scenario: Reenvío de un comando con observaciones

- **GIVEN** una venta ya aceptada con `LISTA_NO_VIGENTE`
- **WHEN** el dispositivo la envía otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** el resultado trae la misma observación y no se registra otra
- **Regla:** SYN-02; INV-06

## ADDED Requirements

### Requirement: Una venta o cobranza sin conexión nunca se rechaza por reglas de negocio

Por el lote, una venta (`VENTA_CONFIRMAR`) o una cobranza (`COBRANZA_REGISTRAR`) en modo `OFFLINE` NO DEBE rechazarse por ninguna regla de negocio de SYN-05 (stock, crédito, lista, descuentos, estado del cliente, permisos, medio de pago desactivado, referencia faltante, producto o presentación desactivados, ubicación tomada al sincronizar, motivo dado de baja después del bootstrap), sola o combinada con las demás: DEBE aceptarse con las observaciones que correspondan. Solo DEBE rechazarse por las causas de SYN-06 (`design.md` D8).

#### Scenario: Cada regla por separado
- **GIVEN** una venta sin conexión que incumple una sola de las reglas de SYN-05
- **WHEN** llega por el lote
- **THEN** se acepta con la observación de esa regla, o sin observación si la regla no tiene una (motivo dado de baja)
- **Regla:** INV-17; SYN-05; SYN-07

#### Scenario: Todas a la vez
- **GIVEN** una venta sin conexión con cobranza que incumple a la vez stock, crédito, lista, cliente suspendido, permiso, medio desactivado y referencia faltante
- **WHEN** llega por el lote
- **THEN** se acepta con todas esas observaciones y su stock, su saldo y su cobranza quedan registrados
- **Regla:** INV-17; SYN-05

#### Scenario: Cobranza sin conexión
- **GIVEN** una cobranza sin conexión del consumidor final (en la cobranza solo él observa `CLIENTE_NO_HABILITADO`; un cliente inactivo se acepta sin observación, change 17 D13) con un medio desactivado, de un usuario que perdió `REGISTRAR_COBRANZA`
- **WHEN** llega por el lote
- **THEN** se acepta con `CLIENTE_NO_HABILITADO`, `MEDIO_INACTIVO` y `PERMISO_REVOCADO`
- **Regla:** INV-17; SYN-05; SYN-10

#### Scenario: Un comando malformado sí se rechaza
- **GIVEN** una venta sin conexión cuyos totales no coinciden con el cálculo sobre los valores enviados
- **WHEN** llega por el lote
- **THEN** se rechaza con `TOTALES_INCONSISTENTES`
- **Regla:** SYN-06; INV-17

#### Scenario: Doble envío de una venta observada
- **GIVEN** una venta sin conexión aceptada con `STOCK_NEGATIVO`
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** devuelve el mismo resultado y el stock baja una sola vez
- **Regla:** INV-06; INV-17
