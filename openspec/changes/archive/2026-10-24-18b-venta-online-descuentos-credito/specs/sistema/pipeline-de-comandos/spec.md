## MODIFIED Requirements

### Requirement: Un permiso faltante rechaza el comando en modo ONLINE

El sistema DEBE verificar los permisos del usuario en cada comando, por REST y por el lote, **dentro del bus (`procesar_comando`) y con el permiso que el catálogo declara para el tipo** (ADR-056, `design.md` D23). En modo `ONLINE`, un usuario que no tenga ninguno de los permisos declarados por el tipo DEBE ser rechazado con `PERMISO_REQUERIDO` (403) antes de que el handler produzca efectos y sin dejar fila de `comando` (SEG-06). En modo `OFFLINE`, un permiso faltante NO DEBE rechazar el comando: el comando DEBE procesarse y quedar aceptado con la observación `PERMISO_REVOCADO` (SYN-10). Para esa verificación, un usuario `INACTIVO` o cuyo rol está inactivo DEBE evaluarse sin permisos (ADR-028). **Todo tipo de comando, admita o no `OFFLINE`, DEBE declarar los permisos que exige (`permisos`, una tupla no vacía con semántica "alguno de", que reemplaza a `permiso_offline`), y el sistema DEBE negarse a arrancar si alguno no lo declara; la única salida es una excepción explícita y justificada, hoy sin usos.** El permiso declarado en el catálogo DEBE coincidir con el que exige la ruta REST del tipo. La comparación en `OFFLINE` se hace contra los permisos que el usuario tiene al sincronizar (`design.md` D11 del change 17).

#### Scenario: Un usuario sin el permiso no ejecuta el comando

- **GIVEN** un usuario autenticado sin el permiso que exige el tipo de comando
- **WHEN** envía ese comando en modo ONLINE
- **THEN** se rechaza y no queda ningún efecto
- **Regla:** SEG-06

#### Scenario: Un comando sobre un recurso de otra organización no revela su existencia

- **GIVEN** un usuario de la organización A y una entidad de la organización B
- **WHEN** envía un comando que la referencia
- **THEN** la respuesta indica que el recurso no existe
- **Regla:** SEG-07, INV-21, TR-08

#### Scenario: Un permiso quitado no rechaza un comando sin conexión

- **GIVEN** una vendedora con su jornada abierta a la que le quitaron `REGISTRAR_COBRANZA` después de cobrar `"50000.00"` sin conexión
- **WHEN** sincroniza esa cobranza en modo `OFFLINE`
- **THEN** se acepta con la observación `PERMISO_REVOCADO`, que indica el permiso, y el saldo del cliente baja `"50000.00"`
- **Regla:** SYN-10; SYN-05; INV-17

#### Scenario: Un usuario dado de baja con cola pendiente

- **GIVEN** un vendedor `INACTIVO` con su jornada abierta y una cobranza sin sincronizar
- **WHEN** sincroniza la cobranza en modo `OFFLINE`
- **THEN** se acepta con `PERMISO_REVOCADO` y el motivo `USUARIO_INACTIVO`
- **Regla:** ADR-028 (D9.3-B); SYN-10

#### Scenario: Un rol desactivado

- **GIVEN** un vendedor cuyo rol pasó a inactivo, con una cobranza sin sincronizar
- **WHEN** la sincroniza en modo `OFFLINE`
- **THEN** se acepta con `PERMISO_REVOCADO` y el motivo `ROL_INACTIVO`
- **Regla:** ADR-028 (D9.4-A); SYN-10

#### Scenario: Con el permiso no hay observación

- **GIVEN** un vendedor con `REGISTRAR_COBRANZA` y su jornada abierta
- **WHEN** sincroniza una cobranza en modo `OFFLINE`
- **THEN** se acepta sin `PERMISO_REVOCADO`
- **Regla:** SYN-10

#### Scenario: Todo tipo offline declara su permiso

- **GIVEN** el catálogo de tipos de comando cargado al arrancar
- **WHEN** se recorren los tipos que admiten `OFFLINE`
- **THEN** cada uno declara el permiso que exige
- **Regla:** SEG-06; `02` §6.3 paso 4

#### Scenario: Todo tipo declara su permiso

