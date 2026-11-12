## Purpose

Define cómo un dispositivo entrega al servidor la cola de comandos que generó: cuántos por vez, en qué orden se procesan, qué devuelve el servidor por cada uno y cuándo el lote se corta en seco para no alterar el orden de las operaciones (`02` §6.4, SYN-03, SYN-09).

## ADDED Requirements

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
