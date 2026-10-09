# Productos y Presentaciones Specification

## Purpose

Define el producto y sus presentaciones como datos maestros escritos solo por comandos: código único, unidad base, alícuota, categoría y marca; presentaciones con unidades base enteras, uso en venta y en compra; exactamente una presentación de referencia de venta; unidades congeladas una vez usadas y desactivación en lugar de borrado (CAT-01 a CAT-06, INV-18, ADR-010).

## Requirements

### Requirement: Un producto se crea con sus presentaciones en un solo comando
El sistema DEBE crear un producto con el comando `PRODUCTO_CREAR` (`ONLINE`, `GESTIONAR_CATALOGO`), cuyo contenido incluye código, nombre, categoría, marca opcional, proveedor, unidad base, alícuota de IVA y al menos una presentación, exactamente una de ellas marcada como referencia. El proveedor es obligatorio y DEBE existir activo en la organización (CAT-01, CAT-06); `catalogo` lo valida con la clave foránea compuesta y con la consulta de proveedor que registra `proveedores`, sin importarlo (`design.md` D9 del change 06; ADR-025). El producto y todas sus presentaciones DEBEN registrarse completos o no registrarse (INV-01). El producto y sus presentaciones nacen activos. La versión del contenido sin proveedor deja de aceptarse (`design.md` D6 del change 06).

#### Scenario: Alta de un vino con botella y caja x6
- **WHEN** la categoría activa `Vinos`, la alícuota activa `21%` y el proveedor activo `Bodega Andina` existen en la organización A y se envía `PRODUCTO_CREAR` con código `VA-001`, nombre `Vino A`, proveedor `Bodega Andina`, unidad base `botella`, presentaciones `Botella` (1 unidad, venta y compra) y `Caja x6` (6 unidades, venta y compra, referencia)
- **THEN** el comando queda `ACEPTADO` y existen el producto, con `Bodega Andina` como proveedor, y sus dos presentaciones, activos, con `Caja x6` como única presentación de referencia
- **Regla:** CAT-01; CAT-02; CAT-03; CAT-06; ADR-010

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

#### Scenario: Proveedor ausente, inexistente, inactivo o ajeno
- **WHEN** se envía `PRODUCTO_CREAR` sin proveedor, o con un proveedor que no existe en la organización del token, es ajeno o está inactivo
- **THEN** sin proveedor el contenido es inválido; inexistente o ajeno responde 404; inactivo se rechaza con `PROVEEDOR_INACTIVO`; en todos los casos no se crea ninguna fila
- **Regla:** CAT-01; CAT-06; INV-21; `design.md` D5 (del change 06)

#### Scenario: Sin consulta de proveedor registrada se rechaza
- **WHEN** se envía `PRODUCTO_CREAR` con un proveedor válido y la aplicación arrancó sin la consulta de proveedor registrada en `catalogo`
- **THEN** el comando falla por error de configuración y no se crea ninguna fila (nunca se acepta sin validar el proveedor)
- **Regla:** TR-10; `design.md` D9 (del change 06); ADR-025

#### Scenario: Versión anterior del comando sin proveedor
- **WHEN** se envía `PRODUCTO_CREAR` en la versión 1 del contenido, que no trae proveedor
- **THEN** el comando se rechaza por versión no admitida y no se crea ninguna fila
- **Regla:** `02` §6.6; `design.md` D6 (del change 06)

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

### Requirement: El producto registra su proveedor obligatorio
Cada producto DEBE registrar exactamente un proveedor de su organización (CAT-06). La base de datos DEBE impedir un producto sin proveedor y DEBE impedir que el proveedor pertenezca a otra organización, con una clave foránea compuesta que incluye `organizacion_id`. Los productos existentes antes de este cambio DEBEN quedar con proveedor antes de que la restricción de obligatoriedad se aplique (`design.md` D2 del change 06: un proveedor provisorio inactivo por organización, creado por la migración).

#### Scenario: La base rechaza un producto sin proveedor
- **WHEN** se intenta insertar o actualizar directamente un producto con proveedor nulo
- **THEN** la base rechaza la escritura por la restricción `NOT NULL`
- **Regla:** CAT-01; CAT-06; `03` §5 (obligatorio en etapa 1)

#### Scenario: La base rechaza un proveedor de otra organización
- **WHEN** se intenta escribir directamente un producto de A con el identificador de un proveedor de B
- **THEN** la base rechaza la escritura por la clave foránea compuesta
- **Regla:** INV-02; INV-21; `03` §2.4

