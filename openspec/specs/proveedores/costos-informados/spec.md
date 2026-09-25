# Costos Informados Specification

## Purpose

Define el registro de costos informados por los proveedores: en cualquier presentación de compra, con o sin IVA y con bonificación opcional, con vigencia desde; su conversión a costo base por unidad base (CST-02, calculado igual en servidor y cliente), su inmutabilidad (CST-03), la resolución del costo vigente a una fecha y el historial por producto. Es la entrada de costos de precios (PRC-11) y no se usa para costear ventas (CST-04).

## Requirements

### Requirement: Un costo informado se registra por comando con su costo base derivado
El sistema DEBE registrar costos informados con el comando `COSTO_INFORMAR` (`ONLINE`, permiso `EDITAR_COSTOS`). Cada costo registra proveedor, producto, presentación, valor por presentación, si incluye IVA, bonificación opcional como fracción (default `0`), vigencia desde (fecha) y observación opcional (CST-01). El servidor DEBE congelar en el costo la alícuota vigente del producto al registrarlo y DEBE calcular y guardar el costo base con la fórmula de CST-02, redondeado a 6 decimales con `ROUND_HALF_UP` una sola vez al final. Valor, bonificación, alícuota y costo base DEBEN viajar como string en JSON.

#### Scenario: Caja x12 sin IVA
- **GIVEN** el producto activo `Cerveza B` del proveedor activo `Distribuidora Norte`, con la presentación activa de compra `Caja x12` (12 unidades) y alícuota `21%`
- **WHEN** un usuario con `EDITAR_COSTOS` envía `COSTO_INFORMAR` con `Caja x12` a `"18000.00"`, sin IVA, sin bonificación, vigencia desde `2026-09-01`
- **THEN** el comando queda `ACEPTADO` y el costo queda registrado con costo base `"1500.000000"`, alícuota aplicada `"0.210000"` y una sola fila de auditoría con el `operation_id`
- **Regla:** CST-01; CST-02 (ejemplo 1); AUD-01

#### Scenario: Botella sin IVA
- **GIVEN** el producto `Vino A` con la presentación de compra `Botella` (1 unidad)
- **WHEN** se informa `Botella` a `"1000.00"`, sin IVA, sin bonificación
- **THEN** el costo base es `"1000.000000"`
- **Regla:** CST-02 (ejemplo 2); ADR-010 (cualquier presentación)

#### Scenario: Caja x12 con IVA incluido
- **GIVEN** `Cerveza B` con alícuota `21%` y `Caja x12`
- **WHEN** se informa `Caja x12` a `"18000.00"` con IVA incluido
- **THEN** el costo base es `"1239.669421"` (18.000 / 1,21 / 12, redondeado solo al final) y la alícuota aplicada `"0.210000"`
- **Regla:** CST-02 (ejemplo 3); TR-03

#### Scenario: Caja x12 con bonificación
- **GIVEN** `Cerveza B` y `Caja x12`
- **WHEN** se informa `Caja x12` a `"18000.00"`, sin IVA, con bonificación `"0.100000"`
- **THEN** el costo base es `"1350.000000"` (18.000 × 0,9 / 12)
- **Regla:** CST-02 (ejemplo 4); TR-02

#### Scenario: Doble envío no duplica el costo
- **GIVEN** un `COSTO_INFORMAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y el costo existe una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con otro valor
- **GIVEN** un `COSTO_INFORMAR` aceptado con `operation_id` X y valor `"18000.00"`
- **WHEN** se reenvía con `operation_id` X y valor `"19000.00"`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y no se registra el costo de `"19000.00"`
- **Regla:** SYN-02

#### Scenario: Sin permiso para editar costos
- **GIVEN** un usuario sin `EDITAR_COSTOS` (rol Supervisor comercial)
- **WHEN** envía `COSTO_INFORMAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se registra ningún costo
- **Regla:** `01` §19 (`EDITAR_COSTOS`)

#### Scenario: Valor o bonificación inválidos
- **GIVEN** `Cerveza B` y `Caja x12`
- **WHEN** se informa un valor `"0.00"`, negativo o con más de 2 decimales, o una bonificación negativa, mayor o igual a `"1"` o con más de 6 decimales
- **THEN** se rechaza con `VALOR_INVALIDO` o `BONIFICACION_INVALIDA` y no se registra ningún costo
- **Regla:** TR-01; TR-02; TR-10

### Requirement: El costo se informa sobre una presentación de compra activa del producto y del proveedor del producto
La presentación DEBE pertenecer al producto, estar activa y usarse en compra. El producto DEBE estar activo. El proveedor DEBE estar activo y DEBE ser el proveedor actual del producto (`design.md` D3). Un producto, presentación o proveedor inexistente o de otra organización DEBE responder 404.

