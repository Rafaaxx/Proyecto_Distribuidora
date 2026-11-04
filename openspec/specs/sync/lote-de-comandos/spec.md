# Sincronización - Lote de Comandos

## Purpose

Define cómo un dispositivo entrega al servidor la cola de comandos que generó: cuántos por vez, en qué orden se procesan, qué devuelve el servidor por cada uno y cuándo el lote se corta en seco para no alterar el orden de las operaciones (`02` §6.4, SYN-03, SYN-09).

## Requirements

### Requirement: El dispositivo entrega su cola en lotes ordenados

El sistema DEBE exponer un punto de entrada de sincronización que recibe hasta cincuenta comandos por lote, ordenados por la secuencia con que el dispositivo los generó, y DEBE procesarlos en ese orden. Un lote con más comandos que el máximo DEBE rechazarse entero, sin procesar ninguno (`02` §6.4).

#### Scenario: Los comandos se procesan en el orden de la cola

- **GIVEN** un lote con una venta y su anulación, en ese orden de secuencia
- **WHEN** el servidor lo procesa
- **THEN** la venta se procesa antes que su anulación
- **Regla:** SYN-03 (un comando que depende de otro se procesa después de él)

#### Scenario: Un lote desordenado se procesa por secuencia, no por posición

- **GIVEN** un lote cuyos comandos llegan en un orden distinto al de sus secuencias
- **WHEN** el servidor lo procesa
- **THEN** los procesa en orden de secuencia creciente
- **Regla:** SYN-03

#### Scenario: Un lote que excede el máximo se rechaza entero

- **GIVEN** un lote con cincuenta y un comandos
- **WHEN** se envía
- **THEN** se rechaza y ninguno de sus comandos queda procesado
- **Regla:** `02` §6.4 (hasta 50 comandos por lote)

#### Scenario: Un lote vacío no es un error

- **GIVEN** un dispositivo sin comandos pendientes
- **WHEN** envía un lote vacío
- **THEN** la respuesta es exitosa y no contiene resultados
- **Regla:** `02` §6.4

### Requirement: El servidor devuelve un resultado por comando

El servidor DEBE responder un resultado por cada comando procesado, identificado por su `operation_id`, con el estado final, el código de error cuando corresponda y la lista de observaciones del comando (código, tipo e identificador de la operación observada y detalle; vacía si no hay). El reenvío de un comando ya procesado DEBE devolver las mismas observaciones. Un resultado `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO` NO DEBE detener el procesamiento del resto del lote. Las observaciones DEBEN ser solo las del propio comando (`02` §6.4, SYN-04, SYN-07, SYN-09; `design.md` D3).

#### Scenario: Un rechazo no detiene el lote

- **GIVEN** un lote de tres comandos cuyo segundo se rechaza por una regla
- **WHEN** el servidor lo procesa
- **THEN** los tres tienen resultado y el tercero fue procesado
- **Regla:** `02` §6.4, SYN-04

#### Scenario: Cada resultado se identifica por su comando

- **GIVEN** un lote de varios comandos
- **WHEN** el servidor responde
- **THEN** cada resultado indica el identificador de operación al que corresponde
- **Regla:** SYN-09 (el dispositivo no elimina una operación local hasta recibir su resultado)

#### Scenario: Venta sin conexión con observaciones

- **GIVEN** una venta sin conexión que deja stock negativo de un producto y se cobra con un medio desactivado
- **WHEN** el servidor la acepta
- **THEN** el resultado es `ACEPTADO_CON_OBSERVACIONES` y trae `STOCK_NEGATIVO` sobre la venta con el producto en el detalle y `MEDIO_INACTIVO` sobre la cobranza con la línea, el medio y el importe
- **Regla:** SYN-04; SYN-07

#### Scenario: Resultado sin observaciones

- **GIVEN** una venta aceptada sin observaciones y otra rechazada
- **WHEN** el servidor responde
- **THEN** las dos traen la lista de observaciones vacía
- **Regla:** SYN-04

#### Scenario: Reenvío de un comando con observaciones

- **GIVEN** una venta ya aceptada con `LISTA_NO_VIGENTE`
- **WHEN** el dispositivo la envía otra vez con el mismo `operation_id` y el mismo contenido
- **THEN** el resultado trae la misma observación y no se registra otra
- **Regla:** SYN-02; INV-06

