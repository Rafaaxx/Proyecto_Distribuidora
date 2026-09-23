# Productos y Presentaciones Specification

## Purpose

Define el producto y sus presentaciones como datos maestros escritos solo por comandos: código único, unidad base, alícuota, categoría y marca; presentaciones con unidades base enteras, uso en venta y en compra; exactamente una presentación de referencia de venta; unidades congeladas una vez usadas y desactivación en lugar de borrado (CAT-01 a CAT-06, INV-18, ADR-010).

## Requirements

### Requirement: Un producto se crea con sus presentaciones en un solo comando
El sistema DEBE crear un producto con el comando `PRODUCTO_CREAR` (`ONLINE`, `GESTIONAR_CATALOGO`), cuyo contenido incluye código, nombre, categoría, marca opcional, unidad base, alícuota de IVA y al menos una presentación, exactamente una de ellas marcada como referencia. El producto y todas sus presentaciones DEBEN registrarse completos o no registrarse (INV-01). El producto y sus presentaciones nacen activos.

#### Scenario: Alta de un vino con botella y caja x6
- **WHEN** la categoría activa `Vinos` y la alícuota activa `21%` existen en la organización A y se envía `PRODUCTO_CREAR` con código `VA-001`, nombre `Vino A`, unidad base `botella`, presentaciones `Botella` (1 unidad, venta y compra) y `Caja x6` (6 unidades, venta y compra, referencia)
- **THEN** el comando queda `ACEPTADO` y existen el producto y sus dos presentaciones, activos, con `Caja x6` como única presentación de referencia
- **Regla:** CAT-01; CAT-02; CAT-03; ADR-010

#### Scenario: Doble envío del alta no duplica el producto
- **WHEN** se reenvía un `PRODUCTO_CREAR` aceptado con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y el producto y sus presentaciones existen una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con contenido distinto
- **WHEN** un `PRODUCTO_CREAR` aceptado con `operation_id` X y código `VA-001` se reenvía con `operation_id` X pero código `VA-002`
- **THEN** el comando se rechaza con `COMANDO_INCONSISTENTE` y no se crea `VA-002`
- **Regla:** SYN-02

#### Scenario: Alta sin presentaciones
- **WHEN** se envía `PRODUCTO_CREAR` con la lista de presentaciones vacía
- **THEN** el comando se rechaza con el código `PRODUCTO_SIN_PRESENTACIONES` y no se crea ninguna fila
- **Regla:** CAT-02 (una o más presentaciones)

#### Scenario: Alta sin presentación de referencia o con dos
- **WHEN** se envía `PRODUCTO_CREAR` con ninguna presentación marcada como referencia, o con dos
- **THEN** el comando se rechaza con el código `REFERENCIA_INVALIDA` y no se crea ninguna fila
- **Regla:** CAT-03 (exactamente una presentación de referencia)

#### Scenario: Una falla en una presentación no deja el producto a medias
- **WHEN** se procesa un `PRODUCTO_CREAR` cuya segunda presentación tiene 0 unidades
- **THEN** se rechaza con el código `UNIDADES_INVALIDAS` y no queda ni el producto ni la primera presentación
- **Regla:** INV-01; CAT-02 (unidades base, entero ≥ 1)

#### Scenario: Alícuota, categoría o marca inexistente, inactiva o ajena
- **WHEN** se envía `PRODUCTO_CREAR` con una alícuota, categoría o marca que no existe en la organización del token, o existe pero está inactiva, o es ajena
- **THEN** la respuesta es 404 si no existe o es ajena, y se rechaza con `ALICUOTA_INACTIVA`, `CATEGORIA_INACTIVA` o `MARCA_INACTIVA` si está inactiva, y no se crea ninguna fila
- **Regla:** CAT-01; CAT-05; INV-21

### Requirement: El código del producto es único dentro de la organización
El código de producto DEBE ser único entre los productos de la organización, activos o no, y la base de datos DEBE garantizarlo aun ante altas concurrentes. Organizaciones distintas PUEDEN repetir códigos. El código se DEBE guardar sin espacios al inicio ni al final y NO DEBE quedar vacío.

#### Scenario: Código repetido
- **WHEN** el producto `VA-001` existe en la organización A y se envía `PRODUCTO_CREAR` o `PRODUCTO_MODIFICAR` que deja otro producto con código `VA-001` en A
- **THEN** el comando se rechaza con el código `CODIGO_DUPLICADO` y no cambia ninguna fila
- **Regla:** CAT-01 (código único dentro de la organización)

#### Scenario: Dos altas concurrentes con el mismo código
- **WHEN** dos transacciones con commits reales envían `PRODUCTO_CREAR` con código `VA-001` en A al mismo tiempo con `operation_id` distintos
- **THEN** exactamente una queda `ACEPTADA` y la otra se rechaza con `CODIGO_DUPLICADO`
- **Regla:** CAT-01; `03` §5 (`UNIQUE (organizacion_id, codigo)`)