#### Scenario: Los productos existentes quedan con proveedor al migrar
- **WHEN** la base tiene productos sin proveedor creados antes de este cambio y se aplica la migración
- **THEN** todos los productos quedan con un proveedor de su propia organización, la restricción de obligatoriedad queda aplicada y ningún otro dato del producto cambia
- **Regla:** CAT-06; `03` §17 (columna obligatoria en pasos); `design.md` D2 (del change 06)

### Requirement: Un producto se modifica y desactiva por comando
El sistema DEBE modificar código, nombre, categoría, marca, proveedor, unidad base, alícuota y actividad de un producto con `PRODUCTO_MODIFICAR`, cuyo contenido es el estado completo deseado e incluye el proveedor. Asignar un proveedor distinto del actual DEBE exigir que esté activo; conservar el proveedor actual DEBE aceptarse aunque esté inactivo. Un producto NO DEBE borrarse: se desactiva y PUEDE reactivarse (CAT-05). Desactivar un producto NO DEBE cambiar el estado de sus presentaciones. Cambiar el proveedor NO DEBE modificar los costos informados ya registrados.

#### Scenario: Desactivar y reactivar un producto
- **WHEN** el producto activo `Vino A` se envía con `PRODUCTO_MODIFICAR` con `activo = false` y luego con `activo = true`
- **THEN** el producto queda inactivo y luego activo, y sus presentaciones conservan su estado en ambos pasos
- **Regla:** CAT-05

#### Scenario: Cambiar la alícuota del producto
- **WHEN** el producto `Vino A` con alícuota `21%` se envía con `PRODUCTO_MODIFICAR` con alícuota `10,5%`
- **THEN** el producto queda con `10,5%`
- **Regla:** CAT-01 (alícuota de IVA por producto); VTA-03 (las ventas ya confirmadas congelan su alícuota)

#### Scenario: Cambiar el proveedor del producto
- **WHEN** `Vino A` tiene proveedor `Bodega Andina` con costos informados y se envía `PRODUCTO_MODIFICAR` con el proveedor activo `Bodega Sur`
- **THEN** el producto queda con `Bodega Sur` y los costos informados de `Bodega Andina` siguen existiendo sin cambios
- **Regla:** CAT-06; CST-03

#### Scenario: Asignar un proveedor inactivo
- **WHEN** se envía `PRODUCTO_MODIFICAR` sobre `Vino A` con un proveedor inactivo distinto del actual
- **THEN** el comando se rechaza con `PROVEEDOR_INACTIVO` y el producto no cambia
- **Regla:** CAT-05; `design.md` D5 (del change 06)

#### Scenario: Conservar un proveedor que quedó inactivo
- **WHEN** el proveedor actual de un producto está inactivo (por ejemplo, el proveedor provisorio que la migración asignó, `design.md` D2 del change 06) y se envía `PRODUCTO_MODIFICAR` que solo cambia el nombre, conservando ese proveedor
- **THEN** el comando queda `ACEPTADO`
- **Regla:** CAT-06; `design.md` D2 y D5 (del change 06)

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
El sistema DEBE listar productos de la organización con paginación por cursor y límite máximo por página, filtrables por texto (código o nombre), categoría, marca, actividad y proveedor (`proveedor_id`, filtro en el servidor; deuda nominada por el change 06, `design.md` del change 11), y DEBE devolver el detalle de un producto con todas sus presentaciones y cuál es la de referencia. El detalle DEBE incluir el proveedor asignado: `proveedor_id` y `proveedor_nombre`, este último obtenido mediante la consulta de proveedor que registra `proveedores` (`design.md` D9, D13 del change 06; ADR-025), sin que `catalogo` lea la tabla `proveedor` directamente y sin ampliar el permiso de `GET /proveedores/opciones` (D8 del change 06). `proveedor_nombre` se incluye tanto si el proveedor está activo como si está inactivo. Ninguna consulta DEBE devolver datos de otra organización.

#### Scenario: Listado paginado por cursor
- **GIVEN** más productos en A que el tamaño de página pedido
- **WHEN** se piden páginas sucesivas con el cursor devuelto
- **THEN** cada producto aparece exactamente una vez y la última página no devuelve cursor
- **Regla:** `02` §11 (paginación por cursor)