- **GIVEN** el catálogo de tipos de comando cargado al arrancar
- **WHEN** se recorren todos los tipos, admitan o no `OFFLINE`
- **THEN** cada uno declara los permisos que exige, o una excepción justificada de una lista explícita (hoy vacía), y un tipo sin ninguno de los dos impide arrancar
- **Regla:** SEG-06; `02` §6.3 paso 4; ADR-056

#### Scenario: Un usuario sin el permiso no lo evade por el lote

- **GIVEN** Pedro, vendedor sin `ADMIN_USUARIOS`
- **WHEN** envía `ROL_PERMISOS_CAMBIAR` por el lote en modo `ONLINE` para sumar `AUTORIZAR_DESCUENTO` a su rol
- **THEN** se rechaza con `PERMISO_REQUERIDO`, no queda fila de `comando` y el rol no cambia
- **Regla:** SEG-06; ADR-028; ADR-056; INV-01

#### Scenario: El mismo comando con el permiso da el mismo resultado por REST y por el lote

- **GIVEN** un usuario con el permiso que declara el tipo
- **WHEN** envía el mismo comando por REST y, con otro `operation_id`, por el lote en modo `ONLINE`
- **THEN** ambos dan el mismo resultado
- **Regla:** SEG-06; `02` §6.1

#### Scenario: Un usuario inactivo con token vigente

- **GIVEN** un usuario `INACTIVO` con un access token todavía vigente
- **WHEN** envía un comando por el lote en modo `ONLINE`
- **THEN** se rechaza con `PERMISO_REQUERIDO`; el mismo comando en modo `OFFLINE` se acepta con `PERMISO_REVOCADO`
- **Regla:** ADR-028 (D9.3-B); SYN-10

#### Scenario: El permiso de la ruta coincide con el del catálogo

- **GIVEN** el catálogo de tipos y las rutas REST de escritura
- **WHEN** se compara, para cada tipo, el permiso que exige la ruta con el que declara el catálogo
- **THEN** coinciden en todos
- **Regla:** SEG-06; ADR-056

### Requirement: Un comando se ejecuta igual por REST y por el lote

Todo handler registrado DEBE recibir, por cualquiera de los dos puntos de entrada, la misma sesión de la transacción (sin poder confirmarla ni revertirla) y el mismo reloj del bus, con una firma que el verificador de tipos comprueba sin excepciones (`02` §6.1: "no existe una segunda implementación de ninguna operación"; `design.md` D9 del change 17). Un comando válido enviado por el lote en modo `ONLINE` DEBE producir el mismo resultado que por REST, **salvo los tipos que reciben un secreto fuera del contenido (`exige_credenciales_efimeras`), que solo entran por su ruta** (ADR-056).

#### Scenario: Una transferencia por el lote en modo ONLINE

- **GIVEN** un usuario con `TRANSFERIR_STOCK` y dos ubicaciones libres con stock
- **WHEN** envía `STOCK_TRANSFERIR` por el lote en modo `ONLINE`
- **THEN** se acepta y deja los mismos movimientos que por REST
- **Regla:** `02` §6.1; ADR-048 punto 5

#### Scenario: Una transición de jornada por el lote

- **GIVEN** un usuario con `RENDIR_JORNADA` y una jornada `ABIERTA`
- **WHEN** envía `JORNADA_RENDIR` por el lote en modo `ONLINE`
- **THEN** la jornada pasa a `EN_RENDICION`, igual que por REST
- **Regla:** `02` §6.1; ADR-049 punto 19

#### Scenario: Todos los tipos registrados se pueden despachar por el lote

- **GIVEN** el registro de handlers cargado al arrancar
- **WHEN** se despacha por el lote un comando de cada tipo con un contenido que su esquema rechaza
- **THEN** cada uno responde un rechazo de contenido, nunca un error interno por la forma de invocar al handler
- **Regla:** SYN-06; `02` §6.3

#### Scenario: Un handler no confirma la transacción por el lote

- **GIVEN** un handler que intenta confirmar la transacción
- **WHEN** se lo despacha por el lote
- **THEN** la confirmación se rechaza y el comando no deja efectos propios
- **Regla:** `02` §5.2 (los handlers no hacen commit)

#### Scenario: Un tipo con secretos no se despacha por el lote

- **GIVEN** un tipo declarado con `exige_credenciales_efimeras`
- **WHEN** se lo envía por el lote
- **THEN** se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO` (ver `sync/lote-de-comandos`)
- **Regla:** `02` §17; ADR-056
