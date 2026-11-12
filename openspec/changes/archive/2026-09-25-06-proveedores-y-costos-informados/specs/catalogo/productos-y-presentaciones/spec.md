## MODIFIED Requirements

### Requirement: Productos y presentaciones se consultan por organización
El sistema DEBE listar productos de la organización con paginación por cursor y límite máximo por página, filtrables por texto (código o nombre), categoría, marca y actividad, y DEBE devolver el detalle de un producto con todas sus presentaciones y cuál es la de referencia. El detalle DEBE incluir el proveedor asignado: `proveedor_id` y `proveedor_nombre`, este último obtenido mediante la consulta de proveedor que registra `proveedores` (`design.md` D9, D13; ADR-025), sin que `catalogo` lea la tabla `proveedor` directamente y sin ampliar el permiso de `GET /proveedores/opciones` (D8). `proveedor_nombre` se incluye tanto si el proveedor está activo como si está inactivo. Ninguna consulta DEBE devolver datos de otra organización.

#### Scenario: Listado paginado por cursor
- **GIVEN** más productos en A que el tamaño de página pedido
- **WHEN** se piden páginas sucesivas con el cursor devuelto
- **THEN** cada producto aparece exactamente una vez y la última página no devuelve cursor
- **Regla:** `02` §11 (paginación por cursor)

#### Scenario: Detalle con presentación de referencia
- **WHEN** se pide el detalle de `Vino A`
- **THEN** se devuelven sus presentaciones con unidades, usos y actividad, `Caja x6` marcada como referencia, y el proveedor asignado con su nombre
- **Regla:** CAT-02; CAT-03; CAT-06

#### Scenario: Detalle de un producto con proveedor inactivo muestra su nombre
- **WHEN** se pide el detalle de un producto cuyo proveedor actual, `Bodega Sur`, está inactivo (por ejemplo, el proveedor provisorio de la migración, `design.md` D2)
- **THEN** la respuesta incluye `proveedor_nombre = "Bodega Sur"` y no un texto genérico
- **Regla:** CAT-06; `design.md` D2, D5, D9 y D13 (opción B); ADR-025

#### Scenario: Producto de otra organización
- **WHEN** un usuario de A pide el detalle de un producto de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

### Requirement: Un producto se crea con sus presentaciones en un solo comando
El sistema DEBE crear un producto con el comando `PRODUCTO_CREAR` (`ONLINE`, `GESTIONAR_CATALOGO`), cuyo contenido incluye código, nombre, categoría, marca opcional, proveedor, unidad base, alícuota de IVA y al menos una presentación, exactamente una de ellas marcada como referencia. El proveedor es obligatorio y DEBE existir activo en la organización (CAT-01, CAT-06); `catalogo` lo valida con la clave foránea compuesta y con la consulta de proveedor que registra `proveedores`, sin importarlo (`design.md` D9; ADR-025). El producto y todas sus presentaciones DEBEN registrarse completos o no registrarse (INV-01). El producto y sus presentaciones nacen activos. La versión del contenido sin proveedor deja de aceptarse (`design.md` D6).

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
- **Regla:** CAT-01; CAT-06; INV-21; `design.md` D5

#### Scenario: Sin consulta de proveedor registrada se rechaza
- **WHEN** se envía `PRODUCTO_CREAR` con un proveedor válido y la aplicación arrancó sin la consulta de proveedor registrada en `catalogo`
- **THEN** el comando falla por error de configuración y no se crea ninguna fila (nunca se acepta sin validar el proveedor)
- **Regla:** TR-10; `design.md` D9; ADR-025

#### Scenario: Versión anterior del comando sin proveedor
- **WHEN** se envía `PRODUCTO_CREAR` en la versión 1 del contenido, que no trae proveedor
- **THEN** el comando se rechaza por versión no admitida y no se crea ninguna fila
- **Regla:** `02` §6.6; `design.md` D6

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
- **Regla:** CAT-05; `design.md` D5

#### Scenario: Conservar un proveedor que quedó inactivo
- **WHEN** el proveedor actual de un producto está inactivo (por ejemplo, el proveedor provisorio que la migración asignó, `design.md` D2) y se envía `PRODUCTO_MODIFICAR` que solo cambia el nombre, conservando ese proveedor
- **THEN** el comando queda `ACEPTADO`
- **Regla:** CAT-06; `design.md` D2 y D5

#### Scenario: Producto inexistente o de otra organización
- **WHEN** un usuario de A envía `PRODUCTO_MODIFICAR` sobre un producto de B
- **THEN** la respuesta es 404 y el producto de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: No existe borrado de productos
- **WHEN** se busca en la API cualquier operación que elimine un producto o una presentación
- **THEN** no existe, y el usuario de aplicación de la base no tiene `DELETE` sobre `producto` ni `presentacion`
- **Regla:** CAT-05; TR-06

## ADDED Requirements

### Requirement: El producto registra su proveedor obligatorio
Cada producto DEBE registrar exactamente un proveedor de su organización (CAT-06). La base de datos DEBE impedir un producto sin proveedor y DEBE impedir que el proveedor pertenezca a otra organización, con una clave foránea compuesta que incluye `organizacion_id`. Los productos existentes antes de este cambio DEBEN quedar con proveedor antes de que la restricción de obligatoriedad se aplique (`design.md` D2: un proveedor provisorio inactivo por organización, creado por la migración).

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
- **Regla:** CAT-06; `03` §17 (columna obligatoria en pasos); `design.md` D2

## REMOVED Requirements

### Requirement: El producto registra su proveedor único
**Reason**: Era la versión transitoria del change 05 (`design.md` D1 del 05-catalogo): el proveedor no podía informarse ni validarse porque la tabla `proveedor` no existía. Este change crea la tabla y hace el proveedor obligatorio.
**Migration**: Reemplazado por "El producto registra su proveedor obligatorio" (ADDED en este change) y por el proveedor obligatorio de `PRODUCTO_CREAR`/`PRODUCTO_MODIFICAR` v2. Los productos existentes sin proveedor se completan en la migración (`design.md` D2).
