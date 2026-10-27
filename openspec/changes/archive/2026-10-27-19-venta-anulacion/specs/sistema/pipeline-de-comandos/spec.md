## ADDED Requirements

### Requirement: El catálogo declara `VENTA_ANULAR`

El catálogo de tipos DEBE declarar `VENTA_ANULAR` v1 con el permiso `ANULAR_VENTA`, solo en modo `ONLINE` hasta el change 22c (VTA-24), y el bus DEBE exigir ese permiso en todo camino (ADR-056). La fila de la venta y después la de su cobranza DEBEN tomarse antes del nivel 1 del orden global (`02` §7.3) (`design.md` D1, D10, D19).

#### Scenario: Por REST y por el lote
- **WHEN** un usuario sin `ANULAR_VENTA` envía `VENTA_ANULAR` por REST o en un lote en modo `ONLINE`
- **THEN** en los dos caminos recibe `PERMISO_REQUERIDO` y nada cambia
- **Regla:** ADR-056; SEG-06

#### Scenario: Modo OFFLINE
- **WHEN** llega `VENTA_ANULAR` en modo `OFFLINE`
- **THEN** se rechaza como tipo que no admite ese modo
- **Regla:** `02` §6.5; VTA-24