### Requirement: El producto registra su proveedor único
Cada producto DEBE registrar un único proveedor (CAT-06). Mientras la tabla de proveedores no exista (change 06), el proveedor NO DEBE poder informarse ni validarse en este change; el change 06 DEBE hacerlo obligatorio y agregar la clave foránea compuesta.

#### Scenario: El alta no exige proveedor antes del change 06
- **WHEN** la tabla `proveedor` todavía no existe y se envía `PRODUCTO_CREAR` sin proveedor
- **THEN** el comando queda `ACEPTADO` con el proveedor vacío
- **Regla:** CAT-06 (deuda nominada al change 06, `design.md` D1)

### Requirement: Un producto se modifica y desactiva por comando
El sistema DEBE modificar código, nombre, categoría, marca, unidad base, alícuota y actividad de un producto con `PRODUCTO_MODIFICAR`, cuyo contenido es el estado completo deseado. Un producto NO DEBE borrarse: se desactiva y PUEDE reactivarse (CAT-05). Desactivar un producto NO DEBE cambiar el estado de sus presentaciones.

#### Scenario: Desactivar y reactivar un producto
- **WHEN** el producto activo `Vino A` se envía con `PRODUCTO_MODIFICAR` con `activo = false` y luego con `activo = true`
- **THEN** el producto queda inactivo y luego activo, y sus presentaciones conservan su estado en ambos pasos
- **Regla:** CAT-05

#### Scenario: Cambiar la alícuota del producto
- **WHEN** el producto `Vino A` con alícuota `21%` se envía con `PRODUCTO_MODIFICAR` con alícuota `10,5%`
- **THEN** el producto queda con `10,5%`
- **Regla:** CAT-01 (alícuota de IVA por producto); VTA-03 (las ventas ya confirmadas congelan su alícuota)

#### Scenario: Producto inexistente o de otra organización
- **WHEN** un usuario de A envía `PRODUCTO_MODIFICAR` sobre un producto de B
- **THEN** la respuesta es 404 y el producto de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: No existe borrado de productos
- **WHEN** se busca en la API cualquier operación que elimine un producto o una presentación
- **THEN** no existe, y el usuario de aplicación de la base no tiene `DELETE` sobre `producto` ni `presentacion`
- **Regla:** CAT-05; TR-06

### Requirement: Las presentaciones se agregan y modifican por comando
El sistema DEBE agregar una presentación a un producto existente con `PRESENTACION_AGREGAR` y modificar nombre, unidades base, uso en venta, uso en compra y actividad con `PRESENTACION_MODIFICAR`. Las unidades base DEBEN ser un entero ≥ 1. La presentación de referencia NO DEBE desactivarse ni dejar de usarse en venta; para eso primero se cambia la referencia.

#### Scenario: Agregar una presentación de compra
- **WHEN** el producto `Cerveza B` con referencia `Caja x12` existe y se envía `PRESENTACION_AGREGAR` con `Pack x24` (24 unidades, solo compra)
- **THEN** el producto tiene la nueva presentación activa, no de referencia
- **Regla:** CAT-02; ADR-010 (presentaciones de compra y de venta independientes)

#### Scenario: Unidades no enteras o menores a 1
- **WHEN** se envía `PRESENTACION_AGREGAR` o `PRESENTACION_MODIFICAR` con unidades `0`, `-6` o `2.5`
- **THEN** el comando se rechaza con `UNIDADES_INVALIDAS` (o como contenido inválido si no es entero) y no cambia ninguna fila
- **Regla:** CAT-02; INV-04

#### Scenario: Desactivar la presentación de referencia
- **WHEN** `Caja x6` es referencia de `Vino A` y se envía `PRESENTACION_MODIFICAR` sobre `Caja x6` con `activo = false` o con `usar_en_venta = false`
- **THEN** el comando se rechaza con `REFERENCIA_INVALIDA` y `Caja x6` no cambia
- **Regla:** CAT-03 (la referencia debe usarse en venta)

#### Scenario: Presentación de otra organización
- **WHEN** un usuario de A envía `PRESENTACION_MODIFICAR` sobre una presentación de B
- **THEN** la respuesta es 404 y la presentación no cambia
- **Regla:** INV-21

### Requirement: Cada producto tiene exactamente una presentación de referencia
Todo producto DEBE tener en todo momento exactamente una presentación marcada como referencia, activa y usada en venta. La base de datos DEBE impedir dos referencias para el mismo producto aun ante escrituras concurrentes, y DEBE impedir una referencia que no se use en venta. La referencia DEBE cambiarse con `PRESENTACION_REFERENCIA_CAMBIAR`, que en una sola operación desmarca la anterior y marca la nueva.

