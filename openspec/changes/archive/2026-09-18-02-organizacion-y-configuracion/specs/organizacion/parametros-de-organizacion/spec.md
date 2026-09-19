## Purpose

Define qué es una organización en el sistema y qué parámetros configurables gobiernan su operación (moneda, zona horaria, modo impositivo, política de crédito, redondeo, facturación, sesión), de modo que ninguna regla de negocio posterior quede escrita como constante en el código (`01` §4, `03` §4).

## ADDED Requirements

### Requirement: La organización define moneda, zona horaria y estado
El sistema DEBE representar cada organización con su nombre, su moneda en código ISO 4217, su zona horaria IANA y su estado (`ACTIVA` o `SUSPENDIDA`); el CUIT es opcional. La zona horaria de la organización DEBE ser la que determina la fecha de negocio de una operación a partir de su `occurred_at` (TR-04, `03` §4).

#### Scenario: La organización inicial queda configurada con sus valores de referencia
- **GIVEN** un sistema recién migrado sin organizaciones
- **WHEN** se siembra la organización inicial
- **THEN** su moneda es `ARS` y su zona horaria es `America/Argentina/Mendoza`
- **AND** su estado es `ACTIVA`
- **Regla:** `01` §4 (columna "Organización inicial": moneda ARS, zona horaria America/Argentina/Mendoza)

#### Scenario: La fecha de negocio se deriva de la zona horaria de la organización
- **GIVEN** una organización con zona horaria `America/Argentina/Mendoza`
- **AND** una operación cuyo `occurred_at` es un momento UTC que cae en el día anterior en esa zona
- **WHEN** se determina la fecha de negocio de la operación
- **THEN** es la fecha del `occurred_at` convertido a la zona horaria de la organización, no la fecha UTC
- **Regla:** TR-04 (la fecha de negocio de una operación es su `occurred_at` convertido a la zona horaria de la organización)

#### Scenario: Un estado desconocido se rechaza
- **GIVEN** una organización existente
- **WHEN** se intenta dejar su estado en un valor distinto de `ACTIVA` o `SUSPENDIDA`
- **THEN** la operación falla con un error explícito y el estado no cambia
- **Regla:** `03` §4 (`estado`: `ACTIVA`, `SUSPENDIDA`)

### Requirement: Cada organización tiene exactamente una fila de configuración
El sistema DEBE mantener una y solo una fila de configuración por organización, identificada por la propia organización. NO DEBE ser posible crear una segunda fila de configuración para la misma organización ni dejar una organización sin configuración una vez sembrada (`01` §4, `03` §4).

#### Scenario: Una segunda configuración para la misma organización se rechaza
- **GIVEN** una organización que ya tiene su fila de configuración
- **WHEN** se intenta crear otra fila de configuración para esa misma organización
- **THEN** la base rechaza la inserción por clave duplicada
- **Regla:** `03` §4 (`configuracion_organizacion`: una fila por organización, `organizacion_id` es PK y FK)

#### Scenario: La configuración de una organización no es legible desde otra
- **GIVEN** la organización A con su configuración y la organización B con la suya
- **WHEN** se lee la configuración indicando la organización B
- **THEN** se obtiene únicamente la configuración de B
- **Regla:** TR-08

### Requirement: Los parámetros de operación viven en la configuración de la organización
La configuración de una organización DEBE contener los parámetros de `01` §4 con las columnas y dominios de `03` §4: modo impositivo (`A`, `B`, `C`), lista de precios por defecto, política de crédito por defecto (`ADVERTIR`, `AUTORIZAR`, `BLOQUEAR`), tolerancia de crédito sin conexión (tipo `IMPORTE` o `PORCENTAJE` y valor), habilitación de descuento manual, obligatoriedad de motivo en descuento manual y al usar lista no vigente, redondeo por defecto (múltiplo y dirección `ARRIBA`, `CERCANO`, `ABAJO`), venta a consumidor final genérico y su cliente, estado de facturación inicial (`NO_REQUIERE`, `PENDIENTE`), modalidad de IVA al facturar (`CLIENTE`, `ABSORBIDO`), intentos de PIN antes de bloquear, versión mínima de la aplicación y desvío máximo de reloj en segundos.

#### Scenario: La organización inicial toma los valores por defecto documentados
- **GIVEN** un sistema recién migrado
- **WHEN** se siembra la configuración de la organización inicial
- **THEN** su modo impositivo es `A`
- **AND** su política de crédito por defecto es `AUTORIZAR`
- **AND** el descuento manual está habilitado
- **AND** el motivo es obligatorio al usar una lista no asignada o una versión anterior
- **AND** el estado de facturación inicial por defecto es `NO_REQUIERE`
- **AND** los intentos de PIN antes de bloquear son `5`
- **Regla:** `01` §4 (columna "Organización inicial")

#### Scenario: Un parámetro sin valor definido queda explícitamente sin definir
- **GIVEN** los parámetros que `01` §4 marca como "A definir al configurar" (tolerancia de crédito sin conexión, obligatoriedad de motivo en descuento manual, redondeo por defecto, venta a consumidor final, modalidad de IVA al facturar)
- **WHEN** se siembra la configuración de la organización inicial
- **THEN** esos parámetros quedan sin valor, no con un valor inventado por el sistema
- **AND** el sistema no supone un valor por omisión para ellos
- **Regla:** `01` §4 (valor "A definir al configurar" / "A definir")

#### Scenario: Un valor fuera del dominio de un parámetro se rechaza
- **GIVEN** la configuración de una organización
- **WHEN** se intenta fijar la política de crédito por defecto en un valor distinto de `ADVERTIR`, `AUTORIZAR` o `BLOQUEAR`
- **THEN** la operación falla con un error explícito y la configuración no cambia
- **Regla:** `03` §4 (`politica_credito_default`: `ADVERTIR`, `AUTORIZAR`, `BLOQUEAR`)

#### Scenario: Los parámetros monetarios no usan punto flotante
- **GIVEN** las columnas de tolerancia de crédito sin conexión y de múltiplo de redondeo
- **WHEN** se recorre el catálogo de columnas de la base
- **THEN** ambas son numéricas exactas con 2 decimales, no de punto flotante binario
- **Regla:** INV-03, `03` §4 (`tolerancia_offline_valor` y `redondeo_multiplo`: `numeric(14,2)`)

### Requirement: La siembra de la organización inicial es idempotente
La operación que siembra la organización inicial, su configuración y sus catálogos DEBE poder ejecutarse más de una vez sin duplicar filas ni sobrescribir valores que un operador haya cambiado después.

#### Scenario: Sembrar dos veces no duplica ni pisa
- **GIVEN** un sistema con la organización inicial ya sembrada y su política de crédito cambiada a `BLOQUEAR` por un operador
- **WHEN** se ejecuta la siembra por segunda vez
- **THEN** no se crea una segunda organización ni una segunda fila de configuración
- **AND** la política de crédito sigue siendo `BLOQUEAR`
- **Regla:** `01` §4, TR-06 (ninguna decisión ya tomada se pisa por una reejecución)

#### Scenario: Sembrar sobre una base sin migrar falla explícitamente
- **GIVEN** una base sin las tablas de organización
- **WHEN** se ejecuta la siembra
- **THEN** falla con un error explícito que indica que faltan migraciones
- **AND** no crea ninguna tabla
- **Regla:** `03` §17 (todo cambio de esquema va en una migración de Alembic)
