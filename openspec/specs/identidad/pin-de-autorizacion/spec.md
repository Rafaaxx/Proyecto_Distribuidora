# Identidad - PIN de Autorización

## Purpose

Define el PIN con el que un supervisor autoriza una excepción cuando el vendedor no tiene señal: cómo se define, cómo se guarda para que el dispositivo pueda validarlo sin conexión, y cómo se rota desde administración (SEG-03, SEG-05, ADR-011, `02` §12.4).

## Requirements

### Requirement: El PIN de autorización es distinto del PIN de desbloqueo y tiene al menos seis dígitos

Un supervisor DEBE poder definir un PIN de autorización de al menos seis dígitos, distinto del PIN con el que se desbloquea la sesión local. El sistema DEBE rechazar un PIN que no cumpla la longitud o el formato (`02` §12.4, ADR-011).

> **Pendiente de confirmación humana (bloqueante):** si el PIN en claro llega al servidor o si el dispositivo envía la derivación ya calculada. De eso depende quién puede hacer cumplir la longitud mínima y la rotación. Ver `design.md` D2. Los escenarios de abajo describen el comportamiento observable bajo la alternativa recomendada (el servidor valida y deriva) y se revisan si se elige otra.

#### Scenario: Un PIN de menos de seis dígitos se rechaza

- **GIVEN** un usuario con rol Supervisor comercial
- **WHEN** intenta definir un PIN de autorización de cinco dígitos
- **THEN** la operación se rechaza con un error de dominio de código estable
- **AND** el PIN anterior, si lo había, sigue vigente
- **Regla:** `02` §12.4 (al menos 6 dígitos), ADR-011

#### Scenario: Un PIN con caracteres que no son dígitos se rechaza

- **GIVEN** un usuario con rol Supervisor comercial
- **WHEN** intenta definir un PIN que contiene letras o símbolos
- **THEN** la operación se rechaza con un error de dominio de código estable
- **Regla:** `02` §12.4 (PIN numérico)

#### Scenario: El PIN de autorización no es el de desbloqueo

- **GIVEN** un supervisor con un PIN de desbloqueo definido en su dispositivo
- **WHEN** define su PIN de autorización
- **THEN** son dos secretos independientes y cambiar uno no cambia el otro
- **Regla:** `02` §12.4 (distinto del de desbloqueo), SEG-03

### Requirement: El PIN se guarda como derivación irrecuperable con su sal y sus iteraciones

El sistema DEBE guardar el PIN de autorización únicamente como derivación de la que no se pueda reconstruir el PIN, junto con la sal y la cantidad de iteraciones con que se derivó, para que un dispositivo sin conexión pueda validar un PIN ingresado reproduciendo la misma derivación (`02` §12.4, `03` §4).

#### Scenario: El PIN nunca queda almacenado en claro

- **GIVEN** un supervisor con PIN de autorización definido
- **WHEN** se inspecciona lo almacenado para ese usuario
- **THEN** hay una derivación, una sal y una cantidad de iteraciones
- **AND** el PIN en claro no está almacenado en ningún lado
- **Regla:** `03` §4 (`pin_autorizacion_hash`, `_sal`, `_iteraciones`), ADR-011

#### Scenario: La misma derivación se reproduce con el PIN correcto

- **GIVEN** la derivación, la sal y las iteraciones almacenadas de un supervisor
- **WHEN** se deriva el PIN correcto con esa sal y esas iteraciones
- **THEN** el resultado coincide con la derivación almacenada
- **AND** derivar un PIN distinto no coincide
- **Regla:** `02` §12.4 (el bootstrap incluye la derivación con su sal para validación local)

#### Scenario: Dos supervisores con el mismo PIN tienen derivaciones distintas

- **GIVEN** dos supervisores que eligen el mismo PIN
- **WHEN** se inspeccionan sus derivaciones almacenadas
- **THEN** son distintas, porque cada uno tiene su propia sal
- **Regla:** `02` §12.4 (derivación PBKDF2 con sal)

#### Scenario: El PIN nunca queda registrado

- **GIVEN** una definición o una rotación de PIN de autorización
- **WHEN** se inspeccionan los registros producidos por la petición
- **THEN** no aparece el PIN en ninguno, en ningún nivel de registro
- **Regla:** `02` §17 (nunca se registran contraseñas, PIN ni tokens)

#### Scenario: La derivación no se expone a un usuario sin necesidad de validar sin conexión

- **GIVEN** un usuario con rol Vendedor/Repartidor
- **WHEN** consulta los datos de un supervisor por cualquier vía de lectura de este change
- **THEN** la respuesta no contiene la derivación del PIN ni su sal
- **Regla:** SYN-11 (los datos del bootstrap se minimizan; la entrega de credenciales de supervisor es del bootstrap, change 21)

