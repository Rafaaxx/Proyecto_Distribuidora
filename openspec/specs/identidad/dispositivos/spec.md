# Identidad - Dispositivos

## Purpose

Define el dispositivo como la unidad desde la que un usuario opera: se registra en su primer inicio de sesión, recibe un prefijo de numeración propio que hace únicos los números de nota de venta, y puede revocarse para cortar el acceso de un equipo perdido (SEG-02, `02` §7.7, `02` §12.2).

## Requirements

### Requirement: Un dispositivo se registra en su primer inicio de sesión

El sistema DEBE registrar un dispositivo la primera vez que se presenta en un inicio de sesión exitoso, dentro de la organización del usuario que inicia sesión. Los inicios de sesión posteriores desde ese mismo dispositivo NO DEBEN crear un registro nuevo (SEG-02).

#### Scenario: El primer inicio de sesión registra el dispositivo

- **GIVEN** un usuario activo y un identificador de dispositivo nunca visto en su organización
- **WHEN** inicia sesión correctamente
- **THEN** queda registrado un dispositivo en estado `ACTIVO` en esa organización
- **Regla:** SEG-02, `02` §12.2

#### Scenario: El segundo inicio de sesión reutiliza el dispositivo

- **GIVEN** un dispositivo ya registrado y activo
- **WHEN** el mismo usuario vuelve a iniciar sesión desde él
- **THEN** no se crea un registro nuevo y el dispositivo conserva su prefijo
- **Regla:** SEG-02, `02` §7.7 (el prefijo es estable)

#### Scenario: Dos usuarios de la misma organización comparten un dispositivo

- **GIVEN** un dispositivo registrado por el usuario A
- **WHEN** el usuario B de la misma organización inicia sesión desde ese mismo dispositivo
- **THEN** el inicio de sesión se acepta sobre el dispositivo ya registrado
- **AND** el dispositivo conserva un único prefijo
- **Regla:** SEG-02, `02` §7.7 (el prefijo es del dispositivo, no del usuario)

#### Scenario: Un identificador de dispositivo de otra organización no se reutiliza

- **GIVEN** un dispositivo registrado en la organización A
- **WHEN** un usuario de la organización B inicia sesión presentando ese mismo identificador
- **THEN** se registra un dispositivo nuevo en la organización B
- **AND** nada del dispositivo de la organización A resulta alcanzable ni modificable
- **Regla:** INV-21, TR-08

### Requirement: El servidor asigna a cada dispositivo un prefijo de numeración único en la organización

El servidor —y no el dispositivo— DEBE asignar el prefijo de numeración al registrar el dispositivo. El prefijo DEBE ser único dentro de la organización, porque de él depende que el número de nota de venta sea único (VTA-06, `02` §7.7, `03` §4).

#### Scenario: El prefijo lo asigna el servidor

- **GIVEN** un dispositivo que se registra e informa un prefijo de su preferencia
- **WHEN** el servidor lo registra
- **THEN** el prefijo del dispositivo es el que asignó el servidor, no el informado
- **Regla:** `02` §7.7 (prefijo único asignado por el servidor al registrarse)

#### Scenario: Dos dispositivos de la misma organización no comparten prefijo

- **GIVEN** una organización con un dispositivo ya registrado
- **WHEN** se registra un segundo dispositivo en esa organización
- **THEN** recibe un prefijo distinto del primero
- **Regla:** `03` §4 (`UNIQUE (organizacion_id, prefijo)`), VTA-06

#### Scenario: Dos organizaciones pueden usar el mismo prefijo

- **GIVEN** un dispositivo de la organización A con un prefijo asignado
- **WHEN** se registra un dispositivo en la organización B
- **THEN** puede recibir el mismo prefijo sin conflicto, porque la unicidad es por organización
- **Regla:** `03` §4 (`UNIQUE (organizacion_id, prefijo)`), VTA-06 (el número es único por organización)

### Requirement: El sistema conserva el último correlativo registrado de cada dispositivo

El sistema DEBE guardar, por dispositivo, el último correlativo de numeración que registró, para que el dispositivo pueda retomar la numeración sin repetir números si perdió sus datos locales (`02` §7.7).

#### Scenario: Un dispositivo recién registrado arranca sin correlativo consumido

- **GIVEN** un dispositivo recién registrado
- **WHEN** se consulta su último correlativo registrado
- **THEN** indica que todavía no se registró ningún número para ese dispositivo
- **Regla:** `02` §7.7