### Requirement: Un error transitorio corta el lote en ese comando

Cuando el procesamiento de un comando del lote termina en un error transitorio tras agotar sus reintentos, el servidor DEBE detener el lote en ese punto y NO DEBE procesar los comandos siguientes, para preservar el orden. La respuesta DEBE distinguir los comandos procesados de los no procesados (SYN-03, `02` §6.3, `02` §6.4).

#### Scenario: Los comandos posteriores a un error transitorio no se procesan

- **GIVEN** un lote de tres comandos cuyo segundo termina en error transitorio
- **WHEN** el servidor lo procesa
- **THEN** el primero tiene resultado final, el segundo informa error transitorio y el tercero no fue procesado
- **Regla:** SYN-03, `02` §6.4

#### Scenario: El reenvío del lote cortado no duplica lo ya aceptado

- **GIVEN** un lote cortado en el segundo comando, con el primero ya aceptado
- **WHEN** el dispositivo reenvía el lote completo sin cambiar ningún identificador de operación
- **THEN** el primero devuelve su resultado original sin producir efectos nuevos
- **AND** el segundo y el tercero se procesan
- **Regla:** SYN-02, INV-06 (doble sync no duplica)

### Requirement: La cola pertenece al usuario y al dispositivo que la generaron

El servidor DEBE aceptar un lote solo del usuario que generó esos comandos, autenticado en el dispositivo desde el que se generaron. Un comando cuyo usuario o dispositivo no coincide con los de la sesión DEBE rechazarse (`02` §6.4, SEG-02).

#### Scenario: Otro usuario no puede sincronizar la cola ajena

- **GIVEN** comandos generados por el usuario A en su dispositivo
- **WHEN** el usuario B, autenticado en ese mismo dispositivo, los envía en un lote
- **THEN** se rechazan y no queda ningún efecto
- **Regla:** `02` §6.4 (la cola pertenece al usuario que generó los comandos)

#### Scenario: Otro dispositivo no puede sincronizar la cola ajena

- **GIVEN** comandos generados por un usuario en el dispositivo X
- **WHEN** ese mismo usuario los envía autenticado en el dispositivo Y
- **THEN** se rechazan y no queda ningún efecto
- **Regla:** `02` §6.4, SEG-02

#### Scenario: Un lote sin sesión no se procesa

- **GIVEN** una petición de sincronización sin token de acceso
- **WHEN** llega al servidor
- **THEN** se rechaza por falta de autenticación y no queda ningún efecto
- **Regla:** SEG-06, `02` §6.4

### Requirement: La baja de un usuario no cierra el canal de su cola pendiente

> **(D9)** Requisito del cierre de la brecha de sesión (ADR-028, dominio CRÍTICO, aprobado por el usuario el 2026-09-25). Refleja la opción aprobada D9.3-B. La segunda parte se implementa en el change 17 (`design.md` D10).

El lote de sincronización NO DEBE rechazar en bloque, por ruta, a un usuario autenticado que está `INACTIVO` o cuyo rol está inactivo. DEBE procesar su lote comando por comando, igual que el de un usuario activo, para que una venta o cobranza registrada sin conexión nunca quede sin forma de llegar al servidor (`00` §3, SYN-05, SYN-09).

Con la verificación de permisos por comando del lote (paso 4 de `02` §6.3), para ese usuario:

- un comando `OFFLINE` DEBE aceptarse con la observación `PERMISO_REVOCADO` (SYN-10);
- un comando `ONLINE` DEBE rechazarse, igual que en REST.

#### Scenario: El lote de un usuario dado de baja no se rechaza en bloque
- **GIVEN** un usuario con un access token todavía vigente, que pasó a `INACTIVO`
- **WHEN** envía un lote de sincronización
- **THEN** el lote no se rechaza como no autenticado por la ruta
- **AND** cada comando recibe su propio resultado, como en el lote de un usuario activo
- **Regla:** ADR-028 (D9.3-B); SYN-05; SYN-09

