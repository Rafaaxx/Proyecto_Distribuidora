# Kardex — Especificación

## Purpose

Consultar el kardex de un producto en una ubicación: sus movimientos en orden de `occurred_at` con el saldo acumulado calculado en la base al consultar, y el stock por ubicación, sin exponer costos a quien no tiene `VER_COSTOS` (STK-04, `02` §11, `01` §19).

## Requirements

### Requirement: Kardex con saldo acumulado

El sistema DEBE devolver, para un producto y una ubicación obligatorios, los movimientos en orden ascendente `(occurred_at, id)` con el saldo acumulado calculado en SQL sobre toda la historia, el `saldo_anterior` a `desde` y el saldo actual; con filtro opcional `desde`/`hasta` en fechas de negocio de la zona de la organización (`hasta` inclusivo) y paginación por cursor opaco con límite 50 por defecto y máximo 200 (`design.md` D11, TR-04). La lectura DEBE exigir el permiso de `design.md` D3.

#### Scenario: Kardex de una ubicación

- **GIVEN** stock inicial de 60 y luego −12 unidades de Vino A en el depósito
- **WHEN** se consulta el kardex del depósito
- **THEN** aparecen los dos movimientos con acumulados 60 y 48 y el saldo actual 48
- **Regla:** STK-04

#### Scenario: Filtro de período con saldo anterior

- **GIVEN** movimientos en dos días distintos
- **WHEN** se consulta con `desde` igual al segundo día
- **THEN** `saldo_anterior` es la suma de lo anterior y los acumulados parten de ese valor
- **Regla:** STK-04; TR-04

#### Scenario: Movimiento con `occurred_at` anterior

- **GIVEN** un kardex ya consultado
- **WHEN** se registra un movimiento con `occurred_at` anterior al último
- **THEN** la siguiente consulta lo ubica en su lugar y recalcula los acumulados posteriores
- **Regla:** STK-04

#### Scenario: Rango, límite o cursor inválidos

- **GIVEN** un usuario con permiso
- **WHEN** consulta con `desde` posterior a `hasta`, límite fuera de 1 a 200 o un cursor ilegible
- **THEN** la respuesta es `RANGO_DE_FECHAS_INVALIDO`, 422 o `CURSOR_INVALIDO` respectivamente
- **Regla:** `02` §11; `design.md` D11

### Requirement: Stock por ubicación

El sistema DEBE devolver el stock de una ubicación por producto, en unidad base entera, con la presentación de referencia necesaria para mostrarlo en cajas + unidades (CAT-08), paginado por cursor y con el permiso de `design.md` D3.

#### Scenario: Stock del depósito

- **GIVEN** 31 unidades de Vino A (caja x6) en el depósito
- **WHEN** se consulta el stock del depósito
- **THEN** la respuesta trae 31 unidades base y 6 unidades de referencia, que la pantalla muestra como 5 cajas + 1 unidad
- **Regla:** STK-01; CAT-08

### Requirement: Los costos solo se exponen con `VER_COSTOS`

Los campos de costo del kardex (`costo_unitario`) y del stock (promedio) DEBEN omitirse para un usuario sin `VER_COSTOS` (`01` §19, `design.md` D3).

#### Scenario: Vendedor consulta el kardex

- **GIVEN** un usuario Vendedor con el permiso de lectura de D3 y sin `VER_COSTOS`
- **WHEN** consulta el kardex
- **THEN** recibe cantidades y acumulados, sin ningún campo de costo
- **Regla:** `01` §19

#### Scenario: Administrador consulta el kardex

- **GIVEN** un Administrador
- **WHEN** consulta el kardex
- **THEN** cada movimiento trae su `costo_unitario` como string
- **Regla:** `01` §19; `02` §10.2

### Requirement: Kardex y stock son de su organización

Un producto o una ubicación de otra organización o inexistentes DEBEN responder 404 sin revelar movimientos (INV-21, SEG-07).

#### Scenario: Ubicación ajena

- **GIVEN** una ubicación de la organización B
- **WHEN** un usuario de A consulta su stock o su kardex
- **THEN** la respuesta es 404
- **Regla:** INV-21

#### Scenario: Sin permiso

- **GIVEN** un usuario sin el permiso de D3
- **WHEN** consulta el kardex
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** SEG-06

### Requirement: El kardex muestra el motivo, la operación y su estado en cada movimiento

Cada movimiento del kardex DEBE traer `origen_tipo` y `origen_id` (la transferencia o el ajuste que lo originó) y, si es de tipo `AJUSTE`, el nombre de su motivo (`design.md` D7). Un movimiento con origen `TRANSFERENCIA` o `AJUSTE_STOCK` DEBE traer además el estado de esa operación (`CONFIRMADA` o `ANULADA`), y los movimientos inversos de una anulación DEBEN distinguirse por su origen `ANULACION_TRANSFERENCIA` o `ANULACION_AJUSTE_STOCK`, con el mismo `origen_id` que los originales (`design.md` D5, D5.1). Esos datos NO DEBEN exponer costos ni datos de otra organización, y la lectura sigue exigiendo `TRANSFERIR_STOCK` (ADR-036).

#### Scenario: Ajuste en el kardex

- **GIVEN** un ajuste de −6 de Vino A en el depósito por "Rotura"
- **WHEN** un Vendedor consulta el kardex de Vino A en el depósito
- **THEN** el movimiento aparece como `AJUSTE` −6 con el motivo "Rotura", `origen_tipo` `AJUSTE_STOCK`, el id del ajuste y estado `CONFIRMADA`, sin costo
- **Regla:** STK-08; `01` §19

#### Scenario: Transferencia en el kardex de las dos ubicaciones

- **GIVEN** una transferencia de 48 de Vino A del depósito a "Camioneta 1"
- **WHEN** se consulta el kardex de Vino A en cada ubicación
- **THEN** el depósito muestra `TRANSFERENCIA_SALIDA` −48 y la camioneta `TRANSFERENCIA_ENTRADA` +48, ambos con `origen_tipo` `TRANSFERENCIA` y el mismo `origen_id`, sin motivo
- **Regla:** STK-07; STK-04

#### Scenario: Transferencia anulada en el kardex

- **GIVEN** una transferencia de 60 de Vino A del depósito a "Camioneta 1", anulada
- **WHEN** se consulta el kardex de Vino A en "Camioneta 1"
- **THEN** aparecen `TRANSFERENCIA_ENTRADA` +60 con origen `TRANSFERENCIA` y estado `ANULADA`, y `TRANSFERENCIA_SALIDA` −60 con origen `ANULACION_TRANSFERENCIA`, ambos con el mismo `origen_id`, y el saldo acumulado vuelve al anterior
- **Regla:** STK-04; TR-06; `design.md` D5.1

#### Scenario: Ajuste anulado en el kardex

- **GIVEN** el ajuste de −6 por "Rotura" anulado con "Error de carga"
- **WHEN** se consulta el kardex de Vino A en el depósito
- **THEN** aparecen el `AJUSTE` −6 con el motivo "Rotura" y estado `ANULADA`, y un `AJUSTE` +6 con origen `ANULACION_AJUSTE_STOCK` y el motivo "Error de carga"
- **Regla:** STK-08; TR-06; `design.md` D5.1
