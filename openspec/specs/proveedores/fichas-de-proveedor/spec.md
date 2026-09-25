# Fichas de Proveedor Specification

## Purpose

Define el proveedor como dato maestro de la organización, escrito solo por comandos del bus: ficha (nombre, CUIT, contacto, teléfono, email), activación y desactivación sin borrado, y consulta aislada por organización. El proveedor no guarda saldo: su cuenta corriente llega con el change 08 (CC-04).

## Requirements

### Requirement: Un proveedor se da de alta por comando
El sistema DEBE crear un proveedor con el comando `PROVEEDOR_CREAR` (`ONLINE`, permiso `GESTIONAR_PROVEEDORES`), cuyo contenido incluye nombre obligatorio y, opcionales, CUIT, contacto, teléfono y email. El proveedor nace activo. El identificador lo genera el servidor (UUIDv7) y se devuelve en el resultado. El proveedor NO DEBE tener ningún dato de saldo.

#### Scenario: Alta de un proveedor
- **GIVEN** la organización A sin proveedores
- **WHEN** un usuario con `GESTIONAR_PROVEEDORES` envía `PROVEEDOR_CREAR` con nombre `Bodega Andina`, CUIT `30-71234567-1` y teléfono
- **THEN** el comando queda `ACEPTADO`, el proveedor existe activo en A con el CUIT guardado solo con dígitos (`30712345671`) y se registra una sola fila de auditoría con el `operation_id`
- **Regla:** CAT-06; AUD-02; `03` §6 (`proveedor`)

#### Scenario: Doble envío del alta no duplica el proveedor
- **GIVEN** un `PROVEEDOR_CREAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y el proveedor existe una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con contenido distinto
- **GIVEN** un `PROVEEDOR_CREAR` aceptado con `operation_id` X y nombre `Bodega Andina`
- **WHEN** se reenvía con `operation_id` X y nombre `Bodega Sur`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y no se crea `Bodega Sur`
- **Regla:** SYN-02

#### Scenario: Sin permiso se rechaza sin efectos
- **GIVEN** un usuario sin `GESTIONAR_PROVEEDORES` (rol Vendedor)
- **WHEN** envía `PROVEEDOR_CREAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, no se crea el proveedor ni queda reserva del `operation_id`
- **Regla:** `01` §19 (`GESTIONAR_PROVEEDORES`); SEG

#### Scenario: Nombre vacío
- **GIVEN** la organización A
- **WHEN** se envía `PROVEEDOR_CREAR` con nombre vacío o solo espacios
- **THEN** se rechaza con `NOMBRE_INVALIDO` y no se crea ninguna fila
- **Regla:** TR-10

### Requirement: Nombre y CUIT del proveedor no se repiten en la organización
El nombre del proveedor, sin espacios al inicio ni al final, DEBE ser único entre los proveedores de la organización, activos o no. El CUIT es opcional; si se informa DEBE tener exactamente 11 dígitos (se aceptan guiones y espacios, que se descartan) y DEBE ser único en la organización. La base de datos DEBE garantizar ambas unicidades aun ante altas concurrentes. Organizaciones distintas PUEDEN repetir nombre y CUIT. (`design.md` D7.)

#### Scenario: Nombre repetido
- **GIVEN** el proveedor `Bodega Andina` existe en A
- **WHEN** se envía `PROVEEDOR_CREAR` o `PROVEEDOR_MODIFICAR` que deja otro proveedor con nombre `Bodega Andina` en A
- **THEN** se rechaza con `NOMBRE_DUPLICADO` y no cambia ninguna fila
- **Regla:** `design.md` D7

#### Scenario: CUIT repetido o mal formado
- **GIVEN** un proveedor con CUIT `30712345671` existe en A
- **WHEN** se envía otro proveedor con CUIT `30-71234567-1`, o con un CUIT de 10 dígitos o con letras
- **THEN** se rechaza con `CUIT_DUPLICADO` o `CUIT_INVALIDO` respectivamente y no se crea ninguna fila
- **Regla:** `design.md` D7

#### Scenario: El mismo nombre en otra organización es válido
- **GIVEN** el proveedor `Bodega Andina` existe en B
- **WHEN** un usuario de A envía `PROVEEDOR_CREAR` con nombre `Bodega Andina`
- **THEN** el comando queda `ACEPTADO`
- **Regla:** TR-08; INV-02

#### Scenario: Dos altas concurrentes con el mismo nombre
- **GIVEN** la organización A sin el proveedor `Bodega Andina`
- **WHEN** dos transacciones con commits reales envían `PROVEEDOR_CREAR` con nombre `Bodega Andina` a la vez con `operation_id` distintos
- **THEN** exactamente una queda `ACEPTADA` y la otra se rechaza con `NOMBRE_DUPLICADO`
- **Regla:** `design.md` D7

