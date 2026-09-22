# Identidad - Usuarios y Roles

## Purpose

Define qué es un usuario del sistema, qué rol tiene, qué permisos le confiere ese rol y qué tope de descuento rige para él, de modo que el catálogo de permisos de `01` §19 sea la única fuente de lo que cada persona puede hacer.

## Requirements

### Requirement: El catálogo de permisos es global y lo fija el código

El sistema DEBE mantener el catálogo de permisos como dato global, sin organización, sincronizado desde el código y no editable por ninguna organización. El catálogo DEBE contener exactamente los permisos de `01` §19 (`03` §4, `03` §17).

#### Scenario: El catálogo contiene los permisos de la documentación

- **GIVEN** el esquema migrado a la última revisión
- **WHEN** se consulta el catálogo de permisos
- **THEN** están presentes los 39 permisos de `01` §19, incluidos `ADMIN_USUARIOS`, `GESTIONAR_DISPOSITIVOS`, `VENDER`, `VER_COSTOS`, `AUTORIZAR_DESCUENTO` y `VER_AUDITORIA`
- **AND** ninguno tiene organización asociada
- **Regla:** `01` §19, `03` §4 (el catálogo de `permiso` es global, sin organización)

#### Scenario: Sincronizar el catálogo dos veces no lo duplica

- **GIVEN** el catálogo de permisos ya sincronizado
- **WHEN** se vuelve a aplicar la sincronización
- **THEN** la cantidad de permisos no cambia y ninguno queda duplicado
- **Regla:** `03` §17 (los datos de catálogo que dependen del código se sincronizan por migración)

#### Scenario: Una organización no puede crear ni borrar permisos

- **GIVEN** un usuario con `ADMIN_USUARIOS`
- **WHEN** intenta agregar un permiso que no está en el catálogo o quitar uno existente
- **THEN** la operación no está disponible: el catálogo no es editable desde la aplicación
- **Regla:** `03` §4 (el catálogo de `permiso` se sincroniza por migración)

### Requirement: Un rol agrupa permisos y fija un tope de descuento

Un rol DEBE pertenecer a una organización, tener un nombre, un conjunto de permisos tomados del catálogo global y un tope de descuento. La organización DEBE poder modificar la composición de sus roles y sus topes, porque los cinco roles son plantillas y no valores fijos (`01` §19).

#### Scenario: Las cinco plantillas de rol quedan disponibles al crear la organización

- **GIVEN** una organización recién creada
- **WHEN** se consultan sus roles
- **THEN** existen los cinco roles de `01` §19: Administrador, Administración, Supervisor comercial, Vendedor/Repartidor y Consulta/Dirección
- **AND** cada uno tiene exactamente los permisos que `01` §19 le marca
- **Regla:** `01` §19 (los roles son plantillas)

#### Scenario: El vendedor no recibe permisos de costo ni de utilidad

- **GIVEN** la organización con sus cinco roles sembrados
- **WHEN** se consultan los permisos del rol Vendedor/Repartidor
- **THEN** incluyen `VENDER`, `REGISTRAR_COBRANZA`, `ABRIR_JORNADA`, `TRANSFERIR_STOCK` y `DESCUENTO_MANUAL`
- **AND** no incluyen `VER_COSTOS` ni `VER_UTILIDAD`
- **Regla:** `01` §19 (el vendedor ve el saldo y el crédito disponible de sus clientes; no ve costos ni utilidad)

#### Scenario: Una organización cambia la composición de un rol

- **GIVEN** el rol Supervisor comercial de una organización
- **WHEN** un usuario con `ADMIN_USUARIOS` le quita el permiso `LIBERAR_UBICACION`
- **THEN** ese rol deja de conferir `LIBERAR_UBICACION` en esa organización
- **AND** el mismo rol de otra organización no cambia
- **Regla:** `01` §19, TR-08 (todo dato de negocio solo es modificable desde su organización)

#### Scenario: Un rol no puede referirse a un permiso inexistente

