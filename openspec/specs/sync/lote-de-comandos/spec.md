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

El servidor DEBE responder un resultado por cada comando procesado, identificado por su `operation_id`, con el estado final y, cuando corresponda, el código de error y las observaciones. Un resultado `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO` NO DEBE detener el procesamiento del resto del lote (`02` §6.4, SYN-04, SYN-09).

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
