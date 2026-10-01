# Costo promedio — Especificación

## Purpose

Mantener el costo promedio ponderado móvil de cada producto en la organización, recalculado por cada ingreso con costo y con su historia reconstruible, como único lugar del sistema que calcula costos (CST-10, CST-11, CST-13, CST-14; ADR-002).

## Requirements

### Requirement: Un costo promedio por producto y organización

El sistema DEBE mantener en `costo_producto` (clave `(organizacion_id, producto_id)`) un único `costo_promedio` en `numeric(18,6)` y el `stock_total` del producto sumando todas sus ubicaciones (CST-10, `02` §7.2). Mientras el producto no tuvo ningún ingreso con costo, el promedio DEBE ser nulo ("sin costo"), nunca cero (`design.md` D10).

#### Scenario: Producto sin ingresos

- **GIVEN** el producto Vino A sin movimientos
- **WHEN** se consulta su costo
- **THEN** el promedio es nulo y el stock total es 0
- **Regla:** CST-10; `design.md` D10

#### Scenario: Un solo promedio para todas las ubicaciones

- **GIVEN** un ingreso de 60 unidades de Vino A a `"1000.000000"` en el depósito
- **WHEN** ingresan 60 unidades a `"1100.000000"` en un vehículo
- **THEN** el promedio del producto es `"1050.000000"` y el stock total es 120
- **Regla:** CST-10; CST-11

### Requirement: Un ingreso con costo recalcula el promedio

Un ingreso con costo DEBE recalcular el promedio así: si el stock total previo es mayor que cero, `(stock × promedio + cantidad × costo) / (stock + cantidad)`; si es cero o negativo, el promedio pasa a ser el costo del ingreso (CST-11). El cálculo DEBE hacerse con decimal exacto sin redondeos intermedios y redondearse a 6 decimales con mitad hacia arriba una sola vez al final (TR-02, TR-03). Los casos DEBEN existir primero en `shared/fixtures/calculo/cst-11-costo-promedio.json` y pasar en las suites de Python y TypeScript (`design.md` D14).

#### Scenario: Ejemplo de `01` §6.2

- **GIVEN** stock total 48 con promedio `"1050.000000"`
- **WHEN** ingresan 60 unidades a `"1200.000000"`
- **THEN** el promedio es `"1133.333333"` y el stock total 108
- **Regla:** CST-11

#### Scenario: Stock previo cero

- **GIVEN** stock total 0 con promedio `"1050.000000"`
- **WHEN** ingresan 60 unidades a `"1200.000000"`
- **THEN** el promedio es `"1200.000000"`
- **Regla:** CST-11

#### Scenario: Stock previo negativo

- **GIVEN** stock total −5 con promedio `"1050.000000"`
- **WHEN** ingresan 60 unidades a `"1200.000000"`
- **THEN** el promedio es `"1200.000000"` y el stock total 55
- **Regla:** CST-11

#### Scenario: Casos compartidos en ambas suites

- **GIVEN** los casos de `cst-11-costo-promedio.json`
- **WHEN** corren pytest y Vitest
- **THEN** cada caso es una prueba con su `id` en las dos suites y ambas pasan
- **Regla:** CST-11; `02` §10.4

### Requirement: Un egreso no modifica el promedio

Un egreso de stock DEBE reducir `stock_total` sin cambiar el promedio y DEBE valorizarse al promedio vigente (CST-12, `design.md` D4).

#### Scenario: Egreso al promedio vigente

- **GIVEN** stock total 120 con promedio `"1050.000000"`
- **WHEN** egresan 72 unidades
- **THEN** el promedio sigue en `"1050.000000"`, el stock total es 48 y el movimiento se valoriza a `"1050.000000"` por unidad
- **Regla:** CST-12; `01` §6.2

### Requirement: La historia del promedio es reconstruible

Cada ingreso que recalcula el promedio DEBE dejar una fila de solo inserción en `costo_producto_mov` con `origen_tipo`, `origen_id`, `cantidad`, `costo_ingreso`, `stock_anterior`, `promedio_anterior`, `stock_nuevo`, `promedio_nuevo`, `recalculado`, `operation_id` y `registered_at`, de modo que el promedio en cualquier momento pueda reconstruirse (CST-13, `03` §7). `app_runtime` DEBE tener solo `SELECT` e `INSERT` sobre la tabla (INV-05).

#### Scenario: Historia de un stock inicial

- **GIVEN** stock total 60 con promedio `"1000.000000"`
- **WHEN** ingresan 60 unidades a `"1100.000000"` por stock inicial
- **THEN** hay una fila con origen `STOCK_INICIAL`, stock 60 → 120, promedio `"1000.000000"` → `"1050.000000"` y `recalculado = true`
- **Regla:** CST-13

#### Scenario: La historia no se edita

- **GIVEN** una conexión como `app_runtime`
- **WHEN** intenta `UPDATE` o `DELETE` sobre `costo_producto_mov`
- **THEN** PostgreSQL lo rechaza
- **Regla:** INV-05; CST-13

### Requirement: Solo el servicio de costeo calcula costos

El recálculo del promedio y la valorización de egresos DEBEN vivir en el módulo `costeo`; ningún otro módulo DEBE calcularlos ni escribir `costo_producto` o `costo_producto_mov` (CST-14, ADR-002, `02` §5.3).

#### Scenario: Límites de módulo

- **GIVEN** los contratos de import-linter
- **WHEN** se ejecuta `lint-imports`
- **THEN** `costeo` no importa módulos de negocio y los demás lo usan solo por su `service.py`
- **Regla:** CST-14; `02` §5.3

### Requirement: El promedio solo lo ve quien tiene `VER_COSTOS`

La lectura del promedio vigente de un producto DEBE exponerse en `GET /api/v1/catalogo/productos/{producto_id}/costo` (ruta de `catalogo`, que resuelve el producto en la organización del token y luego consulta a `costeo/service.py`) y DEBE exigir `VER_COSTOS`; un producto ajeno o inexistente DEBE responder 404 (`01` §19, `design.md` D3 y su enmienda del 2026-09-30).

#### Scenario: Vendedor sin `VER_COSTOS`

- **GIVEN** un usuario Vendedor
- **WHEN** pide el costo promedio de un producto
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19

#### Scenario: Producto ajeno

- **GIVEN** un producto de la organización B
- **WHEN** un Administrador de A pide su costo promedio
- **THEN** la respuesta es 404, sin revelar nada del producto
- **Regla:** INV-21

#### Scenario: Producto inexistente

- **GIVEN** un identificador de producto que no existe
- **WHEN** un Administrador pide su costo promedio
- **THEN** la respuesta es 404
- **Regla:** INV-21

#### Scenario: Producto sin ingresos

- **GIVEN** un producto de la organización sin ningún ingreso con costo
- **WHEN** un Administrador pide su costo promedio
- **THEN** la respuesta es 200 con `costo_promedio` nulo y `stock_total` 0
- **Regla:** `design.md` D10