### Requirement: El PIN de autorización se puede rotar desde administración

Un usuario con `ADMIN_USUARIOS` DEBE poder forzar la rotación del PIN de autorización de un supervisor de su organización, porque la rotación es una de las mitigaciones sobre las que ADR-011 apoya el riesgo aceptado del PIN numérico.

#### Scenario: Rotar el PIN invalida el anterior

- **GIVEN** un supervisor con PIN de autorización definido
- **WHEN** se rota su PIN
- **THEN** la derivación almacenada cambia
- **AND** el PIN anterior deja de validar
- **Regla:** ADR-011 (mitigación: rotación desde administración)

#### Scenario: Rotar sin el permiso se rechaza

- **GIVEN** un usuario cuyo rol no tiene `ADMIN_USUARIOS`
- **WHEN** intenta rotar el PIN de autorización de otro usuario
- **THEN** la operación se rechaza indicando que falta el permiso
- **Regla:** SEG-06, `01` §19 (`ADMIN_USUARIOS`)

#### Scenario: Rotar el PIN de un usuario de otra organización no lo encuentra

- **GIVEN** un supervisor de la organización A y un administrador de la organización B
- **WHEN** el administrador de B intenta rotar el PIN de ese supervisor
- **THEN** la respuesta es "no encontrado" y la derivación del supervisor de A no cambia
- **Regla:** SEG-07, INV-21

#### Scenario: La rotación queda auditada sin exponer el PIN

- **GIVEN** una rotación de PIN efectuada
- **WHEN** se consulta la auditoría
- **THEN** hay un registro con quién rotó, sobre qué usuario y cuándo
- **AND** el registro no contiene el PIN ni su derivación
- **Regla:** AUD-01 (se auditan los cambios de usuarios), AUD-02, `02` §17

### Requirement: Solo los usuarios que pueden autorizar tienen PIN de autorización

El sistema DEBE permitir el PIN de autorización únicamente a usuarios cuyo rol confiere algún permiso de autorización de excepciones (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO`, `USAR_LISTA_ANTERIOR`), porque es el secreto con el que se ejerce esa autorización sin conexión (`01` §19, `02` §12.4).

#### Scenario: Un vendedor no puede definir PIN de autorización

- **GIVEN** un usuario con rol Vendedor/Repartidor, que no tiene ningún permiso de autorización
- **WHEN** intenta definir un PIN de autorización
- **THEN** la operación se rechaza con un error de dominio de código estable
- **Regla:** `02` §12.4 (cada supervisor tiene un PIN de autorización), `01` §19

#### Scenario: Quitarle a un rol los permisos de autorización invalida el PIN de sus usuarios

- **GIVEN** un usuario con PIN de autorización definido
- **WHEN** su rol pierde todos los permisos de autorización de excepciones
- **THEN** su PIN de autorización deja de estar vigente y no valida ninguna autorización
- **Regla:** SEG-06 (el servidor valida los permisos), ADR-017 (una revocación tiene efecto inmediato con conexión)

### Requirement: La rotación del PIN de autorización se ejecuta como comando idempotente

La rotación del PIN de autorización DEBE ejecutarse como un comando del pipeline de escritura, con su identificador de operación obligatorio, su verificación de permiso y su registro de auditoría con ese identificador. Ni el PIN en claro ni su derivación DEBEN formar parte del resultado guardado del comando, de la huella registrada en un lugar legible, ni de los registros del sistema (`02` §6.5, `02` §12.4, `02` §17, SEG-03, SEG-05).

#### Scenario: Una rotación sin identificador de operación se rechaza

- **GIVEN** un usuario con el permiso de rotar el PIN
- **WHEN** envía la rotación sin identificador de operación
- **THEN** la petición se rechaza y el PIN anterior sigue vigente
- **Regla:** SYN-01, TR-07

#### Scenario: Reenviar la rotación no vuelve a derivar el PIN

- **GIVEN** una rotación ya aceptada
- **WHEN** se reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** la respuesta es el resultado original y la derivación guardada no cambia
- **Regla:** SYN-02, INV-06

#### Scenario: El resultado del comando no contiene el PIN ni su derivación

- **GIVEN** una rotación aceptada
- **WHEN** se consulta el registro del comando y sus registros del sistema
- **THEN** ninguno contiene el PIN en claro ni su derivación
- **Regla:** `02` §17, `02` §18, SEG-05

#### Scenario: Una rotación sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin el permiso de rotar el PIN
- **WHEN** envía la rotación con un identificador de operación válido
- **THEN** se rechaza y el PIN anterior sigue vigente
- **Regla:** SEG-06
