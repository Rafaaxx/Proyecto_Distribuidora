## ADDED Requirements

### Requirement: Se crean roles nuevos

`ROL_CREAR` v1 DEBE crear un rol activo con nombre, permisos del catálogo y tope de descuento (por defecto 0), con `ADMIN_USUARIOS`, solo con conexión. El nombre DEBE recortarse, tener entre 1 y 100 caracteres y ser único en la organización sin distinguir mayúsculas, incluidos los roles de baja (`design.md` D10).

#### Scenario: Crear un rol
- **WHEN** un administrador crea "Repartidor" con `VENDER` y `REGISTRAR_COBRANZA` y tope 0
- **THEN** el rol queda activo con esos permisos, se puede asignar a usuarios y queda una fila de auditoría del alta
- **Regla:** `01` §19; AUD-01

#### Scenario: Nombre repetido
- **GIVEN** el rol "Vendedor" en la organización A
- **WHEN** se crea "vendedor" en A
- **THEN** la respuesta es 409 `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO` y no se crea nada
- **Regla:** INV-01

#### Scenario: Nombre inválido
- **WHEN** se crea un rol con nombre vacío o de más de 100 caracteres
- **THEN** la respuesta es 422 `IDENTIDAD_NOMBRE_DE_ROL_INVALIDO`
- **Regla:** INV-01

#### Scenario: Permiso fuera del catálogo
- **WHEN** se crea un rol con un permiso que no existe
- **THEN** se rechaza como en el cambio de permisos y no se crea nada
- **Regla:** `03` §4; INV-01

#### Scenario: El mismo nombre en otra organización
- **GIVEN** el rol "Repartidor" en B
- **WHEN** se crea "Repartidor" en A
- **THEN** se acepta
- **Regla:** INV-02

#### Scenario: Doble envío
- **GIVEN** un alta de rol ya aceptada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin crear otro rol
- **Regla:** INV-06

### Requirement: Un rol se renombra

`ROL_RENOMBRAR` v1 DEBE cambiar el nombre de un rol de la organización con las mismas reglas de nombre del alta, con `ADMIN_USUARIOS`, solo con conexión, y auditarlo con el nombre anterior y el nuevo. Las plantillas sembradas se renombran como cualquier rol.

#### Scenario: Renombrar una plantilla
- **WHEN** se renombra "Vendedor/Repartidor" a "Vendedor"
- **THEN** el rol, sus usuarios y sus permisos no cambian salvo el nombre, y la auditoría guarda los dos nombres
- **Regla:** `01` §19; AUD-01

#### Scenario: Rol de otra organización
- **WHEN** un administrador de A renombra un rol de B
- **THEN** la respuesta es 404
- **Regla:** INV-21

### Requirement: Un rol sin usuarios activos se da de baja y se reactiva

`ROL_BAJA` v1 DEBE pasar un rol a `activo = false` solo si no tiene usuarios `ACTIVO` asignados; si los tiene, DEBE rechazarse con `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS` (409). `ROL_REACTIVAR` v1 DEBE volverlo a activo. Ambos con `ADMIN_USUARIOS`, solo con conexión, auditados. Un rol de baja NO DEBE poder asignarse y DEBE seguir visible en la lista de roles como "De baja" (`design.md` D11).

#### Scenario: Baja de un rol sin usuarios
- **GIVEN** el rol "Repartidor" sin usuarios
- **WHEN** un administrador lo da de baja
- **THEN** el rol queda de baja, no aparece para asignar y queda una fila de auditoría
- **Regla:** ADR-028 D9.4; AUD-01

#### Scenario: Baja de un rol con usuarios activos
- **GIVEN** el rol Vendedor con dos usuarios activos
- **WHEN** se lo da de baja
- **THEN** la respuesta es 409 `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`, el rol sigue activo y ninguna sesión se toca
- **Regla:** ADR-028 D9.4; INV-01

#### Scenario: Baja de un rol con solo usuarios inactivos
- **GIVEN** un rol cuyo único usuario está `INACTIVO`
- **WHEN** se lo da de baja
- **THEN** se acepta
- **Regla:** ADR-028 D9.4

#### Scenario: Baja frente a un cambio de rol simultáneo
- **GIVEN** el rol "Repartidor" sin usuarios activos
- **WHEN** a la vez un administrador lo da de baja y otro le asigna ese rol a un usuario activo
- **THEN** o la baja se aplica y el cambio de rol responde `IDENTIDAD_ROL_INACTIVO`, o el cambio se aplica y la baja responde `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`; nunca queda un usuario activo en un rol de baja
- **Regla:** `design.md` D4; INV-01

#### Scenario: Reactivar
- **GIVEN** un rol de baja
- **WHEN** se lo reactiva
- **THEN** vuelve a poder asignarse
- **Regla:** AUD-01

#### Scenario: Doble envío
- **GIVEN** una baja de rol ya aceptada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06

### Requirement: La pantalla de roles crea, renombra y da de baja

La pantalla "Roles y permisos" DEBE ofrecer, con `ADMIN_USUARIOS`, "Nuevo rol" (con la opción de copiar los permisos de un rol existente), "Renombrar", "Dar de baja" y "Reactivar", mostrar el estado de cada rol y la cantidad de usuarios con tope propio, y explicar en palabras simples `IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS`, `IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO` e `IDENTIDAD_SIN_ADMINISTRADOR` (`design.md` D16).

#### Scenario: Copiar permisos
- **WHEN** el administrador crea un rol eligiendo "copiar permisos de Supervisor"
- **THEN** el formulario se precarga con los permisos de Supervisor y se pueden cambiar antes de guardar
- **Regla:** `01` §19

#### Scenario: Rol con usuarios activos
- **WHEN** la baja de un rol se rechaza por tener usuarios activos
- **THEN** la pantalla dice cuántos son y que primero hay que cambiarles el rol
- **Regla:** ADR-028 D9.4
