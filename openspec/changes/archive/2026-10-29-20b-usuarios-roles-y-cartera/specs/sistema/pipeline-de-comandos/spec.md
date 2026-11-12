## ADDED Requirements

### Requirement: El catálogo declara los comandos de usuarios, roles y cartera

El catálogo de tipos DEBE declarar, todos v1 y solo en modo `ONLINE`: con `ADMIN_USUARIOS`, `USUARIO_MODIFICAR`, `USUARIO_BAJA`, `USUARIO_REACTIVAR`, `USUARIO_ROL_CAMBIAR`, `USUARIO_CONTRASENA_RESTABLECER` (con credenciales efímeras fuera del contenido), `USUARIO_TOPE_DESCUENTO_DEFINIR`, `ROL_CREAR`, `ROL_RENOMBRAR`, `ROL_BAJA` y `ROL_REACTIVAR`; con `GESTIONAR_CLIENTES`, `CLIENTE_VENDEDOR_ASIGNAR`. El bus DEBE exigir ese permiso en todo camino (ADR-056) (`design.md` D1, D10, D11, D12, D15).

#### Scenario: Por REST y por el lote
- **WHEN** un usuario sin el permiso declarado envía cualquiera de estos comandos por REST o en un lote en modo `ONLINE`
- **THEN** en los dos caminos recibe `PERMISO_REQUERIDO` y nada cambia
- **Regla:** ADR-056; SEG-06

#### Scenario: Modo OFFLINE
- **WHEN** llega cualquiera de estos comandos en modo `OFFLINE`
- **THEN** se rechaza como tipo que no admite ese modo
- **Regla:** `02` §6.5

#### Scenario: La contraseña no entra por el lote
- **WHEN** llega `USUARIO_CONTRASENA_RESTABLECER` en un lote
- **THEN** se rechaza como tipo que exige credenciales efímeras, sin ejecutar el handler
- **Regla:** ADR-056

#### Scenario: Quien ejecuta se revalida con el bloqueo tomado
- **GIVEN** un comando de baja, reactivación o cambio de rol cuyo autor fue dado de baja mientras el comando esperaba el bloqueo de la organización
- **WHEN** el comando obtiene el bloqueo
- **THEN** se rechaza con `PERMISO_REQUERIDO` sin cambios
- **Regla:** `design.md` D4; SEG-06; INV-01

### Requirement: El catálogo declara el cambio de la propia contraseña

El catálogo DEBE declarar `CONTRASENA_PROPIA_CAMBIAR` v1 solo en modo `ONLINE`, **sin permiso requerido** (cualquier usuario autenticado y activo) y con credenciales efímeras fuera del contenido. El bus DEBE rechazarlo en un lote y en modo `OFFLINE`, y el contenido vacío DEBE rechazar todo campo extra (`design.md` D20).

#### Scenario: Cualquier usuario autenticado
- **GIVEN** un usuario activo sin ningún permiso de administración
- **WHEN** envía el cambio de su propia contraseña por REST
- **THEN** el bus no responde `PERMISO_REQUERIDO` y lo procesa
- **Regla:** ADR-056; SEG-06

#### Scenario: Sin sesión
- **WHEN** llega sin access token válido o de un usuario `INACTIVO`
- **THEN** responde 401 sin ejecutar el handler
- **Regla:** ADR-028 D9.1

#### Scenario: Lote y modo OFFLINE
- **WHEN** llega en un lote o en modo `OFFLINE`
- **THEN** se rechaza como tipo que exige credenciales efímeras o que no admite ese modo, sin ejecutar el handler
- **Regla:** ADR-056; `02` §6.5
