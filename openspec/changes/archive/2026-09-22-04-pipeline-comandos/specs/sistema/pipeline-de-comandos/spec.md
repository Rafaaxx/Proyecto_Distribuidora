## Purpose

Define el camino único por el que toda escritura de negocio entra al sistema: un comando con identificador propio, huella del contenido y modo, que se reserva contra duplicados, se valida, se ejecuta dentro de una sola transacción y deja un resultado reproducible. Es el mecanismo que hace que reenviar una operación no la duplique (ADR-012, `02` §6, INV-06).

## ADDED Requirements

### Requirement: Toda escritura de negocio es un comando con identificador de operación

El sistema DEBE tratar toda escritura de negocio —online u offline— como un comando que lleva `operation_id`, tipo, versión, modo, organización, usuario, dispositivo, jornada cuando corresponda, `occurred_at`, secuencia, versión de aplicación y contenido. Una petición de escritura sin `operation_id` DEBE rechazarse; el sistema NO DEBE generarlo por su cuenta (SYN-01, TR-07).

La organización, el usuario y el dispositivo del comando DEBEN provenir del token de la sesión y NO DEBEN tomarse del contenido, aunque el contenido los informe.

#### Scenario: Una escritura sin identificador de operación se rechaza

- **GIVEN** un usuario autenticado con permiso para la operación
- **WHEN** envía una escritura de negocio sin informar su identificador de operación
- **THEN** la petición se rechaza y no queda ningún efecto en la base
- **AND** el error indica que el identificador de operación es obligatorio
- **Regla:** SYN-01, TR-07

#### Scenario: El contenido no puede elegir la organización

- **GIVEN** un usuario autenticado en la organización A
- **WHEN** envía un comando cuyo contenido informa la organización B
- **THEN** el comando se ejecuta contra la organización A
- **AND** nada de la organización B resulta alcanzable ni modificable
- **Regla:** INV-21, TR-08, `02` §6.2 (organización y usuario salen del token)

#### Scenario: Un identificador de operación que no es un identificador válido se rechaza

- **GIVEN** un usuario autenticado
- **WHEN** envía una escritura cuyo identificador de operación no es un identificador válido
- **THEN** la petición se rechaza como malformada y no queda ningún efecto
- **Regla:** SYN-06 (solo se rechazan comandos malformados, inconsistentes, ajenos, con dependencias inexistentes o de dispositivos revocados)

### Requirement: El servidor calcula la huella canónica del contenido

El servidor DEBE calcular la huella del comando a partir del contenido recibido, con una serialización canónica que produce la misma huella para el mismo contenido sin importar el orden de las claves ni el cliente que lo generó. El servidor NO DEBE aceptar ni usar una huella informada por el cliente. Los importes y porcentajes DEBEN participar de la huella como texto, nunca como número de punto flotante (`02` §6.2, INV-03).

#### Scenario: El mismo contenido en distinto orden produce la misma huella

- **GIVEN** dos comandos con el mismo contenido, con las claves del objeto en distinto orden
- **WHEN** el servidor calcula su huella
- **THEN** ambas huellas son iguales
- **Regla:** `02` §6.2 (JSON canónico con claves ordenadas)

#### Scenario: Un contenido distinto produce una huella distinta

- **GIVEN** dos comandos cuyo contenido difiere solo en un importe
- **WHEN** el servidor calcula su huella
- **THEN** las huellas son distintas
- **Regla:** SYN-02 (la huella distingue contenidos)

#### Scenario: La huella informada por el cliente se ignora

- **GIVEN** un comando que informa una huella que no corresponde a su contenido
- **WHEN** el servidor lo procesa
- **THEN** usa la huella que calculó él mismo
- **AND** el comando no se rechaza por esa discrepancia
- **Regla:** `02` §6.2 (el servidor la calcula; no confía en la del cliente)

#### Scenario: La huella es estable entre el cliente y el servidor

- **GIVEN** el mismo contenido serializado por el motor canónico del dispositivo y por el del servidor
- **WHEN** se comparan sus huellas
- **THEN** son iguales
- **Regla:** ADR-012, INV-06 (el dispositivo reenvía sin cambiar el `operation_id` ni el contenido)

### Requirement: Un identificador de operación es único por organización

El sistema DEBE garantizar en la base que un `operation_id` se registre una sola vez por organización, de modo que dos procesamientos concurrentes del mismo comando no produzcan dos efectos. La garantía NO DEBE depender de una consulta previa desde la aplicación (INV-06, SYN-02, `03` §15).

#### Scenario: Dos organizaciones pueden usar el mismo identificador de operación

- **GIVEN** un comando ya procesado en la organización A con cierto identificador de operación
- **WHEN** llega un comando con ese mismo identificador en la organización B
- **THEN** se procesa normalmente como comando nuevo
- **Regla:** INV-06 (único **por organización**), INV-21

#### Scenario: Dos envíos simultáneos del mismo comando producen un solo efecto

