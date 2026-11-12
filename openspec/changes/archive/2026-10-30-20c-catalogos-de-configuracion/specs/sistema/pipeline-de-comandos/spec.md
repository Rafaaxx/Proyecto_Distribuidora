## ADDED Requirements

### Requirement: El catálogo declara los comandos de motivos, alícuotas y redondeo por defecto

El catálogo de tipos DEBE declarar, todos v1, solo en modo `ONLINE` y con `ADMIN_CONFIGURACION`: `MOTIVO_CREAR`, `MOTIVO_MODIFICAR`, `ALICUOTA_CREAR`, `ALICUOTA_MODIFICAR` y `REDONDEO_POR_DEFECTO_DEFINIR`. El bus DEBE exigir ese permiso en todo camino (ADR-056). Sus rutas de escritura DEBEN pasar por el bus y ninguna ruta ni comando DEBE borrar motivos ni alícuotas (`design.md` D1, D2, D6, D10 del change 20c).

#### Scenario: Por REST y por el lote
- **WHEN** un usuario sin `ADMIN_CONFIGURACION` envía cualquiera de estos comandos por REST o en un lote en modo `ONLINE`
- **THEN** en los dos caminos recibe `PERMISO_REQUERIDO` y nada cambia
- **Regla:** ADR-056; SEG-06

#### Scenario: Mismo resultado por los dos caminos
- **WHEN** un administrador envía `MOTIVO_CREAR` por REST y otro igual, con otro nombre, en un lote en modo `ONLINE`
- **THEN** los dos crean el motivo con el mismo efecto y la misma auditoría
- **Regla:** `02` §6.5

#### Scenario: Modo OFFLINE
- **WHEN** llega cualquiera de estos comandos en modo `OFFLINE`
- **THEN** se rechaza como tipo que no admite ese modo
- **Regla:** `02` §6.5

#### Scenario: Ninguna ruta borra
- **WHEN** se enumeran las rutas y los tipos de comando de motivos y alícuotas
- **THEN** ninguno elimina filas, y `app_runtime` sigue sin `DELETE` sobre `motivo` y `alicuota_iva`
- **Regla:** INV-05; TR-06
