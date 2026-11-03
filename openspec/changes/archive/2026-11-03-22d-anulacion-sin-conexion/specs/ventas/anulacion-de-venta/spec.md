## ADDED Requirements

### Requirement: Una venta de la jornada en curso se anula sin conexión

`VENTA_ANULAR` v1 DEBE admitir el modo `OFFLINE`, solo por el lote de sincronización, con el mismo contenido que en `ONLINE` (venta, motivo, observación opcional y `devuelve_dinero`). Sin conexión, la venta DEBE ser de la misma jornada que el sobre de la anulación (la jornada en curso del vendedor); si es de otra jornada o no tiene jornada, la anulación DEBE rechazarse con `JORNADA_AJENA`. Una venta que no existe en la organización DEBE rechazarse con `VENTA_INEXISTENTE` (dependencia inexistente, SYN-06), sin efectos. El resultado aceptado DEBE ser el mismo que en `ONLINE` (venta `ANULADA`, saldo como string, cobranza y si quedó anulada), y el reenvío del mismo `operation_id` DEBE devolverlo sin repetir efectos (`design.md` D1).

#### Scenario: Anulación sin conexión de una venta de la jornada
- **GIVEN** la venta V03-000142 a Kiosco La Esquina por $80.000, sin cobranza, confirmada sin conexión en la jornada J1 de `sup01` en su teléfono
- **WHEN** llega por el lote `VENTA_ANULAR` `OFFLINE` con la jornada J1, el motivo "Error de carga" y sin `devuelve_dinero`
- **THEN** el ítem es `ACEPTADO`, la venta queda `ANULADA`, la mercadería vuelve a la camioneta y la cuenta del cliente se acredita en $80.000
- **Regla:** VTA-24; VTA-20; VTA-21; INV-03

#### Scenario: La venta y su anulación en el mismo lote
- **GIVEN** un lote con una venta sin conexión (secuencia 7) y su anulación (secuencia 8)
- **WHEN** el servidor procesa el lote
- **THEN** la venta se acepta primero y la anulación después; el stock y el saldo del cliente quedan como antes de la venta
- **Regla:** SYN-03; INV-19

#### Scenario: Venta de otra jornada
- **GIVEN** una venta de la jornada de ayer del mismo vendedor
- **WHEN** llega su anulación `OFFLINE` con la jornada de hoy
- **THEN** el ítem es `RECHAZADO` con `JORNADA_AJENA` y nada cambia
- **Regla:** VTA-24; SYN-10; SYN-06

#### Scenario: Venta inexistente
- **GIVEN** una venta sin conexión que el servidor rechazó, de modo que no existe en el sistema
- **WHEN** llega su anulación `OFFLINE`
- **THEN** el ítem es `RECHAZADO` con `VENTA_INEXISTENTE` y nada cambia
- **Regla:** SYN-06; VTA-24

#### Scenario: Venta de otra organización
- **WHEN** llega una anulación `OFFLINE` que nombra una venta de otra organización
- **THEN** el ítem es `RECHAZADO` con `VENTA_INEXISTENTE` y nada cambia en ninguna organización
- **Regla:** INV-21; SYN-06

#### Scenario: Doble envío
- **GIVEN** una anulación sin conexión ya aceptada
- **WHEN** el teléfono reenvía el mismo `operation_id` con el mismo contenido
- **THEN** recibe el mismo resultado y el stock, la cuenta y la cobranza no cambian otra vez
- **Regla:** INV-06; SYN-02

### Requirement: Qué rechaza y qué acepta la anulación sin conexión

Sin conexión, la anulación DEBE rechazarse, sin efectos, si la venta ya está anulada (`VENTA_YA_ANULADA`), si la indicación del dinero cobrado no corresponde (`DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`), si la observación supera los 500 caracteres (`OBSERVACION_INVALIDA`), si el motivo no es de la organización o no es del ámbito `ANULACION_VENTA` (`MOTIVO_INVALIDO`) o si la ubicación de la venta está inactiva (`UBICACION_INACTIVA`). DEBE aceptarse: con un motivo del ámbito dado de baja después del bootstrap, sin observación; si el usuario ya no tiene `ANULAR_VENTA`, con `PERMISO_REVOCADO`; si la jornada fue liberada, con `JORNADA_LIBERADA`; y si la ubicación de la venta está tomada al sincronizar (por la propia jornada en rendición o por la de otro vendedor), con `UBICACION_TOMADA_AL_SINCRONIZAR`: el reingreso queda sin jornada y la auditoría deja la constancia de la jornada que tiene la ubicación. Las observaciones DEBEN anotarse sobre la venta. Con conexión rige la regla de toma de siempre (`design.md` D2).

#### Scenario: Venta ya anulada desde administración
- **GIVEN** una venta que `sup01` anuló con conexión desde `/admin`
- **WHEN** llega la anulación `OFFLINE` del teléfono
- **THEN** el ítem es `RECHAZADO` con `VENTA_YA_ANULADA` y hay una sola anulación
- **Regla:** VTA-20; INV-06; SYN-06