#### Scenario: Presentación que no es de compra, inactiva o de otro producto
- **GIVEN** `Vino A` con `Caja x6` solo de venta, una presentación inactiva, y la `Caja x12` de `Cerveza B`
- **WHEN** se informa un costo de `Vino A` sobre cualquiera de ellas
- **THEN** se rechaza con `PRESENTACION_INVALIDA` y no se registra ningún costo
- **Regla:** ADR-010 (presentaciones de compra); `00` §5 (cualquier presentación de compra); CAT-05

#### Scenario: Producto o proveedor inactivo
- **GIVEN** un producto inactivo, o un proveedor inactivo
- **WHEN** se informa un costo que los usa
- **THEN** se rechaza con `PRODUCTO_INACTIVO` o `PROVEEDOR_INACTIVO` y no se registra ningún costo
- **Regla:** CAT-05; `design.md` D5

#### Scenario: Proveedor distinto del proveedor del producto
- **GIVEN** `Cerveza B` cuyo proveedor es `Distribuidora Norte`, y el proveedor activo `Bodega Andina`
- **WHEN** se informa un costo de `Cerveza B` con proveedor `Bodega Andina`
- **THEN** se rechaza con `PROVEEDOR_NO_CORRESPONDE` y no se registra ningún costo
- **Regla:** CAT-06 (un único proveedor por producto en etapa 1); `design.md` D3

#### Scenario: Referencias de otra organización
- **GIVEN** un proveedor, producto o presentación de B
- **WHEN** un usuario de A informa un costo que los usa
- **THEN** la respuesta es 404 y no se registra ningún costo
- **Regla:** INV-21; SEG-07

### Requirement: Varios costos de un proveedor se registran en una sola operación
`COSTO_INFORMAR` DEBE admitir uno o varios costos del mismo proveedor, cada uno con su producto, presentación, valor, IVA, bonificación, vigencia y observación, con un máximo de 200 costos por operación (`design.md` D12). Todos los costos de la operación DEBEN registrarse o ninguno. Una operación sin costos, o con dos costos del mismo producto, presentación y vigencia, DEBE rechazarse.

#### Scenario: Dos costos en una operación
- **GIVEN** `Cerveza B` (`Caja x12`) y `Vino A` (`Botella`), ambos de `Distribuidora Norte`
- **WHEN** se envía un `COSTO_INFORMAR` con `Caja x12` a `"18000.00"` sin IVA y `Botella` a `"1000.00"` sin IVA
- **THEN** quedan registrados los dos costos con costos base `"1500.000000"` y `"1000.000000"`, con el mismo `operation_id`
- **Regla:** CST-05; CST-02

#### Scenario: INV-01 — una falla en un costo no deja los demás
- **GIVEN** una operación con tres costos cuyo tercero usa una presentación que no es de compra
- **WHEN** se procesa el `COSTO_INFORMAR`
- **THEN** se rechaza con `PRESENTACION_INVALIDA` y no queda registrado ninguno de los tres
- **Regla:** INV-01; CST-05

#### Scenario: Operación vacía o con costos repetidos
- **GIVEN** un proveedor activo
- **WHEN** se envía `COSTO_INFORMAR` sin costos, con más de 200 costos, o con dos costos del mismo producto, presentación y vigencia desde
- **THEN** se rechaza con `COSTOS_INVALIDOS` y no se registra ningún costo
- **Regla:** CST-05; `design.md` D12

### Requirement: Los costos informados no se sobrescriben
Un costo informado registrado NO DEBE modificarse ni borrarse; un costo nuevo NO DEBE alterar los anteriores. El usuario de aplicación de la base NO DEBE tener `UPDATE` ni `DELETE` sobre la tabla de costos informados. El costo guardado DEBE conservar la alícuota aplicada y el costo base con que se registró aunque después cambie la alícuota del producto.

#### Scenario: Un costo nuevo no altera el anterior
- **GIVEN** el costo de `Caja x12` a `"18000.00"` con vigencia `2026-09-01`
- **WHEN** se informa `Caja x12` a `"18000.00"` con bonificación `"0.100000"` y vigencia `2026-10-01`
- **THEN** ambos costos existen y el primero conserva todos sus valores
- **Regla:** CST-03; TR-06

#### Scenario: La base impide modificar o borrar un costo
- **GIVEN** un costo informado registrado
- **WHEN** el usuario de aplicación intenta `UPDATE` o `DELETE` directo sobre él
- **THEN** la base lo rechaza por falta de permiso
- **Regla:** CST-03; TR-06

#### Scenario: Cambiar la alícuota del producto no recalcula costos pasados
- **GIVEN** un costo con IVA incluido registrado con alícuota aplicada `"0.210000"` y costo base `"1239.669421"`
- **WHEN** la alícuota del producto cambia a `10,5%`
- **THEN** el costo conserva alícuota aplicada `"0.210000"` y costo base `"1239.669421"`
- **Regla:** CST-03; `03` §6 (`alicuota_aplicada` congelada)

