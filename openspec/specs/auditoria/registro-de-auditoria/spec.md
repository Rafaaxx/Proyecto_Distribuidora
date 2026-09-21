# Auditoría - Registro de Auditoría

## Purpose

Define el libro de auditoría del sistema: qué eventos se registran, con qué campos, y la garantía de que una vez escrito un registro no se modifica ni se borra, ni siquiera por error de la aplicación (AUD-01 a AUD-03, INV-05, `03` §2.5).

## Requirements

### Requirement: La auditoría es un libro de solo agregado

El registro de auditoría DEBE ser de solo inserción. El sistema NO DEBE modificar ni eliminar un registro de auditoría existente, y esa garantía DEBE estar en la base de datos, no solo en la aplicación: el usuario con el que la aplicación se conecta NO DEBE tener permiso de modificación ni de borrado sobre las tablas de libro (AUD-03, INV-05, `03` §2.5, `02` §18).

#### Scenario: La aplicación no puede modificar un registro de auditoría

- **GIVEN** un registro de auditoría existente y la conexión con la que opera la aplicación
- **WHEN** se intenta modificarlo
- **THEN** la base rechaza la operación por falta de permisos
- **AND** el registro queda intacto
- **Regla:** INV-05 (ningún registro de auditoría confirmado se borra), `03` §15 (permisos del usuario de aplicación sobre tablas de libro)

#### Scenario: La aplicación no puede borrar un registro de auditoría

- **GIVEN** un registro de auditoría existente y la conexión con la que opera la aplicación
- **WHEN** se intenta borrarlo
- **THEN** la base rechaza la operación por falta de permisos
- **AND** el registro queda intacto
- **Regla:** INV-05, AUD-03 (la auditoría es de solo agregado)

#### Scenario: La aplicación sí puede insertar y leer

- **GIVEN** la conexión con la que opera la aplicación
- **WHEN** inserta un registro de auditoría y lo vuelve a leer
- **THEN** ambas operaciones se aceptan
- **Regla:** AUD-01 (se auditan los eventos listados), INV-05

#### Scenario: Toda tabla de libro tiene sus permisos restringidos

- **GIVEN** el conjunto de tablas declaradas como libro de la base migrada
- **WHEN** se recorren los permisos del usuario de aplicación sobre cada una
- **THEN** ninguna le concede modificación ni borrado
- **AND** la verificación falla nombrando la tabla y el permiso sobrante, o la tabla que no tiene permisos declarados
- **Regla:** INV-05, `03` §2.5 (las tablas de libro son de solo inserción y una prueba lo verifica)

#### Scenario: La aplicación no es dueña del esquema

- **GIVEN** la conexión con la que opera la aplicación
- **WHEN** se intenta alterar la estructura de una tabla
- **THEN** la base rechaza la operación
- **Regla:** `02` §18 (el usuario de base de datos de la aplicación no es superusuario ni dueño del esquema; las migraciones usan un usuario distinto)

### Requirement: Cada registro de auditoría guarda el contexto completo del evento

Un registro de auditoría DEBE guardar usuario, dispositivo, acción, entidad, identificador de la entidad, el valor anterior y el nuevo cuando aplique, motivo, autorizador, el momento en que ocurrió, el momento en que el servidor lo registró y el identificador de la operación que lo originó (AUD-02, `03` §13, TR-05, TR-07).

#### Scenario: Un evento auditado registra sus dos momentos

- **GIVEN** una operación auditable ejecutada
- **WHEN** se consulta su registro de auditoría
- **THEN** tiene tanto el momento en que ocurrió como el momento en que el servidor lo registró
- **AND** ambos son momentos con zona horaria
- **Regla:** TR-05 (toda operación registra `occurred_at` y `registered_at`), TR-04

#### Scenario: Un cambio de valor registra el antes y el después

- **GIVEN** un dispositivo activo que se revoca
- **WHEN** se consulta el registro de auditoría de esa revocación
- **THEN** el valor anterior indica el estado `ACTIVO` y el nuevo indica `REVOCADO`
- **Regla:** AUD-02 (valor anterior y nuevo cuando aplica)

#### Scenario: Un evento sin cambio de valor no inventa uno

- **GIVEN** un inicio de sesión exitoso
- **WHEN** se consulta su registro de auditoría
- **THEN** tiene usuario, dispositivo, acción y momentos, y no tiene valor anterior ni nuevo
- **Regla:** AUD-02 ("cuando aplica")

#### Scenario: Un registro de auditoría no contiene secretos

- **GIVEN** los registros de auditoría de un inicio de sesión, una rotación de PIN y un cambio de contraseña
- **WHEN** se inspecciona su contenido
- **THEN** ninguno contiene la contraseña, el PIN, sus derivaciones ni un token
- **Regla:** `02` §17 (nunca se registran contraseñas, PIN ni tokens)

#### Scenario: Un registro de auditoría pertenece a una organización

- **GIVEN** un evento auditado en la organización A
- **WHEN** un usuario de la organización B consulta la auditoría
- **THEN** ese registro no aparece
- **Regla:** INV-02, INV-21, TR-08

### Requirement: Los eventos de identidad de esta etapa quedan auditados

El sistema DEBE registrar en auditoría, como mínimo, los eventos de identidad que AUD-01 enumera: el inicio de sesión y los cambios de usuarios, roles, permisos y dispositivos (AUD-01).

#### Scenario: El inicio de sesión queda auditado

- **GIVEN** un inicio de sesión exitoso
- **WHEN** se consulta la auditoría
- **THEN** hay un registro con el usuario, el dispositivo y el momento
- **Regla:** AUD-01 (se audita el inicio de sesión)

#### Scenario: Un inicio de sesión fallido también queda auditado

- **GIVEN** un intento de inicio de sesión con contraseña incorrecta
- **WHEN** se consulta la auditoría
- **THEN** hay un registro del intento fallido
- **AND** no contiene la contraseña intentada
- **Regla:** AUD-01, `02` §17

#### Scenario: Un cambio de composición de rol queda auditado

- **GIVEN** un rol al que se le quita un permiso
- **WHEN** se consulta la auditoría
- **THEN** hay un registro con quién lo cambió, sobre qué rol y qué permiso quedó antes y después
- **Regla:** AUD-01 (se auditan los cambios de usuarios, roles, permisos y dispositivos), AUD-02

#### Scenario: Un alta de usuario queda auditada

- **GIVEN** un usuario recién creado
- **WHEN** se consulta la auditoría
- **THEN** hay un registro del alta con quién la hizo y sobre qué usuario
- **AND** no contiene la contraseña del usuario creado
- **Regla:** AUD-01, `02` §17

#### Scenario: Si la operación auditada falla, no queda registro de auditoría

- **GIVEN** una revocación de dispositivo que falla por una violación de restricción
- **WHEN** se consulta la auditoría
- **THEN** no hay ningún registro de esa revocación
- **Regla:** INV-01 (una operación de negocio se registra completa o no se registra)
