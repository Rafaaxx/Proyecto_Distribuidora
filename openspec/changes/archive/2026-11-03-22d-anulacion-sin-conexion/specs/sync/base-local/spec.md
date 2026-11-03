## ADDED Requirements

### Requirement: La base local guarda las anulaciones del dispositivo

La base local DEBE tener una tabla de anulaciones, una por venta, con su `operation_id` único, su jornada y su estado de envío («Sin enviar», «Enviada», «Con observaciones» o «Rechazada»). Pasar de la versión anterior a esta NO DEBE perder la sesión, el PIN de desbloqueo, el identificador del dispositivo, los datos maestros ni las operaciones guardadas. El bootstrap, el cierre de sesión, el inicio de sesión de otro usuario, el bloqueo del PIN y recibir el resultado NO DEBEN borrar anulaciones (`design.md` D6).

#### Scenario: Actualización de la base con ventas guardadas
- **GIVEN** un teléfono con la base anterior, sesión, PIN, datos del día y dos ventas sin enviar
- **WHEN** abre la versión de la aplicación con la tabla de anulaciones
- **THEN** la sesión, el PIN, el `dispositivo_id`, los datos y las dos ventas con su cola siguen, y la tabla de anulaciones existe vacía
- **Regla:** `02` §13.2; SYN-09

#### Scenario: Bootstrap con una anulación sin enviar
- **GIVEN** una anulación sin enviar con sus movimientos y su comando
- **WHEN** se aplica un bootstrap
- **THEN** la anulación, sus movimientos y su comando quedan exactamente iguales
- **Regla:** `02` §13.4; SYN-09; INV-05

#### Scenario: Anulación rechazada
- **GIVEN** una anulación que el servidor rechazó
- **WHEN** el vendedor cierra sesión y vuelve a entrar
- **THEN** la anulación sigue en el teléfono, «Rechazada», y no se reenvía sola
- **Regla:** SYN-09; INV-05
