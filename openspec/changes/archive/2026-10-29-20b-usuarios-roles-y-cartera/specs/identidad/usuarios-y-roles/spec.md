## ADDED Requirements

### Requirement: Ninguna baja ni cambio de rol deja la organización sin administrador

`USUARIO_BAJA`, `USUARIO_ROL_CAMBIAR` y `ROL_BAJA` DEBEN rechazarse con `IDENTIDAD_SIN_ADMINISTRADOR` (409) cuando, después del cambio, ningún usuario `ACTIVO` con rol activo de la organización tendría `ADMIN_USUARIOS`, con la misma regla que `ROL_PERMISOS_CAMBIAR` (ADR-053). El rechazo NO DEBE cambiar el usuario ni el rol, revocar sesiones ni borrar ningún PIN. La regla DEBE valer con operaciones simultáneas (`design.md` D3, D4).

#### Scenario: El único administrador se cambia a un rol sin el permiso
- **GIVEN** Rafa, único usuario activo con `ADMIN_USUARIOS`
- **WHEN** Rafa se asigna a sí mismo un rol sin ese permiso
- **THEN** la respuesta es 409 `IDENTIDAD_SIN_ADMINISTRADOR`, Rafa conserva su rol y su PIN
- **Regla:** ADR-053; INV-01

#### Scenario: La regla de la baja como defensa en profundidad
- **GIVEN** que la autobaja está prohibida, el último administrador solo puede quedar dado de baja por una carrera entre comandos
- **WHEN** la regla del último administrador se evalúa dentro de la baja con el bloqueo de la organización tomado
- **THEN** una baja que dejaría cero administradores responde 409 `IDENTIDAD_SIN_ADMINISTRADOR` sin revocar sesiones ni borrar el PIN
- **Regla:** ADR-053; ADR-028 D9.5; INV-01

#### Scenario: Otro administrador queda activo
- **GIVEN** Rafa y Laura activos con `ADMIN_USUARIOS`
- **WHEN** Laura da de baja a Rafa
- **THEN** la baja se acepta
- **Regla:** `01` §19; ADR-053

#### Scenario: Dos administradores se dan de baja entre sí
- **GIVEN** Rafa, Laura y Pedro activos con `ADMIN_USUARIOS`
- **WHEN** Rafa da de baja a Laura y Laura da de baja a Rafa al mismo tiempo
- **THEN** exactamente una de las dos bajas se aplica; la otra responde `PERMISO_REQUERIDO` porque quien la envió ya no está activo, y la organización conserva al menos un administrador
- **Regla:** `design.md` D4; INV-01

#### Scenario: Los dos últimos administradores a la vez
- **GIVEN** Rafa y Laura, los únicos activos con `ADMIN_USUARIOS`
- **WHEN** Rafa da de baja a Laura y Laura le cambia el rol a Rafa al mismo tiempo
- **THEN** una se acepta y la otra se rechaza; la organización conserva un usuario activo con `ADMIN_USUARIOS`
- **Regla:** ADR-053; INV-01

#### Scenario: Otra organización no cuenta
- **GIVEN** la organización B con varios administradores y A con uno solo
- **WHEN** en A se da de baja a su único administrador
- **THEN** la respuesta es 409 `IDENTIDAD_SIN_ADMINISTRADOR`
- **Regla:** INV-02

### Requirement: El tope de descuento propio de un usuario se define por comando

`USUARIO_TOPE_DESCUENTO_DEFINIR` v1 DEBE fijar o quitar (`null`) el tope de descuento propio de un usuario, con `ADMIN_USUARIOS`, solo con conexión, con la misma validación que el tope del rol, y dejar una fila de auditoría con el valor anterior y el nuevo. Con tope propio rige el propio; sin él, el del rol (`design.md` D12).

#### Scenario: Definir un tope propio mayor que el del rol
- **GIVEN** el vendedor Juan con el rol Vendedor de tope 5 %
- **WHEN** un administrador le define un tope propio de `"0.100000"`
- **THEN** el contexto de venta de Juan informa 10 % y la auditoría guarda `null` como anterior y `"0.100000"` como nuevo
- **Regla:** DSC-06; AUD-01; INV-03

#### Scenario: Quitar el tope propio
- **GIVEN** Juan con tope propio 10 % y su rol con 5 %
- **WHEN** se le define `null`
- **THEN** rige el 5 % del rol
- **Regla:** DSC-06; `03` §4

#### Scenario: Fuera de rango
- **WHEN** se envía `"1.500000"` o un valor negativo
- **THEN** la respuesta es 422 `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO` y el tope no cambia
- **Regla:** TR-02; INV-01

#### Scenario: Doble envío
- **GIVEN** un tope ya definido
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06

### Requirement: El alta de usuario exige un rol activo y un nombre de usuario libre

`USUARIO_CREAR` DEBE rechazar un rol con `activo = false` (409 `IDENTIDAD_ROL_INACTIVO`) y un nombre de inicio de sesión ya usado en la organización (409 `IDENTIDAD_USUARIO_DUPLICADO`), sin crear nada (`design.md` D9).

#### Scenario: Rol de baja
- **WHEN** se da de alta un usuario con un rol dado de baja
- **THEN** la respuesta es 409 `IDENTIDAD_ROL_INACTIVO` y no se crea ningún usuario
- **Regla:** ADR-028 D9.4; INV-01

#### Scenario: Nombre de usuario repetido
- **GIVEN** el usuario `vendedor` en la organización A
- **WHEN** se da de alta otro `vendedor` en A
- **THEN** la respuesta es 409 `IDENTIDAD_USUARIO_DUPLICADO`
- **Regla:** `03` §4

#### Scenario: El mismo nombre en otra organización
- **GIVEN** el usuario `vendedor` en la organización B
- **WHEN** se da de alta `vendedor` en A
- **THEN** se acepta
- **Regla:** INV-02
