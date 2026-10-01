# Ubicaciones — Especificación

## Purpose

Definir las ubicaciones de stock de una organización (depósitos, vehículos y otras), con su tipo, su indicador de toma y su estado, como maestro que el libro de stock, las jornadas y las transferencias referencian (STK-01, STK-02).

## Requirements

### Requirement: Una ubicación tiene nombre, tipo, indicador de toma y estado

El sistema DEBE registrar cada ubicación en la organización del token con `nombre`, `tipo` (`DEPOSITO`, `VEHICULO` u `OTRO`), `requiere_toma` y `activo` (STK-02, `03` §9), más `actualizado_en` y `actualizado_por_id` como todo maestro (`03` §2.3, `design.md` D7). El alta (`UBICACION_CREAR`) y la modificación (`UBICACION_MODIFICAR`) DEBEN ser comandos solo `ONLINE` del bus, idempotentes por `operation_id` (SYN-02), auditados (AUD-01) y exigir el permiso de `design.md` D2. Una ubicación nace activa.

#### Scenario: Alta de un depósito

- **GIVEN** un usuario con el permiso de D2 en la organización A
- **WHEN** envía `UBICACION_CREAR` con nombre `Depósito central`, tipo `DEPOSITO` y `requiere_toma = false`
- **THEN** existe la ubicación activa en la organización A y hay un registro de auditoría con el `operation_id`
- **Regla:** STK-02; AUD-01

#### Scenario: Doble envío del mismo alta

- **GIVEN** un `UBICACION_CREAR` ya aceptado
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y sigue existiendo una sola ubicación
- **Regla:** SYN-02; INV-06

#### Scenario: Mismo `operation_id` con otro contenido

- **GIVEN** un `UBICACION_CREAR` ya aceptado
- **WHEN** se reenvía con el mismo `operation_id` y otro nombre
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y no se crea nada
- **Regla:** SYN-02

#### Scenario: Sin permiso

- **GIVEN** un usuario sin el permiso de D2
- **WHEN** envía `UBICACION_CREAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se crea nada
- **Regla:** SEG-06

#### Scenario: Modo OFFLINE rechazado

- **GIVEN** un lote de sincronización
- **WHEN** incluye un `UBICACION_CREAR` en modo `OFFLINE`
- **THEN** el comando queda `RECHAZADO` con `MODO_NO_ADMITIDO_PARA_TIPO` sin efectos
- **Regla:** `02` §6.5

### Requirement: Un vehículo siempre requiere toma

Una ubicación de tipo `VEHICULO` DEBE tener `requiere_toma = true`; el comando que lo contradiga DEBE rechazarse con `VEHICULO_REQUIERE_TOMA` y la base DEBE impedirlo con una restricción de verificación (STK-02, `design.md` D7).

#### Scenario: Vehículo sin toma

- **GIVEN** un usuario con el permiso de D2
- **WHEN** envía `UBICACION_CREAR` con tipo `VEHICULO` y `requiere_toma = false`
- **THEN** se rechaza con `VEHICULO_REQUIERE_TOMA` y no se crea nada
- **Regla:** STK-02

#### Scenario: La base impide un vehículo sin toma

- **GIVEN** la base migrada
- **WHEN** se inserta directamente una ubicación `VEHICULO` con `requiere_toma = false`
- **THEN** la restricción `ck_ubicacion__vehiculo_requiere_toma` la rechaza
- **Regla:** STK-02; `design.md` D7

### Requirement: El nombre de la ubicación es único en la organización

El nombre, normalizado, NO DEBE repetirse entre ubicaciones de la misma organización, activas o no (`design.md` D7); una repetición se rechaza con `NOMBRE_DUPLICADO`. Organizaciones distintas pueden usar el mismo nombre.

#### Scenario: Nombre repetido

- **GIVEN** la ubicación `Depósito central` en la organización A
- **WHEN** se crea otra con nombre ` depósito central `
- **THEN** se rechaza con `NOMBRE_DUPLICADO`
- **Regla:** `design.md` D7

#### Scenario: Mismo nombre en otra organización

- **GIVEN** la ubicación `Depósito central` en la organización A
- **WHEN** la organización B crea `Depósito central`
- **THEN** se acepta
- **Regla:** TR-08

### Requirement: Una ubicación con stock no se desactiva

Una ubicación con algún saldo de stock distinto de cero NO DEBE desactivarse (`UBICACION_CON_STOCK`, `design.md` D8). Una ubicación inactiva DEBE poder reactivarse. Sobre una ubicación inactiva NO DEBEN registrarse movimientos nuevos (`UBICACION_INACTIVA`).

#### Scenario: Desactivar con stock

- **GIVEN** el depósito con 60 unidades de un producto
- **WHEN** se envía `UBICACION_MODIFICAR` con `activo = false`
- **THEN** se rechaza con `UBICACION_CON_STOCK` y la ubicación sigue activa
- **Regla:** `design.md` D8

#### Scenario: Desactivar sin stock y reactivar

- **GIVEN** una ubicación sin saldos distintos de cero
- **WHEN** se desactiva y luego se reactiva
- **THEN** ambas modificaciones se aceptan y quedan auditadas
- **Regla:** STK-02; AUD-01

### Requirement: Las ubicaciones son de su organización

Toda lectura y escritura de ubicaciones DEBE filtrar por la organización del token; una ubicación de otra organización o inexistente DEBE responder 404 (SEG-07, INV-21).

#### Scenario: Modificar una ubicación ajena

- **GIVEN** una ubicación de la organización B
- **WHEN** un usuario de la organización A envía `UBICACION_MODIFICAR` sobre ella
- **THEN** la respuesta es 404 y la ubicación no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Listar ubicaciones

- **GIVEN** ubicaciones en las organizaciones A y B
- **WHEN** un usuario de A con el permiso de lectura de D3 lista ubicaciones
- **THEN** recibe solo las de A, paginadas por cursor
- **Regla:** TR-08; `02` §11
