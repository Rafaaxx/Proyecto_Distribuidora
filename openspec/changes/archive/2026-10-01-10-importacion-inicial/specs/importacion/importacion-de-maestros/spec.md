## Purpose

Dar de alta en bloque, desde planillas, los proveedores, los productos con sus presentaciones, los clientes y los costos informados de la organización, aplicando exactamente las mismas reglas que sus comandos de alta individuales y resolviendo las referencias por claves naturales visibles para el usuario.

## ADDED Requirements

### Requirement: Mismas reglas que el alta individual

Cada fila de una importación de maestros DEBE validarse y escribirse con las mismas reglas que el alta individual de su entidad (`PROVEEDOR_CREAR`, `PRODUCTO_CREAR`, `CLIENTE_CREAR`, `COSTO_INFORMAR`) y DEBE producir, ante el mismo dato inválido, el mismo código de error, asociado a su número de fila y columna (TR-10). Un registro creado por importación NO DEBE distinguirse de uno creado por pantalla, salvo por su `operation_id`.

#### Scenario: Mismo error que la pantalla

- **GIVEN** una planilla de proveedores cuya fila 2 tiene `cuit` = `20-1234`
- **WHEN** se importa
- **THEN** el informe muestra fila 2, columna `cuit`, `CUIT_INVALIDO`, el mismo código que devuelve el alta individual
- **Regla:** TR-10

### Requirement: Solo altas, sin modificar existentes

Una importación de maestros DEBE crear registros nuevos y NO DEBE modificar ninguno existente (`design.md` D6). Una fila cuya clave natural ya existe en la organización DEBE dar el error de duplicado de su entidad (`NOMBRE_DUPLICADO`, `CUIT_DUPLICADO`, `CODIGO_DUPLICADO`, `DOCUMENTO_DUPLICADO`). Dos filas del mismo archivo con la misma clave natural DEBEN dar `FILA_DUPLICADA` en la segunda, citando la primera.

#### Scenario: Producto ya existente

- **GIVEN** el producto de código `VA-750` ya cargado por pantalla
- **WHEN** se importa una planilla de productos con una fila `VA-750`
- **THEN** esa fila da `CODIGO_DUPLICADO` y el producto existente no cambia
- **Regla:** CAT-01; `design.md` D6

#### Scenario: Clave repetida dentro del archivo

- **GIVEN** una planilla de proveedores con "Bodega Sur" en las filas 2 y 5
- **WHEN** se importa
- **THEN** la fila 5 da `FILA_DUPLICADA` indicando la fila 2
- **Regla:** `design.md` D6

### Requirement: Referencias por claves naturales

Las referencias DEBEN resolverse dentro de la organización del token (INV-21) por las claves naturales de `design.md` D4: categoría y marca por nombre, alícuota por porcentaje, proveedor por nombre, producto por código, presentación por nombre dentro de su producto, cliente por código o por documento, ubicación por nombre; la comparación no distingue mayúsculas ni espacios al borde, y una clave que coincide con más de un registro DEBE dar `REFERENCIA_AMBIGUA`. Una referencia que no existe en la organización, o que existe solo en otra, DEBE dar `REFERENCIA_NO_ENCONTRADA` en la fila y columna, sin revelar si existe en otra organización. Una referencia a una entidad inactiva DEBE dar el código de inactivo de la regla de destino (`CATEGORIA_INACTIVA`, `MARCA_INACTIVA`, `ALICUOTA_INACTIVA`, `PROVEEDOR_INACTIVO`, `PRODUCTO_INACTIVO`).

#### Scenario: Categoría inexistente

- **GIVEN** una planilla de productos con `categoria` = "Vinoss" y ninguna categoría con ese nombre
- **WHEN** se importa
- **THEN** la fila da `REFERENCIA_NO_ENCONTRADA` en `categoria` y no se crea ninguna categoría
- **Regla:** CAT-01; `design.md` D4

#### Scenario: Proveedor de otra organización

- **GIVEN** un proveedor "Bodega Sur" que existe solo en otra organización
- **WHEN** una planilla de productos lo referencia
- **THEN** la fila da `REFERENCIA_NO_ENCONTRADA`, igual que si no existiera en ninguna
- **Regla:** INV-21; TR-08

#### Scenario: Alícuota por porcentaje

- **GIVEN** las alícuotas activas 21%, 10,5% y 0%
- **WHEN** una fila de productos trae `alicuota` = `10,5`
- **THEN** el producto queda con la alícuota de 10,5%
- **Regla:** CAT-01; `01` §4

### Requirement: Importar proveedores

La planilla de proveedores DEBE tener las columnas `nombre` (obligatoria), `cuit`, `contacto`, `telefono` y `email`. Cada proveedor DEBE nacer activo, con las validaciones del alta individual (nombre normalizado y único, CUIT de 11 dígitos y único si se informa).

#### Scenario: Dos proveedores válidos

- **GIVEN** una planilla con "Bodega Sur" (CUIT `30-71234567-8`) y "Cervecería Norte" sin CUIT
- **WHEN** se importa
- **THEN** existen los dos proveedores activos y "Bodega Sur" tiene el CUIT normalizado a 11 dígitos
- **Regla:** `design.md` D6

#### Scenario: CUIT repetido con un proveedor existente

- **GIVEN** un proveedor existente con CUIT `30712345678`
- **WHEN** una fila trae el mismo CUIT con guiones
- **THEN** la fila da `CUIT_DUPLICADO`
- **Regla:** `03` §6 (`ux_proveedor__cuit`)

### Requirement: Importar productos con sus presentaciones

