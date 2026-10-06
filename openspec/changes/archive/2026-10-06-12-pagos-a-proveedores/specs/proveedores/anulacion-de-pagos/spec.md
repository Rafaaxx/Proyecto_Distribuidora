## Purpose

Definir la anulación de un pago a proveedor: única forma de corregir un pago confirmado, con permiso y motivo, por movimiento inverso y sin borrar ni editar nada (PAG-03, TR-06). Escrita con la opción A de `design.md` D1, D2, D5 y D10, pendientes de aprobación (tarea 0.1).

## ADDED Requirements

### Requirement: Un pago se anula por comando con permiso y motivo

Un pago `CONFIRMADA` DEBE poder anularse con el comando `PAGO_PROVEEDOR_ANULAR` (solo `ONLINE`, con `Operation-Id`), que exige `ANULAR_PAGO_PROVEEDOR` y un motivo activo del ámbito `ANULACION_PAGO` de la organización (`MOTIVO_INVALIDO` si no lo es) (PAG-03, `design.md` D1). La anulación DEBE dejar el pago `ANULADA` con motivo, usuario y momento, y DEBE insertar en la cuenta del proveedor un movimiento `ANULACION_PAGO` que aumenta el saldo por el importe del pago, con el pago como origen (CC-03). Un pago ya anulado DEBE rechazarse con `PAGO_YA_ANULADO`. La anulación DEBE admitirse aunque el proveedor esté inactivo (`design.md` D5).

#### Scenario: Anulación de un pago independiente
- **GIVEN** el proveedor P con saldo `"152460.00"` y, después, un pago de `"52460.00"` (saldo `"100000.00"`)
- **WHEN** se anula el pago con el motivo "Pago rechazado o devuelto"
- **THEN** el pago queda `ANULADA` con motivo, usuario y momento, la cuenta tiene `ANULACION_PAGO` `AUMENTA` de `"52460.00"` y el saldo vuelve a `"152460.00"`
- **Regla:** PAG-03; CC-03; `01` §18 (Pago: CONFIRMADA → ANULADA)

#### Scenario: Pago ya anulado
- **GIVEN** un pago `ANULADA`
- **WHEN** se envía `PAGO_PROVEEDOR_ANULAR` con otro `Operation-Id`
- **THEN** se rechaza con `PAGO_YA_ANULADO` y no se registra un segundo movimiento
- **Regla:** PAG-03; `01` §18

#### Scenario: Motivo de otro ámbito
- **WHEN** se anula con un motivo del ámbito `ANULACION_COMPRA`, con uno inactivo o con uno de otra organización
- **THEN** se rechaza con `MOTIVO_INVALIDO` y el pago sigue `CONFIRMADA`
- **Regla:** PAG-03; TR-09; `design.md` D1

#### Scenario: Sin permiso de anular
- **WHEN** un usuario con `REGISTRAR_PAGO_PROVEEDOR` y sin `ANULAR_PAGO_PROVEEDOR` envía `PAGO_PROVEEDOR_ANULAR`
- **THEN** la respuesta es 403 y el pago sigue `CONFIRMADA`
- **Regla:** `01` §19; SEG-06

#### Scenario: Pago de otra organización
- **WHEN** un usuario de A anula un pago de B
- **THEN** la respuesta es 404 y el pago de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Proveedor inactivo
- **GIVEN** un pago a un proveedor que se desactivó después
- **WHEN** se anula el pago
- **THEN** queda `ANULADA` con su `ANULACION_PAGO`
- **Regla:** PAG-03; `design.md` D5

#### Scenario: Anulación solo con conexión
- **WHEN** llega `PAGO_PROVEEDOR_ANULAR` en modo `OFFLINE` por el lote de sincronización
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5

### Requirement: El pago de una compra de contado solo se anula por separado si la compra ya está anulada

Un pago de origen `COMPRA` cuya compra está `CONFIRMADA` NO DEBE anularse con `PAGO_PROVEEDOR_ANULAR` (`PAGO_DE_COMPRA_VIGENTE`): solo se anula junto con su compra (CMP-05). Si la compra ya está `ANULADA` y el pago sigue `CONFIRMADA` (anulación sin devolución del pago), el pago DEBE poder anularse por separado con las mismas reglas que un pago independiente (`design.md` D2).

#### Scenario: Pago de una compra vigente
- **GIVEN** una compra de contado `CONFIRMADA` de `"152460.00"` con su pago
- **WHEN** se envía `PAGO_PROVEEDOR_ANULAR` sobre ese pago
- **THEN** se rechaza con `PAGO_DE_COMPRA_VIGENTE` y el pago sigue `CONFIRMADA`
- **Regla:** CMP-03; CMP-05; `design.md` D2

