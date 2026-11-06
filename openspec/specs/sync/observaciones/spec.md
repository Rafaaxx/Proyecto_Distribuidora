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

### Requirement: Toda autorización sin conexión deja una observación

Una venta sin conexión cuyo descuento manual o cuyo exceso de crédito se resolvió por PIN de supervisor o por permiso propio DEBE llevar una observación `AUTORIZACION_OFFLINE` por cada autorización, con el tipo (`DESCUENTO` o `CREDITO`), la resolución, el autorizador y si el autorizador conserva el permiso al sincronizar. La venta NO DEBE rechazarse si el autorizador ya no tiene el permiso; un autorizador inexistente o de otra organización DEBE rechazar el comando como dependencia inexistente. El catálogo de SYN-07 suma `AUTORIZACION_OFFLINE`.

#### Scenario: PIN de supervisor sin conexión

- **GIVEN** una venta sin conexión con 10 % manual autorizado por Marta con PIN
- **WHEN** se sincroniza
- **THEN** se acepta con `AUTORIZACION_OFFLINE` tipo `DESCUENTO`, autorizadora Marta y `autorizador_con_permiso = true`
- **Regla:** SEG-05; ADR-011; `02` §12.4

#### Scenario: El autorizador perdió el permiso

- **GIVEN** a Marta le quitaron `SUPERAR_CREDITO` después del bootstrap
- **WHEN** llega una venta con exceso autorizado por su PIN
- **THEN** se acepta con `AUTORIZACION_OFFLINE` tipo `CREDITO` y `autorizador_con_permiso = false`
- **Regla:** SYN-05; INV-17

#### Scenario: Autorizador inexistente

- **WHEN** la venta nombra un autorizador que no existe en la organización
- **THEN** se rechaza y el lote sigue
- **Regla:** SYN-06; INV-21

#### Scenario: Doble envío

- **WHEN** el lote reenvía la venta
- **THEN** devuelve el resultado original sin duplicar la observación
- **Regla:** INV-06

### Requirement: Lo que llega con la jornada ya rendida se acepta con observación

Una venta, una anulación de venta o una cobranza sin conexión cuya jornada del sobre está `EN_RENDICION` o `CERRADA` DEBE aceptarse (INV-17) con una observación `JORNADA_RENDIDA` sobre la operación (detalle: jornada y momento de la rendición), además de las que ya correspondan. `JORNADA_RENDIDA` DEBE pertenecer al catálogo de SYN-07 (`design.md` D7).

#### Scenario: Venta tardía
- **GIVEN** la jornada de Juan rendida a las 18:00
- **WHEN** llega una venta sin conexión de esa jornada
- **THEN** se acepta con `JORNADA_RENDIDA` y `UBICACION_TOMADA_AL_SINCRONIZAR`, y descuenta el stock sin jornada
- **Regla:** SYN-05; SYN-07; INV-17; STK-09

#### Scenario: Cobranza tardía con la jornada cerrada
- **GIVEN** la jornada de Juan `CERRADA`
- **WHEN** llega una cobranza sin conexión de $50.000 a Kiosco La Esquina de esa jornada
- **THEN** se acepta con `JORNADA_RENDIDA` y baja el saldo del cliente
- **Regla:** SYN-05; INV-17; RUT-05

#### Scenario: Anulación tardía
- **GIVEN** la jornada de Juan `EN_RENDICION`
- **WHEN** llega una anulación sin conexión de una venta de esa jornada
- **THEN** se acepta con `JORNADA_RENDIDA`
- **Regla:** SYN-07; VTA-24

#### Scenario: Doble envío de la operación tardía
- **GIVEN** una cobranza tardía ya aceptada con `JORNADA_RENDIDA`
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** se devuelve el resultado original y no se registra otra observación
- **Regla:** SYN-02; INV-06

### Requirement: La resolución de una observación no se edita ni se borra

Una observación DEBE pasar solo de `PENDIENTE` a `RESUELTA`. La base DEBE garantizar que una observación `RESUELTA` tiene usuario, momento y comentario de 1 a 500 caracteres, y que una `PENDIENTE` no tiene ninguno de los tres; la aplicación solo DEBE poder actualizar esas columnas y el estado, nunca el código, el detalle, la operación ni el comando, y nunca borrar (SYN-08, INV-05, `design.md` D2).

#### Scenario: La aplicación no cambia el detalle
- **GIVEN** una observación registrada
- **WHEN** la aplicación intenta cambiar su código, su detalle o la operación
- **THEN** la base lo impide
- **Regla:** INV-05; SYN-08

#### Scenario: Resuelta sin comentario
- **WHEN** se intenta guardar una observación `RESUELTA` sin comentario o sin usuario
- **THEN** la base lo impide
- **Regla:** SYN-08

#### Scenario: Las de antes del change siguen pendientes
- **GIVEN** observaciones registradas antes de la migración
- **WHEN** se aplica
- **THEN** siguen `PENDIENTE`, sin resolución, y la migración sube y baja limpia
- **Regla:** `04` §2.1 punto 4

### Requirement: Una venta sin conexión de un producto desactivado se acepta con observación

Una venta sin conexión con una línea cuyo producto o presentación está desactivado al sincronizar DEBE aceptarse (SYN-05, INV-17) con una observación `PRODUCTO_DESACTIVADO` por línea afectada (detalle: línea, producto, presentación y cuál está inactivo), además de las que ya correspondan. `PRODUCTO_DESACTIVADO` DEBE pertenecer al catálogo de SYN-07 (`design.md` D10). Con conexión, el rechazo sigue igual.

#### Scenario: Producto desactivado después del bootstrap
- **GIVEN** un producto que la oficina desactivó después de que el teléfono de Juan bajó los datos
- **WHEN** llega una venta sin conexión con ese producto
- **THEN** se acepta con `PRODUCTO_DESACTIVADO` sobre esa línea y descuenta el stock
- **Regla:** SYN-05; SYN-07; INV-17; ADR-054

#### Scenario: Presentación desactivada
- **WHEN** llega una venta sin conexión con una presentación desactivada de un producto activo
- **THEN** se acepta con `PRODUCTO_DESACTIVADO` que indica la presentación
- **Regla:** SYN-07; INV-17

#### Scenario: Doble envío
- **GIVEN** la venta ya aceptada con `PRODUCTO_DESACTIVADO`
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** devuelve el resultado original sin duplicar la observación
- **Regla:** SYN-02; INV-06
