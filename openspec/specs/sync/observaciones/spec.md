# Sincronización - Observaciones

## Purpose

Define la observación como la marca que deja una operación aceptada sobre la que hay algo que revisar: de dónde nace, qué guarda, con qué código y en qué estado queda. La bandeja de revisión y la resolución con comentario son del change 25; acá nace el mecanismo que las alimenta (SYN-04, SYN-07, SYN-08).

## Requirements

### Requirement: Una observación nace del procesamiento de un comando aceptado

El sistema DEBE registrar como observación cada marca de revisión que produce el handler de un comando aceptado, dentro de la misma transacción del comando. Una observación DEBE quedar asociada al comando que la originó y a la operación sobre la que recae, y DEBE nacer en estado `PENDIENTE`. Un comando RECHAZADO NO DEBE dejar observaciones (SYN-04, SYN-07, SYN-08).

#### Scenario: La observación queda asociada a su comando y a su operación

- **GIVEN** un comando aceptado cuyo handler produce una observación
- **WHEN** termina su procesamiento
- **THEN** queda una observación que referencia ese comando y la operación observada
- **AND** su estado es `PENDIENTE`
- **Regla:** SYN-07, SYN-08

#### Scenario: Un comando aceptado con observaciones lo refleja en su estado

- **GIVEN** un comando cuyo handler produce dos observaciones
- **WHEN** termina su procesamiento
- **THEN** el estado del comando es `ACEPTADO_CON_OBSERVACIONES`
- **AND** quedan dos observaciones registradas
- **Regla:** SYN-04, SYN-07

#### Scenario: Un comando rechazado no deja observaciones

- **GIVEN** un comando que se rechaza
- **WHEN** termina su procesamiento
- **THEN** no queda ninguna observación de ese comando
- **Regla:** SYN-04 (la observación acompaña a una operación aceptada)

#### Scenario: Las observaciones se revierten con el comando que falla

- **GIVEN** un comando cuyo handler registra una observación y después falla
- **WHEN** la transacción se revierte
- **THEN** no queda ninguna observación de ese comando
- **Regla:** INV-01, SYN-04

#### Scenario: El reenvío de un comando ya aceptado no duplica sus observaciones

- **GIVEN** un comando aceptado con una observación registrada
- **WHEN** el dispositivo lo reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** sigue existiendo una sola observación para ese comando
- **Regla:** SYN-02, INV-06

### Requirement: El código de una observación pertenece al catálogo de la etapa

Una observación DEBE llevar uno de los códigos que SYN-07 enumera para la etapa 1 y DEBE poder acompañarlo de un detalle con los datos del caso. Un código fuera del catálogo NO DEBE poder registrarse (SYN-07).

#### Scenario: Un código fuera del catálogo no se registra

- **GIVEN** un handler que intenta producir una observación con un código que no está en SYN-07
- **WHEN** el comando se procesa
- **THEN** la observación no queda registrada con ese código
- **Regla:** SYN-07

#### Scenario: La observación conserva el detalle del caso

- **GIVEN** un comando aceptado que produce una observación con datos del caso
- **WHEN** se consulta la observación
- **THEN** conserva su código y el detalle que la acompaña
- **Regla:** SYN-07, SYN-08 (la resolución se apoya en el detalle)

### Requirement: Una observación pendiente permanece hasta que alguien la resuelve

Una observación DEBE permanecer en estado `PENDIENTE` y NO DEBE modificar ni revertir la operación que observa. El sistema DEBE poder listar las pendientes de una organización por código de forma eficiente, y NO DEBE permitir borrarlas (SYN-08, INV-02, INV-05, `03` §13).

#### Scenario: La observación no altera la operación observada

- **GIVEN** una operación aceptada con una observación pendiente
- **WHEN** se consulta la operación
- **THEN** sus datos son los mismos que antes de la observación
- **Regla:** SYN-08 (resolverla no modifica la operación; las correcciones se hacen con operaciones nuevas)

#### Scenario: Las observaciones pendientes se consultan por organización y código

- **GIVEN** observaciones pendientes y resueltas en dos organizaciones
- **WHEN** se consultan las pendientes de una organización por código
- **THEN** se obtienen solo las pendientes de esa organización con ese código
- **Regla:** INV-02, INV-21, `03` §13 (índice parcial sobre las pendientes)

#### Scenario: La aplicación no puede borrar una observación

- **GIVEN** una observación registrada
- **WHEN** la aplicación intenta borrarla
- **THEN** la base rechaza la operación
- **Regla:** INV-05, TR-06
