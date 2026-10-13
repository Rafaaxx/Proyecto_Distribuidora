## ADDED Requirements

### Requirement: Un comando que nombra una jornada debe nombrar una jornada existente

Cuando el sobre de un comando trae una jornada, esa jornada DEBE existir y pertenecer a la organización de la sesión. Si no, el comando DEBE rechazarse con `JORNADA_INEXISTENTE` antes de reservar su `operation_id`: no queda registro del comando ni efecto alguno, y en un lote los demás comandos se siguen procesando (SYN-06: dependencias inexistentes; `design.md` D12). La base DEBE garantizar además, con una referencia compuesta por organización, que ningún comando registrado nombre una jornada inexistente (INV-02). Un comando sin jornada sigue siendo válido. Esta verificación NO decide si la jornada es del usuario ni si su estado admite el comando: esa regla es de cada tipo de comando de ruta.

#### Scenario: Comando de un lote con una jornada inexistente

- **GIVEN** un lote de tres comandos, el segundo con un identificador de jornada que no existe
- **WHEN** el servidor procesa el lote
- **THEN** el segundo responde `RECHAZADO` con `JORNADA_INEXISTENTE` y no queda registrado como comando
- **AND** el primero y el tercero reciben su propio resultado
- **Regla:** SYN-06; SYN-04; `02` §6.4

#### Scenario: Jornada de otra organización

- **GIVEN** una jornada que pertenece a otra organización
- **WHEN** llega un comando cuyo sobre nombra esa jornada
- **THEN** se rechaza con `JORNADA_INEXISTENTE`, igual que una jornada que no existe
- **Regla:** INV-21; SEG-07

#### Scenario: Comando con una jornada existente

- **GIVEN** una jornada `ABIERTA` de la organización
- **WHEN** llega un comando cuyo sobre nombra esa jornada y se acepta
- **THEN** el comando queda registrado con esa jornada
- **Regla:** SYN-01

#### Scenario: Comando sin jornada

- **GIVEN** un comando de administración enviado por un endpoint REST, sin jornada
- **WHEN** se procesa
- **THEN** se registra sin jornada, como antes de este change
- **Regla:** SYN-01

#### Scenario: Doble envío de un comando con jornada

- **GIVEN** un comando con jornada ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin reprocesar
- **Regla:** SYN-02; INV-06

#### Scenario: La base rechaza un comando escrito por fuera del servicio

- **GIVEN** la tabla de comandos
- **WHEN** se intenta insertar directamente un comando con una jornada inexistente
- **THEN** la base lo rechaza
- **Regla:** INV-02
