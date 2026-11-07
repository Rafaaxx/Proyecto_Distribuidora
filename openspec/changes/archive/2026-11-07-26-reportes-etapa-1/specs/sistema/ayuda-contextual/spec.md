## ADDED Requirements

### Requirement: Los reportes explican período, anuladas, cantidades y utilidad

`/admin` DEBE tener las claves de ayuda `reportes.periodo` (junto a «Desde»/«Hasta»), `reportes.anuladas` (en «Ventas anuladas del período»), `reportes.cajasEquivalentes` (en «Cajas equivalentes»), `reportes.utilidad` (en «Utilidad», solo visible con `VER_UTILIDAD`), `reportes.lineasSinCosto` (en la nota de líneas sin costo), `reportes.rendiciones` (en «Rendiciones»), `reportes.saldos` (en las dos pestañas de saldos), `reportes.observacionesPorVendedor` y `reportes.ajustesPorMotivo`, con los textos aprobados en la tarea 0.2, sin ejemplos, cada uno citando la regla o el ADR en que se apoya (ADR-051; `design.md` D13).

#### Scenario: Ayuda de las anuladas
- **WHEN** la persona abre la ayuda de «Ventas anuladas del período»
- **THEN** lee que una venta anulada no suma en el período en que se hizo aunque se haya anulado después, sin ejemplo
- **Regla:** REP-02; ADR-051

#### Scenario: Ayuda de la utilidad
- **WHEN** `consulta` abre la ayuda de «Utilidad»
- **THEN** lee que es el neto menos el costo congelado y que no cambia con los costos o precios posteriores
- **Regla:** REP-04; REP-05

#### Scenario: Ayuda de las cajas equivalentes
- **WHEN** abre la ayuda de «Cajas equivalentes»
- **THEN** lee que se usan las unidades de la referencia que tenía el producto en cada venta
- **Regla:** REP-03; REP-05

#### Scenario: Clave o ID inexistente
- **WHEN** una pantalla usa una clave que no existe o un texto cita un ID que no está en `docs/`
- **THEN** la prueba de claves de ayuda falla
- **Regla:** ADR-051
