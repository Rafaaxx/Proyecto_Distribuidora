## ADDED Requirements

### Requirement: La base local guarda las cobranzas independientes del dispositivo

La tabla de cobranzas de la base local DEBE guardar, además del cobro en el momento de una venta, las cobranzas independientes del dispositivo, con su propio estado de envío, buscables por `operation_id`, cliente, jornada y estado. Pasar a esta versión NO DEBE perder ni modificar la sesión, el PIN de desbloqueo, los datos maestros, las ventas, sus cobros, las anulaciones, los movimientos ni la cola; un cobro guardado antes de esta versión DEBE seguir leyéndose como el cobro de su venta. El bootstrap, el cierre de sesión y el inicio de sesión de otro usuario NO DEBEN tocar las cobranzas (`design.md` D5).

#### Scenario: Actualización de la base
- **GIVEN** un teléfono con la base anterior, sesión, PIN, datos del día y dos ventas con cobro, una anulación y su cola
- **WHEN** abre la versión de la aplicación con cobranzas independientes
- **THEN** todo sigue igual y los dos cobros se leen como cobros de su venta
- **Regla:** `02` §13.2; INV-05

#### Scenario: Bootstrap con cobranzas pendientes
- **GIVEN** una cobranza independiente «Sin enviar»
- **WHEN** se aplica un bootstrap
- **THEN** la cobranza, su movimiento y su comando quedan exactamente iguales
- **Regla:** `02` §13.4; SYN-09; INV-01

#### Scenario: Cerrar sesión con una cobranza pendiente
- **GIVEN** una cobranza independiente «Sin enviar»
- **WHEN** el vendedor cierra sesión
- **THEN** la cobranza sigue guardada y se envía cuando vuelve a entrar
- **Regla:** SYN-09; INV-05
