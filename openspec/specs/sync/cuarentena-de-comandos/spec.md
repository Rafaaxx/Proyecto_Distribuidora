# Sincronización - Cuarentena de Comandos

## Purpose

Define qué pasa con los comandos que llegan desde un dispositivo revocado: se rechazan, pero no se descartan. Quedan guardados íntegros para que una persona pueda revisarlos después, porque un equipo revocado puede contener operaciones reales de un vendedor que no supo que perdió el acceso (SYN-06).

## Requirements

### Requirement: Un comando de un dispositivo revocado se rechaza y se guarda

El sistema DEBE rechazar todo comando proveniente de un dispositivo revocado y DEBE guardarlo íntegro en cuarentena antes de responder, conservando organización, dispositivo, usuario, identificador de operación, tipo, contenido completo, motivo y momento de recepción. El comando NO DEBE producir ningún efecto de negocio y NO DEBE perderse (SYN-06).

#### Scenario: El comando de un dispositivo revocado no produce efectos

- **GIVEN** un dispositivo en estado `REVOCADO`
- **WHEN** llega un comando desde ese dispositivo
- **THEN** la respuesta es RECHAZADO
- **AND** no queda ningún efecto de negocio en la base
- **Regla:** SYN-06, SEG-02

#### Scenario: El comando rechazado queda en cuarentena con su contenido completo

- **GIVEN** un dispositivo revocado que envía un comando con contenido
- **WHEN** el servidor lo rechaza
- **THEN** queda un registro de cuarentena con el identificador de operación, el tipo, el contenido completo y el motivo
- **Regla:** SYN-06 (no se pierden)

#### Scenario: La cuarentena sobrevive al rechazo de la operación

- **GIVEN** un comando de un dispositivo revocado
- **WHEN** el procesamiento del comando se revierte por su rechazo
- **THEN** el registro de cuarentena queda persistido igualmente
- **Regla:** SYN-06, `02` §6.3 (se guarda en una transacción aparte)

#### Scenario: Un lote entero de un dispositivo revocado queda en cuarentena

- **GIVEN** un dispositivo revocado que envía un lote de tres comandos
- **WHEN** el servidor lo procesa
- **THEN** los tres se rechazan y los tres quedan en cuarentena
- **Regla:** SYN-06

#### Scenario: El reenvío de un comando ya puesto en cuarentena no lo duplica

- **GIVEN** un comando de un dispositivo revocado ya registrado en cuarentena
- **WHEN** el dispositivo lo reenvía con el mismo identificador de operación
- **THEN** la respuesta vuelve a ser RECHAZADO
- **AND** no queda un segundo registro de cuarentena para ese identificador de operación
- **Regla:** SYN-06, INV-06

### Requirement: La cuarentena queda dentro de la organización y no se borra

Un registro de cuarentena DEBE pertenecer a la organización del dispositivo y NO DEBE ser alcanzable desde otra. El sistema NO DEBE permitir borrarlo; conserva los campos previstos para dejar constancia de su revisión (SYN-06, INV-02, INV-21, INV-05).

#### Scenario: La cuarentena de otra organización no es alcanzable

- **GIVEN** un registro de cuarentena de la organización A
- **WHEN** se consulta desde la organización B
- **THEN** no aparece
- **Regla:** INV-02, INV-21, TR-08

#### Scenario: La aplicación no puede borrar un registro de cuarentena

- **GIVEN** un registro de cuarentena existente
- **WHEN** la aplicación intenta borrarlo
- **THEN** la base rechaza la operación
- **Regla:** INV-05, SYN-06 (no se pierden)

### Requirement: La cuarentena se revisa y se resuelve sin reenviarse

Un comando en cuarentena DEBE poder revisarse con `REVISAR_OBSERVACIONES` en la lista de rechazos (origen «Teléfono dado de baja») y resolverse con `RECHAZO_RESOLVER`: queda con el usuario que lo revisó, el momento, un comentario de 1 a 500 caracteres y, opcional, el vínculo a la operación cargada con conexión que lo corrige. Un comando en cuarentena NO DEBE reenviarse, reprocesarse ni ejecutarse nunca, ni por su teléfono ni desde `/admin`; la corrección es una operación nueva (SYN-06, SYN-08, `design.md` D7).

#### Scenario: Revisar la venta de un teléfono dado de baja
- **GIVEN** una venta de Juan en cuarentena porque su teléfono se dio de baja
- **WHEN** la Supervisora la resuelve con un comentario y el vínculo a la venta que cargó con conexión
- **THEN** la cuarentena queda revisada con su usuario, momento, comentario y vínculo
- **AND** no se crea ninguna venta por la cuarentena
- **Regla:** SYN-06; SYN-08

#### Scenario: El teléfono dado de baja reenvía
- **GIVEN** una cuarentena ya resuelta
- **WHEN** el teléfono dado de baja vuelve a enviar el mismo comando
- **THEN** se responde RECHAZADO con `DISPOSITIVO_REVOCADO`, sigue habiendo un solo registro y su resolución no cambia
- **Regla:** SYN-06; INV-06

#### Scenario: Ya revisada
- **WHEN** se intenta resolver una cuarentena ya revisada
- **THEN** se rechaza con `RECHAZO_YA_RESUELTO` (409)
- **Regla:** `01` §18

#### Scenario: Cuarentena de otra organización
- **WHEN** un usuario de la organización A intenta resolver una cuarentena de la organización B
- **THEN** responde 404
- **Regla:** INV-21

#### Scenario: Solo cambian las columnas de la revisión
- **WHEN** la aplicación intenta cambiar el contenido, el tipo o el motivo de una cuarentena
- **THEN** la base lo impide
- **Regla:** INV-05; SYN-06 (no se pierden)