#### Scenario: El último correlativo no retrocede

- **GIVEN** un dispositivo cuyo último correlativo registrado es 142
- **WHEN** se intenta registrar un correlativo menor o igual a 142
- **THEN** el último correlativo registrado sigue siendo 142
- **Regla:** `02` §7.7 (el dispositivo usa el mayor entre el del servidor y el local), VTA-06

### Requirement: Un dispositivo puede revocarse y la revocación corta su sesión

Un usuario con `GESTIONAR_DISPOSITIVOS` DEBE poder revocar un dispositivo de su organización. La revocación DEBE invalidar todos los refresh tokens de ese dispositivo y DEBE impedir que vuelva a iniciar sesión. El registro del dispositivo NO DEBE borrarse: cambia de estado y queda con quién lo revocó y cuándo (SEG-02, `02` §12.2, `03` §4).

#### Scenario: Revocar un dispositivo invalida sus refresh tokens

- **GIVEN** un dispositivo activo con una sesión que puede renovarse
- **WHEN** un usuario con `GESTIONAR_DISPOSITIVOS` lo revoca
- **THEN** el dispositivo queda en estado `REVOCADO` con el revocador y el momento registrados
- **AND** la renovación de sesión desde ese dispositivo se rechaza
- **Regla:** SEG-02, `02` §12.2

#### Scenario: Un dispositivo revocado no puede volver a iniciar sesión

- **GIVEN** un dispositivo revocado
- **WHEN** un usuario con credenciales correctas intenta iniciar sesión desde él
- **THEN** el intento se rechaza
- **Regla:** SEG-02

#### Scenario: Revocar sin el permiso se rechaza

- **GIVEN** un usuario cuyo rol no tiene `GESTIONAR_DISPOSITIVOS`
- **WHEN** intenta revocar un dispositivo de su organización
- **THEN** la operación se rechaza indicando que falta el permiso
- **AND** el dispositivo sigue activo
- **Regla:** SEG-06 (el servidor valida los permisos en cada comando), `01` §19

#### Scenario: Revocar un dispositivo de otra organización no lo encuentra

- **GIVEN** un dispositivo de la organización A y un usuario de la organización B con `GESTIONAR_DISPOSITIVOS`
- **WHEN** intenta revocarlo
- **THEN** la respuesta es "no encontrado" y el dispositivo de la organización A sigue activo
- **Regla:** SEG-07 (un recurso de otra organización responde como inexistente), INV-21

#### Scenario: Revocar un dispositivo ya revocado no cambia nada

- **GIVEN** un dispositivo ya revocado
- **WHEN** se lo vuelve a revocar
- **THEN** conserva el revocador y el momento del primer registro de revocación
- **Regla:** TR-06 (ninguna operación confirmada se edita)

#### Scenario: La revocación queda auditada

- **GIVEN** una revocación de dispositivo efectuada
- **WHEN** se consulta la auditoría
- **THEN** hay un registro con el usuario que revocó, el dispositivo afectado y el estado anterior y nuevo
- **Regla:** AUD-01 (se auditan los cambios de dispositivos), AUD-02

### Requirement: Un usuario con el permiso puede ver los dispositivos de su organización

Un usuario con `GESTIONAR_DISPOSITIVOS` DEBE poder listar los dispositivos de su organización con su estado, su prefijo y su último correlativo registrado, y no DEBE ver los de ninguna otra (`01` §19, INV-21).

#### Scenario: El listado incluye solo los dispositivos propios

- **GIVEN** la organización A con dos dispositivos y la organización B con uno
- **WHEN** un usuario de la organización A con `GESTIONAR_DISPOSITIVOS` lista los dispositivos
- **THEN** obtiene exactamente los dos de la organización A
- **Regla:** INV-21, TR-08

#### Scenario: El listado incluye los revocados

- **GIVEN** una organización con un dispositivo activo y uno revocado
- **WHEN** se listan sus dispositivos
- **THEN** aparecen ambos, distinguidos por su estado
- **Regla:** TR-06 (ninguna operación confirmada se borra), `03` §4 (`estado`)

#### Scenario: Listar sin el permiso se rechaza

- **GIVEN** un usuario cuyo rol no tiene `GESTIONAR_DISPOSITIVOS`
- **WHEN** intenta listar los dispositivos de su organización
- **THEN** la petición se rechaza indicando que falta el permiso
- **Regla:** SEG-06, `01` §19

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
