## RENAMED Requirements

- FROM: `### Requirement: Un egreso no deja stock negativo en este change`
- TO: `### Requirement: Un egreso deja stock negativo solo con permiso`

## MODIFIED Requirements

### Requirement: Un egreso deja stock negativo solo con permiso

Un egreso de stock DEBE aplicarse con la condición de saldo suficiente de `02` §7.4 y, si no alcanza, DEBE rechazarse con `STOCK_INSUFICIENTE` sin cambios. La única excepción en la etapa actual es el egreso de una anulación de compra (CMP-07): si quien la registra tiene `PERMITIR_STOCK_NEGATIVO`, el egreso DEBE aplicarse sin condición y el resultado DEBE informar qué saldos quedaron negativos para que la operación quede con la observación `STOCK_NEGATIVO` (STK-05, `design.md` D10 del change 11). Las correcciones de stock inicial siguen sin excepción (STK-10).

#### Scenario: Egreso mayor que el saldo
- **GIVEN** 10 unidades de Vino A en el depósito
- **WHEN** se registra un egreso de 11
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 10
- **Regla:** STK-05; `02` §7.4

#### Scenario: Egreso de anulación de compra con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `ANULACION_COMPRA` de 60 con permiso de stock negativo
- **THEN** el saldo queda en −12, el stock total baja 60 y el resultado informa el saldo negativo
- **Regla:** CMP-07; STK-05

#### Scenario: Egreso de anulación de compra sin permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `ANULACION_COMPRA` de 60 sin permiso de stock negativo
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 48
- **Regla:** CMP-07; STK-05

## ADDED Requirements

### Requirement: El egreso de una anulación de compra revierte su ingreso

Un movimiento `ANULACION_COMPRA` DEBE ser un egreso que lleva el costo base de la línea de compra que revierte; DEBE quedar en el libro con ese costo y DEBE delegar en `costeo` la reversión del promedio (CMP-06), en lugar de valorizarse al promedio vigente. Un egreso `ANULACION_COMPRA` sin costo DEBE rechazarse con `COSTO_INVALIDO` (`design.md` D9 del change 11).

#### Scenario: Costo del egreso en el kardex
- **GIVEN** una compra de 60 unidades de Vino A a costo base `"1100.000000"`
- **WHEN** se anula
- **THEN** el kardex muestra un movimiento `ANULACION_COMPRA` de −60 con costo `"1100.000000"`
- **Regla:** CMP-06; STK-03; CST-13

### Requirement: Una reversión de compra admite un producto inactivo

Un movimiento `ANULACION_COMPRA` DEBE registrarse aunque el producto esté inactivo, porque revierte una operación existente (CAT-05, `design.md` D11 del change 11). Los demás tipos siguen rechazando un producto inactivo (`PRODUCTO_INACTIVO`). Una ubicación inactiva sigue rechazando todo movimiento (`UBICACION_INACTIVA`).

#### Scenario: Reversión con producto inactivo
- **GIVEN** Vino A inactivo con 60 unidades en el depósito
- **WHEN** se registra un egreso `ANULACION_COMPRA` de 60
- **THEN** se acepta y el saldo queda en 0
- **Regla:** CAT-05; `design.md` D11

#### Scenario: Otro tipo con producto inactivo
- **GIVEN** Vino A inactivo
- **WHEN** se registra un ingreso `COMPRA`
- **THEN** se rechaza con `PRODUCTO_INACTIVO`
- **Regla:** CAT-05
