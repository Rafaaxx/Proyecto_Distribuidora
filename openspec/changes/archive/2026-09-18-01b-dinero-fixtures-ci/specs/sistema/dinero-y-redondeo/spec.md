## Purpose

Define el contrato único de representación y redondeo de importes, costos y porcentajes en backend, frontend y base de datos, de modo que ninguna parte del sistema use punto flotante binario para dinero y que ambos lados redondeen idéntico (INV-03, `02` §10).

Nota de trazabilidad: este change no implementa reglas de negocio de `01-dominio.md`. Los escenarios citan el invariante INV-03 y las secciones de `02-arquitectura.md` y `03-modelo-de-datos.md` que los originan.

## ADDED Requirements

### Requirement: Redondeo de importes con medio hacia arriba
El sistema DEBE ofrecer una única operación de redondeo de importes que cuantiza a 2 decimales con `ROUND_HALF_UP` explícito, disponible tanto en el backend como en el frontend con el mismo resultado para la misma entrada (`02` §10.1, `02` §10.3). El contexto de redondeo por defecto del lenguaje NO DEBE usarse para cuantizar.

#### Scenario: El medio se desempata hacia arriba
- **GIVEN** el importe exacto `0.125`
- **WHEN** se redondea como importe
- **THEN** el resultado es `0.13`, no `0.12`
- **AND** el resultado tiene exactamente 2 decimales
- **Regla:** `02` §10.1 (ROUND_HALF_UP explícito; el contexto decimal por defecto redondea al par y no debe usarse)

#### Scenario: Backend y frontend coinciden
- **GIVEN** el mismo conjunto de importes de entrada
- **WHEN** se redondean con la operación de importes del backend y con la del frontend
- **THEN** ambas producen exactamente la misma cadena de salida para cada entrada
- **Regla:** `02` §10.3 (el frontend expone las mismas funciones de redondeo que el backend)

#### Scenario: Un negativo en el medio se desempata alejándose de cero
- **GIVEN** el importe exacto `-0.125`
- **WHEN** se redondea como importe
- **THEN** el resultado es `-0.13`
- **Regla:** `02` §10.1 (ROUND_HALF_UP: el medio se aleja de cero, no hacia el par)

### Requirement: Redondeo de costos y porcentajes a seis decimales
El sistema DEBE ofrecer una operación de redondeo de costos por unidad base y porcentajes que cuantiza a 6 decimales con `ROUND_HALF_UP`, disponible en backend y frontend con resultados idénticos, correspondiente a las columnas `numeric(18,6)` y `numeric(9,6)` del esquema (`02` §10.1, `03` §2.2).

#### Scenario: Un costo unitario se cuantiza a seis decimales
- **GIVEN** el costo exacto `1.0000005`
- **WHEN** se redondea como costo
- **THEN** el resultado es `1.000001`
- **AND** el resultado tiene exactamente 6 decimales
- **Regla:** `02` §10.1 (`numeric(18,6)` para costos por unidad base)

#### Scenario: Una alícuota se representa como fracción de seis decimales
- **GIVEN** la alícuota de IVA del 21 %
- **WHEN** se representa como porcentaje del sistema
- **THEN** su valor es `0.210000`
- **Regla:** `03` §2.2 (porcentajes y alícuotas como fracción, 21 % = `0.210000`)

### Requirement: Rechazo de entradas que no son dinero exacto
Las operaciones de redondeo DEBEN rechazar con un error explícito cualquier entrada que no sea un valor decimal exacto, en particular un número de punto flotante binario del lenguaje o un valor no numérico (INV-03).

#### Scenario: Se intenta redondear un flotante binario
- **GIVEN** un valor de punto flotante binario del lenguaje
- **WHEN** se pasa a la operación de redondeo de importes
- **THEN** la operación falla con un error explícito y no devuelve un importe
- **Regla:** INV-03 (ningún importe, costo o porcentaje se representa con punto flotante binario)

#### Scenario: Se intenta redondear un texto que no es número
- **GIVEN** la cadena `"abc"`
- **WHEN** se pasa a la operación de redondeo de importes
- **THEN** la operación falla con un error explícito
- **Regla:** INV-03

### Requirement: Los importes viajan como texto
Los importes, costos y porcentajes DEBEN serializarse como cadena en JSON, con la cantidad de decimales de su tipo, y las cantidades en unidad base como entero (`02` §10.2). El frontend NO DEBE convertir un importe a número para calcular; solo para formatear.

#### Scenario: Serialización de un importe
- **GIVEN** el importe `31250` con dos decimales
- **WHEN** se serializa a JSON
- **THEN** aparece como la cadena `"31250.00"`, no como número
- **Regla:** `02` §10.2 (los importes viajan en JSON como string)

#### Scenario: Deserialización en el frontend
- **GIVEN** la cadena `"31250.00"` recibida desde la API
- **WHEN** el frontend la convierte a valor monetario
- **THEN** obtiene un decimal exacto y en ningún punto pasa por el tipo numérico nativo del lenguaje
- **Regla:** `02` §10.3 (ningún importe se convierte a `number` para calcular)

### Requirement: El esquema no admite punto flotante binario
El esquema de base de datos NO DEBE contener columnas de tipo `real`, `double precision`, `float` ni `money`, y el sistema DEBE verificarlo automáticamente recorriendo el catálogo de columnas de una base migrada (INV-03, `03` §2.2, `04` §5).

#### Scenario: La base migrada no tiene columnas de punto flotante
- **GIVEN** una base de datos PostgreSQL con todas las migraciones aplicadas
- **WHEN** se recorre el catálogo de columnas de los esquemas de la aplicación
- **THEN** ninguna columna tiene tipo `real`, `double precision`, `float` ni `money`
- **Regla:** INV-03; `03` §2.2 (DEBE NO usarse `float`, `real`, `double precision`, `money` ni `serial`)

#### Scenario: Una migración introduce una columna de punto flotante
- **GIVEN** una migración que agrega una columna `double precision`
- **WHEN** se ejecuta la verificación del catálogo de columnas sobre la base migrada
- **THEN** la verificación falla e identifica la tabla y la columna infractora
- **Regla:** INV-03 (el invariante se cubre con una prueba que lo cita por identificador)
