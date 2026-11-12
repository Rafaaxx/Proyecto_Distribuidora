## Purpose

Definir la única forma de corregir una cobranza confirmada: su anulación total, con permiso y motivo, que devuelve el saldo del cliente sin borrar nada (COB-05, CC-02, TR-06, INV-05). Escrita con la opción A de `design.md` D6, D7, D15, D16 y D18, aprobadas el 2026-10-15.

## ADDED Requirements

### Requirement: Una cobranza se anula por comando con motivo

El sistema DEBE anular una cobranza con el comando `COBRANZA_ANULAR` v1 (solo `ONLINE`, con `Operation-Id`, permiso `ANULAR_COBRANZA`), que indica la cobranza, un motivo activo de la organización del ámbito `ANULACION_COBRANZA` y una observación opcional de hasta 500 caracteres. La anulación DEBE dejar la cobranza `ANULADA`, registrar la anulación con motivo, observación, usuario y momento, y registrar en la misma transacción un movimiento `ANULACION_COBRANZA` que aumenta el saldo del cliente por el importe completo (COB-05, CC-02, ADR-034 punto 5). Ningún registro se borra ni se edita, salvo el estado de la cobranza (TR-06, INV-05).

#### Scenario: Cheque rechazado
- **GIVEN** la cobranza de `"20000.00"` de `Kiosco La Esquina`, cuyo saldo es `"130000.00"`
- **WHEN** un usuario con `ANULAR_COBRANZA` la anula con el motivo "Pago rechazado o no acreditado" y la observación `"cheque 1234 sin fondos"`
- **THEN** la cobranza queda `ANULADA`, su anulación guarda el motivo y la observación, la cuenta tiene un movimiento `ANULACION_COBRANZA` `AUMENTA` por `"20000.00"` y el saldo es `"150000.00"`
- **Regla:** COB-05; CC-02; CC-04

#### Scenario: La cobranza original sigue a la vista
- **WHEN** se consulta la cuenta del cliente después de anular
- **THEN** están el movimiento `COBRANZA` y el `ANULACION_COBRANZA`, y la cobranza conserva sus medios
- **Regla:** TR-06; INV-05; CC-06

#### Scenario: Sin permiso
- **GIVEN** un usuario con `REGISTRAR_COBRANZA` y sin `ANULAR_COBRANZA`
- **WHEN** intenta anular
- **THEN** recibe 403 y no queda ningún efecto
- **Regla:** COB-05; SEG-06

#### Scenario: Motivo de otro ámbito o inactivo
- **WHEN** se anula con un motivo de `ANULACION_PAGO`, o con uno inactivo de `ANULACION_COBRANZA`
- **THEN** se rechaza con `MOTIVO_INVALIDO` y no queda ningún efecto
- **Regla:** COB-05; TR-09

#### Scenario: Observación demasiado larga
- **WHEN** la observación de anulación tiene 501 caracteres
- **THEN** se rechaza con un error de validación (422) sin ningún efecto
- **Regla:** `design.md` D7

#### Scenario: Anulación sin conexión
- **WHEN** llega `COBRANZA_ANULAR` en modo `OFFLINE` por el lote
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5

#### Scenario: Cobranza de otra organización
- **WHEN** se intenta anular una cobranza de otra organización
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío
- **WHEN** se reenvía la misma anulación con el mismo contenido
- **THEN** se devuelve el resultado original y hay un solo `ANULACION_COBRANZA`
- **Regla:** INV-06

### Requirement: Una cobranza se anula una sola vez y entera

Solo una cobranza `CONFIRMADA` DEBE poder anularse; una ya `ANULADA` DEBE responder `COBRANZA_YA_ANULADA` (409). No existe anulación parcial. Una cobranza de origen `VENTA` DEBE rechazarse con `COBRANZA_DE_VENTA` (409): se anula con su venta (VTA-22). Una cobranza de un cliente inactivo o de una jornada cerrada o liberada SÍ DEBE poder anularse (`design.md` D7). La base DEBE impedir dos anulaciones de la misma cobranza.

#### Scenario: Anular dos veces
- **GIVEN** una cobranza ya anulada
- **WHEN** se envía otra anulación con otro `operation_id`
- **THEN** se rechaza con `COBRANZA_YA_ANULADA` y no hay un segundo movimiento
- **Regla:** COB-05; `design.md` D7

#### Scenario: Dos anulaciones simultáneas
- **WHEN** dos sesiones anulan a la vez la misma cobranza y confirman
- **THEN** una se acepta y la otra responde `COBRANZA_YA_ANULADA`; hay un solo `ANULACION_COBRANZA` y una sola anulación
- **Regla:** INV-13; INV-01; `02` §7.3

#### Scenario: Cobranza de una jornada cerrada
- **GIVEN** una cobranza de una jornada ya `CERRADA`
- **WHEN** se la anula con motivo
- **THEN** se acepta y el saldo vuelve a como estaba antes de la cobranza
- **Regla:** `design.md` D7

#### Scenario: Cliente inactivo
- **GIVEN** una cobranza de un cliente que después pasó a `INACTIVO`
- **WHEN** se la anula
- **THEN** se acepta
- **Regla:** `design.md` D7

#### Scenario: Una segunda anulación escrita por fuera del servicio
- **WHEN** se inserta directamente en la base una segunda anulación de la misma cobranza
- **THEN** la base la rechaza
- **Regla:** INV-05; `design.md` D16

### Requirement: La anulación queda auditada con su motivo

El comando aceptado DEBE dejar una sola fila de auditoría con el usuario, el dispositivo, la acción `COBRANZA_ANULAR`, la cobranza y el motivo (AUD-01, AUD-02, `design.md` D15). Un comando rechazado NO DEBE dejar fila ni motivo.

#### Scenario: Fila con motivo
- **WHEN** se acepta la anulación con el motivo "Error de carga"
- **THEN** existe una fila de auditoría `COBRANZA_ANULAR` con ese motivo
- **Regla:** AUD-01; AUD-02

#### Scenario: Rechazo sin fila
- **WHEN** la anulación se rechaza con `COBRANZA_YA_ANULADA`
- **THEN** no queda fila de auditoría de ese comando con motivo
- **Regla:** AUD-02; SYN-04
