## ADDED Requirements

### Requirement: El alta de usuario se ejecuta como comando idempotente

El alta de un usuario DEBE ejecutarse como un comando del pipeline de escritura, con su identificador de operación obligatorio, su verificación de permiso y su registro de auditoría con ese identificador. Reenviar el alta con el mismo identificador de operación y el mismo contenido NO DEBE crear un segundo usuario (`02` §6.5, SYN-01, SYN-02, INV-06).

#### Scenario: Un alta de usuario sin identificador de operación se rechaza

- **GIVEN** un usuario con el permiso de administrar usuarios
- **WHEN** envía un alta de usuario sin identificador de operación
- **THEN** la petición se rechaza y no queda ningún usuario nuevo
- **Regla:** SYN-01, TR-07

#### Scenario: Reenviar el alta no crea un segundo usuario

- **GIVEN** un alta de usuario ya aceptada
- **WHEN** se reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** la respuesta es el resultado original y sigue existiendo un solo usuario
- **Regla:** SYN-02, INV-06

#### Scenario: Reenviar el alta con otro contenido se rechaza como inconsistente

- **GIVEN** un alta de usuario ya aceptada
- **WHEN** llega otra con el mismo identificador de operación y otro nombre de usuario
- **THEN** se rechaza con el código `COMANDO_INCONSISTENTE` y no queda un usuario nuevo
- **Regla:** SYN-02

#### Scenario: Un alta sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin el permiso de administrar usuarios
- **WHEN** envía un alta de usuario con un identificador de operación válido
- **THEN** se rechaza y no queda ningún usuario nuevo ni registro del comando como aceptado
- **Regla:** SEG-06

#### Scenario: El alta queda auditada con su identificador de operación

- **GIVEN** un alta de usuario aceptada
- **WHEN** se consulta su registro de auditoría
- **THEN** lleva el identificador de operación del comando
- **Regla:** AUD-01, AUD-02, TR-07
