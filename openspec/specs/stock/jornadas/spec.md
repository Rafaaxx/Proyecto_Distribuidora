# Jornadas — Especificación

## Purpose

Definir la jornada de un vendedor sobre una ubicación: su apertura con toma exclusiva, sus estados, la rendición mínima, el cierre, la liberación forzada con motivo y sus consultas, de modo que una ubicación que requiere toma nunca tenga más de una jornada no cerrada (RUT-01, RUT-03, RUT-08, RUT-09, INV-16; `01` §18; ADR-005).

## Requirements

### Requirement: Abrir una jornada toma la ubicación

El comando `JORNADA_ABRIR` DEBE crear una jornada `ABIERTA` del usuario y del dispositivo de la sesión sobre la ubicación indicada, y esa ubicación DEBE quedar tomada (RUT-01, RUT-03). DEBE exigir el permiso `ABRIR_JORNADA` y conexión: es solo `ONLINE` (`02` §6.5). La ubicación DEBE ser de la organización (si no, 404), estar activa (`UBICACION_INACTIVA`) y requerir toma (`UBICACION_SIN_TOMA`, `design.md` D3). El usuario y el dispositivo de la jornada NO DEBEN poder elegirse en el contenido: salen de la sesión. La apertura NO ejecuta el bootstrap, que pertenece al change 21 (`design.md` D5).

#### Scenario: Apertura de una jornada sobre un vehículo libre

- **GIVEN** un Vendedor con `ABRIR_JORNADA`, sin jornada abierta, y "Camioneta 1" (vehículo, requiere toma, activa) sin jornada
- **WHEN** envía `JORNADA_ABRIR` con la ubicación "Camioneta 1"
- **THEN** se crea una jornada `ABIERTA` con su usuario, su dispositivo, la ubicación y el momento de apertura
- **AND** "Camioneta 1" queda tomada por esa jornada
- **Regla:** RUT-01; RUT-03

#### Scenario: Apertura sin permiso

- **GIVEN** un usuario del rol Administración, que no tiene `ABRIR_JORNADA`
- **WHEN** envía `JORNADA_ABRIR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO` y no se crea ninguna jornada
- **Regla:** RUT-03; SEG-06; `01` §19

#### Scenario: Ubicación de otra organización

- **GIVEN** una ubicación que pertenece a otra organización
- **WHEN** un Vendedor envía `JORNADA_ABRIR` con esa ubicación
- **THEN** responde 404 y no se crea ninguna jornada
- **Regla:** INV-21; SEG-07

#### Scenario: Ubicación inactiva

- **GIVEN** "Camioneta 3" inactiva
- **WHEN** un Vendedor envía `JORNADA_ABRIR` con esa ubicación
- **THEN** se rechaza con `UBICACION_INACTIVA`
- **Regla:** ADR-038

#### Scenario: Ubicación que no requiere toma

- **GIVEN** "Depósito central" (depósito, sin toma)
- **WHEN** un Vendedor envía `JORNADA_ABRIR` con esa ubicación
- **THEN** se rechaza con `UBICACION_SIN_TOMA` y no se crea ninguna jornada
- **Regla:** RUT-01; `design.md` D3

#### Scenario: La apertura no se acepta sin conexión

- **GIVEN** un lote de sincronización con un `JORNADA_ABRIR` en modo `OFFLINE`
- **WHEN** el servidor procesa el lote
- **THEN** ese comando se rechaza y no se crea ninguna jornada
- **Regla:** RUT-03; `02` §6.5

#### Scenario: Doble envío de la misma apertura

