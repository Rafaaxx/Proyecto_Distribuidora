## Purpose

Registrar cada importación como un comando del bus, con permiso, atomicidad, idempotencia, informe de errores por fila e historial consultable, para que la puesta en marcha quede trazable y nunca deje datos a medio cargar.

## ADDED Requirements

### Requirement: Comando de importación

El sistema DEBE ofrecer el comando `IMPORTACION_REGISTRAR` (solo `ONLINE`, `02` §6.5) con el tipo de importación (`PROVEEDORES`, `PRODUCTOS`, `CLIENTES`, `COSTOS`, `STOCK_INICIAL`, `SALDOS_INICIALES`, según `design.md` D8/D9), el nombre del archivo y sus filas, con `operation_id` en el encabezado `Operation-Id`. DEBE exigir `IMPORTAR_DATOS` (`01` §19) y quedar auditado una sola vez por el bus (AUD-01, ADR-022). Un comando de importación enviado en modo `OFFLINE` DEBE rechazarse.

#### Scenario: Importación aceptada

- **GIVEN** un Administrador y una planilla de proveedores con dos filas válidas
- **WHEN** la importa con un `Operation-Id` nuevo
- **THEN** responde 201 con el identificador de la importación, `filas_total` 2 y `filas_ok` 2; existe una fila en `importacion` con tipo `PROVEEDORES`, el nombre del archivo y el estado de éxito, y una sola auditoría del comando
- **Regla:** AUD-01; ADR-022

#### Scenario: Sin permiso

- **GIVEN** un usuario con `GESTIONAR_CATALOGO` pero sin `IMPORTAR_DATOS`
- **WHEN** intenta importar productos
- **THEN** recibe 403 `PERMISO_REQUERIDO` y no se escribe nada
- **Regla:** `01` §19; SEG

#### Scenario: Sin Operation-Id

- **WHEN** se importa sin encabezado `Operation-Id`
- **THEN** se rechaza con 400 `OPERATION_ID_REQUERIDO` (igual que el resto de las escrituras) y no se escribe nada
- **Regla:** TR-07; SYN-01

#### Scenario: Modo offline rechazado

- **GIVEN** un `IMPORTACION_REGISTRAR` dentro de un lote de sincronización en modo `OFFLINE`
- **WHEN** el bus lo procesa
- **THEN** se rechaza porque el tipo solo admite `ONLINE`
- **Regla:** `02` §6.5

### Requirement: Todo o nada con informe completo

Una importación DEBE registrarse completa o no registrarse (INV-01), según `design.md` D1 (recomendado: todo o nada). El sistema DEBE validar y ejecutar todas las filas y, si al menos una falla, NO DEBE dejar ningún efecto (ni entidades, ni movimientos, ni fila de `importacion`) y DEBE responder 422 `IMPORTACION_CON_ERRORES` con la lista completa de errores, cada uno con `fila`, `columna` (si aplica), `codigo` y `mensaje`; no solo el primero.

#### Scenario: Una fila mala impide toda la importación

- **GIVEN** una planilla de clientes con 300 filas, de las cuales la 45 y la 210 tienen documento inválido
- **WHEN** se importa
- **THEN** responde 422 `IMPORTACION_CON_ERRORES` con dos errores (filas 45 y 210, `DOCUMENTO_INVALIDO`) y no existe ninguno de los 298 clientes restantes
- **Regla:** INV-01

#### Scenario: Falla inyectada a mitad de archivo

- **GIVEN** una importación de stock inicial de 10 filas válidas
- **WHEN** se inyecta una falla después de escribir el movimiento de la quinta fila
- **THEN** no queda ningún movimiento, saldo, historia de costo ni fila de `importacion` de esa importación
- **Regla:** INV-01; `02` §15

#### Scenario: Corregir y reenviar

- **GIVEN** una importación rechazada con errores
- **WHEN** el usuario corrige las filas y la reenvía con un `Operation-Id` nuevo
- **THEN** se importan todas las filas sin duplicar nada de la primera tentativa
- **Regla:** INV-01; SYN-02

### Requirement: Idempotencia

Reenviar el mismo comando de importación DEBE ser idempotente (INV-06, SYN-02): mismo `operation_id` y mismo contenido devuelve el resultado original sin duplicar efectos; mismo `operation_id` con contenido distinto DEBE rechazarse con `COMANDO_INCONSISTENTE`.

#### Scenario: Doble envío

- **GIVEN** una importación de saldos iniciales ya aceptada
- **WHEN** se reenvía el mismo archivo con el mismo `Operation-Id`
- **THEN** se devuelve el resultado original y los saldos no cambian
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo Operation-Id con otro archivo

- **GIVEN** una importación ya aceptada
- **WHEN** se envía otro archivo con el mismo `Operation-Id`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** SYN-02

### Requirement: Aislamiento por organización

La importación DEBE escribir solo en la organización del token y resolver toda referencia dentro de ella (INV-02, INV-21). La organización NO DEBE poder indicarse en el archivo ni en el cuerpo.

#### Scenario: Una columna de organización no se admite

- **GIVEN** una planilla con una columna `organizacion_id`
- **WHEN** se importa
- **THEN** se rechaza con `COLUMNAS_INVALIDAS`
- **Regla:** INV-21; TR-08

### Requirement: Historial de importaciones

El sistema DEBE listar las importaciones registradas de la organización, de la más reciente a la más antigua, con tipo, archivo, filas, usuario y momento, paginadas por cursor (límite por defecto 50, máximo 200), con `IMPORTAR_DATOS`. Una importación de otra organización NO DEBE aparecer.

#### Scenario: Ver el historial

- **GIVEN** dos importaciones aceptadas en la organización y una en otra
- **WHEN** un Administrador lista las importaciones
- **THEN** ve solo las dos de su organización, la más reciente primero
- **Regla:** INV-21; `02` §11

#### Scenario: Historial sin permiso

- **GIVEN** un usuario sin `IMPORTAR_DATOS`
- **WHEN** pide el historial
- **THEN** recibe 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19
