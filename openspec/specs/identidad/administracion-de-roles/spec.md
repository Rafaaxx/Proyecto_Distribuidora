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