- **GIVEN** un `JORNADA_ABRIR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y sigue habiendo una sola jornada
- **Regla:** SYN-02; INV-06

#### Scenario: Mismo identificador con otra ubicación

- **GIVEN** un `JORNADA_ABRIR` ya aceptado sobre "Camioneta 1"
- **WHEN** llega el mismo `operation_id` con "Camioneta 2"
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y la jornada original no cambia
- **Regla:** SYN-02

### Requirement: Una ubicación que requiere toma tiene como máximo una jornada no cerrada

Una ubicación NO DEBE tener más de una jornada en estado `ABIERTA` o `EN_RENDICION` (INV-16). La base DEBE garantizarlo con una restricción única, y la segunda apertura DEBE fallar por esa restricción y no por una verificación previa (`02` §7.5), con `UBICACION_TOMADA` (409). Una jornada `CERRADA` o `LIBERADA` NO ocupa la ubicación.

#### Scenario: Segunda apertura sobre una ubicación tomada

- **GIVEN** "Camioneta 1" con una jornada `ABIERTA` de Juan
- **WHEN** Pedro envía `JORNADA_ABRIR` con "Camioneta 1"
- **THEN** se rechaza con `UBICACION_TOMADA` y no se crea otra jornada
- **Regla:** INV-16; RUT-01

#### Scenario: Dos aperturas simultáneas sobre la misma ubicación

- **GIVEN** "Camioneta 1" libre y dos vendedores en dos dispositivos
- **WHEN** los dos envían `JORNADA_ABRIR` con "Camioneta 1" al mismo tiempo
- **THEN** exactamente una se acepta y la otra responde `UBICACION_TOMADA`
- **AND** queda una sola jornada no cerrada sobre "Camioneta 1"
- **Regla:** INV-16; `02` §7.5

#### Scenario: La base rechaza una segunda jornada escrita por fuera del servicio

- **GIVEN** una jornada `EN_RENDICION` sobre "Camioneta 1"
- **WHEN** se inserta directamente en la base otra jornada `ABIERTA` sobre la misma ubicación
- **THEN** la base la rechaza por la restricción única
- **Regla:** INV-16; `03` §15

#### Scenario: Una ubicación vuelve a abrirse después del cierre

- **GIVEN** "Camioneta 1" cuya jornada anterior está `CERRADA`
- **WHEN** un Vendedor envía `JORNADA_ABRIR` con "Camioneta 1"
- **THEN** se acepta
- **Regla:** RUT-08; INV-16

#### Scenario: Una ubicación vuelve a abrirse después de la liberación

- **GIVEN** "Camioneta 1" cuya jornada anterior está `LIBERADA`
- **WHEN** un Vendedor envía `JORNADA_ABRIR` con "Camioneta 1"
- **THEN** se acepta
- **Regla:** RUT-09; INV-16

### Requirement: Un usuario y un dispositivo tienen a lo sumo una jornada no cerrada

Un usuario NO DEBE tener más de una jornada no cerrada (`USUARIO_CON_JORNADA`, 409) y un dispositivo tampoco (`DISPOSITIVO_CON_JORNADA`, 409), garantizado también por la base (`design.md` D3; RUT-04; ADR-005).

#### Scenario: El mismo usuario intenta tomar un segundo vehículo

- **GIVEN** Juan con una jornada `ABIERTA` sobre "Camioneta 1"
- **WHEN** envía `JORNADA_ABRIR` con "Camioneta 2", libre
- **THEN** se rechaza con `USUARIO_CON_JORNADA` y "Camioneta 2" sigue libre
- **Regla:** RUT-04; `design.md` D3

#### Scenario: Otro usuario intenta abrir desde un dispositivo con jornada

- **GIVEN** el dispositivo V03 con una jornada `ABIERTA` de Juan
- **WHEN** Pedro inicia sesión en V03 y envía `JORNADA_ABRIR` con "Camioneta 2"
- **THEN** se rechaza con `DISPOSITIVO_CON_JORNADA`
- **Regla:** ADR-005; `design.md` D3

#### Scenario: Después de cerrar puede abrir otra

- **GIVEN** Juan, cuya jornada sobre "Camioneta 1" está `CERRADA`
- **WHEN** envía `JORNADA_ABRIR` con "Camioneta 2"
- **THEN** se acepta
- **Regla:** RUT-08

### Requirement: La jornada se rinde y se cierra siguiendo su máquina de estados

`JORNADA_RENDIR` DEBE pasar una jornada de `ABIERTA` a `EN_RENDICION` y `JORNADA_CERRAR` de `EN_RENDICION` a `CERRADA`; ambos exigen `RENDIR_JORNADA`, son solo `ONLINE` y valen sobre la jornada de cualquier usuario de la organización (`01` §18, §19). El cierre DEBE liberar la ubicación (RUT-08). En este change la rendición NO registra conteo ni diferencias (change 24; `design.md` D2). Cualquier otra transición DEBE rechazarse con `JORNADA_ESTADO_INVALIDO` (409) sin modificar la jornada. Cada transición DEBE guardar su momento y su usuario.

#### Scenario: Rendir una jornada abierta

- **GIVEN** una jornada `ABIERTA` de Juan sobre "Camioneta 1" y una Supervisora con `RENDIR_JORNADA`
- **WHEN** la Supervisora envía `JORNADA_RENDIR` sobre esa jornada
- **THEN** la jornada queda `EN_RENDICION` con el momento y el usuario de la rendición
- **AND** "Camioneta 1" sigue tomada
- **Regla:** `01` §18; RUT-05; `design.md` D2

#### Scenario: Cerrar una jornada en rendición libera la ubicación

- **GIVEN** una jornada `EN_RENDICION` sobre "Camioneta 1"
- **WHEN** un usuario con `RENDIR_JORNADA` envía `JORNADA_CERRAR`
- **THEN** la jornada queda `CERRADA` con el momento y el usuario del cierre
- **AND** "Camioneta 1" queda libre
- **Regla:** RUT-08; `01` §18

#### Scenario: Cerrar una jornada que no se rindió

- **GIVEN** una jornada `ABIERTA`
- **WHEN** un usuario con `RENDIR_JORNADA` envía `JORNADA_CERRAR`
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO` y la jornada sigue `ABIERTA`
- **Regla:** `01` §18