- **GIVEN** un usuario con `ADMIN_USUARIOS`
- **WHEN** intenta asignar a un rol un código de permiso que no está en el catálogo global
- **THEN** la operación se rechaza con un error de dominio de código estable y el rol queda sin cambios
- **Regla:** `03` §4 (`rol_permiso` referencia el catálogo global de permisos)

### Requirement: Un usuario pertenece a una organización y tiene exactamente un rol

Un usuario DEBE pertenecer a una organización, tener un nombre de usuario único dentro de ella, una contraseña almacenada como derivación irrecuperable, un rol y un estado (`ACTIVO` o `INACTIVO`). Los permisos de un usuario DEBEN ser los de su rol; no existen permisos asignados directamente al usuario en esta etapa (`03` §4).

#### Scenario: Dos organizaciones pueden tener el mismo nombre de usuario

- **GIVEN** la organización A con un usuario llamado `admin`
- **WHEN** se crea un usuario llamado `admin` en la organización B
- **THEN** el alta se acepta y ambos usuarios coexisten como personas distintas
- **Regla:** `03` §4 (`UNIQUE (organizacion_id, usuario)`), TR-08

#### Scenario: Un nombre de usuario repetido dentro de la organización se rechaza

- **GIVEN** la organización A con un usuario llamado `vendedor1`
- **WHEN** se intenta crear otro usuario llamado `vendedor1` en la organización A
- **THEN** la operación se rechaza y no queda ningún usuario nuevo
- **Regla:** `03` §4 (`UNIQUE (organizacion_id, usuario)`)

#### Scenario: La contraseña no se puede recuperar del sistema

- **GIVEN** un usuario creado con una contraseña
- **WHEN** se consulta ese usuario por cualquier vía de lectura del sistema
- **THEN** la respuesta no contiene la contraseña ni su derivación
- **AND** lo almacenado es una derivación de la que no se puede reconstruir la contraseña
- **Regla:** `03` §4 (`password_hash`, Argon2id), `02` §17 (nunca se registran contraseñas)

#### Scenario: Un usuario inactivo no puede operar

- **GIVEN** un usuario con estado `INACTIVO`
- **WHEN** intenta iniciar sesión con credenciales correctas
- **THEN** el intento se rechaza sin distinguirse de un intento con credenciales incorrectas
- **Regla:** SEG-01 (el inicio de sesión requiere conexión y credenciales), `03` §4 (`estado`)

#### Scenario: Un usuario no puede quedar sin rol

- **GIVEN** un usuario con `ADMIN_USUARIOS`
- **WHEN** intenta crear o modificar un usuario sin indicar un rol
- **THEN** la operación se rechaza con un error de dominio de código estable
- **Regla:** `03` §4 (`usuario.rol_id`)

#### Scenario: Un usuario no puede tomar un rol de otra organización

- **GIVEN** la organización A y un rol que pertenece a la organización B
- **WHEN** se intenta crear en la organización A un usuario con ese rol
- **THEN** la operación se rechaza y el rol ajeno no resulta alcanzable
- **Regla:** INV-21, `03` §2.4 (las claves foráneas entre entidades de negocio son compuestas)

### Requirement: El tope de descuento del usuario puede sobrescribir al del rol

El tope de descuento aplicable a un usuario DEBE ser su propio tope cuando tiene uno definido, y el de su rol cuando no lo tiene. El tope DEBE representarse como fracción decimal exacta de hasta seis decimales, nunca como punto flotante (TR-02, INV-03).

#### Scenario: Sin tope propio rige el del rol

- **GIVEN** un usuario cuyo rol tiene tope de descuento y que no tiene tope propio definido
- **WHEN** se consulta su tope aplicable
- **THEN** es el tope del rol
- **Regla:** `03` §4 (`tope_descuento_override`: si es nulo rige el del rol)

#### Scenario: Con tope propio rige el del usuario

