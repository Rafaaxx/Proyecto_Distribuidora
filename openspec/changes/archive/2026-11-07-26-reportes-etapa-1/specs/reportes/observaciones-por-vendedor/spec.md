## Purpose

Define el reporte de operación sin conexión por vendedor: cuántas ventas hizo cada uno sin señal y cuántos avisos y rechazos dejaron, para hacer visible el abuso del modo sin conexión (`02` §20; SYN-06, SYN-07; ADR-069).

## ADDED Requirements

### Requirement: Avisos y rechazos por vendedor

`GET /api/v1/reportes/observaciones` (con `VER_REPORTES`; período por el `occurred_at` del comando) DEBE devolver, por vendedor con operaciones en el período: ventas confirmadas sin conexión (cantidad, `modo_confirmacion = 'OFFLINE'`), avisos por código (total y pendientes, de las observaciones de sus comandos), operaciones rechazadas (total y pendientes, de `comando_rechazado`) y excesos de crédito detectados al sincronizar (`EXCESO_CREDITO_DETECTADO_SYNC`), contados en la base. Solo cantidades: el detalle de cada aviso sigue en «Revisión». La lista no se pagina (una fila por vendedor) (`design.md` D9, D14).

#### Scenario: Vendedor con avisos y rechazos
- **GIVEN** `vendedor` con tres ventas sin conexión en el período, dos avisos `STOCK_NEGATIVO` (uno resuelto), un `EXCESO_CREDITO_DETECTADO_SYNC` pendiente y una cobranza rechazada pendiente
- **WHEN** se pide el reporte
- **THEN** la fila de `vendedor` informa 3 ventas sin conexión, `STOCK_NEGATIVO` 2 (1 pendiente), 1 exceso detectado (pendiente) y 1 rechazada (pendiente)
- **Regla:** SYN-07; SYN-06; CRE-09

#### Scenario: Fuera del período
- **GIVEN** un aviso de un comando con `occurred_at` del mes anterior
- **WHEN** se pide el mes en curso
- **THEN** ese aviso no se cuenta
- **Regla:** TR-04

#### Scenario: Otra organización
- **WHEN** se pide el reporte
- **THEN** no cuenta observaciones ni rechazos de otra organización
- **Regla:** INV-21

### Requirement: La pestaña «Observaciones por vendedor»

La pestaña DEBE mostrar una fila por vendedor con «Ventas sin conexión», «Avisos» (con «Pendientes»), «Rechazadas» y «Excesos de crédito detectados»; «Ver en Revisión» DEBE ofrecerse solo con `REVISAR_OBSERVACIONES` y llevar a la bandeja filtrada por ese vendedor. Sin datos: «Sin operaciones sin conexión en el período.» (`design.md` D11, D12).

#### Scenario: Acceso a la bandeja según permiso
- **GIVEN** `sup01` (con `REVISAR_OBSERVACIONES`) y `consulta` (sin él)
- **WHEN** abren la pestaña
- **THEN** `sup01` ve «Ver en Revisión» y `consulta` no
- **Regla:** `01` §19; ADR-069
