## Purpose

Administración de los usuarios de la organización desde `/admin`: edición de datos, baja y reactivación, cambio de rol, restablecimiento de la contraseña y tope de descuento propio, todo por comandos auditados que cumplen ADR-028 y ADR-053.

## ADDED Requirements

### Requirement: Los datos de un usuario se modifican por comando

`USUARIO_MODIFICAR` v1 DEBE reemplazar el nombre y el email de un usuario de la organización, con `ADMIN_USUARIOS`, solo con conexión. El nombre DEBE recortarse y no puede quedar vacío ni superar 200 caracteres; un email vacío DEBE guardarse nulo. El nombre de inicio de sesión NO DEBE poder cambiarse (`design.md` D9).

#### Scenario: Modificar nombre y email
- **GIVEN** la usuaria Laura de la organización A
- **WHEN** un usuario con `ADMIN_USUARIOS` cambia su nombre a "Laura Gómez" y su email
- **THEN** el usuario queda con los datos nuevos, su nombre de inicio de sesión no cambia y queda una fila de auditoría con el valor anterior y el nuevo
- **Regla:** AUD-01; AUD-02

#### Scenario: Nombre vacío
- **WHEN** se envía un nombre vacío o solo con espacios
- **THEN** la respuesta es 422 y el usuario no cambia
- **Regla:** INV-01

#### Scenario: Usuario de otra organización
- **WHEN** un administrador de A modifica un usuario de la organización B
- **THEN** la respuesta es 404 y el usuario de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío
- **GIVEN** una modificación ya aceptada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06

### Requirement: La baja de un usuario corta su acceso sin perder su cola offline

`USUARIO_BAJA` v1 DEBE pasar un usuario `ACTIVO` a `INACTIVO`, con `ADMIN_USUARIOS`, solo con conexión, con una observación opcional. En la misma transacción DEBE revocar sus sesiones de refresh vigentes salvo las de los dispositivos con una jornada no cerrada de ese usuario, borrar su PIN de autorización y auditar la baja y la revocación. La baja NO DEBE revocar dispositivos ni tocar los comandos que el usuario tenga pendientes de sincronizar (`design.md` D2; ADR-028 D9.5).

#### Scenario: Baja de un vendedor sin jornada
- **GIVEN** el vendedor Juan, activo, con sesión iniciada en su teléfono y sin jornada abierta
- **WHEN** un administrador lo da de baja
- **THEN** Juan queda `INACTIVO`, su siguiente petición con el access token vigente responde 401 y su siguiente renovación también
- **AND** quedan una fila de auditoría de la baja y una `REVOCAR_SESIONES_REFRESH_USUARIO` con el mismo `operation_id`
- **Regla:** ADR-028 D9.1, D9.5; AUD-01

#### Scenario: Baja con jornada abierta
- **GIVEN** el vendedor Juan con una jornada `ABIERTA` en su teléfono y ventas sin conexión en la cola
- **WHEN** un administrador lo da de baja y después el teléfono renueva la sesión y envía el lote
- **THEN** la renovación de ese dispositivo se acepta, las ventas offline se aceptan con la observación `PERMISO_REVOCADO` y toda otra ruta responde 401
- **Regla:** ADR-028 D9.3-B; SYN-05; SYN-10; INV-17

#### Scenario: La baja borra el PIN de autorización
- **GIVEN** la supervisora Ana con PIN de autorización definido
- **WHEN** se la da de baja
- **THEN** ya no tiene PIN y no figura entre los autorizadores disponibles; al reactivarla hay que definirlo de nuevo
- **Regla:** ADR-011; SEG-05

#### Scenario: Baja de un usuario ya inactivo
- **WHEN** se da de baja a un usuario `INACTIVO`
- **THEN** la respuesta es 409 `IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA` y nada cambia
- **Regla:** `01` §18; INV-01

#### Scenario: Autobaja
- **GIVEN** la organización A con dos usuarios activos con `ADMIN_USUARIOS`, Rafa y Laura
- **WHEN** Rafa se da de baja a sí mismo
- **THEN** la respuesta es 409 `IDENTIDAD_AUTOBAJA`, Rafa sigue activo y ninguna sesión se revoca
- **Regla:** `design.md` D5; INV-01

#### Scenario: Usuario de otra organización
- **WHEN** un administrador de A da de baja a un usuario de B
- **THEN** la respuesta es 404 y el usuario de B sigue activo
- **Regla:** INV-21

#### Scenario: Doble envío
- **GIVEN** una baja ya aceptada
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original, sin otra revocación ni otra fila de auditoría
- **Regla:** INV-06

### Requirement: Un usuario dado de baja se reactiva

`USUARIO_REACTIVAR` v1 DEBE pasar un usuario `INACTIVO` a `ACTIVO`, con `ADMIN_USUARIOS`, solo con conexión, y auditarlo. El usuario DEBE iniciar sesión de nuevo; su rol, su tope propio y su cartera se conservan.

#### Scenario: Reactivar
- **GIVEN** el vendedor Juan `INACTIVO`
- **WHEN** un administrador lo reactiva
- **THEN** Juan queda `ACTIVO`, puede iniciar sesión y queda una fila de auditoría de la reactivación
- **Regla:** `01` §18; AUD-01

#### Scenario: Reactivar a un usuario activo
- **WHEN** se reactiva un usuario `ACTIVO`
- **THEN** la respuesta es 409 `IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA`
- **Regla:** INV-01