- **GIVEN** un usuario con un tope propio distinto del de su rol
- **WHEN** se consulta su tope aplicable
- **THEN** es el tope propio del usuario, aunque sea menor o mayor que el del rol
- **Regla:** `03` §4 (`tope_descuento_override`)

#### Scenario: El tope se representa en decimal exacto

- **GIVEN** un tope de descuento del 10 %
- **WHEN** se almacena y se vuelve a leer
- **THEN** su representación es `0.100000`, con seis decimales exactos
- **AND** ningún punto del sistema lo convierte a punto flotante binario
- **Regla:** TR-02 (los porcentajes se representan con 6 decimales como fracción), INV-03

#### Scenario: Un tope fuera de rango se rechaza

- **GIVEN** un usuario con `ADMIN_USUARIOS`
- **WHEN** intenta fijar un tope de descuento negativo o mayor que `1.000000`
- **THEN** la operación se rechaza con un error de dominio de código estable
- **Regla:** TR-02, `01` §19 (el tope acota el descuento manual)

### Requirement: La organización arranca con un usuario administrador y sin contraseña por omisión

La puesta en marcha de una organización DEBE producir un usuario con el rol Administrador cuya contraseña se provee al momento de la puesta en marcha. El sistema NO DEBE tener ninguna contraseña inicial fija ni por omisión.

#### Scenario: Sin contraseña provista la puesta en marcha falla

- **GIVEN** una puesta en marcha que no recibe la contraseña del administrador inicial
- **WHEN** se ejecuta
- **THEN** falla indicando que falta la contraseña
- **AND** no crea ningún usuario
- **Regla:** `02` §18 (los secretos se cargan desde el entorno, no desde el repositorio)

#### Scenario: Repetir la puesta en marcha no pisa la contraseña existente

- **GIVEN** una organización ya puesta en marcha cuyo administrador cambió su contraseña
- **WHEN** se vuelve a ejecutar la puesta en marcha
- **THEN** el usuario administrador conserva su contraseña actual
- **AND** no se crea un segundo administrador
- **Regla:** `04` §2.1 (la puesta en marcha es idempotente; mismo criterio que la siembra del change 02)

### Requirement: El alta de usuario se ejecuta como comando idempotente

El alta de un usuario DEBE ejecutarse como un comando del pipeline de escritura, con su identificador de operación obligatorio, su verificación de permiso y su registro de auditoría con ese identificador. Reenviar el alta con el mismo identificador de operación y el mismo contenido NO DEBE crear un segundo usuario (`02` §6.5, SYN-01, SYN-02, INV-06).

#### Scenario: Un alta de usuario sin identificador de operación se rechaza

- **GIVEN** un usuario con el permiso de administrar usuarios
- **WHEN** envía un alta de usuario sin identificador de operación
- **THEN** la petición se rechaza y no queda ningún usuario nuevo
- **Regla:** SYN-01, TR-07

#### Scenario: Reenviar el alta no crea un segundo usuario

- **GIVEN** un alta de usuario ya aceptada
- **WHEN** se reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** la respuesta es el resultado original y sigue existiendo un solo usuario
- **Regla:** SYN-02, INV-06

#### Scenario: Reenviar el alta con otro contenido se rechaza como inconsistente

- **GIVEN** un alta de usuario ya aceptada
- **WHEN** llega otra con el mismo identificador de operación y otro nombre de usuario
- **THEN** se rechaza con el código `COMANDO_INCONSISTENTE` y no queda un usuario nuevo
- **Regla:** SYN-02

#### Scenario: Un alta sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin el permiso de administrar usuarios
- **WHEN** envía un alta de usuario con un identificador de operación válido
- **THEN** se rechaza y no queda ningún usuario nuevo ni registro del comando como aceptado
- **Regla:** SEG-06

#### Scenario: El alta queda auditada con su identificador de operación

- **GIVEN** un alta de usuario aceptada
- **WHEN** se consulta su registro de auditoría
- **THEN** lleva el identificador de operación del comando
- **Regla:** AUD-01, AUD-02, TR-07
