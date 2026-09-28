## MODIFIED Requirements

### Requirement: Cada ruta de negocio declara el permiso que exige y el servidor lo verifica

Toda ruta de negocio DEBE declarar qué permiso requiere, y el servidor DEBE verificarlo en cada petición contra los permisos vigentes del rol del usuario. Ocultar una acción en la interfaz NO reemplaza esta validación (SEG-06).

La única ruta autenticada que no declara un permiso es la consulta de la propia sesión (`GET /api/v1/yo`, ADR-027). Exige un access token válido, pero ningún permiso, porque su propósito es informar qué permisos tiene el usuario. Queda exenta de forma explícita y enumerable, junto a las de autenticación y sistema, y no por una regla de nombre.

#### Scenario: Con el permiso, la operación procede

- **GIVEN** un usuario cuyo rol tiene `GESTIONAR_DISPOSITIVOS`
- **WHEN** invoca una ruta que exige ese permiso
- **THEN** la operación se ejecuta
- **Regla:** SEG-06, `01` §19

#### Scenario: Sin el permiso, la operación se rechaza con un código estable

- **GIVEN** un usuario cuyo rol no tiene `GESTIONAR_DISPOSITIVOS`
- **WHEN** invoca una ruta que exige ese permiso
- **THEN** la petición se rechaza con el código de dominio `PERMISO_REQUERIDO`
- **AND** la respuesta no modifica ningún dato
- **Regla:** SEG-06, `02` §11 (errores en formato Problem Details con un campo `codigo` de dominio estable)

#### Scenario: Una ruta de negocio sin permiso declarado no llega a existir

- **GIVEN** el conjunto de rutas de negocio registradas
- **WHEN** se inspecciona cuál permiso exige cada una
- **THEN** todas declaran uno
- **AND** la verificación falla nombrando la ruta y el método que lo omite
- **Regla:** SEG-06 (el servidor valida los permisos en cada comando)

#### Scenario: Las rutas de autenticación y de sistema no exigen permiso

- **GIVEN** las rutas de inicio, renovación y cierre de sesión, y las de salud, versión y documentación
- **WHEN** se ejecuta la verificación anterior
- **THEN** quedan exentas por estar declaradas explícitamente, no por una regla de nombre
- **Regla:** SEG-01 (el inicio de sesión ocurre antes de que haya usuario autenticado)

#### Scenario: La consulta de la propia sesión no exige permiso pero sí sesión

- **GIVEN** la ruta `GET /api/v1/yo`, declarada explícitamente como exenta de permiso
- **WHEN** se ejecuta la verificación de permiso por ruta
- **THEN** la ruta no se marca como infractora
- **AND** una petición a esa ruta sin access token igual se rechaza como no autenticada
- **Regla:** ADR-027 (requiere un access token válido y ningún permiso en particular); SEG-06

## ADDED Requirements

### Requirement: Solo un usuario activo con rol activo pasa la autorización

> **(D9)** Requisito del cierre de la brecha de sesión (ADR-028, dominio CRÍTICO, aprobado por el usuario el 2026-09-25). Refleja las opciones aprobadas: D9.2-A (401 existente) y D9.4-A (un rol inactivo se trata como un usuario inactivo).

En cada petición a una ruta que exige permiso, el servidor DEBE verificar, antes de mirar el permiso, que el usuario del token existe en la organización del token, que su estado es `ACTIVO` y que su rol está activo. Si alguna condición falla, DEBE rechazar la petición como no autenticada (401), sin ejecutar nada ni registrar comandos. La verificación DEBE leerse en cada petición, sin esperar a que venza el access token, igual que los permisos (ADR-017). Los permisos vigentes de un usuario inactivo, o de un usuario con rol inactivo, DEBEN ser el conjunto vacío para cualquier consumidor (falla cerrada). La verificación NO DEBE hacerse en la extracción del contexto del token que comparten todas las rutas autenticadas, porque el lote de sincronización debe seguir recibiendo la cola pendiente (ADR-028, D9.3).

#### Scenario: Un usuario dado de baja pierde el acceso en la petición siguiente
- **GIVEN** un usuario con rol Administrador y un access token todavía vigente
- **WHEN** pasa a `INACTIVO` e invoca con ese token el listado de dispositivos
- **THEN** la petición se rechaza como no autenticada (401), no con `PERMISO_REQUERIDO`
- **Regla:** ADR-028; ADR-017 (efecto inmediato con conexión); SEG-06

#### Scenario: Una escritura de un usuario dado de baja no deja efectos
- **GIVEN** un usuario que pasó a `INACTIVO` con un access token todavía vigente
- **WHEN** envía una escritura de negocio con `Operation-Id`
- **THEN** se rechaza como no autenticada y no queda ningún comando ni registro de auditoría de esa operación
- **Regla:** ADR-028; ADR-012 (toda escritura pasa por el bus); SEG-06

#### Scenario: Un rol desactivado corta el acceso de sus usuarios
- **GIVEN** un usuario activo con un access token vigente, cuyo rol pasa a inactivo
- **WHEN** invoca una ruta que exige un permiso que ese rol tiene en su composición
- **THEN** la petición se rechaza como no autenticada (401)
- **Regla:** ADR-028 (D9.4-A)

#### Scenario: Reactivar al usuario devuelve el acceso con el mismo token
- **GIVEN** un usuario que pasó a `INACTIVO` y fue rechazado con su access token vigente
- **WHEN** vuelve a `ACTIVO` e invoca la misma ruta con el mismo access token, todavía vigente
- **THEN** la operación se ejecuta
- **Regla:** ADR-017 (la autorización se lee en cada petición); ADR-028

#### Scenario: La baja de un usuario no afecta a otra organización
- **GIVEN** dos organizaciones, A y B, cada una con un usuario activo con sesión iniciada
- **WHEN** el usuario de A pasa a `INACTIVO`
- **THEN** el usuario de B sigue operando con normalidad
- **Regla:** INV-21; ADR-028