#### Scenario: Cambiar la referencia
- **WHEN** `Vino A` tiene referencia `Caja x6` y la presentación activa de venta `Caja x12` existe, y se envía `PRESENTACION_REFERENCIA_CAMBIAR` hacia `Caja x12`
- **THEN** `Caja x12` es la única referencia y `Caja x6` deja de serlo, sin que exista un momento visible con cero o dos referencias
- **Regla:** CAT-03

#### Scenario: La nueva referencia no se usa en venta o está inactiva
- **WHEN** `Pack x24` solo de compra, o una presentación inactiva, existen y se envía `PRESENTACION_REFERENCIA_CAMBIAR` hacia ella
- **THEN** el comando se rechaza con `REFERENCIA_INVALIDA` y la referencia anterior se conserva
- **Regla:** CAT-03 (la referencia debe usarse en venta); CAT-05

#### Scenario: La base rechaza una segunda referencia escrita por fuera del servicio
- **WHEN** un producto con una referencia existe y se intenta insertar o actualizar directamente otra presentación del mismo producto con `es_referencia = true`
- **THEN** la base rechaza la escritura por el índice único parcial de referencia
- **Regla:** CAT-03 (índice único); `03` §5 (`ux_presentacion__referencia`)

#### Scenario: Dos cambios de referencia concurrentes
- **WHEN** `Vino A` tiene referencia `Botella` y las presentaciones de venta `Caja x6` y `Caja x12` existen, y dos transacciones con commits reales envían al mismo tiempo `PRESENTACION_REFERENCIA_CAMBIAR` hacia `Caja x6` y hacia `Caja x12`
- **THEN** al terminar ambas, el producto tiene exactamente una referencia
- **Regla:** CAT-03

#### Scenario: La base rechaza una referencia que no se usa en venta
- **WHEN** se intenta escribir directamente una presentación con `es_referencia = true` y `usar_en_venta = false`
- **THEN** la base la rechaza por `ck_presentacion__referencia_venta`
- **Regla:** CAT-03; `03` §5

### Requirement: Las unidades de una presentación usada no cambian
Las unidades base de una presentación que ya fue usada en alguna operación NO DEBEN modificarse; el comando DEBE rechazarse con `UNIDADES_CONGELADAS` indicando que se cree una presentación nueva y se desactive la anterior. El resto de sus datos (nombre, usos, actividad) SÍ PUEDE modificarse. "Usada" lo determinan los módulos que registran operaciones, consultados por el catálogo sin depender de ellos (`design.md` D2).

#### Scenario: Cambiar las unidades de una presentación sin uso
- **WHEN** la presentación `Caja x6` de `Vino A` sin ninguna operación que la use existe y se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** la presentación queda con 12 unidades
- **Regla:** CAT-04 (la restricción aplica solo a presentaciones usadas)

#### Scenario: INV-18 — cambiar las unidades de una presentación usada
- **WHEN** la presentación `Caja x6` de `Vino A` que un módulo de operaciones informa como usada existe y se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** el comando se rechaza con `UNIDADES_CONGELADAS` y la presentación conserva 6 unidades
- **Regla:** INV-18; CAT-04

#### Scenario: Una presentación usada sí puede renombrarse o desactivarse
- **WHEN** la presentación usada `Caja x6` que no es referencia existe y se envía `PRESENTACION_MODIFICAR` con el mismo número de unidades, otro nombre y `activo = false`
- **THEN** el comando queda `ACEPTADO` con el nuevo nombre e inactiva
- **Regla:** CAT-04 (se crea una nueva y se desactiva la anterior); CAT-05

### Requirement: Productos y presentaciones se consultan por organización
El sistema DEBE listar productos de la organización con paginación por cursor y límite máximo por página, filtrables por texto (código o nombre), categoría, marca y actividad, y DEBE devolver el detalle de un producto con todas sus presentaciones y cuál es la de referencia. Ninguna consulta DEBE devolver datos de otra organización.

#### Scenario: Listado paginado por cursor
- **WHEN** existen más productos en A que el tamaño de página pedido y se piden páginas sucesivas con el cursor devuelto
- **THEN** cada producto aparece exactamente una vez y la última página no devuelve cursor
- **Regla:** `02` §11 (paginación por cursor)

#### Scenario: Detalle con presentación de referencia
- **WHEN** se pide el detalle de `Vino A`
- **THEN** se devuelven sus presentaciones con unidades, usos y actividad, y `Caja x6` marcada como referencia
- **Regla:** CAT-02; CAT-03

#### Scenario: Producto de otra organización
- **WHEN** un usuario de A pide el detalle de un producto de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
