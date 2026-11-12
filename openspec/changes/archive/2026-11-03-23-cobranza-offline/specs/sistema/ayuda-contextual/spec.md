## ADDED Requirements

### Requirement: Las pantallas de ruta explican la cobranza

El área de ruta DEBE tener las claves de ayuda `ruta.cobrar` (en «Cobrar»), `ruta.medios` (en los medios de la pantalla de cobro), `ruta.saldoDespuesDelCobro` (junto al saldo resultante) y `ruta.cobranzaRechazada` (en el detalle de una cobranza rechazada y en «Sincronización»), y las revisadas `ruta.creditoSinSenal`, `ruta.sincronizar`, `ruta.observacionesYRechazos`, `ruta.jornadaNoAbierta` y `ruta.versionMinima`, con los textos aprobados, sin ejemplos, citando sus reglas. Todo ID citado DEBE existir en `01-dominio.md` o en `docs/adr/` (`design.md` D12).

#### Scenario: Ayuda de la pantalla de cobro
- **WHEN** el vendedor abre la ayuda de «Cobrar», de los medios o del saldo después del cobro
- **THEN** ve el texto aprobado, sin ejemplo, también sin señal
- **Regla:** COB-01; COB-02; CRE-08; ADR-051

#### Scenario: Ayuda de una cobranza rechazada
- **WHEN** abre la ayuda en el detalle de una cobranza rechazada
- **THEN** lee que el teléfono deja de descontarla de la cuenta del cliente y que debe avisar a administración
- **Regla:** SYN-06; SYN-09

#### Scenario: Textos revisados
- **WHEN** abre la ayuda del crédito, de «Sincronizar», de observaciones y rechazos, de la jornada no abierta o de la versión mínima
- **THEN** el texto nombra también las cobranzas
- **Regla:** CRE-08; SYN-03; RUT-09

#### Scenario: Clave o ID inexistente
- **WHEN** una pantalla usa una clave que no existe o un texto cita un ID que no está en `docs/`
- **THEN** la prueba de claves de ayuda falla
- **Regla:** ADR-051
