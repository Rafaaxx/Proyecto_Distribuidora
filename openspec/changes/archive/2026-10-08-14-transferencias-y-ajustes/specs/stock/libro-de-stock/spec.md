## ADDED Requirements

### Requirement: Los ingresos de transferencia y de ajuste no llevan costo

Un movimiento positivo de tipo `TRANSFERENCIA_ENTRADA` o `AJUSTE` DEBE registrarse sin costo de entrada (con costo es `COSTO_INVALIDO`), NO DEBE recalcular el promedio y DEBE guardar como `costo_unitario` el promedio vigente del producto, o nulo si no tiene (CST-12, `design.md` D3, D9). La única excepción son los movimientos inversos de una anulación (requisito siguiente). Un ingreso de tipo `DIFERENCIA_RENDICION` sigue rechazándose con `TIPO_MOVIMIENTO_INVALIDO` hasta el change 24. Los ingresos que recalculan siguen siendo `STOCK_INICIAL`, `COMPRA` y `ANULACION_VENTA` (CST-11).

#### Scenario: Entrada de transferencia valorizada al promedio

- **GIVEN** Vino A con stock total 120 y promedio `"1050.000000"`
- **WHEN** el servicio de stock registra un egreso `TRANSFERENCIA_SALIDA` de 48 en el depósito y un ingreso `TRANSFERENCIA_ENTRADA` de 48 en "Camioneta 1", sin costo
- **THEN** los dos movimientos guardan `"1050.000000"`, el stock total sigue en 120 y el promedio no cambia
- **Regla:** STK-07; CST-12; INV-15

#### Scenario: Ingreso de transferencia con costo

- **GIVEN** el servicio de stock
- **WHEN** se registra un ingreso `TRANSFERENCIA_ENTRADA` o `AJUSTE` con origen `TRANSFERENCIA` o `AJUSTE_STOCK` y costo `"1000.000000"`
- **THEN** se rechaza con `COSTO_INVALIDO` y no se escribe nada
- **Regla:** CST-12; `design.md` D9

#### Scenario: Ingreso de rendición todavía no admitido

- **GIVEN** el servicio de stock
- **WHEN** se registra un ingreso `DIFERENCIA_RENDICION`
- **THEN** se rechaza con `TIPO_MOVIMIENTO_INVALIDO`
- **Regla:** ADR-039; RUT-06

### Requirement: Los movimientos inversos de una anulación guardan el costo original

Un movimiento `TRANSFERENCIA_SALIDA`, `TRANSFERENCIA_ENTRADA` o `AJUSTE` con origen `ANULACION_TRANSFERENCIA` o `ANULACION_AJUSTE_STOCK` DEBE llevar el `costo_unitario` del movimiento que revierte (que puede ser nulo) y el servicio de stock DEBE guardarlo tal cual, sin valorizarlo al promedio vigente, sin recalcular el promedio y sin historia de costo; el stock total DEBE moverse por la cantidad (CST-12, CST-13, `design.md` D5, D5.1, D5.2). Los inversos reutilizan los tipos de STK-03: NO se agregan tipos de movimiento.

#### Scenario: Inverso de un ajuste a su costo original

- **GIVEN** Vino A con promedio vigente `"1100.000000"` y un ajuste anterior de −6 registrado a `"1050.000000"`
- **WHEN** el servicio de stock registra un ingreso `AJUSTE` de 6 con origen `ANULACION_AJUSTE_STOCK` y costo `"1050.000000"`
- **THEN** el movimiento guarda `"1050.000000"`, el stock total sube 6, el promedio sigue en `"1100.000000"` y no hay fila nueva en `costo_producto_mov`
- **Regla:** CST-12; CST-13; `design.md` D5.2

#### Scenario: Inverso de un movimiento sin costo

- **GIVEN** una transferencia de un producto sin promedio, cuyos movimientos guardaron costo nulo
- **WHEN** se registran sus inversos con origen `ANULACION_TRANSFERENCIA` y costo nulo
- **THEN** se aceptan y guardan costo nulo
- **Regla:** ADR-039; `design.md` D5.2

### Requirement: Un movimiento toma su producto en modo compartido

El servicio de stock DEBE tomar cada producto de las líneas con bloqueo compartido, por id ascendente, después de las ubicaciones y antes de `costo_producto` y `stock_saldo`, para que un movimiento y la desactivación de ese producto se esperen entre sí: nunca DEBE quedar un movimiento nuevo sobre un producto recién desactivado (ADR-038 punto 5, `design.md` D4, D4.2; enmienda `02` §7.3). El resto del orden global de bloqueo NO cambia.

#### Scenario: Movimiento y desactivación simultáneos del mismo producto

- **GIVEN** "Vino Rosado" activo sin stock, un ingreso de 6 en "Camioneta 1" y, a la vez, su desactivación
- **WHEN** las dos transacciones confirman
- **THEN** o el ingreso falla con `PRODUCTO_INACTIVO` y el producto queda inactivo sin stock, o la desactivación falla con `PRODUCTO_CON_STOCK` y el producto queda activo con 6; nunca queda un producto inactivo con stock
- **Regla:** CAT-05; ADR-038; `design.md` D4.2

#### Scenario: Stock inicial y compras no cambian su resultado

- **GIVEN** las suites de stock inicial, compras e importación previas a este change
- **WHEN** se ejecutan con el bloqueo compartido del producto
- **THEN** pasan sin cambios
- **Regla:** `02` §7.3; `design.md` D4.2

## MODIFIED Requirements

### Requirement: Un egreso deja stock negativo solo con permiso

Un egreso de stock DEBE aplicarse con la condición de saldo suficiente de `02` §7.4 y, si no alcanza, DEBE rechazarse con `STOCK_INSUFICIENTE` sin cambios. Las excepciones en la etapa actual son el egreso de una anulación de compra (CMP-07), la salida de una transferencia (`design.md` D1 del change 14) y los egresos inversos de una anulación de transferencia o de ajuste (`design.md` D5 del change 14): si quien los registra tiene `PERMITIR_STOCK_NEGATIVO`, el egreso DEBE aplicarse sin condición y el resultado DEBE informar qué saldos quedaron negativos para que la operación quede con la observación `STOCK_NEGATIVO` (STK-05, `design.md` D10 del change 11). Un egreso `AJUSTE` que no es el inverso de una anulación NO tiene excepción: nunca deja el saldo negativo. Las correcciones de stock inicial siguen sin excepción (STK-10).

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

#### Scenario: Salida de transferencia con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `TRANSFERENCIA_SALIDA` de 60 con permiso de stock negativo
- **THEN** el saldo queda en −12 y el resultado informa el saldo negativo
- **Regla:** STK-05; `design.md` D1 del change 14

#### Scenario: Ajuste negativo con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `AJUSTE` de 60 con origen `AJUSTE_STOCK` y permiso de stock negativo
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 48
- **Regla:** STK-05; `design.md` D1 del change 14

#### Scenario: Inverso de una anulación de ajuste con permiso
- **GIVEN** 5 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `AJUSTE` de 12 con origen `ANULACION_AJUSTE_STOCK`, con y sin permiso de stock negativo
- **THEN** con permiso el saldo queda en −7 y el resultado informa el saldo negativo; sin permiso se rechaza con `STOCK_INSUFICIENTE`
- **Regla:** STK-05; `design.md` D5 del change 14

#### Scenario: Corrección de stock inicial con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra una corrección `STOCK_INICIAL` de −60 con permiso de stock negativo
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 48
- **Regla:** STK-10