- **GIVEN** dos peticiones concurrentes con el mismo identificador de operación y el mismo contenido
- **WHEN** ambas se procesan al mismo tiempo, cada una confirmando su transacción
- **THEN** la operación queda registrada una sola vez
- **AND** ambas respuestas informan el mismo resultado
- **Regla:** INV-06, SYN-02 (doble sync no duplica)

### Requirement: Reenviar un comando ya procesado devuelve su resultado original

Cuando llega un comando cuyo `operation_id` ya está registrado en la organización, el sistema DEBE comparar la huella. Con la misma huella DEBE devolver el resultado guardado sin volver a ejecutar el handler. Con una huella distinta DEBE rechazarlo con el código `COMANDO_INCONSISTENTE` y NO DEBE alterar el resultado ya registrado (SYN-02).

#### Scenario: Reenvío idéntico devuelve el resultado guardado

- **GIVEN** un comando ya aceptado
- **WHEN** el dispositivo lo reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** la respuesta es el resultado original
- **AND** no se produce ningún efecto nuevo en la base
- **Regla:** SYN-02, INV-06

#### Scenario: Mismo identificador con contenido distinto se rechaza

- **GIVEN** un comando ya aceptado
- **WHEN** llega otro con el mismo identificador de operación y contenido distinto
- **THEN** se rechaza con el código `COMANDO_INCONSISTENTE`
- **AND** el resultado del comando original queda intacto
- **Regla:** SYN-02, SYN-06

#### Scenario: Reenvío de un comando rechazado devuelve el mismo rechazo

- **GIVEN** un comando ya procesado con resultado RECHAZADO y su motivo registrado
- **WHEN** el dispositivo lo reenvía con el mismo contenido
- **THEN** la respuesta vuelve a ser ese rechazo, con el mismo motivo
- **Regla:** SYN-02, SYN-09 (un RECHAZADO queda visible en el dispositivo)

### Requirement: El comando se ejecuta en una sola transacción que abre y cierra el pipeline

El sistema DEBE ejecutar la reserva de idempotencia, el handler, el registro del resultado, las observaciones y la auditoría de un comando dentro de una única transacción. El handler NO DEBE confirmar la transacción. Si el handler falla en modo `ONLINE`, DEBE revertirse toda la transacción, incluida la reserva, de modo que el mismo `operation_id` pueda reintentarse con el contenido corregido (`02` §6.3, INV-01).

#### Scenario: Un fallo del handler no deja efectos parciales

- **GIVEN** un comando cuyo handler falla después de haber escrito una parte de sus efectos
- **WHEN** termina el procesamiento
- **THEN** no queda ninguno de esos efectos en la base
- **Regla:** INV-01 (una operación se confirma entera o no se confirma)

#### Scenario: Un identificador de operación rechazado por regla de negocio puede reintentarse corregido

- **GIVEN** un comando ONLINE rechazado por una regla de negocio
- **WHEN** el cliente lo reenvía con el mismo identificador de operación y el contenido corregido
- **THEN** se procesa como comando nuevo y puede aceptarse
- **Regla:** `02` §6.3 (el fallo ONLINE revierte también la reserva)

#### Scenario: La auditoría del comando se confirma junto con sus efectos

- **GIVEN** un comando aceptado que produce un cambio auditable
- **WHEN** se consulta la auditoría
- **THEN** el registro existe y referencia el identificador de operación del comando
- **Regla:** AUD-02, TR-07, INV-01

### Requirement: El resultado de un comando es uno de tres, y queda registrado

El sistema DEBE registrar para cada comando un estado final entre `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` y `RECHAZADO`, junto con el resultado devuelto al cliente y, cuando corresponda, el código de error. Mientras se procesa, el comando DEBE quedar en un estado intermedio distinto de los tres finales (SYN-04, `03` §13).

#### Scenario: Un comando sin observaciones queda aceptado

- **GIVEN** un comando válido cuyo handler no produce observaciones
- **WHEN** termina su procesamiento
- **THEN** su estado es `ACEPTADO` y su resultado queda registrado
- **Regla:** SYN-04

#### Scenario: Un comando con observaciones lo declara en su estado

- **GIVEN** un comando válido cuyo handler produce al menos una observación
- **WHEN** termina su procesamiento
- **THEN** su estado es `ACEPTADO_CON_OBSERVACIONES`
- **Regla:** SYN-04, SYN-07

#### Scenario: Un comando rechazado registra su código de error

- **GIVEN** un comando que incumple una regla de negocio en modo ONLINE
- **WHEN** termina su procesamiento
- **THEN** su estado es `RECHAZADO` y el registro conserva el código de error estable
- **AND** la respuesta al cliente usa el formato de error de la API
- **Regla:** SYN-04, `02` §11

#### Scenario: El contenido del comando no se conserva cuando se acepta

- **GIVEN** un comando aceptado
- **WHEN** se consulta su registro
- **THEN** conserva tipo, versión, huella, estado y resultado, y no conserva el contenido completo
- **Regla:** `03` §13 (el contenido no se almacena: lo relevante queda en las entidades creadas y en `resultado`)