### Requirement: Un proveedor se modifica y desactiva por comando
El sistema DEBE modificar los datos y la actividad de un proveedor con `PROVEEDOR_MODIFICAR` (`ONLINE`, `GESTIONAR_PROVEEDORES`), cuyo contenido es el estado completo deseado. Un proveedor NO DEBE borrarse: se desactiva y PUEDE reactivarse. Un proveedor inactivo NO DEBE asignarse a un producto nuevo ni recibir costos informados nuevos. Un proveedor con productos activos NO DEBE desactivarse (`design.md` D5; ADR-026).

#### Scenario: Renombrar un proveedor
- **GIVEN** el proveedor activo `Bodega Andina` en A
- **WHEN** se envía `PROVEEDOR_MODIFICAR` con nombre `Bodega Andina S.A.` y el resto igual
- **THEN** el proveedor queda con el nuevo nombre, activo, y `actualizado_en` cambia
- **Regla:** `03` §2.3 (maestros)

#### Scenario: Desactivar y reactivar un proveedor sin productos activos
- **GIVEN** el proveedor `Bodega Sur` sin productos activos
- **WHEN** se envía `PROVEEDOR_MODIFICAR` con `activo = false` y luego con `activo = true`
- **THEN** el proveedor queda inactivo y luego activo, y su historial de costos no cambia
- **Regla:** CAT-05 (analogía: desactivar en vez de borrar); CST-03

#### Scenario: Desactivar un proveedor con productos activos
- **GIVEN** el proveedor `Bodega Andina` es el proveedor del producto activo `Vino A`
- **WHEN** se envía `PROVEEDOR_MODIFICAR` con `activo = false`
- **THEN** se rechaza con `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` y el proveedor sigue activo
- **Regla:** CAT-01; CAT-06; `design.md` D5; ADR-026

#### Scenario: Proveedor de otra organización
- **GIVEN** un proveedor de B
- **WHEN** un usuario de A envía `PROVEEDOR_MODIFICAR` sobre él
- **THEN** la respuesta es 404 y el proveedor de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: No existe borrado de proveedores
- **GIVEN** la API y los permisos de base del usuario de aplicación
- **WHEN** se busca cualquier operación que elimine un proveedor
- **THEN** no existe, y el usuario de aplicación no tiene `DELETE` sobre `proveedor`
- **Regla:** TR-06

### Requirement: Los proveedores se consultan por organización
El sistema DEBE listar los proveedores de la organización con paginación por cursor y límite máximo por página, filtrables por texto (nombre o CUIT) y actividad, y DEBE devolver el detalle de un proveedor. DEBE existir además un listado reducido con identificador y nombre de los proveedores **activos**, para elegir proveedor desde el formulario de producto, protegido por el permiso `GESTIONAR_CATALOGO` (`design.md` D8); el listado completo y el detalle exigen `GESTIONAR_PROVEEDORES`. Ninguna consulta DEBE devolver datos de otra organización.

#### Scenario: Listado paginado por cursor
- **GIVEN** más proveedores en A que el tamaño de página pedido
- **WHEN** se piden páginas sucesivas con el cursor devuelto
- **THEN** cada proveedor aparece exactamente una vez y la última página no devuelve cursor
- **Regla:** `02` §11

#### Scenario: Listado aislado por organización
- **GIVEN** proveedores en A y en B
- **WHEN** un usuario de A lista proveedores, completos o reducidos
- **THEN** no aparece ningún proveedor de B
- **Regla:** INV-21

#### Scenario: Listado reducido para el formulario de producto
- **GIVEN** un usuario con `GESTIONAR_CATALOGO` y sin `GESTIONAR_PROVEEDORES`, y en su organización el proveedor activo `Bodega Andina` y el inactivo `Bodega Sur`
- **WHEN** pide el listado reducido de proveedores
- **THEN** recibe identificador y nombre de `Bodega Andina` y no recibe `Bodega Sur`, sin CUIT ni datos de contacto
- **Regla:** `01` §19; `design.md` D8

#### Scenario: El listado completo exige permiso de proveedores
- **GIVEN** un usuario con `GESTIONAR_CATALOGO` y sin `GESTIONAR_PROVEEDORES`
- **WHEN** pide el listado completo o el detalle de un proveedor
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19 (`GESTIONAR_PROVEEDORES`); `design.md` D8

#### Scenario: Detalle de un proveedor ajeno
- **GIVEN** un proveedor de B
- **WHEN** un usuario de A pide su detalle
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
