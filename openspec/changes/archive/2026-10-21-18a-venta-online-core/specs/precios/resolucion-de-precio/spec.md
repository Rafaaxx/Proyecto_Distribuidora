## ADDED Requirements

### Requirement: Los precios de una versión elegida se resuelven sin bloquear

`precios` DEBE entregar, solo en lectura, los precios de una versión elegida (con sus unidades de referencia, los productos sin precio aparte) y las versiones elegibles de una lista a un momento: las `PUBLICADA` no anuladas cuya vigencia desde no sea posterior al momento. Una versión de otra organización responde como inexistente (INV-21). Las versiones programadas o anuladas NO DEBEN figurar como elegibles (PRC-21, `design.md` D6 del change 18a).

#### Scenario: Versiones elegibles
- **GIVEN** la lista "General" con las versiones 2 y 3 históricas, la 4 vigente, la 5 programada y una anulada
- **WHEN** se piden las versiones elegibles hoy
- **THEN** se devuelven la 4 (vigente) y la 3 y la 2 (históricas), de la más nueva a la más vieja
- **Regla:** PRC-21; PRC-02; PRC-05

#### Scenario: Precios de la versión 3
- **WHEN** se piden los precios de Vino A y Cerveza B en la versión 3, que no tiene a Cerveza B
- **THEN** se devuelve Vino A a `"8600.00"` con unidades de referencia 6 y Cerveza B entre los productos sin precio
- **Regla:** PRC-10; PRC-21

#### Scenario: Versión ajena
- **WHEN** se piden los precios de una versión de otra organización
- **THEN** responde como inexistente
- **Regla:** INV-21