#### Scenario: Rendir dos veces

- **GIVEN** una jornada `EN_RENDICION`
- **WHEN** llega un `JORNADA_RENDIR` con otro `operation_id`
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO`
- **Regla:** `01` §18

#### Scenario: Transición sobre una jornada terminada

- **GIVEN** una jornada `CERRADA` y otra `LIBERADA`
- **WHEN** se envía `JORNADA_RENDIR` o `JORNADA_CERRAR` sobre cualquiera de las dos
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO`
- **Regla:** `01` §18; TR-06

#### Scenario: El vendedor no rinde su propia jornada

- **GIVEN** Juan, Vendedor, sin `RENDIR_JORNADA`, con su jornada `ABIERTA`
- **WHEN** envía `JORNADA_RENDIR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO`
- **Regla:** RUT-05; `01` §19

#### Scenario: Jornada de otra organización

- **GIVEN** una jornada de otra organización
- **WHEN** un usuario con `RENDIR_JORNADA` envía `JORNADA_RENDIR` o `JORNADA_CERRAR` sobre ella
- **THEN** responde 404
- **Regla:** INV-21

#### Scenario: Doble envío del cierre

- **GIVEN** un `JORNADA_CERRAR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original y la jornada sigue `CERRADA` con los datos del primer cierre
- **Regla:** SYN-02; INV-06

### Requirement: Liberar una jornada con motivo

`JORNADA_LIBERAR` DEBE pasar una jornada `ABIERTA` o `EN_RENDICION` a `LIBERADA` y dejar libre su ubicación (RUT-09). DEBE exigir `LIBERAR_UBICACION`, ser solo `ONLINE` y llevar un motivo activo del ámbito `LIBERACION_JORNADA` de la organización (`MOTIVO_INVALIDO`, 422; un motivo ajeno, 404) y una observación opcional de hasta 500 caracteres (`OBSERVACION_INVALIDA`, 422). La jornada DEBE guardar quién la liberó, cuándo y el motivo. Una organización DEBE nacer con motivos de ese ámbito (`design.md` D13). El stock que quede en la ubicación NO se modifica.

#### Scenario: Liberación de una jornada abierta

- **GIVEN** una jornada `ABIERTA` de Juan sobre "Camioneta 1" con 48 unidades de Vino A, y una Supervisora con `LIBERAR_UBICACION`
- **WHEN** la Supervisora envía `JORNADA_LIBERAR` con el motivo "Dispositivo perdido o averiado"
- **THEN** la jornada queda `LIBERADA` con el momento, la Supervisora y el motivo
- **AND** "Camioneta 1" queda libre y conserva sus 48 unidades
- **Regla:** RUT-09; `01` §18

#### Scenario: Liberación de una jornada en rendición

- **GIVEN** una jornada `EN_RENDICION`
- **WHEN** un usuario con `LIBERAR_UBICACION` envía `JORNADA_LIBERAR` con un motivo válido
- **THEN** queda `LIBERADA`
- **Regla:** `01` §18

#### Scenario: Liberación sin permiso

- **GIVEN** un usuario del rol Administración, con `RENDIR_JORNADA` y sin `LIBERAR_UBICACION`
- **WHEN** envía `JORNADA_LIBERAR`
- **THEN** se rechaza con 403 `PERMISO_REQUERIDO` y la jornada no cambia
- **Regla:** RUT-09; `01` §19

#### Scenario: Motivo inactivo o de otro ámbito

- **GIVEN** un motivo inactivo del ámbito `LIBERACION_JORNADA` y un motivo activo del ámbito `AJUSTE_STOCK`
- **WHEN** se envía `JORNADA_LIBERAR` con cualquiera de los dos
- **THEN** se rechaza con `MOTIVO_INVALIDO` y la jornada no cambia
- **Regla:** RUT-09; TR-09

#### Scenario: Motivo de otra organización

- **GIVEN** un motivo que pertenece a otra organización
- **WHEN** se envía `JORNADA_LIBERAR` con ese motivo
- **THEN** responde 404
- **Regla:** INV-21

#### Scenario: Liberar una jornada ya terminada

- **GIVEN** una jornada `CERRADA` y otra `LIBERADA`
- **WHEN** se envía `JORNADA_LIBERAR` sobre cualquiera de las dos
- **THEN** se rechaza con `JORNADA_ESTADO_INVALIDO`
- **Regla:** `01` §18

#### Scenario: Observación demasiado larga

- **GIVEN** una jornada `ABIERTA`
- **WHEN** se envía `JORNADA_LIBERAR` con una observación de 501 caracteres
- **THEN** se rechaza con `OBSERVACION_INVALIDA`
- **Regla:** `design.md` D13

#### Scenario: Doble envío de la liberación

- **GIVEN** un `JORNADA_LIBERAR` ya aceptado
- **WHEN** llega otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y no hay una segunda fila de auditoría
- **Regla:** SYN-02; INV-06

#### Scenario: Una organización nueva tiene motivos de liberación

- **GIVEN** una organización recién creada
- **WHEN** se consultan los motivos activos del ámbito `LIBERACION_JORNADA`
- **THEN** devuelve "Dispositivo perdido o averiado", "Vendedor ausente" y "Otro"
- **Regla:** TR-09; `design.md` D13

### Requirement: Las transiciones de una jornada se auditan

Cada comando de jornada aceptado DEBE dejar exactamente un registro de auditoría con el usuario, el dispositivo, la acción y el `operation_id` (AUD-01, AUD-02; ADR-022). El de `JORNADA_LIBERAR` DEBE llevar el motivo de la liberación (`design.md` D8). Un comando rechazado NO DEBE dejar registro con motivo, y un reenvío idempotente NO DEBE escribir otro registro.

#### Scenario: La liberación queda auditada con su motivo

- **GIVEN** una jornada `ABIERTA`
- **WHEN** una Supervisora la libera con el motivo "Vendedor ausente"
- **THEN** hay un solo registro de auditoría `JORNADA_LIBERAR`, con la Supervisora, su dispositivo, el `operation_id` y el motivo "Vendedor ausente"
- **Regla:** AUD-01; AUD-02; RUT-09

#### Scenario: Apertura, rendición y cierre quedan auditados sin motivo

- **GIVEN** una jornada que se abre, se rinde y se cierra
- **WHEN** se consulta la auditoría de esos tres comandos
- **THEN** hay un registro por comando, cada uno con su usuario y su `operation_id`, y ninguno lleva motivo
- **Regla:** AUD-02; ADR-022

#### Scenario: Una liberación rechazada no deja motivo en la auditoría

- **GIVEN** una jornada `CERRADA`
- **WHEN** se envía `JORNADA_LIBERAR` con un motivo válido y se rechaza con `JORNADA_ESTADO_INVALIDO`
- **THEN** no queda ningún registro de auditoría con ese motivo
- **Regla:** AUD-02; INV-01

### Requirement: Una jornada se registra completa y no se borra

Cada comando de jornada DEBE aplicarse completo o no aplicarse (INV-01). Una jornada NO DEBE poder borrarse, y sus datos de apertura (usuario, dispositivo, ubicación, momento) NO DEBEN poder modificarse: solo cambian el estado y los datos de cada transición (INV-05, TR-06).

#### Scenario: Falla en medio de la apertura

- **GIVEN** un `JORNADA_ABRIR` válido
- **WHEN** el proceso falla después de escribir la jornada y antes de confirmar
- **THEN** no queda ninguna jornada, la ubicación sigue libre y el mismo `operation_id` puede reintentarse
- **Regla:** INV-01

#### Scenario: Falla en medio de la liberación

- **GIVEN** un `JORNADA_LIBERAR` válido sobre una jornada `ABIERTA`
- **WHEN** el proceso falla antes de confirmar
- **THEN** la jornada sigue `ABIERTA`, la ubicación sigue tomada y no hay registro de auditoría
- **Regla:** INV-01

#### Scenario: La aplicación no puede borrar ni reescribir una jornada

- **GIVEN** una jornada `CERRADA`
- **WHEN** el usuario de aplicación de la base intenta borrarla, o cambiar su ubicación, su usuario o su momento de apertura
- **THEN** la base lo rechaza por falta de privilegios
- **Regla:** INV-05; TR-06

#### Scenario: La base rechaza un estado incoherente

- **GIVEN** una jornada `ABIERTA`
- **WHEN** se intenta dejarla `LIBERADA` sin motivo, sin usuario o sin momento de liberación
- **THEN** la base lo rechaza por la restricción de coherencia
- **Regla:** RUT-09; `design.md` D10

### Requirement: Las jornadas se consultan por organización

El sistema DEBE ofrecer el listado de jornadas de la organización (filtros de ubicación, usuario, estado y fechas de negocio en la zona de la organización; más recientes primero; con cursor y límite) y el detalle de una jornada, a quien tenga `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`; y la jornada no cerrada del usuario y del dispositivo de la sesión, a quien tenga `ABRIR_JORNADA` (`design.md` D15). Una jornada de otra organización DEBE responder 404 (INV-21).

#### Scenario: Listado de jornadas

- **GIVEN** tres jornadas de la organización, una `ABIERTA`, una `CERRADA` y una `LIBERADA`, y una jornada de otra organización
- **WHEN** un Vendedor consulta el listado
- **THEN** recibe las tres de su organización, de la más reciente a la más antigua, con ubicación, usuario, dispositivo, estado y momento de apertura
- **Regla:** INV-21; `design.md` D15

#### Scenario: Filtro por estado y ubicación

- **GIVEN** jornadas de "Camioneta 1" y de "Camioneta 2" en distintos estados
- **WHEN** se consulta con ubicación "Camioneta 1" y estado `ABIERTA`
- **THEN** solo devuelve las jornadas abiertas de "Camioneta 1"
- **Regla:** `design.md` D15

#### Scenario: Detalle de una jornada liberada

- **GIVEN** una jornada `LIBERADA`
- **WHEN** se consulta su detalle
- **THEN** muestra los datos de apertura y quién la liberó, cuándo, con qué motivo y con qué observación
- **Regla:** RUT-09

#### Scenario: Mi jornada actual

- **GIVEN** Juan con una jornada `ABIERTA` sobre "Camioneta 1" en el dispositivo V03
- **WHEN** consulta su jornada actual desde V03 y desde otro dispositivo
- **THEN** desde V03 recibe esa jornada y desde el otro dispositivo, 404
- **Regla:** RUT-01; ADR-005

#### Scenario: Usuario sin permisos de jornada

- **GIVEN** un usuario del rol Consulta
- **WHEN** consulta el listado o un detalle
- **THEN** responde 403 `PERMISO_REQUERIDO`
- **Regla:** SEG-06

#### Scenario: Detalle de una jornada ajena

- **GIVEN** una jornada de otra organización
- **WHEN** se consulta su detalle
- **THEN** responde 404
- **Regla:** INV-21; SEG-07

#### Scenario: Rango de fechas inválido

- **GIVEN** un usuario con `RENDIR_JORNADA`
- **WHEN** consulta el listado con una fecha desde posterior a la fecha hasta
- **THEN** se rechaza con `RANGO_DE_FECHAS_INVALIDO`
- **Regla:** TR-04