#### Scenario: Cobranza offline de un usuario dado de baja
- **GIVEN** un vendedor `INACTIVO` con su jornada `ABIERTA` en el dispositivo y una cobranza de `"50000.00"` en la cola
- **WHEN** renueva su sesión con la excepción de jornada no cerrada y envía el lote
- **THEN** la cobranza se acepta con `PERMISO_REVOCADO` y el saldo del cliente baja `"50000.00"`
- **Regla:** ADR-028 (D9.3-B); ADR-049 punto 18; SYN-10

#### Scenario: Comando con conexión de un usuario dado de baja
- **GIVEN** el mismo vendedor `INACTIVO`
- **WHEN** el lote trae un `COBRANZA_REGISTRAR` en modo `ONLINE`
- **THEN** ese comando se rechaza y los demás del lote reciben su propio resultado
- **Regla:** ADR-028; SEG-06

### Requirement: Un comando sin conexión pertenece a una jornada del usuario y del dispositivo

Un comando en modo `OFFLINE` DEBE traer en su sobre una jornada; si no la trae, DEBE rechazarse con `JORNADA_REQUERIDA`. La jornada DEBE ser del usuario y del dispositivo de la sesión; si es de otro usuario o de otro dispositivo, el comando DEBE rechazarse con `JORNADA_AJENA`. En ambos casos no queda registro del comando ni efecto alguno, y el lote sigue (SYN-06). Una jornada inexistente sigue respondiendo `JORNADA_INEXISTENTE`. Si la jornada es del usuario y del dispositivo, el comando NO DEBE rechazarse por el estado de la jornada: con `ABIERTA` se procesa normalmente; con `LIBERADA` se acepta con la observación `JORNADA_LIBERADA`, que indica la jornada y el momento de la liberación (RUT-09); con `EN_RENDICION` o `CERRADA` se acepta sin observación nueva (`design.md` D12 del change 17).

#### Scenario: Cobranza posterior a una liberación
- **GIVEN** la jornada de la camioneta 2 liberada a las 14:00 con un motivo
- **WHEN** a las 19:00 el dispositivo de esa jornada sincroniza una cobranza de `"50000.00"` hecha a las 11:00
- **THEN** se acepta con `JORNADA_LIBERADA`, el saldo del cliente baja `"50000.00"` y la cobranza queda asociada a esa jornada
- **Regla:** RUT-09; SYN-05; SYN-07

#### Scenario: Jornada abierta
- **GIVEN** la jornada del vendedor `ABIERTA` en su dispositivo
- **WHEN** sincroniza una cobranza en modo `OFFLINE`
- **THEN** se acepta sin `JORNADA_LIBERADA`
- **Regla:** RUT-04; SYN-04

#### Scenario: Jornada ya cerrada
- **GIVEN** la jornada del vendedor ya `CERRADA`
- **WHEN** llega una cobranza en modo `OFFLINE` de esa jornada
- **THEN** se acepta sin observación nueva
- **Regla:** SYN-05; INV-17; `design.md` D12

#### Scenario: Comando sin conexión sin jornada
- **WHEN** llega una cobranza en modo `OFFLINE` sin jornada en el sobre
- **THEN** se rechaza con `JORNADA_REQUERIDA`, sin registro del comando, y el lote sigue
- **Regla:** `02` §6.2; SYN-06

#### Scenario: Jornada de otro vendedor
- **GIVEN** la jornada K de otro vendedor
- **WHEN** llega una cobranza en modo `OFFLINE` cuyo sobre nombra K
- **THEN** se rechaza con `JORNADA_AJENA`, sin registro del comando, y el lote sigue
- **Regla:** SYN-06; `02` §6.4

#### Scenario: Liberación simultánea
- **WHEN** una liberación de la jornada y una cobranza offline de esa jornada se procesan a la vez y confirman
- **THEN** la cobranza queda aceptada sin observación (si se procesó antes) o con `JORNADA_LIBERADA` (si se procesó después), nunca con otro resultado
- **Regla:** RUT-09; `02` §7.3

#### Scenario: Doble envío de una cobranza offline
- **GIVEN** una cobranza offline aceptada con `JORNADA_LIBERADA`
- **WHEN** el dispositivo reenvía el mismo comando en otro lote
- **THEN** recibe el resultado original con la misma observación, sin una segunda cobranza, movimiento ni observación
- **Regla:** INV-06; SYN-02; SYN-09

