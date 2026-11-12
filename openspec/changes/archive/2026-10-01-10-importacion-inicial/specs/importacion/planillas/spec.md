## Purpose

Definir cómo el sistema lee una planilla de importación (CSV o Excel): encabezados, conversión exacta de números, fechas y booleanos sin punto flotante, límites del archivo y plantillas descargables, de modo que toda fila llegue a las reglas de negocio con valores exactos o con un error identificable por fila y columna.

## ADDED Requirements

### Requirement: Formatos de archivo admitidos

El sistema DEBE aceptar archivos CSV codificados en UTF-8 (con o sin BOM) o Windows-1252, con separador coma o punto y coma detectado en el encabezado, y archivos Excel `.xlsx` (primera hoja), según `design.md` D2/D3. Cualquier otro formato, un archivo vacío o ilegible DEBE rechazarse completo con `ARCHIVO_INVALIDO` (422) sin procesar ninguna fila.

#### Scenario: CSV en UTF-8 aceptado

- **GIVEN** un Administrador y un CSV UTF-8 de proveedores con encabezado y dos filas válidas
- **WHEN** lo importa
- **THEN** el archivo se lee y sus dos filas pasan a validación
- **Regla:** `design.md` D2

#### Scenario: CSV guardado por Excel en español

- **GIVEN** un CSV en Windows-1252 con separador punto y coma y un proveedor "Cervecería Ñandú"
- **WHEN** se importa
- **THEN** el nombre se lee "Cervecería Ñandú" y las columnas se separan por punto y coma
- **Regla:** `design.md` D2

#### Scenario: Excel aceptado

- **GIVEN** un `.xlsx` de proveedores cuya primera hoja tiene encabezado y dos filas válidas
- **WHEN** lo importa
- **THEN** se leen las dos filas de la primera hoja
- **Regla:** `design.md` D2

#### Scenario: Formato no admitido

- **GIVEN** un archivo `.pdf` o un `.xls` antiguo
- **WHEN** se intenta importar
- **THEN** se rechaza con `ARCHIVO_INVALIDO` y no se escribe nada
- **Regla:** INV-01; `design.md` D2

### Requirement: Encabezados fijos por tipo de importación

La primera fila DEBE ser el encabezado con los nombres de columna de la plantilla del tipo (sin distinguir mayúsculas ni espacios al borde). Una columna obligatoria faltante, una columna desconocida o una columna repetida DEBEN rechazar el archivo completo con `COLUMNAS_INVALIDAS` (422), indicando cuáles. El orden de las columnas NO DEBE importar. Las filas totalmente vacías DEBEN ignorarse.

#### Scenario: Falta una columna obligatoria

- **GIVEN** una planilla de productos sin la columna `codigo`
- **WHEN** se importa
- **THEN** se rechaza con `COLUMNAS_INVALIDAS` que nombra `codigo` y no se escribe nada
- **Regla:** CAT-01; INV-01

#### Scenario: Columna desconocida

- **GIVEN** una planilla de clientes con una columna `observaciones` que la plantilla no tiene
- **WHEN** se importa
- **THEN** se rechaza con `COLUMNAS_INVALIDAS` que nombra `observaciones`
- **Regla:** `design.md` D11

#### Scenario: Columnas en otro orden y filas vacías

- **GIVEN** una planilla de proveedores con las columnas en otro orden y una fila vacía en el medio
- **WHEN** se importa
- **THEN** se lee igual que con el orden de la plantilla y la fila vacía no cuenta como error ni como fila
- **Regla:** `design.md` D11

### Requirement: Número de fila del informe

Toda fila DEBE identificarse en el informe por su número en la planilla tal como lo ve el usuario (el encabezado es la fila 1; la primera fila de datos, la 2), incluso cuando hay filas vacías intermedias.

#### Scenario: Error en la tercera fila de datos

- **GIVEN** una planilla con encabezado y tres filas de datos, la tercera con un CUIT inválido
- **WHEN** se importa
- **THEN** el informe señala la fila 4, columna `cuit`, código `CUIT_INVALIDO`
- **Regla:** `design.md` D1

### Requirement: Números decimales exactos

Los importes, costos, valores y porcentajes DEBEN leerse como decimales exactos, nunca como punto flotante binario (TR-01, TR-02, INV-03). En los valores escritos como texto, el separador decimal DEBE ser la coma, sin separador de miles, según `design.md` D12; un valor con punto, con más de un separador o no numérico DEBE dar `NUMERO_INVALIDO` en esa fila y columna. Una celda numérica de Excel DEBE convertirse a decimal sin pasar por `float` (`design.md` D3). La cantidad de decimales admitida la decide la regla de destino (2 en importes, 6 en costos), sin redondear.

#### Scenario: Coma decimal

- **GIVEN** una fila de costos con `valor` = `18000,00`
- **WHEN** se lee
- **THEN** el valor es exactamente `"18000.00"`
- **Regla:** TR-01; `design.md` D12

#### Scenario: Punto ambiguo rechazado