#### Scenario: Filtro por proveedor
- **GIVEN** en A los productos `Vino A` y `Cerveza B` del proveedor P y `Vino C` del proveedor Q
- **WHEN** se listan con `proveedor_id = P` y `activo = true`
- **THEN** se devuelven solo `Vino A` y `Cerveza B`, paginados por cursor
- **Regla:** CAT-06; `02` §11

#### Scenario: Filtro por proveedor de otra organización
- **WHEN** un usuario de A filtra por el `proveedor_id` de un proveedor de B
- **THEN** la respuesta es una lista vacía, sin revelar datos de B
- **Regla:** INV-21

#### Scenario: Detalle con presentación de referencia
- **WHEN** se pide el detalle de `Vino A`
- **THEN** se devuelven sus presentaciones con unidades, usos y actividad, `Caja x6` marcada como referencia, y el proveedor asignado con su nombre
- **Regla:** CAT-02; CAT-03; CAT-06

#### Scenario: Detalle de un producto con proveedor inactivo muestra su nombre
- **WHEN** se pide el detalle de un producto cuyo proveedor actual, `Bodega Sur`, está inactivo (por ejemplo, el proveedor provisorio de la migración, `design.md` D2 del change 06)
- **THEN** la respuesta incluye `proveedor_nombre = "Bodega Sur"` y no un texto genérico
- **Regla:** CAT-06; `design.md` D2, D5, D9 y D13 (opción B, change 06); ADR-025

#### Scenario: Producto de otra organización
- **WHEN** un usuario de A pide el detalle de un producto de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

### Requirement: Los textos obligatorios del producto no pueden quedar vacíos

El alta y la modificación de un producto DEBEN rechazar un `nombre` vacío o de solo espacios con `NOMBRE_INVALIDO` (422), una `unidad_base` vacía o de solo espacios con `VALOR_OBLIGATORIO` (422) y, en el alta de un producto o al agregar o modificar una presentación, un nombre de presentación vacío o de solo espacios con `NOMBRE_INVALIDO` (422). Los textos válidos DEBEN guardarse recortados. Un rechazo en cualquier presentación DEBE rechazar el producto entero sin escribir nada (INV-01). La regla vive en el dominio de catálogo: la importación de productos (change 10) la hereda sin repetirla (TR-10). Agregado por el change 10 (grupo 12) para cerrar una laguna del alta por pantalla.

#### Scenario: Nombre de producto en blanco

- **GIVEN** la organización A con categoría, proveedor y alícuota activos
- **WHEN** un usuario con `GESTIONAR_CATALOGO` envía `PRODUCTO_CREAR` con `nombre` = `   `
- **THEN** responde 422 con `NOMBRE_INVALIDO` y no se crea ningún producto
- **Regla:** CAT-01; INV-01

#### Scenario: Unidad base vacía

- **GIVEN** el mismo contexto
- **WHEN** se envía `PRODUCTO_CREAR` con `unidad_base` = ` `
- **THEN** responde 422 con `VALOR_OBLIGATORIO` y no se crea ningún producto
- **Regla:** CAT-01

#### Scenario: Nombre de presentación vacío

- **GIVEN** el mismo contexto y un producto con dos presentaciones, la segunda con nombre `  `
- **WHEN** se envía `PRODUCTO_CREAR`
- **THEN** responde 422 con `NOMBRE_INVALIDO` y no se crea el producto ni ninguna presentación
- **Regla:** CAT-02; INV-01

### Requirement: Una presentación usada en una compra congela sus unidades

Una presentación que figura en alguna línea de compra, confirmada o anulada, DEBE contar como usada para INV-18: `proveedores` DEBE registrar su verificador de uso en el puerto del catálogo (ADR-023), con el mismo patrón que el del costo informado (deuda nominada por los changes 05 y 06).

#### Scenario: INV-18 — presentación usada en una compra
- **GIVEN** la presentación `Caja x6` de `Vino A` usada en una compra y sin costos informados
- **WHEN** se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** se rechaza con `UNIDADES_CONGELADAS` y conserva 6 unidades
- **Regla:** INV-18; CAT-04; ADR-023

#### Scenario: La anulación no libera las unidades
- **GIVEN** la misma compra anulada
- **WHEN** se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** se rechaza con `UNIDADES_CONGELADAS`
- **Regla:** INV-18; TR-06

### Requirement: Un producto con stock no se desactiva