#### Scenario: El proveedor devuelve el dinero después de anular la compra
- **GIVEN** una compra de contado de `"152460.00"` anulada con `devuelve_pago = false`, con saldo `"-152460.00"` del proveedor
- **WHEN** se anula su pago con un motivo de `ANULACION_PAGO`
- **THEN** el pago queda `ANULADA`, la cuenta tiene `ANULACION_PAGO` de `"152460.00"` y el saldo es `"0.00"`
- **Regla:** CMP-05; PAG-03; `design.md` D2

#### Scenario: Pago ya anulado junto con su compra
- **GIVEN** una compra de contado anulada con `devuelve_pago = true`
- **WHEN** se envía `PAGO_PROVEEDOR_ANULAR` sobre su pago
- **THEN** se rechaza con `PAGO_YA_ANULADO`
- **Regla:** CMP-05; PAG-03

### Requirement: Anular un pago es una operación atómica que no borra nada

Todos los efectos de `PAGO_PROVEEDOR_ANULAR` DEBEN registrarse en una sola transacción o ninguno (INV-01), y reenviar el comando NO DEBE duplicarlos (INV-06). La anulación NO DEBE borrar ni modificar el pago más allá de su estado y sus datos de anulación, ni sus medios, ni el movimiento `PAGO` original (INV-05, TR-06). Dos anulaciones simultáneas del mismo pago, o una anulación del pago simultánea con la anulación de su compra, DEBEN producir una sola `ANULACION_PAGO` (`design.md` D10).

#### Scenario: INV-01 — falla antes de la cuenta
- **GIVEN** una falla inyectada después de marcar el pago y antes del movimiento de cuenta
- **WHEN** se procesa la anulación
- **THEN** el pago sigue `CONFIRMADA` y no queda movimiento ni cambio de saldo
- **Regla:** INV-01

#### Scenario: INV-05 — nada se borra
- **WHEN** se anula un pago con dos medios
- **THEN** siguen existiendo el pago, sus dos medios y el movimiento `PAGO` original sin cambios, y el usuario de aplicación no puede borrar pagos ni medios
- **Regla:** INV-05; TR-06; CC-06

#### Scenario: Doble envío de la anulación
- **GIVEN** un pago anulado con `Operation-Id` Y
- **WHEN** se reenvía el mismo contenido con Y
- **THEN** se devuelve el resultado original y existe una sola `ANULACION_PAGO`
- **Regla:** INV-06; SYN-02

#### Scenario: Dos anulaciones simultáneas del mismo pago
- **WHEN** dos sesiones envían a la vez `PAGO_PROVEEDOR_ANULAR` sobre el mismo pago con distinto `Operation-Id`
- **THEN** una se acepta, la otra recibe `PAGO_YA_ANULADO` y hay una sola `ANULACION_PAGO`
- **Regla:** PAG-03; `02` §7.3

#### Scenario: Anulación del pago simultánea con la de su compra
- **GIVEN** una compra de contado `CONFIRMADA` de `"152460.00"` con su pago
- **WHEN** una sesión anula la compra con `devuelve_pago = true` y otra envía `PAGO_PROVEEDOR_ANULAR` sobre su pago
- **THEN** ninguna queda bloqueada indefinidamente, la compra queda `ANULADA`, el pago `ANULADA` y hay una sola `ANULACION_PAGO`; la anulación del pago recibe `PAGO_DE_COMPRA_VIGENTE` o `PAGO_YA_ANULADO` según el orden
- **Regla:** CMP-05; `02` §7.3; `design.md` D10

#### Scenario: Propiedad — registrar y anular deja el saldo como estaba
- **GIVEN** un saldo aleatorio válido del proveedor
- **WHEN** se registra un pago aleatorio válido y se lo anula sin movimientos intermedios
- **THEN** el saldo es el inicial y coincide con la suma del libro
- **Regla:** INV-13; PAG-03

### Requirement: La anulación de un pago queda auditada

Un pago anulado DEBE quedar auditado por el bus con el `operation_id` del comando de anulación, el usuario y el motivo (AUD-01, AUD-02, ADR-022).

#### Scenario: Auditoría de la anulación
- **WHEN** se anula un pago
- **THEN** existe una sola fila de auditoría con el `operation_id` de la anulación
- **Regla:** AUD-01; AUD-02; ADR-022