### Requirement: VENTA_CONFIRMAR se acepta por el lote sin conexión

El catálogo de tipos DEBE declarar `VENTA_CONFIRMAR` con modos `ONLINE` y `OFFLINE`, `permiso_offline = VENDER` y la venta como operación observable, de modo que `PERMISO_REVOCADO` y `JORNADA_LIBERADA` del bus se anoten sobre la venta (ADR-052, `design.md` D1 del change 18a). Por REST DEBE seguir siendo solo `ONLINE`.

#### Scenario: Venta sin conexión de un vendedor sin el permiso
- **GIVEN** Juan, a quien le quitaron `VENDER` después de abrir su jornada
- **WHEN** el lote trae su venta en modo `OFFLINE` con su jornada
- **THEN** se acepta con `PERMISO_REVOCADO` anotada sobre la venta (permiso `VENDER`, motivo `PERMISO_QUITADO`)
- **Regla:** SYN-10; INV-17

#### Scenario: Jornada liberada
- **GIVEN** la jornada de Juan liberada por un Supervisor
- **WHEN** llega su venta sin conexión
- **THEN** se acepta con `JORNADA_LIBERADA` sobre la venta
- **Regla:** RUT-09

#### Scenario: Ubicación tomada al sincronizar
- **GIVEN** la ubicación de la jornada de Juan tomada al sincronizar (su jornada en `EN_RENDICION`, o liberada y retomada por otra)
- **WHEN** llega su venta sin conexión
- **THEN** se acepta con `UBICACION_TOMADA_AL_SINCRONIZAR` sobre la venta (junto a `JORNADA_LIBERADA` si corresponde) y no con `UBICACION_TOMADA`
- **Regla:** SYN-05; SYN-07; INV-17; STK-09

#### Scenario: Sin jornada
- **WHEN** llega una venta `OFFLINE` sin jornada en el sobre
- **THEN** se rechaza con `JORNADA_REQUERIDA` y el lote sigue
- **Regla:** SYN-10; SYN-06

#### Scenario: Doble envío
- **WHEN** el lote reenvía la misma venta con el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones
- **Regla:** INV-06; SYN-02

### Requirement: Los tipos que reciben secretos no se admiten en el lote

El lote de sincronización NO DEBE admitir, en ningún modo, los tipos de comando declarados con `exige_credenciales_efimeras` (`USUARIO_CREAR`, `PIN_AUTORIZACION_ROTAR`, `PIN_AUTORIZACION_PROPIO_DEFINIR`): su secreto (contraseña o PIN) viaja fuera del contenido y solo entra por la ruta del tipo. Un ítem de esos tipos DEBE rechazarse con `MODO_NO_ADMITIDO_PARA_TIPO` (422) antes de reservar el `operation_id`, sin dejar fila de `comando`, y su contenido NO DEBE aparecer en los registros. Si el dispositivo está revocado, ese ítem DEBE responderse `DISPOSITIVO_REVOCADO` sin guardarse en `comando_cuarentena`; los demás ítems del mismo lote DEBEN ir a cuarentena como siempre (SYN-06). Un ítem de cualquier tipo que traiga credenciales fuera del contenido DEBE rechazarse como malformado sin guardarlas.

#### Scenario: USUARIO_CREAR por el lote

- **GIVEN** un administrador con `ADMIN_USUARIOS`
- **WHEN** envía `USUARIO_CREAR` por el lote, en modo `ONLINE`
- **THEN** se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO`, no queda usuario ni fila de `comando` y el contenido no aparece en los registros
- **Regla:** SYN-06; `02` §17; ADR-056

#### Scenario: Rotar o definir el PIN por el lote, con o sin conexión

- **WHEN** se envía `PIN_AUTORIZACION_ROTAR` o `PIN_AUTORIZACION_PROPIO_DEFINIR` por el lote, en modo `ONLINE` o `OFFLINE`
- **THEN** se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO` antes de reservar y el PIN no cambia
- **Regla:** SYN-06; `02` §17; ADR-056

#### Scenario: Un tipo con secretos desde un dispositivo revocado