`PRODUCTO_MODIFICAR` que pasa un producto de activo a inactivo DEBE rechazarse con `PRODUCTO_CON_STOCK` (409), sin cambiar nada, si el producto tiene algún saldo de stock **distinto de cero** en cualquier ubicación de la organización, incluidos los saldos negativos; se mira cada saldo, no el stock total (CAT-05, ADR-038 puntos 4 y 5, `design.md` D4 del change 14). Reactivar un producto, o guardar uno que ya estaba inactivo sin cambiar su estado, NO DEBE disparar la comprobación. El catálogo DEBE consultar el stock sin depender del módulo de stock, por un verificador que ese módulo registra al arrancar; sin verificador registrado, la desactivación DEBE fallar con un error de configuración y NO DEBE aceptarse sin comprobar (`design.md` D4.1; ADR-023, ADR-025). La desactivación DEBE tomar el producto con bloqueo exclusivo, para serializarse con un movimiento de stock simultáneo: nunca DEBE quedar un producto inactivo con stock recién ingresado (`design.md` D4.2). Los productos que ya estaban inactivos con stock antes de esta regla NO se modifican: para vaciarlos se reactivan, se vacían y se vuelven a desactivar.

#### Scenario: Desactivar un producto con stock

- **GIVEN** "Vino Rosado" activo con 18 unidades en "Camioneta 1" y 0 en el depósito
- **WHEN** se envía `PRODUCTO_MODIFICAR` con `activo` falso
- **THEN** se rechaza con `PRODUCTO_CON_STOCK` (409) y el producto sigue activo
- **Regla:** CAT-05; ADR-038; `design.md` D4

#### Scenario: Desactivar un producto sin stock

- **GIVEN** "Vino Rosado" activo, con movimientos en el libro y todos sus saldos en 0
- **WHEN** se envía `PRODUCTO_MODIFICAR` con `activo` falso
- **THEN** se acepta y el producto queda inactivo
- **Regla:** CAT-05; `design.md` D4

#### Scenario: Saldos que se compensan

- **GIVEN** un producto activo con +5 en el depósito y −5 en "Camioneta 1" (stock total 0)
- **WHEN** se lo desactiva
- **THEN** se rechaza con `PRODUCTO_CON_STOCK`
- **Regla:** STK-04; `design.md` D4

#### Scenario: Saldo negativo

- **GIVEN** un producto activo con −12 en el depósito
- **WHEN** se lo desactiva
- **THEN** se rechaza con `PRODUCTO_CON_STOCK`
- **Regla:** STK-05; `design.md` D4

#### Scenario: Modificar otros datos de un producto con stock

- **GIVEN** un producto activo con stock
- **WHEN** se envía `PRODUCTO_MODIFICAR` cambiando el nombre y dejando `activo` verdadero
- **THEN** se acepta
- **Regla:** CAT-05; `design.md` D4

#### Scenario: Producto ya inactivo con stock

- **GIVEN** "Vino Blanco" inactivo desde antes de esta regla, con 6 unidades en el depósito
- **WHEN** se envía `PRODUCTO_MODIFICAR` dejándolo inactivo, y después otro reactivándolo
- **THEN** ambos se aceptan; ya activo, no puede volver a desactivarse hasta que su saldo sea 0
- **Regla:** CAT-05; `design.md` D4

#### Scenario: Sin verificador de stock registrado

- **GIVEN** el catálogo sin ningún verificador de stock registrado
- **WHEN** se desactiva un producto
- **THEN** la operación falla con un error de configuración y el producto sigue activo
- **Regla:** TR-10; ADR-025; `design.md` D4.1

#### Scenario: Stock de otra organización

- **GIVEN** un producto de la organización A sin stock y un producto de la organización B con stock
- **WHEN** la organización A desactiva el suyo
- **THEN** se acepta: solo cuentan los saldos de su organización
- **Regla:** INV-21; SEG-07

#### Scenario: Desactivación e ingreso simultáneos

- **GIVEN** un producto activo sin stock, su desactivación y, a la vez, una transferencia que le ingresa 6 unidades en "Camioneta 1"
- **WHEN** las dos transacciones confirman
- **THEN** o la desactivación falla con `PRODUCTO_CON_STOCK`, o la transferencia falla con `PRODUCTO_INACTIVO`; nunca queda un producto inactivo con stock
- **Regla:** CAT-05; ADR-038; `design.md` D4.2
