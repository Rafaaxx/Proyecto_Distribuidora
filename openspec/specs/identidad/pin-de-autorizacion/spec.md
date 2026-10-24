# Identidad - PIN de Autorización

## Purpose

Define el PIN con el que un supervisor autoriza una excepción cuando el vendedor no tiene señal: cómo se define, cómo se guarda para que el dispositivo pueda validarlo sin conexión, y cómo se rota desde administración (SEG-03, SEG-05, ADR-011, `02` §12.4).

## Requirements

### Requirement: El PIN de autorización es distinto del PIN de desbloqueo y tiene al menos seis dígitos

Un supervisor DEBE poder definir un PIN de autorización de al menos seis dígitos, distinto del PIN con el que se desbloquea la sesión local. El sistema DEBE rechazar un PIN que no cumpla la longitud o el formato, o que sea trivial: todos los dígitos iguales o una escalera de paso 1, ascendente o descendente, sin vuelta (`02` §12.4, ADR-011, ADR-019). La regla vale igual para la rotación desde administración y para "Mi PIN", y se controla solo al definir: un PIN ya definido sigue validando. El PIN de desbloqueo vive solo en el dispositivo y el servidor no lo conoce: los dos son secretos independientes.

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

#### Scenario: Un PIN trivial se rechaza

- **GIVEN** un usuario con rol Supervisor comercial
- **WHEN** intenta definir `000000`, `777777`, `123456`, `012345` o `987654`
- **THEN** la operación se rechaza con `IDENTIDAD_PIN_AUTORIZACION_INVALIDO`, sin el valor en el mensaje
- **AND** `482913` y `135792` se aceptan
- **Regla:** ADR-019 (rechaza PIN triviales: secuencias, repeticiones)

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

### Requirement: El servidor verifica el PIN de autorización sin guardarlo

Con conexión, el sistema DEBE verificar el PIN de autorización de un supervisor contra su derivación guardada cuando una venta necesita su autorización. El PIN DEBE viajar separado del contenido del comando: NO DEBE formar parte de la huella, del contenido guardado en cuarentena, del resultado del comando, de la auditoría ni de los registros. Un PIN incorrecto, un autorizador sin PIN o con el PIN invalidado DEBEN responder igual, `PIN_INCORRECTO` (403). El lote de sincronización NO DEBE aceptar un PIN.

#### Scenario: PIN correcto

- **GIVEN** Marta con PIN definido y `AUTORIZAR_DESCUENTO`
- **WHEN** Pedro confirma una venta sobre su tope con el PIN de Marta
- **THEN** la venta se acepta con Marta como autorizadora
- **Regla:** SEG-05; DSC-06

#### Scenario: PIN incorrecto

- **WHEN** se envía un PIN distinto
- **THEN** se rechaza con `PIN_INCORRECTO` y no queda venta
- **Regla:** SEG-05; INV-01

#### Scenario: Autorizador sin PIN

- **GIVEN** un supervisor con el permiso pero sin PIN definido
- **WHEN** se lo indica como autorizador con cualquier PIN
- **THEN** se rechaza con `PIN_INCORRECTO`, igual que un PIN equivocado
- **Regla:** SEG-05; ADR-011

#### Scenario: El PIN no queda en ningún lado

- **GIVEN** una venta confirmada y otra rechazada, ambas con PIN
- **WHEN** se inspeccionan la huella, el resultado, la auditoría, la cuarentena y los registros
- **THEN** el PIN no aparece en ninguno y la huella es la misma que sin el PIN
- **Regla:** `02` §17; ADR-019

#### Scenario: PIN en el lote

- **WHEN** un ítem del lote de sincronización trae un PIN
- **THEN** se rechaza como malformado y el PIN no se guarda en cuarentena ni en registros
- **Regla:** SYN-06; ADR-011

#### Scenario: Reenvío de una venta autorizada

