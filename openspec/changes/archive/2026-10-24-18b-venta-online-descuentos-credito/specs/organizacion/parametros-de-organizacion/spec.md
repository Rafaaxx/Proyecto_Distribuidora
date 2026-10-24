## ADDED Requirements

### Requirement: La política y la tolerancia de crédito de la organización se definen por comando

Un usuario con `ADMIN_CONFIGURACION` DEBE poder definir, con conexión, la política de crédito por defecto (`ADVERTIR`, `AUTORIZAR`, `BLOQUEAR`) y la tolerancia sin conexión (tipo `IMPORTE` o `PORCENTAJE` y valor no negativo, juntos, o los dos vacíos) mediante un comando con `operation_id`, auditado con el valor anterior y el nuevo. Un tipo sin valor o un valor sin tipo DEBE rechazarse con `TOLERANCIA_OFFLINE_INVALIDA`. Los clientes con política o tolerancia propias NO DEBEN cambiar.

#### Scenario: Cargar la tolerancia de la organización

- **GIVEN** la organización con tolerancia vacía
- **WHEN** el Administrador define AUTORIZAR y tolerancia `IMPORTE` `"20000.00"`
- **THEN** la configuración cambia, queda auditada y un cliente sin tolerancia propia hereda $20.000
- **Regla:** CRE-03; CRE-06; AUD-01

#### Scenario: Tolerancia incompleta

- **WHEN** se envía tipo `PORCENTAJE` sin valor
- **THEN** se rechaza con `TOLERANCIA_OFFLINE_INVALIDA` y nada cambia
- **Regla:** CRE-06; ADR-032

#### Scenario: Política fuera del catálogo

- **WHEN** se envía la política `PERMITIR`
- **THEN** se rechaza como contenido inválido
- **Regla:** CRE-03

#### Scenario: Sin el permiso

- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía el comando
- **THEN** se rechaza con `PERMISO_REQUERIDO`
- **Regla:** SEG-06

#### Scenario: Doble envío

- **WHEN** se reenvía con el mismo `operation_id` y contenido
- **THEN** devuelve el resultado original sin otra fila de auditoría
- **Regla:** INV-06

### Requirement: El descuento manual y el crédito se configuran desde la pantalla de configuración

La pantalla de configuración de `/admin` DEBE mostrar y permitir cambiar, con `ADMIN_CONFIGURACION`, si el descuento manual está habilitado, si exige motivo, la política de crédito por defecto y la tolerancia sin conexión, con su ayuda contextual.

#### Scenario: Cambiar la política por defecto

- **GIVEN** el Administrador en "Configuración"
- **WHEN** cambia la política por defecto a ADVERTIR y guarda
- **THEN** la pantalla muestra el valor nuevo y los clientes sin política propia lo heredan en su próxima venta
- **Regla:** CRE-03
