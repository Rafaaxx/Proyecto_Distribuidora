## ADDED Requirements

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
