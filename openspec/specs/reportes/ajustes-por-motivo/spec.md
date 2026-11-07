# Reportes - Ajustes por motivo

## Purpose

Define el reporte de ajustes de stock por motivo y de las diferencias de rendición del período, con unidades y, para quien ve costos, su valor (STK-03, RUT-06; ADR-048).

## Requirements

### Requirement: Ajustes agrupados por motivo y diferencias de rendición aparte

`GET /api/v1/reportes/ajustes` (con `VER_REPORTES`; período por el `occurred_at` del ajuste) DEBE agrupar los ajustes `CONFIRMADA` por motivo con: cantidad de ajustes, unidades base que entraron y que salieron y, con `VER_COSTOS`, el valor de cada sentido (`cantidad_base × costo_unitario` congelado, sumado exacto y redondeado una vez a 2 decimales por cifra, como string), las unidades sin costo aparte, y el detalle por producto dentro de cada motivo. DEBE informar en una fila aparte los movimientos `DIFERENCIA_RENDICION` del período con las mismas columnas. Los ajustes anulados NO DEBEN sumar y se informa su cantidad. La lista no se pagina (una fila por motivo) (STK-03, RUT-06, TR-03; `design.md` D10, D14).

#### Scenario: Pérdidas por rotura
- **GIVEN** dos ajustes del período con el motivo «Rotura»: −6 y −3 unidades de un vino con costo unitario `"500.000000"`
- **WHEN** `ges01` pide el reporte
- **THEN** «Rotura» informa 2 ajustes, 9 unidades salidas y valor de las salidas `"4500.00"`
- **Regla:** STK-03; ADR-048

#### Scenario: Ajuste anulado
- **GIVEN** un ajuste del período anulado después
- **WHEN** se pide el reporte
- **THEN** no suma en su motivo y se informa «Ajustes anulados: 1»
- **Regla:** TR-06; ADR-048

#### Scenario: Diferencias de rendición
- **GIVEN** una rendición del período con un faltante de 2 unidades
- **WHEN** se pide el reporte
- **THEN** la fila «Diferencias de rendición» informa 2 unidades salidas
- **Regla:** RUT-06

#### Scenario: Sin permiso de costos
- **WHEN** `consulta` (sin `VER_COSTOS`) pide el reporte
- **THEN** recibe las unidades y los valores en `null`
- **Regla:** `01` §19 (VER_COSTOS)

### Requirement: La pestaña «Ajustes por motivo»

La pestaña DEBE mostrar una fila por motivo (desplegable con el detalle por producto), la fila «Diferencias de rendición», la nota de ajustes anulados y, solo con `VER_COSTOS`, las columnas de valor. Sin datos: «Sin ajustes en el período.» (`design.md` D11, D12).

#### Scenario: Período sin ajustes
- **WHEN** elige un período sin ajustes ni diferencias
- **THEN** ve «Sin ajustes en el período.»
- **Regla:** STK-03
