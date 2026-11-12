## ADDED Requirements

### Requirement: La revocación de un dispositivo se ejecuta como comando idempotente

La revocación de un dispositivo DEBE ejecutarse como un comando del pipeline de escritura, con su identificador de operación obligatorio, su verificación de permiso y su registro de auditoría con ese identificador. Reenviar la revocación con el mismo identificador de operación NO DEBE producir un segundo efecto ni un segundo registro de auditoría (`02` §6.5, SEG-02, SYN-02, INV-06).

#### Scenario: Una revocación sin identificador de operación se rechaza

- **GIVEN** un usuario con el permiso de gestionar dispositivos
- **WHEN** envía una revocación sin identificador de operación
- **THEN** la petición se rechaza y el dispositivo sigue activo
- **Regla:** SYN-01, TR-07

#### Scenario: Reenviar la revocación devuelve el resultado original

- **GIVEN** una revocación ya aceptada
- **WHEN** se reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** la respuesta es el resultado original
- **AND** queda un solo registro de auditoría de esa revocación
- **Regla:** SYN-02, INV-06, AUD-02

#### Scenario: La revocación por comando sigue cortando la sesión del dispositivo

- **GIVEN** un dispositivo activo con sesión vigente
- **WHEN** se revoca mediante el comando correspondiente
- **THEN** sus refresh quedan inválidos y el dispositivo no puede renovar su sesión
- **Regla:** SEG-02, SEG-06

#### Scenario: Una revocación sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin el permiso de gestionar dispositivos
- **WHEN** envía la revocación con un identificador de operación válido
- **THEN** se rechaza y el dispositivo sigue activo
- **Regla:** SEG-06