#### Scenario: Reactivar con rol de baja
- **GIVEN** un usuario `INACTIVO` cuyo rol está dado de baja
- **WHEN** se lo reactiva
- **THEN** queda `ACTIVO` pero no puede iniciar sesión hasta que se le asigne un rol activo, y la pantalla lo avisa
- **Regla:** ADR-028 D9.4-A

### Requirement: El rol de un usuario se cambia por comando

`USUARIO_ROL_CAMBIAR` v1 DEBE asignar a un usuario otro rol activo de la organización, con `ADMIN_USUARIOS`, solo con conexión. NO DEBE revocar sesiones: el cambio rige en la petición siguiente. Si el rol nuevo no tiene ningún permiso de autorización de excepciones, DEBE borrar el PIN de autorización del usuario (`design.md` D7).

#### Scenario: Cambio a un rol con menos permisos
- **GIVEN** la supervisora Ana con PIN y el rol Supervisor
- **WHEN** se le asigna el rol Vendedor
- **THEN** su siguiente petición se evalúa con los permisos de Vendedor, su PIN queda borrado y queda una fila de auditoría con el rol anterior y el nuevo
- **Regla:** ADR-017; ADR-011; AUD-01

#### Scenario: Rol de baja
- **WHEN** se asigna a un usuario un rol con `activo = false`
- **THEN** la respuesta es 409 `IDENTIDAD_ROL_INACTIVO` y el usuario conserva su rol
- **Regla:** ADR-028 D9.4; INV-01

#### Scenario: Rol de otra organización
- **WHEN** se asigna a un usuario de A un rol de B
- **THEN** la respuesta es 404 y el usuario conserva su rol
- **Regla:** INV-21

#### Scenario: Cambio del propio rol
- **GIVEN** Rafa y Laura con `ADMIN_USUARIOS` en el rol Administrador
- **WHEN** Rafa se asigna a sí mismo el rol Administración, que no tiene `ADMIN_USUARIOS`
- **THEN** el cambio se acepta y la siguiente petición de Rafa a usuarios responde 403
- **Regla:** `design.md` D5; ADR-053

#### Scenario: Doble envío
- **GIVEN** un cambio de rol ya aceptado
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original sin una segunda fila de auditoría
- **Regla:** INV-06

### Requirement: El administrador restablece la contraseña de un usuario

`USUARIO_CONTRASENA_RESTABLECER` v1 DEBE fijar una contraseña nueva a un usuario de la organización, con `ADMIN_USUARIOS`, solo con conexión. La contraseña DEBE viajar fuera del contenido del comando y no aparecer en la huella, el comando, la cuarentena, la auditoría ni el resultado. En la misma transacción DEBE revocar las sesiones del usuario salvo las de dispositivos con jornada no cerrada y desbloquear su inicio de sesión (`design.md` D8).

#### Scenario: Restablecer
- **GIVEN** la usuaria Laura bloqueada por intentos fallidos y con una sesión abierta en la PC
- **WHEN** un administrador le restablece la contraseña
- **THEN** Laura puede iniciar sesión con la nueva, la sesión anterior ya no renueva y la auditoría registra el restablecimiento sin la contraseña
- **Regla:** ADR-018; ADR-056; ADR-057

#### Scenario: Contraseña inválida
- **WHEN** se envía una contraseña que no cumple las reglas del alta (menos de 8 caracteres o en blanco; no se exigen mayúsculas, números ni símbolos)
- **THEN** la respuesta es 422, la contraseña anterior sigue vigente y ninguna sesión se revoca
- **Regla:** INV-01

#### Scenario: La contraseña no queda guardada en claro
- **WHEN** se lee el comando, la auditoría y la respuesta de un restablecimiento
- **THEN** ninguno contiene la contraseña
- **Regla:** ADR-056; SEG-06

### Requirement: La pantalla de usuarios

El área "Usuarios" de `/admin` DEBE ofrecerse solo con `ADMIN_USUARIOS` y DEBE permitir listar con estado y rol, filtrar por estado, dar de alta, editar datos, cambiar el rol, definir el tope propio, restablecer la contraseña, desbloquear y dar de baja o reactivar, con confirmación y con los avisos de `design.md` D5 y D6 (cambio del propio rol, jornada abierta, clientes asignados). Cada error de dominio DEBE explicarse en palabras simples, y un reintento DEBE reutilizar el mismo `Operation-Id`.

#### Scenario: Sin permiso
- **GIVEN** la sesión del vendedor
- **WHEN** abre `/admin/usuarios`
- **THEN** no ve la sección en el menú y la pantalla muestra el aviso de falta de permiso
- **Regla:** ADR-027; SEG-06

#### Scenario: Baja con jornada abierta y clientes asignados
- **GIVEN** el vendedor Juan con una jornada abierta y clientes asignados
- **WHEN** el administrador elige "Dar de baja"
- **THEN** la confirmación avisa de la jornada y de los clientes antes de enviar
- **Regla:** `design.md` D6; RUT-09

#### Scenario: Último administrador
- **WHEN** la baja o el cambio de rol se rechaza con `IDENTIDAD_SIN_ADMINISTRADOR`
- **THEN** la pantalla explica que la organización se quedaría sin nadie que administre usuarios y roles, y el usuario sigue como estaba
- **Regla:** ADR-053
