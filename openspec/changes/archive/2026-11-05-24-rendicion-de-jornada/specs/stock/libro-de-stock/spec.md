## ADDED Requirements

### Requirement: La diferencia de rendición entra por la única puerta sin recalcular el promedio

La puerta del libro DEBE admitir `DIFERENCIA_RENDICION` con signo, solo con origen `RENDICION` (cualquier otro origen, `TIPO_MOVIMIENTO_INVALIDO`). DEBE valorizarlo al promedio vigente sin recalcularlo ni escribir historia de costo, subiendo o bajando `stock_total` (CST-12, CST-13); sin promedio, con costo nulo. NO DEBE dejar el saldo negativo (`STOCK_INSUFICIENTE`), con o sin `PERMITIR_STOCK_NEGATIVO` (`design.md` D5).

#### Scenario: Sobrante al promedio vigente
- **GIVEN** Vino A con promedio `"1050.000000"` y stock total 120
- **WHEN** entra un `DIFERENCIA_RENDICION` de +2 con origen `RENDICION`
- **THEN** el movimiento guarda `"1050.000000"`, el stock total pasa a 122 y el promedio y la historia de costo no cambian
- **Regla:** CST-12; CST-13; INV-03

#### Scenario: Faltante que dejaría negativo
- **GIVEN** saldo 2 de Vino A en "Camioneta 1"
- **WHEN** llega un `DIFERENCIA_RENDICION` de −3
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y no se escribe nada, aunque el usuario tenga `PERMITIR_STOCK_NEGATIVO`
- **Regla:** STK-05; INV-01

#### Scenario: Diferencia con otro origen
- **WHEN** se intenta registrar un `DIFERENCIA_RENDICION` con un origen que no es `RENDICION`
- **THEN** se rechaza con `TIPO_MOVIMIENTO_INVALIDO`
- **Regla:** STK-03
