## ADDED Requirements

### Requirement: El bootstrap informa la secuencia procesada de la jornada

El bootstrap DEBE incluir en la sesión la secuencia procesada: la mayor secuencia de los comandos de la jornada del bootstrap, del usuario y del dispositivo de la sesión, que el servidor tiene registrados en la misma foto que el stock y los saldos, o nulo si no tiene ninguno. NO DEBE considerar comandos de otro dispositivo, de otro usuario, de otra jornada ni de otra organización (`design.md` D1).

#### Scenario: Ventas ya procesadas
- **GIVEN** la jornada abierta de `vendedor` con comandos registrados de secuencias 5, 6 y 7
- **WHEN** pide el bootstrap
- **THEN** la secuencia procesada es 7 y el stock y los saldos ya incluyen esas ventas
- **Regla:** SYN-11; CRE-08; RUT-04

#### Scenario: Jornada sin comandos
- **GIVEN** una jornada recién abierta sin comandos
- **WHEN** se pide el bootstrap
- **THEN** la secuencia procesada es nula
- **Regla:** SYN-11

#### Scenario: Lote cortado por un error transitorio
- **GIVEN** un lote con las secuencias 8, 9 y 10 que se cortó en la 9 por un error transitorio
- **WHEN** se pide el bootstrap
- **THEN** la secuencia procesada es 8
- **Regla:** SYN-03; `02` §6.4

#### Scenario: Comandos de otra jornada o de otro teléfono
- **GIVEN** comandos de secuencia 20 de una jornada anterior del mismo usuario y de secuencia 30 de otro dispositivo
- **WHEN** el vendedor pide el bootstrap de su jornada actual sin comandos propios
- **THEN** la secuencia procesada es nula
- **Regla:** SYN-11; INV-21

#### Scenario: Doble envío antes del bootstrap
- **GIVEN** la venta de secuencia 7 enviada dos veces y procesada una sola vez
- **WHEN** se pide el bootstrap
- **THEN** la secuencia procesada es 7 y el stock refleja la venta una sola vez
- **Regla:** INV-06