- **GIVEN** una venta aceptada con PIN
- **WHEN** se reenvía con el mismo `operation_id` y contenido
- **THEN** devuelve el resultado original sin volver a verificar el PIN
- **Regla:** INV-06; SYN-02

### Requirement: Los intentos fallidos bloquean el PIN por un rato

> Revisado por el usuario el 2026-10-22 (`design.md` D3 revisada).

El sistema DEBE contar los fallos de PIN por par (usuario que envía el comando, autorizador) aunque la venta se revierta. Con `intentos_pin_max` fallos del mismo par, ese usuario NO DEBE poder usar el PIN de ese autorizador (`PIN_BLOQUEADO`, 429, también con el PIN correcto), y el autorizador DEBE seguir autorizando para los demás. Con 20 fallos contra el mismo autorizador sumando todos los usuarios, el PIN de ese autorizador DEBE quedar bloqueado para todos (`PIN_BLOQUEADO`, sin revelar cuál de los dos límites se alcanzó). Cada bloqueo DEBE durar 15 minutos desde el último fallo contado. Un intento hecho durante un bloqueo NO DEBE verificar el PIN, NO DEBE contar como fallo ni extender el bloqueo. Cuentan como fallo el PIN incorrecto, el autorizador sin PIN, con PIN invalidado, inactivo o con rol inactivo; no cuenta un autorizador sin el permiso que la autorización exige, que se rechaza antes de verificar el PIN. Cada bloqueo DEBE dejar una fila de auditoría, sin el PIN.

#### Scenario: Cinco fallos bloquean a quien los cometió

- **GIVEN** `intentos_pin_max = 5`
- **WHEN** Pedro envía cinco PIN incorrectos de Marta y después el correcto dentro de los 15 minutos
- **THEN** el sexto intento de Pedro se rechaza con `PIN_BLOQUEADO` y queda una fila de auditoría del bloqueo con alcance de usuario, Pedro como quien intenta y Marta como entidad
- **Regla:** SEG-04; ADR-011

#### Scenario: Los fallos de otro no bloquean al resto

- **GIVEN** Pedro bloqueado frente al PIN de Marta
- **WHEN** Juan confirma una venta con el PIN correcto de Marta
- **THEN** la venta se acepta con Marta como autorizadora
- **Regla:** ADR-011; SEG-05

#### Scenario: El tope general bloquea el PIN para todos

- **GIVEN** cuatro usuarios que suman 20 fallos contra el PIN de Marta en 15 minutos
- **WHEN** un quinto usuario envía el PIN correcto de Marta
- **THEN** se rechaza con `PIN_BLOQUEADO` y queda una fila de auditoría del bloqueo con alcance general
- **Regla:** SEG-04; ADR-011

#### Scenario: Los intentos durante el bloqueo no lo extienden

- **GIVEN** Pedro con fallos a las 10:02, 10:05, 10:07, 10:09 y 10:10 contra el PIN de Marta
- **WHEN** reintenta a las 10:20 y otra vez a las 10:25 con el PIN correcto
- **THEN** a las 10:20 recibe `PIN_BLOQUEADO` sin que se registre un fallo nuevo, y a las 10:25 el PIN autoriza
- **Regla:** ADR-011

#### Scenario: Pasado el bloqueo el cupo vuelve entero

- **GIVEN** un bloqueo de Pedro frente a Marta ya vencido
- **WHEN** Pedro vuelve a fallar una vez
- **THEN** ese fallo cuenta como el primero y no bloquea
- **Regla:** ADR-011

#### Scenario: Un autorizador inactivo responde como un PIN incorrecto

- **GIVEN** Marta con PIN definido, dada de baja o con su rol inactivo
- **WHEN** se la indica como autorizadora con su PIN correcto
- **THEN** se rechaza con `PIN_INCORRECTO` y cuenta como fallo
- **Regla:** ADR-011; ADR-028; SEG-05

#### Scenario: Un autorizador sin el permiso no se verifica