#### Scenario: Motivo dado de baja después del bootstrap
- **GIVEN** el motivo "Otro" de `ANULACION_VENTA`, activo en el bootstrap y desactivado antes de sincronizar
- **WHEN** llega una anulación `OFFLINE` con ese motivo
- **THEN** se acepta sin observación y la anulación guarda ese motivo
- **Regla:** VTA-24; ADR-063

#### Scenario: Motivo de otro ámbito
- **WHEN** llega una anulación `OFFLINE` con un motivo del ámbito `ANULACION_COBRANZA`
- **THEN** el ítem es `RECHAZADO` con `MOTIVO_INVALIDO` y nada cambia
- **Regla:** VTA-20; SYN-06

#### Scenario: Devolución que no corresponde
- **GIVEN** una venta sin cobranza
- **WHEN** llega su anulación `OFFLINE` con `devuelve_dinero`
- **THEN** el ítem es `RECHAZADO` con `DEVOLUCION_INVALIDA` y nada cambia
- **Regla:** VTA-22; SYN-06

#### Scenario: Permiso revocado
- **GIVEN** el vendedor tenía `ANULAR_VENTA` en el bootstrap y se lo quitaron antes de sincronizar
- **WHEN** llega su anulación `OFFLINE`
- **THEN** se acepta con `PERMISO_REVOCADO` sobre la venta
- **Regla:** SYN-10; VTA-24

#### Scenario: Jornada liberada
- **GIVEN** la jornada J1 fue liberada desde `/admin` mientras el teléfono no tenía señal
- **WHEN** llega una anulación `OFFLINE` de una venta de J1 con la jornada J1
- **THEN** se acepta con `JORNADA_LIBERADA` sobre la venta
- **Regla:** RUT-09; SYN-07

#### Scenario: Camioneta tomada por otro vendedor al sincronizar
- **GIVEN** la jornada J1 fue liberada y la camioneta 2 la tomó Pedro en una jornada `ABIERTA`
- **WHEN** llega la anulación `OFFLINE` de una venta de J1 sobre la camioneta 2, de un usuario sin `LIBERAR_UBICACION`
- **THEN** se acepta con `JORNADA_LIBERADA` y `UBICACION_TOMADA_AL_SINCRONIZAR`, el reingreso queda sin jornada y la auditoría nombra la jornada de Pedro
- **Regla:** STK-09; SYN-07; AUD-01

#### Scenario: Ubicación inactiva
- **WHEN** llega una anulación `OFFLINE` de una venta cuya ubicación fue desactivada
- **THEN** el ítem es `RECHAZADO` con `UBICACION_INACTIVA` y nada cambia
- **Regla:** STK-02; VTA-21

#### Scenario: Reenvío de una anulación con observaciones
- **GIVEN** una anulación aceptada con `JORNADA_LIBERADA`
- **WHEN** se reenvía el mismo `operation_id`
- **THEN** el resultado trae la misma observación y no se registra otra
- **Regla:** INV-06; SYN-04

### Requirement: La anulación sin conexión lleva la jornada del sobre

Sin conexión, la anulación DEBE guardar la jornada del sobre. El reingreso DEBE llevar esa jornada cuando la ubicación es la de esa jornada y la jornada está `ABIERTA`, y quedar sin jornada en los demás casos. DEBE ejecutarse con la misma transacción, el mismo orden de bloqueo y los mismos efectos que con conexión (reingreso al costo congelado, acreditación del total y, con devolución, la anulación de la cobranza de la venta) (`design.md` D3).

#### Scenario: Anulación con la jornada abierta
- **GIVEN** la jornada J1 `ABIERTA` sobre la camioneta 2
- **WHEN** se acepta la anulación `OFFLINE` de una venta de J1
- **THEN** la anulación y el reingreso llevan la jornada J1
- **Regla:** RUT-04; STK-09; RUT-07

#### Scenario: Anulación con devolución
- **GIVEN** una venta de $80.000 con $30.000 cobrados en el acto
- **WHEN** se acepta su anulación `OFFLINE` con `devuelve_dinero` verdadero
- **THEN** la cobranza queda anulada y el stock y el saldo del cliente quedan exactamente como antes de la venta
- **Regla:** VTA-22; INV-19; COB-05

#### Scenario: Anulación sin devolución
- **GIVEN** la misma venta
- **WHEN** se acepta su anulación `OFFLINE` con `devuelve_dinero` falso
- **THEN** el saldo del cliente difiere del previo a la venta solo en los $30.000 cobrados, a favor del cliente
- **Regla:** VTA-22; INV-19

#### Scenario: Anulación sin conexión contra una anulación con conexión
- **GIVEN** la anulación `OFFLINE` de una venta y la anulación con conexión de la misma venta, en transacciones simultáneas
- **WHEN** las dos confirman
- **THEN** una se acepta y la otra se rechaza con `VENTA_YA_ANULADA`; hay un solo reingreso y una sola acreditación
- **Regla:** INV-06; INV-12; INV-13; VTA-20
