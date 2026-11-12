## ADDED Requirements

### Requirement: La anulación de una venta recalcula el promedio con el costo congelado

El reingreso de una anulación de venta DEBE recalcular el promedio con el costo unitario congelado de la línea (6 decimales), con la fórmula de CST-11 y una fila de historia de origen `ANULACION_VENTA`. Una línea sin costo NO DEBE recalcular ni dejar historia. Los casos DEBEN estar en los fixtures compartidos de CST-11 antes del código (`design.md` D5, D17).

#### Scenario: Ejemplo de CST-11
- **GIVEN** stock total 108 con promedio $1.133,333333
- **WHEN** se anula la venta de 72 a $1.050,000000
- **THEN** el promedio pasa a $1.100,000000 y la historia guarda promedio anterior $1.133,333333, nuevo $1.100,000000, stock anterior 108, nuevo 180 y `recalculado` verdadero
- **Regla:** CST-11; CST-13; VTA-21

#### Scenario: Stock total previo negativo
- **GIVEN** stock total −5 con promedio $1.000,000000
- **WHEN** se anula una venta de 72 a $1.050,000000
- **THEN** el promedio pasa a $1.050,000000
- **Regla:** CST-11

#### Scenario: Línea sin costo
- **WHEN** se anula una línea vendida sin costo
- **THEN** el promedio no cambia y no hay fila de historia
- **Regla:** CST-12; ADR-058

#### Scenario: Casos compartidos
- **WHEN** corren pytest y Vitest sobre `cst-11-costo-promedio.json`
- **THEN** los casos de anulación de venta dan el mismo promedio en los dos lenguajes
- **Regla:** ADR-016; CST-14
