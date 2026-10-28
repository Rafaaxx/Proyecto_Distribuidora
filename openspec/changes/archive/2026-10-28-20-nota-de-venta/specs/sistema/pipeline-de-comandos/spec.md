## ADDED Requirements

### Requirement: El catálogo declara `NOTA_VENTA_CONFIGURAR`

El catálogo de tipos DEBE declarar `NOTA_VENTA_CONFIGURAR` v1 con el permiso `ADMIN_CONFIGURACION`, solo en modo `ONLINE`, y el bus DEBE exigir ese permiso en todo camino (ADR-056) (`design.md` D10).

#### Scenario: Por REST y por el lote
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía `NOTA_VENTA_CONFIGURAR` por REST o en un lote en modo `ONLINE`
- **THEN** en los dos caminos recibe `PERMISO_REQUERIDO` y nada cambia
- **Regla:** ADR-056; SEG-06

#### Scenario: Modo OFFLINE
- **WHEN** llega `NOTA_VENTA_CONFIGURAR` en modo `OFFLINE`
- **THEN** se rechaza como tipo que no admite ese modo
- **Regla:** `02` §6.5

### Requirement: El catálogo declara el comando del nombre y el CUIT de la organización

El catálogo de tipos DEBE declarar el comando del nombre y el CUIT de la organización `ORGANIZACION_DATOS_CONFIGURAR` v1 (`design.md` D15 a1) con el permiso `ADMIN_CONFIGURACION`, solo en modo `ONLINE`, y el bus DEBE exigir ese permiso en todo camino (ADR-056).

#### Scenario: Por REST y por el lote
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía el comando del nombre y el CUIT por REST o en un lote en modo `ONLINE`
- **THEN** en los dos caminos recibe `PERMISO_REQUERIDO` y nada cambia
- **Regla:** ADR-056; SEG-06

#### Scenario: Modo OFFLINE
- **WHEN** llega el comando del nombre y el CUIT en modo `OFFLINE`
- **THEN** se rechaza como tipo que no admite ese modo
- **Regla:** `02` §6.5
