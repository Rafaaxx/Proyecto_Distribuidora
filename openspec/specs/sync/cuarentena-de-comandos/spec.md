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
