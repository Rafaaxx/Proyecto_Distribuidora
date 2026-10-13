## ADDED Requirements

### Requirement: Un movimiento referencia una jornada existente de su organización

Un movimiento de stock DEBE poder quedar registrado con la jornada que lo generó, y esa jornada DEBE existir y pertenecer a la misma organización que el movimiento: la base DEBE garantizarlo con una referencia compuesta por organización (INV-02; ADR-039 punto 7; `design.md` D11). Un movimiento sin jornada sigue siendo válido. Agregar la referencia NO DEBE modificar ni borrar ningún movimiento existente (INV-05).

#### Scenario: Movimiento con una jornada inexistente

- **GIVEN** el libro de stock
- **WHEN** se intenta insertar un movimiento con un identificador de jornada que no existe
- **THEN** la base lo rechaza
- **Regla:** INV-02; ADR-039 punto 7

#### Scenario: Movimiento con una jornada de otra organización

- **GIVEN** una jornada de la organización B
- **WHEN** se intenta insertar un movimiento de la organización A con esa jornada
- **THEN** la base lo rechaza
- **Regla:** INV-02; INV-21

#### Scenario: Movimiento sin jornada

- **GIVEN** un stock inicial registrado sobre "Depósito central"
- **WHEN** se consulta su movimiento
- **THEN** está registrado sin jornada
- **Regla:** STK-03

#### Scenario: Los movimientos anteriores se conservan al agregar la referencia

- **GIVEN** una base con movimientos de stock inicial, compras, transferencias y ajustes, todos sin jornada
- **WHEN** se aplica la migración de este change
- **THEN** todos los movimientos siguen existiendo con los mismos valores
- **AND** el saldo de cada producto y ubicación sigue siendo la suma de sus movimientos
- **Regla:** INV-05; INV-12
