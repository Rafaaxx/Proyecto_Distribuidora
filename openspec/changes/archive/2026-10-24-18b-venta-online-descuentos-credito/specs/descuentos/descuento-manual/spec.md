## ADDED Requirements

### Requirement: Los parámetros del descuento manual se definen por comando

Un usuario con `ADMIN_CONFIGURACION` DEBE poder definir, con conexión, si la organización habilita el descuento manual y si exige motivo, mediante un comando con `operation_id`. Los dos valores DEBEN enviarse juntos y ser booleanos; una vez definido, el motivo obligatorio deja de ser nulo. El cambio DEBE quedar auditado con el valor anterior y el nuevo y NO DEBE afectar a las ventas ya confirmadas.

#### Scenario: Exigir motivo

- **GIVEN** la organización con el motivo sin definir
- **WHEN** el Administrador define habilitado y motivo obligatorio
- **THEN** el comando queda `ACEPTADO`, la configuración cambia y queda una fila de auditoría con antes y después
- **Regla:** DSC-06; AUD-01

#### Scenario: Sin el permiso

- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía el comando
- **THEN** se rechaza con `PERMISO_REQUERIDO` y nada cambia
- **Regla:** SEG-06

#### Scenario: Valor que no es booleano

- **WHEN** se envía el motivo obligatorio como texto o nulo
- **THEN** se rechaza como contenido inválido
- **Regla:** DSC-06

#### Scenario: Doble envío

- **WHEN** se reenvía con el mismo `operation_id` y contenido
- **THEN** devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06

### Requirement: El motivo del descuento manual es un motivo del catálogo

El motivo de un descuento manual DEBE ser un motivo de la organización del ámbito `DESCUENTO_MANUAL`; para la evaluación del tope, un motivo presente cuenta como presente y uno ausente como ausente.

#### Scenario: Motivo del ámbito

- **GIVEN** el motivo activo "Cliente frecuente" del ámbito `DESCUENTO_MANUAL`
- **WHEN** se evalúa un descuento manual con ese motivo y la organización lo exige
- **THEN** la evaluación no pide motivo
- **Regla:** DSC-06; TR-09