- **GIVEN** una fila de saldos con `importe` = `1.500`
- **WHEN** se lee
- **THEN** la fila da `NUMERO_INVALIDO` en la columna `importe` (no se interpreta como 1,5 ni como 1500)
- **Regla:** TR-01; `design.md` D12

#### Scenario: Separador de miles rechazado

- **GIVEN** una fila de saldos con `importe` = `1.234,56`
- **WHEN** se lee
- **THEN** la fila da `NUMERO_INVALIDO` en la columna `importe`
- **Regla:** `design.md` D12

#### Scenario: Celda numérica de Excel sin error binario

- **GIVEN** un `.xlsx` con una celda numérica de costo `1239.669421`
- **WHEN** se lee
- **THEN** el costo es exactamente `"1239.669421"`, sin dígitos espurios de punto flotante
- **Regla:** INV-03; TR-02; `design.md` D3

### Requirement: Cantidades enteras

Las cantidades en unidad base y las unidades de presentación DEBEN ser enteros; un valor con decimales distintos de cero o no numérico DEBE dar `CANTIDAD_INVALIDA` en la fila (INV-04).

#### Scenario: Cantidad con decimales

- **GIVEN** una fila de stock inicial con `cantidad_base` = `10,5`
- **WHEN** se lee
- **THEN** la fila da `CANTIDAD_INVALIDA`
- **Regla:** INV-04

### Requirement: Fechas y booleanos

Las fechas DEBEN aceptarse como `AAAA-MM-DD`, `DD/MM/AAAA` o celda de fecha de Excel; otra forma DEBE dar `FECHA_INVALIDA`. Los booleanos DEBEN aceptar `S`, `SI`, `SÍ`, `N`, `NO` (sin distinguir mayúsculas); otro valor DEBE dar `VALOR_INVALIDO`.

#### Scenario: Fecha en formato local

- **GIVEN** una fila de costos con `vigencia_desde` = `01/10/2026`
- **WHEN** se lee
- **THEN** la vigencia es el 1 de octubre de 2026
- **Regla:** CST-01

#### Scenario: Booleano inválido

- **GIVEN** una fila de costos con `incluye_iva` = `quizás`
- **WHEN** se lee
- **THEN** la fila da `VALOR_INVALIDO` en `incluye_iva`
- **Regla:** CST-01

### Requirement: Celdas obligatorias

Una celda obligatoria vacía o de solo espacios (por ejemplo el `codigo` de un cliente o de un producto, `design.md` D6) DEBE dar `VALOR_OBLIGATORIO` en la fila y la columna correspondientes. Es el código estable del dominio de la importación; las reglas de los maestros que exigen un texto (nombre, unidad base) usan sus propios códigos (`NOMBRE_INVALIDO`, `VALOR_OBLIGATORIO`) porque las aplica el servicio dueño (TR-10).

#### Scenario: Código de cliente vacío

- **GIVEN** una fila de clientes con `codigo` vacío
- **WHEN** se importa
- **THEN** la fila da `VALOR_OBLIGATORIO` en la columna `codigo` y no se escribe nada
- **Regla:** CLI-01; `design.md` D6; INV-01

#### Scenario: Unidad base de producto en blanco

- **GIVEN** una fila de productos con `unidad_base` de solo espacios
- **WHEN** se importa
- **THEN** la fila da `VALOR_OBLIGATORIO` en la columna `unidad_base`, el mismo código que el alta por pantalla
- **Regla:** CAT-01; TR-10

### Requirement: Límites del archivo

Un archivo DEBE tener al menos una fila de datos y como máximo el límite de filas y de tamaño de `design.md` D11 (recomendado: 2.000 filas y 5 MB). Fuera de ellos se DEBE rechazar completo con `ARCHIVO_DEMASIADO_GRANDE` o `ARCHIVO_SIN_FILAS` (422).

#### Scenario: Archivo sin filas de datos

- **GIVEN** una planilla con solo el encabezado
- **WHEN** se importa
- **THEN** se rechaza con `ARCHIVO_SIN_FILAS`
- **Regla:** `design.md` D11

#### Scenario: Archivo con demasiadas filas

- **GIVEN** una planilla con una fila más que el límite
- **WHEN** se importa
- **THEN** se rechaza con `ARCHIVO_DEMASIADO_GRANDE` y no se escribe nada
- **Regla:** `design.md` D11; INV-01

### Requirement: Plantillas descargables

El sistema DEBE ofrecer, por cada tipo de importación, una plantilla CSV con el encabezado exacto y sin filas de datos, descargable con `IMPORTAR_DATOS`. La plantilla DEBE poder importarse sin errores de columnas.

#### Scenario: Descargar la plantilla de productos

- **GIVEN** un Administrador
- **WHEN** descarga la plantilla de productos
- **THEN** recibe un CSV cuyo encabezado son exactamente las columnas de productos
- **Regla:** `design.md` D11

#### Scenario: Plantilla sin permiso

- **GIVEN** un usuario sin `IMPORTAR_DATOS`
- **WHEN** pide una plantilla
- **THEN** recibe 403 `PERMISO_REQUERIDO`
- **Regla:** SEG; `01` §19
