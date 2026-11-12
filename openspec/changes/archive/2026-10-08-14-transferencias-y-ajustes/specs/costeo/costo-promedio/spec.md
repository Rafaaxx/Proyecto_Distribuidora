## ADDED Requirements

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
