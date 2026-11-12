## ADDED Requirements

### Requirement: Ningún cambio de permisos deja la organización sin administrador

`ROL_PERMISOS_CAMBIAR` DEBE rechazarse con `IDENTIDAD_SIN_ADMINISTRADOR` (409) cuando, después del cambio, ningún usuario `ACTIVO` con rol activo de la organización tendría `ADMIN_USUARIOS` (`design.md` D8 del change 17b, ADR-053). El rechazo NO DEBE cambiar el rol ni invalidar ningún PIN. La regla DEBE valer también con dos cambios simultáneos sobre roles distintos. Un cambio que no quita `ADMIN_USUARIOS`, o que lo quita dejando otro usuario activo con ese permiso, se acepta como hasta ahora.

#### Scenario: Quitar el permiso al único rol que lo tiene
- **GIVEN** la organización A, donde solo el rol Administrador tiene `ADMIN_USUARIOS` y Rafa es su único usuario activo
- **WHEN** Rafa le quita `ADMIN_USUARIOS` al rol Administrador
- **THEN** la respuesta es 409 con `IDENTIDAD_SIN_ADMINISTRADOR` y el rol conserva todos sus permisos
- **Regla:** ADR-053; TR-10

#### Scenario: Otro usuario activo conserva el permiso
- **GIVEN** la organización A, donde el rol Administración también tiene `ADMIN_USUARIOS` y Laura es su usuaria activa
- **WHEN** se le quita `ADMIN_USUARIOS` al rol Administrador
- **THEN** el cambio se acepta y Laura sigue pudiendo administrar roles
- **Regla:** `01` §19; ADR-053

#### Scenario: El otro rol solo tiene usuarios inactivos
- **GIVEN** el rol Administración con `ADMIN_USUARIOS` cuyo único usuario está `INACTIVO`
- **WHEN** se le quita `ADMIN_USUARIOS` al rol Administrador, cuyo único usuario es Rafa
- **THEN** la respuesta es 409 con `IDENTIDAD_SIN_ADMINISTRADOR`
- **Regla:** ADR-053; ADR-028

#### Scenario: El rechazo no toca el PIN
- **GIVEN** un cambio sobre el rol Administrador que quita `ADMIN_USUARIOS` y los cuatro permisos de autorización, rechazado con `IDENTIDAD_SIN_ADMINISTRADOR`
- **WHEN** se mira el PIN de autorización de Rafa
- **THEN** sigue vigente
- **Regla:** ADR-011; INV-01

#### Scenario: Dos cambios simultáneos
- **GIVEN** los roles Administrador y Administración con `ADMIN_USUARIOS`, cada uno con un usuario activo, y ningún otro rol con ese permiso
- **WHEN** dos administradores les quitan `ADMIN_USUARIOS` a la vez, uno a cada rol
- **THEN** uno se acepta y el otro responde `IDENTIDAD_SIN_ADMINISTRADOR`; la organización conserva un usuario activo con `ADMIN_USUARIOS`
- **Regla:** ADR-053; INV-01

#### Scenario: Otra organización no cuenta
- **GIVEN** la organización B con usuarios activos con `ADMIN_USUARIOS`, y A con uno solo
- **WHEN** en A se le quita `ADMIN_USUARIOS` al único rol que lo tiene
- **THEN** la respuesta es 409 con `IDENTIDAD_SIN_ADMINISTRADOR`
- **Regla:** TR-08; INV-02

#### Scenario: Doble envío
- **GIVEN** un cambio de permisos ya aceptado
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06