La planilla de productos DEBE describir cada producto con sus presentaciones según `design.md` D5 (recomendado: una fila por presentación, agrupadas por `codigo`, con los datos del producto repetidos). Cada producto DEBE cumplir CAT-01 (código único, nombre, categoría, marca opcional, unidad base, alícuota y proveedor), CAT-02 (unidades base entero ≥ 1, uso en venta y en compra) y CAT-03 (exactamente una presentación de referencia, de venta). Las filas de un mismo `codigo` con datos de producto distintos DEBEN dar `PRODUCTO_INCONSISTENTE`. Un error en cualquier presentación de un producto DEBE impedir el alta de ese producto entero, y el informe DEBE señalar la fila de la presentación.

#### Scenario: Vino con caja y botella

- **GIVEN** dos filas `VA-750` "Vino A", proveedor "Bodega Sur": "Caja x6" de 6 unidades, referencia, venta y compra; "Botella" de 1 unidad, venta
- **WHEN** se importa
- **THEN** existe Vino A con dos presentaciones y la caja x6 como referencia
- **Regla:** CAT-02; CAT-03; CAT-07

#### Scenario: Producto sin referencia

- **GIVEN** las filas de `CB-473` sin ninguna presentación marcada como referencia
- **WHEN** se importa
- **THEN** la primera fila del producto da `REFERENCIA_INVALIDA` y el producto no se crea
- **Regla:** CAT-03

#### Scenario: Referencia que no es de venta

- **GIVEN** una fila con `es_referencia` = `S` y `usar_en_venta` = `N`
- **WHEN** se importa
- **THEN** la fila da `REFERENCIA_INVALIDA`
- **Regla:** CAT-03

#### Scenario: Datos de producto contradictorios entre filas

- **GIVEN** dos filas de `VA-750`, una con categoría "Vinos" y otra con "Espumantes"
- **WHEN** se importa
- **THEN** la segunda fila da `PRODUCTO_INCONSISTENTE`
- **Regla:** CAT-01; `design.md` D5

#### Scenario: Unidades inválidas

- **GIVEN** una presentación con `unidades_base` = `0`
- **WHEN** se importa
- **THEN** la fila da `UNIDADES_INVALIDAS`
- **Regla:** CAT-02; INV-04

### Requirement: Importar clientes

La planilla de clientes DEBE tener las columnas de la ficha de alta (`nombre`, `codigo`, `razon_social`, `documento_tipo`, `documento_numero`, `direccion`, `contacto`, `telefono`, `email`, `estado_facturacion_default`), con la obligatoriedad de `design.md` D6 (recomendado: `codigo` obligatorio en la planilla). Cada cliente DEBE nacer `ACTIVO`, sin datos de crédito (heredan los de la organización) y sin lista asignada, como en el alta individual. Los documentos DEBEN validarse y normalizarse según CLI-05.

#### Scenario: Cliente con CUIT

- **GIVEN** una fila con código `C001`, documento CUIT `20-12345678-9`, dirección y contacto
- **WHEN** se importa
- **THEN** existe el cliente `C001` `ACTIVO` con documento `20123456789` y sin límite propio
- **Regla:** CLI-01; CLI-05

#### Scenario: DNI de longitud inválida

- **GIVEN** una fila con documento DNI `123456`
- **WHEN** se importa
- **THEN** la fila da `DOCUMENTO_INVALIDO`
- **Regla:** CLI-05

#### Scenario: Ficha incompleta

- **GIVEN** una fila sin `direccion`
- **WHEN** se importa
- **THEN** la fila da `FICHA_INCOMPLETA` en `direccion`
- **Regla:** CLI-01

### Requirement: Importar costos informados

La planilla de costos DEBE tener las columnas `producto_codigo`, `presentacion`, `valor`, `incluye_iva`, `bonificacion` (porcentaje, opcional), `vigencia_desde` y `observacion` (opcional); el proveedor es el proveedor actual del producto (CAT-06). Cada fila DEBE registrarse por el mismo camino que `COSTO_INFORMAR`: costo base derivado según CST-02, sin sobrescribir costos anteriores (CST-03), con presentación de compra activa del producto, y DEBE congelar las unidades de esa presentación (INV-18). Esta capacidad existe solo si `design.md` D8 confirma que la importación de costos entra en la etapa 1.

#### Scenario: Costo por caja sin IVA

- **GIVEN** Cerveza B con presentación "Caja x12" de compra
- **WHEN** se importa una fila con `valor` = `18000`, `incluye_iva` = `N`, sin bonificación
- **THEN** queda un costo informado con costo base `"1500.000000"`
- **Regla:** CST-01; CST-02

#### Scenario: Costo con IVA incluido

- **GIVEN** Cerveza B con alícuota 21% y "Caja x12" de compra
- **WHEN** se importa `valor` = `18000`, `incluye_iva` = `S`
- **THEN** el costo base es `"1239.669421"`
- **Regla:** CST-02

#### Scenario: Costo con bonificación

- **WHEN** se importa `valor` = `18000`, `incluye_iva` = `N`, `bonificacion` = `10`
- **THEN** el costo base es `"1350.000000"`
- **Regla:** CST-02; TR-02

#### Scenario: Presentación que no es de compra

- **GIVEN** la presentación "Botella" de Vino A, solo de venta
- **WHEN** una fila de costos la usa
- **THEN** la fila da `PRESENTACION_INVALIDA`
- **Regla:** CST-01

#### Scenario: La presentación con costo queda congelada

- **GIVEN** un costo importado sobre "Caja x12" de Cerveza B
- **WHEN** después se intenta cambiar sus unidades por pantalla
- **THEN** se rechaza con `UNIDADES_CONGELADAS`
- **Regla:** INV-18; CAT-04