- **GIVEN** Juan, con PIN definido y sin `AUTORIZAR_DESCUENTO`
- **WHEN** se lo indica como autorizador de un descuento sobre el tope con cualquier PIN
- **THEN** se rechaza con `AUTORIZADOR_SIN_PERMISO`, sin verificar el PIN ni contar un fallo
- **Regla:** DSC-06; SEG-06

#### Scenario: El fallo se cuenta aunque la venta se revierta

- **WHEN** una venta se rechaza por `PIN_INCORRECTO`
- **THEN** no queda ninguna fila de la venta y sí queda el intento fallido con quien intentó y el autorizador
- **Regla:** INV-01

#### Scenario: Definir un PIN nuevo reinicia los dos contadores

- **GIVEN** Marta con fallos de varios usuarios en los últimos 15 minutos, o ya bloqueada por un usuario o para todos
- **WHEN** se define un PIN nuevo para Marta, sea por la rotación desde administración o por "Mi PIN"
- **THEN** el PIN nuevo autoriza para todos y un fallo posterior cuenta como el primero de su par y del tope general
- **AND** si el comando de definición se rechaza, los contadores no se reinician
- **Regla:** ADR-011; SEG-04

### Requirement: El PIN de autorización se administra desde una pantalla

Un usuario con `ADMIN_USUARIOS` DEBE poder ver, para los usuarios activos cuyo rol confiere algún permiso de autorización, si tienen PIN definido (sin la derivación), y definirlo o cambiarlo desde `/admin` con el comando de rotación existente.

#### Scenario: Definir el PIN de un supervisor

- **GIVEN** Marta sin PIN
- **WHEN** el Administrador le define `482913` dos veces en el diálogo
- **THEN** Marta figura con PIN definido y la derivación no se muestra
- **Regla:** SEG-05; ADR-019

#### Scenario: PIN trivial

- **WHEN** se intenta definir `123456`
- **THEN** se rechaza con el error de formato del PIN y la pantalla lo muestra
- **Regla:** ADR-019

### Requirement: La rotación del PIN por un administrador no deja el PIN en el comando

`PIN_AUTORIZACION_ROTAR` DEBE recibir el PIN como dato efímero fuera del contenido del comando, igual que el resto de las credenciales (D2): el PIN NO DEBE entrar a la huella, a `comando`, a `comando_cuarentena`, a la auditoría, al resultado ni a los registros. Un contenido que traiga el PIN dentro DEBE rechazarse como malformado.

#### Scenario: La huella no depende del PIN

- **GIVEN** un Administrador que define el PIN de Marta con un `Operation-Id`
- **WHEN** se inspeccionan la huella y el comando guardado, y luego se reenvía el mismo `Operation-Id` con otro PIN
- **THEN** la huella es la misma, el PIN no aparece en ningún registro y el reenvío devuelve el resultado original sin volver a derivar
- **Regla:** SEG-05; INV-06; `02` §17; ADR-019

#### Scenario: PIN dentro del contenido

- **WHEN** llega una rotación con el PIN dentro del contenido
- **THEN** se rechaza como contenido inválido sin guardar el PIN
- **Regla:** `02` §17; ADR-022

### Requirement: Cada usuario que puede autorizar define su propio PIN confirmando su contraseña

Un usuario cuyo rol confiere algún permiso de autorización de excepciones (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO`, `USAR_LISTA_ANTERIOR`) DEBE poder definir o cambiar su propio PIN de autorización desde "Mi PIN", con el comando `PIN_AUTORIZACION_PROPIO_DEFINIR` v1, solo con conexión, confirmando su contraseña actual. El usuario DEBE salir del token, nunca del cuerpo. El PIN DEBE cumplir las mismas reglas que en la rotación. La contraseña incorrecta DEBE rechazarse con `IDENTIDAD_CONTRASENA_INCORRECTA` (403) y contar como intento fallido de inicio de sesión (mismo límite de ADR-018; alcanzado, `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, 429). Un usuario sin ningún permiso de autorización DEBE recibir 403. Ni el PIN ni la contraseña DEBEN formar parte del contenido del comando, de la huella, del resultado, de la auditoría ni de los registros. El PIN nuevo DEBE invalidar el anterior.