### Requirement: El costo vigente de un producto se resuelve por fecha
El costo informado vigente de un producto para una fecha DEBE ser el de mayor vigencia desde que no supere esa fecha (CST-03). Si dos costos del producto tienen la misma vigencia desde, DEBE prevalecer el registrado último (`design.md` D4). Si ninguno alcanza la fecha, el producto no tiene costo vigente. La fecha por defecto es la fecha de negocio actual en la zona horaria de la organización (TR-04). Las vigencias futuras se aceptan y no son vigentes hasta su fecha. La consulta DEBE exigir `VER_COSTOS`.

#### Scenario: Vigente entre dos vigencias
- **GIVEN** costos de `Cerveza B` con vigencia `2026-09-01` (costo base `"1500.000000"`) y `2026-10-01` (costo base `"1350.000000"`)
- **WHEN** se consulta el costo vigente para `2026-09-15`, para `2026-10-01` y para `2026-08-31`
- **THEN** se obtiene `"1500.000000"`, `"1350.000000"` y "sin costo vigente" respectivamente
- **Regla:** CST-03

#### Scenario: Misma vigencia desde
- **GIVEN** dos costos de `Cerveza B` con vigencia `2026-09-01`, registrados en ese orden con costos base `"1500.000000"` y `"1350.000000"`
- **WHEN** se consulta el costo vigente para `2026-09-01`
- **THEN** se obtiene `"1350.000000"`
- **Regla:** CST-03; `design.md` D4

#### Scenario: Consulta sin permiso de ver costos
- **GIVEN** un usuario sin `VER_COSTOS` (rol Vendedor)
- **WHEN** pide el costo vigente o el historial de un producto
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19 (`VER_COSTOS`); `01` §19 (el vendedor no ve costos)

### Requirement: El historial de costos de un producto se consulta completo
El sistema DEBE devolver el historial de costos informados de un producto, paginado por cursor, ordenado de la vigencia más reciente a la más antigua, con lo informado (proveedor, presentación, valor, IVA, bonificación, vigencia, observación), la alícuota aplicada, el costo base derivado, el usuario y el momento de registro. Ninguna consulta DEBE devolver costos de otra organización.

#### Scenario: Historial ordenado
- **GIVEN** los dos costos de `Cerveza B` con vigencias `2026-09-01` y `2026-10-01`
- **WHEN** se pide el historial de `Cerveza B`
- **THEN** aparecen primero el de `2026-10-01` y luego el de `2026-09-01`, cada uno con lo informado y su costo base
- **Regla:** CST-01; CST-03

#### Scenario: Historial de un producto ajeno
- **GIVEN** un producto de B con costos
- **WHEN** un usuario de A pide su historial o su costo vigente
- **THEN** la respuesta es 404
- **Regla:** INV-21

### Requirement: El costo base se calcula igual en el servidor y en el cliente
La fórmula de CST-02 DEBE existir como función pura en el backend y en el frontend, y ambas DEBEN pasar el mismo conjunto de casos compartidos, que incluye los cuatro ejemplos de `01` §6.1. El cálculo del cliente es solo una vista previa; el valor registrado es siempre el del servidor.

#### Scenario: Los ejemplos de CST-02 pasan en ambas suites
- **GIVEN** los casos compartidos de costo base
- **WHEN** corren pytest y Vitest
- **THEN** ambas suites obtienen `"1500.000000"`, `"1000.000000"`, `"1239.669421"` y `"1350.000000"` para los cuatro ejemplos de `01` §6.1
- **Regla:** CST-02; ADR-016

#### Scenario: Redondeo solo al final
- **GIVEN** una caja x12 informada a `"10000.00"` sin IVA ni bonificación
- **WHEN** se calcula el costo base en ambas suites
- **THEN** el resultado es `"833.333333"`
- **Regla:** CST-02; TR-03; ADR-010 (ejemplo $10.000 / 12)

### Requirement: Un costo informado congela las unidades de su presentación
Una presentación sobre la que se registró al menos un costo informado DEBE considerarse usada: sus unidades base NO DEBEN modificarse (`design.md` D1: `proveedores` registra su verificador en el puerto de ADR-023).

#### Scenario: INV-18 — presentación con costo informado
- **GIVEN** la `Caja x12` de `Cerveza B` con un costo informado registrado
- **WHEN** se envía `PRESENTACION_MODIFICAR` sobre `Caja x12` con 24 unidades
- **THEN** se rechaza con `UNIDADES_CONGELADAS` y la presentación conserva 12 unidades
- **Regla:** INV-18; CAT-04; ADR-023

#### Scenario: Presentación sin costos sigue editable
- **GIVEN** la presentación `Pack x24` de `Cerveza B` sin costos ni otras operaciones
- **WHEN** se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** la presentación queda con 12 unidades
- **Regla:** CAT-04