### Requirement: Un permiso faltante rechaza el comando en modo ONLINE

El sistema DEBE verificar los permisos del usuario en cada comando. En modo `ONLINE`, un permiso faltante DEBE rechazar el comando. La verificación DEBE ocurrir antes de que el handler produzca efectos (SEG-06).

#### Scenario: Un usuario sin el permiso no ejecuta el comando

- **GIVEN** un usuario autenticado sin el permiso que exige el tipo de comando
- **WHEN** envía ese comando en modo ONLINE
- **THEN** se rechaza y no queda ningún efecto en la base
- **Regla:** SEG-06

#### Scenario: Un comando sobre un recurso de otra organización no revela su existencia

- **GIVEN** un usuario de la organización A y una entidad de la organización B
- **WHEN** envía un comando que la referencia
- **THEN** la respuesta indica que el recurso no existe
- **Regla:** SEG-07, INV-21, TR-08

### Requirement: Un error transitorio de la base se reintenta y no se confunde con un rechazo

El sistema DEBE reintentar la transacción completa de un comando —incluida la reserva de idempotencia— cuando la base informa un fallo de serialización o un interbloqueo, hasta tres veces, esperando entre intentos. Agotados los reintentos, DEBE responder un error transitorio distinguible de un rechazo, para que el cliente reintente más tarde **sin cambiar** el `operation_id` (`02` §6.3).

#### Scenario: Un fallo de serialización se reintenta y el comando termina aceptado

- **GIVEN** un comando cuya primera ejecución encuentra un fallo de serialización
- **WHEN** el pipeline lo reintenta
- **THEN** el comando termina con un estado final y sus efectos quedan registrados una sola vez
- **Regla:** `02` §6.3, INV-06

#### Scenario: Agotados los reintentos, la respuesta es transitoria y no un rechazo

- **GIVEN** un comando que encuentra un fallo de serialización en todos sus intentos
- **WHEN** se agotan los reintentos
- **THEN** la respuesta indica un error transitorio y no un resultado RECHAZADO
- **AND** el comando no queda registrado con estado final
- **Regla:** `02` §6.3, SYN-04, SYN-09

#### Scenario: Un error de dominio no se reintenta

- **GIVEN** un comando que incumple una regla de negocio
- **WHEN** se procesa
- **THEN** se rechaza en el primer intento, sin reintentos
- **Regla:** `02` §6.3 (solo los errores transitorios de la base se reintentan)

### Requirement: Un comando se atiende según su tipo y su versión

El sistema DEBE resolver el handler de un comando por la combinación de tipo y versión, y DEBE validar el contenido contra el esquema de esa combinación antes de ejecutarlo. Un tipo desconocido o una versión sin handler registrado DEBEN rechazarse como malformados, sin efectos. El servidor DEBE conservar los handlers de toda versión que pueda estar en colas activas (`02` §6.3, `02` §6.6, SYN-06).

#### Scenario: Un contenido que no cumple el esquema de su tipo se rechaza

- **GIVEN** un comando de un tipo conocido cuyo contenido omite un dato obligatorio
- **WHEN** se procesa
- **THEN** se rechaza como malformado y no queda ningún efecto
- **Regla:** SYN-06, `02` §6.3

#### Scenario: Un tipo de comando desconocido se rechaza

- **GIVEN** un comando cuyo tipo no está registrado
- **WHEN** se procesa
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** SYN-06

#### Scenario: Una versión anterior del mismo tipo sigue atendiéndose

- **GIVEN** dos versiones registradas de un mismo tipo de comando
- **WHEN** llega un comando de la versión anterior
- **THEN** lo atiende el handler de esa versión, no el de la última
- **Regla:** `02` §6.6 (el servidor conserva los handlers de toda versión en colas activas)

#### Scenario: Una versión sin handler registrado se rechaza sin efectos

- **GIVEN** un comando de un tipo conocido con una versión que no tiene handler
- **WHEN** se procesa
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.6, SYN-06

### Requirement: El modo OFFLINE solo se admite donde está previsto

El sistema DEBE aceptar el modo `OFFLINE` únicamente por el punto de entrada de sincronización y solo para los tipos de comando que lo declaran admisible. Un comando en modo `OFFLINE` recibido por un endpoint REST directo, o de un tipo que no lo admite, DEBE rechazarse (ADR-012, `02` §6.2, `02` §6.5).

#### Scenario: Un endpoint REST directo no acepta modo OFFLINE

- **GIVEN** un usuario autenticado
- **WHEN** envía por un endpoint REST de escritura un comando declarado en modo `OFFLINE`
- **THEN** se rechaza
- **Regla:** ADR-012 (el modo OFFLINE solo se admite por el endpoint de sincronización)

#### Scenario: Un tipo que no admite offline se rechaza en el lote

- **GIVEN** un tipo de comando que solo admite modo `ONLINE` según `02` §6.5
- **WHEN** llega en un lote de sincronización declarado en modo `OFFLINE`
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** `02` §6.5, SYN-06
