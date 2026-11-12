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

### Requirement: La anulación de una compra revierte el promedio o lo mantiene

`costeo` DEBE ofrecer la reversión de un ingreso de compra: con la fila de costo bloqueada, `stock restante = stock total − cantidad` y, si es mayor que cero, `promedio resultante = (stock total × promedio − cantidad × costo de la línea) / stock restante`, con decimal exacto y un único redondeo a 6 decimales con mitad hacia arriba. Si el stock restante es mayor que cero y el promedio resultante es positivo, el promedio DEBE pasar al resultante (`recalculado = true`); en otro caso DEBE mantenerse el vigente (`recalculado = false`). En ambos casos `stock_total` DEBE bajar en la cantidad (CMP-06, CST-14). Los casos DEBEN existir primero en `shared/fixtures/calculo/cst-11-costo-promedio.json` como operación de reversión y pasar en Python y TypeScript (`design.md` D9, D15 del change 11).

#### Scenario: Reversión que recalcula
- **GIVEN** stock total 120 con promedio `"1050.000000"`
- **WHEN** se revierte un ingreso de 60 a `"1100.000000"`
- **THEN** el promedio es `"1000.000000"`, el stock total 60 y `recalculado = true`
- **Regla:** CMP-06; `01` §6.2

#### Scenario: Stock restante no positivo
- **GIVEN** stock total 48 con promedio `"1050.000000"`
- **WHEN** se revierte un ingreso de 60 a `"1100.000000"`
- **THEN** el promedio se mantiene en `"1050.000000"`, el stock total es −12 y `recalculado = false`
- **Regla:** CMP-06

#### Scenario: Promedio resultante no positivo
- **GIVEN** stock total 65 con promedio `"1728.571429"`
- **WHEN** se revierte un ingreso de 60 a `"2000.000000"`
- **THEN** el promedio se mantiene en `"1728.571429"`, el stock total es 5 y `recalculado = false`
- **Regla:** CMP-06

### Requirement: Toda reversión de compra deja historia

Cada reversión DEBE insertar una fila en `costo_producto_mov` con origen `ANULACION_COMPRA`, `origen_id` de la compra, `cantidad` negativa, `costo_ingreso` igual al costo de la línea revertida, stock y promedio anteriores y nuevos y `recalculado`; cuando no se recalcula, `promedio_nuevo` DEBE ser igual a `promedio_anterior` (CST-13, deuda nominada por el change 09, `design.md` D9 del change 11).

#### Scenario: Historia sin recálculo
- **GIVEN** stock total 48 con promedio `"1050.000000"`
- **WHEN** se anula una compra de 60 a `"1100.000000"`
- **THEN** hay una fila `ANULACION_COMPRA` con cantidad −60, costo `"1100.000000"`, stock 48 → −12, promedio `"1050.000000"` → `"1050.000000"` y `recalculado = false`
- **Regla:** CST-13; CMP-06

#### Scenario: El promedio se reconstruye con la historia
- **GIVEN** compras, anulaciones con y sin recálculo y stock inicial de un producto
- **WHEN** se recorre su historia en orden de registro
- **THEN** cada `promedio_anterior` es el `promedio_nuevo` de la fila anterior y el último coincide con `costo_producto`
- **Regla:** CST-13

### Requirement: Un ingreso sin costo no modifica el promedio

El servicio de costeo DEBE ofrecer un ingreso sin costo para las entradas de transferencia, los ajustes positivos y los ingresos inversos de sus anulaciones (que el servicio de stock valoriza al costo del movimiento original, no al valor devuelto; `design.md` D5.2): DEBE sumar la cantidad a `stock_total` con la fila de costo bloqueada, NO DEBE cambiar el promedio, NO DEBE escribir historia en `costo_producto_mov` y DEBE devolver el promedio vigente (nulo si el producto no tiene) para valorizar el movimiento (CST-12, CST-13, CST-14, `design.md` D3, D9). El cálculo DEBE vivir en el dominio de costeo, sin infraestructura.

#### Scenario: Ingreso sin costo con promedio

- **GIVEN** Vino A con stock total 114 y promedio `"1050.000000"`
- **WHEN** ingresan 2 unidades sin costo
- **THEN** el stock total es 116, el promedio sigue en `"1050.000000"`, el valor devuelto para valorizar es `"1050.000000"` y no hay fila nueva en `costo_producto_mov`
- **Regla:** CST-12; CST-13

#### Scenario: Ingreso sin costo sobre stock total negativo

- **GIVEN** Vino A con stock total −12 y promedio `"1050.000000"`
- **WHEN** ingresan 12 unidades sin costo
- **THEN** el stock total es 0 y el promedio sigue en `"1050.000000"`; la próxima compra fija el promedio en su costo porque el stock total previo no es mayor que cero
- **Regla:** CST-11; CST-12

#### Scenario: Una transferencia deja el stock total igual

- **GIVEN** Vino A con stock total 120
- **WHEN** egresan 48 y ingresan 48 sin costo en la misma transacción
- **THEN** el stock total sigue en 120 y el promedio no cambia
- **Regla:** INV-15; CST-12
