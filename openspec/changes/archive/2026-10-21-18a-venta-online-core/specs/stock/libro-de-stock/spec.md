## ADDED Requirements

### Requirement: El egreso de una venta deja stock negativo solo con permiso o sin conexión

Un egreso `VENTA` (origen `VENTA`, la venta como operación) DEBE valorizarse al promedio vigente y devolver ese costo (nulo si el producto no tiene promedio). Con conexión DEBE exigir saldo suficiente en la ubicación salvo `PERMITIR_STOCK_NEGATIVO`, con el que puede dejarlo negativo y lo marca; sin conexión DEBE aplicarse sin condición y marcar el saldo negativo (STK-05, STK-06, `design.md` D11 del change 18a). El permiso sigue sin alcanzar a ajustes ni a correcciones de stock inicial.

#### Scenario: Venta con saldo suficiente
- **GIVEN** Vino A con 48 botellas en el depósito y promedio `"1050.000000"`
- **WHEN** se registra un egreso `VENTA` de 15
- **THEN** el saldo queda en 33, el stock total baja 15, el movimiento guarda costo `"1050.000000"` y el promedio no cambia
- **Regla:** STK-03; CST-12; INV-12

#### Scenario: Negativo sin permiso
- **WHEN** se registra un egreso `VENTA` de 50 con conexión sin el permiso
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y no escribe nada
- **Regla:** STK-05

#### Scenario: Negativo con permiso
- **WHEN** se registra con el permiso
- **THEN** el saldo queda en −2 y el resultado lo marca como negativo
- **Regla:** STK-05

#### Scenario: Negativo sin conexión
- **WHEN** se registra en modo sin condición
- **THEN** el saldo queda en −2 y el resultado lo marca como negativo
- **Regla:** STK-06

#### Scenario: El permiso no alcanza a un ajuste
- **WHEN** un ajuste negativo que deja −2 se registra con el permiso
- **THEN** se rechaza con `STOCK_INSUFICIENTE` como antes
- **Regla:** STK-05; ADR-048