#### Scenario: Definir el propio PIN

- **GIVEN** Marta, con `AUTORIZAR_DESCUENTO` y un PIN anterior
- **WHEN** en "Mi PIN" escribe su contraseña correcta y `482913` dos veces
- **THEN** Marta figura con PIN definido, `482913` autoriza y el PIN anterior ya no
- **AND** queda la fila de auditoría del comando con Marta como actor, sin el PIN, la contraseña ni la derivación
- **Regla:** SEG-05; ADR-011; ADR-022

#### Scenario: Contraseña incorrecta

- **WHEN** Marta envía una contraseña equivocada con un PIN válido
- **THEN** se rechaza con `IDENTIDAD_CONTRASENA_INCORRECTA`, el PIN anterior sigue vigente y queda un intento fallido de inicio de sesión aunque el comando se rechace
- **Regla:** ADR-018; INV-01

#### Scenario: Demasiadas contraseñas incorrectas

- **GIVEN** cinco contraseñas incorrectas de Marta en 15 minutos, entre "Mi PIN" y el inicio de sesión
- **WHEN** vuelve a intentar con la contraseña correcta
- **THEN** se rechaza con `IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS`, sin contar un fallo nuevo, y el inicio de sesión de Marta también queda bloqueado hasta 15 minutos después de su último fallo o hasta que un administrador la desbloquee (ADR-018 enmendado, `design.md` D24)
- **Regla:** ADR-018

#### Scenario: Un usuario sin permisos de autorización

- **GIVEN** Pedro, Vendedor, sin ningún permiso de autorización
- **WHEN** intenta definir su PIN por "Mi PIN"
- **THEN** no ve la entrada en el menú y, por API, se rechaza con 403 `PERMISO_REQUERIDO` sin ningún efecto
- **Regla:** SEG-06; `01` §19

#### Scenario: PIN que no cumple las reglas

- **WHEN** Marta intenta definir `12345`, `12a456`, `123456` o `777777`
- **THEN** se rechaza con `IDENTIDAD_PIN_AUTORIZACION_INVALIDO`, sin el valor en el mensaje, y el PIN anterior sigue vigente
- **Regla:** ADR-019

#### Scenario: Los secretos no quedan en ningún lado

- **GIVEN** un "Mi PIN" aceptado, uno rechazado por contraseña y uno rechazado por PIN inválido
- **WHEN** se inspeccionan la huella, el comando guardado, el resultado, la auditoría y los registros
- **THEN** no aparecen ni el PIN ni la contraseña, y el contenido del comando está vacío
- **Regla:** `02` §17; ADR-019

#### Scenario: Solo con conexión y sobre uno mismo

- **WHEN** llega `PIN_AUTORIZACION_PROPIO_DEFINIR` por el lote de sincronización, o un cuerpo que indica otro `usuario_id`
- **THEN** el lote lo rechaza con `MODO_NO_ADMITIDO_PARA_TIPO` sin fila de comando y sin guardar los secretos (ni en cuarentena), y el cuerpo con `usuario_id` se rechaza por contenido inválido (`design.md` D23)
- **Regla:** SYN-06; SEG-07

#### Scenario: Un rechazo de "Mi PIN" se puede reintentar con el mismo Operation-Id

- **GIVEN** un "Mi PIN" rechazado por contraseña incorrecta
- **WHEN** Marta lo reintenta con el mismo `Operation-Id` y la contraseña correcta
- **THEN** se procesa y define el PIN: el rechazo no quedó guardado como resultado del comando
- **Regla:** INV-06; `02` §6.3

#### Scenario: Reenvío de la misma definición

- **GIVEN** un "Mi PIN" aceptado
- **WHEN** se reenvía con el mismo `Operation-Id`
- **THEN** devuelve el resultado original y la derivación guardada no cambia
- **Regla:** INV-06; SYN-02