- **GIVEN** un dispositivo revocado y un lote con un ítem de `USUARIO_CREAR` y otro ítem de otro tipo
- **WHEN** se envía el lote
- **THEN** el ítem de `USUARIO_CREAR` responde `DISPOSITIVO_REVOCADO` sin fila de `comando_cuarentena`, y el otro ítem sí va a cuarentena
- **Regla:** SYN-06; `02` §17; ADR-056

### Requirement: Una venta o cobranza sin conexión nunca se rechaza por reglas de negocio

Por el lote, una venta (`VENTA_CONFIRMAR`) o una cobranza (`COBRANZA_REGISTRAR`) en modo `OFFLINE` NO DEBE rechazarse por ninguna regla de negocio de SYN-05 (stock, crédito, lista, descuentos, estado del cliente, permisos, medio de pago desactivado, referencia faltante, producto o presentación desactivados, ubicación tomada al sincronizar, motivo dado de baja después del bootstrap), sola o combinada con las demás: DEBE aceptarse con las observaciones que correspondan. Solo DEBE rechazarse por las causas de SYN-06 (`design.md` D8).

#### Scenario: Cada regla por separado
- **GIVEN** una venta sin conexión que incumple una sola de las reglas de SYN-05
- **WHEN** llega por el lote
- **THEN** se acepta con la observación de esa regla, o sin observación si la regla no tiene una (motivo dado de baja)
- **Regla:** INV-17; SYN-05; SYN-07

#### Scenario: Todas a la vez
- **GIVEN** una venta sin conexión con cobranza que incumple a la vez stock, crédito, lista, cliente suspendido, permiso, medio desactivado y referencia faltante
- **WHEN** llega por el lote
- **THEN** se acepta con todas esas observaciones y su stock, su saldo y su cobranza quedan registrados
- **Regla:** INV-17; SYN-05

#### Scenario: Cobranza sin conexión
- **GIVEN** una cobranza sin conexión del consumidor final (en la cobranza solo él observa `CLIENTE_NO_HABILITADO`; un cliente inactivo se acepta sin observación, change 17 D13) con un medio desactivado, de un usuario que perdió `REGISTRAR_COBRANZA`
- **WHEN** llega por el lote
- **THEN** se acepta con `CLIENTE_NO_HABILITADO`, `MEDIO_INACTIVO` y `PERMISO_REVOCADO`
- **Regla:** INV-17; SYN-05; SYN-10

#### Scenario: Un comando malformado sí se rechaza
- **GIVEN** una venta sin conexión cuyos totales no coinciden con el cálculo sobre los valores enviados
- **WHEN** llega por el lote
- **THEN** se rechaza con `TOTALES_INCONSISTENTES`
- **Regla:** SYN-06; INV-17

#### Scenario: Doble envío de una venta observada
- **GIVEN** una venta sin conexión aceptada con `STOCK_NEGATIVO`
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** devuelve el mismo resultado y el stock baja una sola vez
- **Regla:** INV-06; INV-17

### Requirement: VENTA_ANULAR se acepta por el lote sin conexión

El catálogo de tipos DEBE declarar `VENTA_ANULAR` con modos `ONLINE` y `OFFLINE`, el permiso `ANULAR_VENTA` y la venta como operación observable, de modo que `PERMISO_REVOCADO` y `JORNADA_LIBERADA` del bus se anoten sobre la venta anulada. Por REST (`POST /api/v1/ventas/{venta_id}/anulacion`) DEBE seguir siendo solo `ONLINE`. Las reglas de la jornada del sobre (`JORNADA_REQUERIDA`, `JORNADA_AJENA`, `JORNADA_INEXISTENTE`) DEBEN valer igual que para la venta (`design.md` D1, D4).

#### Scenario: Anulación sin conexión por el lote
- **GIVEN** `sup01` con `ANULAR_VENTA` y su jornada `ABIERTA` en su teléfono
- **WHEN** el lote trae `VENTA_ANULAR` en modo `OFFLINE` con su jornada
- **THEN** el ítem se procesa con el handler de la anulación y responde `ACEPTADO` o `ACEPTADO_CON_OBSERVACIONES`
- **Regla:** VTA-24; `02` §6.5

