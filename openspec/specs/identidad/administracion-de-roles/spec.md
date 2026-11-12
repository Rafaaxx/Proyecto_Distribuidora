## Purpose

Permite que un administrador de la organización cambie qué permisos tiene cada rol existente desde `/admin`, sobre el comando `ROL_PERMISOS_CAMBIAR`, viendo el catálogo de permisos con sus descripciones (`01` §19, `00` §3).

## Requirements

### Requirement: El catálogo de permisos se lee por API

El sistema DEBE exponer `GET /identidad/permisos`, con `ADMIN_USUARIOS`, que devuelve el catálogo global de permisos con código, descripción y módulo, en el orden de `01` §19 (`design.md` D7, D9). No depende de la organización y no se edita desde la aplicación.

#### Scenario: Catálogo completo
- **GIVEN** un usuario con `ADMIN_USUARIOS`
- **WHEN** pide el catálogo de permisos
- **THEN** recibe los permisos de `01` §19 con su descripción y su módulo, entre ellos `ANULAR_COBRANZA` con "Anular cobranzas"
- **Regla:** `01` §19; `03` §4 (`permiso`)

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ADMIN_USUARIOS`
- **WHEN** pide el catálogo de permisos
- **THEN** la respuesta es 403
- **Regla:** `01` §19

### Requirement: La pantalla de roles y permisos

`/admin` DEBE tener la sección "Roles y permisos", visible solo con `ADMIN_USUARIOS` (`design.md` D9). Lista los roles de la organización con su estado, su cantidad de permisos y de usuarios activos. Al elegir un rol muestra sus permisos agrupados por módulo, cada uno con su descripción y una casilla. Guardar DEBE mostrar un resumen de lo que agrega y lo que quita y pedir confirmación; DEBE avisar cuando el rol se queda sin permisos de autorización (se borra el PIN de sus usuarios, ADR-011) y cuando quien edita cambia su propio rol. Un rechazo por quedarse sin administrador DEBE explicarse en palabras simples. Un reintento DEBE usar el mismo `Operation-Id`. La pantalla NO DEBE ofrecer crear, desactivar ni borrar roles (D7).

#### Scenario: Quitar un permiso
- **GIVEN** un usuario con `ADMIN_USUARIOS` en "Roles y permisos", con el rol Supervisor comercial elegido
- **WHEN** destilda "Anular cobranzas", guarda y confirma el resumen "Quita: Anular cobranzas"
- **THEN** el rol deja de tener `ANULAR_COBRANZA` y un supervisor que intenta anular una cobranza en su petición siguiente recibe 403
- **Regla:** `01` §19; ADR-017

#### Scenario: Aviso al quitar los permisos de autorización
- **GIVEN** el rol Supervisor comercial con `AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO` y `USAR_LISTA_ANTERIOR`
- **WHEN** destilda los cuatro y guarda
- **THEN** la confirmación avisa que se va a borrar el PIN de autorización de los usuarios del rol
- **Regla:** ADR-011

#### Scenario: Sin administrador
- **GIVEN** que solo los usuarios del rol Administrador tienen `ADMIN_USUARIOS`
- **WHEN** se destilda "Usuarios, roles y permisos" en el rol Administrador y se confirma
- **THEN** la pantalla explica que la organización se quedaría sin nadie que administre usuarios y roles, y el rol queda como estaba
- **Regla:** ADR-053

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `ADMIN_USUARIOS`
- **WHEN** entra a `/admin`
- **THEN** no ve la sección "Roles y permisos"
- **Regla:** ADR-027

#### Scenario: Sin crear ni borrar roles
- **GIVEN** la pantalla "Roles y permisos"
- **WHEN** se la recorre
- **THEN** no ofrece crear, desactivar ni borrar roles
- **Regla:** ADR-028 (D9.5, change de usuarios y roles)

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