#### Scenario: Por REST sigue siendo con conexión
- **WHEN** llega `POST /api/v1/ventas/{venta_id}/anulacion`
- **THEN** el sobre es `ONLINE` y rige la regla de toma de siempre
- **Regla:** `02` §6.5; STK-09

#### Scenario: Sin jornada
- **WHEN** llega una anulación `OFFLINE` sin jornada en el sobre
- **THEN** se rechaza con `JORNADA_REQUERIDA` y el lote sigue
- **Regla:** SYN-10; SYN-06

#### Scenario: Jornada de otro teléfono
- **WHEN** llega una anulación `OFFLINE` con la jornada de otro usuario o de otro dispositivo
- **THEN** se rechaza con `JORNADA_AJENA` y el lote sigue
- **Regla:** SYN-10; SYN-06

#### Scenario: Un rechazo no corta el lote
- **GIVEN** un lote con una anulación de una venta ya anulada y, después, una venta nueva
- **WHEN** el servidor procesa el lote
- **THEN** la anulación es `RECHAZADO` con `VENTA_YA_ANULADA` y la venta nueva se procesa igual
- **Regla:** `02` §6.4; SYN-04

#### Scenario: Doble envío
- **WHEN** el lote reenvía la misma anulación con el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones, sin efectos nuevos
- **Regla:** INV-06; SYN-02

### Requirement: La cobranza del teléfono se acepta por el lote con el contrato fijado

El sobre de `COBRANZA_REGISTRAR` v1 en modo `OFFLINE` que arma el teléfono DEBE coincidir con un fixture de contrato compartido que el esquema del lote acepta y que el teléfono reproduce igual: identificador de la cobranza, cliente, importe como string, de 1 a 20 medios (medio, importe como string y referencia o nula) y la observación o nula, con la jornada de la sesión en el sobre. El servidor DEBE procesarlo con las reglas vigentes de la cobranza sin conexión (ADR-052), sin cambios: rechaza solo lo malformado, lo inexistente o ajeno, el identificador repetido y la jornada del sobre inválida, y acepta todo lo demás con las observaciones que correspondan. Un comando que el teléfono encoló después de una venta del mismo cliente DEBE procesarse después de ella (`design.md` D2).

#### Scenario: Sobre del teléfono aceptado
- **GIVEN** `vendedor` con `REGISTRAR_COBRANZA` y su jornada `ABIERTA` en su teléfono, y Kiosco La Esquina con saldo `"150000.00"`
- **WHEN** el lote trae la cobranza del fixture de `"50000.00"`, con `"30000.00"` en efectivo y `"20000.00"` por transferencia con referencia `"0042"`
- **THEN** responde `ACEPTADO`, el saldo del cliente queda en `"100000.00"` y la cobranza lleva la jornada del sobre
- **Regla:** COB-01; COB-02; COB-03; SYN-01; SYN-05

#### Scenario: Venta y cobranza en el mismo lote
- **GIVEN** un lote con una venta a Kiosco La Esquina (secuencia 7) y una cobranza al mismo cliente (secuencia 8)
- **WHEN** el servidor procesa el lote
- **THEN** procesa la venta y después la cobranza, y el saldo refleja las dos
- **Regla:** SYN-03; CC-05

#### Scenario: Cliente inexistente
- **WHEN** el lote trae una cobranza `OFFLINE` de un cliente que no existe en la organización
- **THEN** se rechaza como dependencia inexistente, sin efectos, y el lote sigue con el ítem siguiente
- **Regla:** SYN-06; INV-21; `02` §6.4

#### Scenario: Medios que no suman el importe
- **WHEN** el lote trae una cobranza `OFFLINE` de `"50000.00"` cuyos medios suman `"49000.00"`
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y no queda ningún efecto
- **Regla:** INV-08; SYN-06

#### Scenario: Doble envío
- **WHEN** el lote reenvía la misma cobranza con el mismo `operation_id` y el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones y el saldo baja una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Lista cerrada de rechazos de la cobranza
- **GIVEN** el fixture de códigos de sincronización
- **WHEN** se recorren los rechazos que el bus y la cobranza pueden devolver a una cobranza `OFFLINE`
- **THEN** cada uno está en la lista de rechazos de la cobranza del fixture, y cada código de la lista existe en el servidor
- **Regla:** SYN-06; SYN-07
