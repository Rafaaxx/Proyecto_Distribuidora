## Purpose

Define el formato y el contenido de los registros del backend: una línea JSON por evento, correlacionada por `request_id`, con las restricciones sobre datos sensibles que exige `02` §17. Es transversal a todos los changes posteriores, que solo agregan campos al contexto ya existente.

Nota de trazabilidad: este change no implementa ninguna regla de negocio de `01-dominio.md`, por lo que los escenarios citan las secciones de `02-arquitectura.md` que los originan.

## ADDED Requirements

### Requirement: Registros en JSON con `request_id`
El backend DEBE emitir cada registro como un único objeto JSON por línea, y toda petición HTTP DEBE tener un `request_id` presente en todos los registros que produce (`02` §17).

#### Scenario: Una petición produce registros correlacionados
- **GIVEN** el backend levantado
- **WHEN** llega una petición HTTP y su procesamiento emite varios registros
- **THEN** cada registro es un objeto JSON válido en una sola línea
- **AND** todos los registros de esa petición llevan el mismo `request_id`
- **Regla:** `02` §17 (logs estructurados en JSON con `request_id`)

#### Scenario: Dos peticiones no comparten identificador
- **GIVEN** el backend levantado
- **WHEN** llegan dos peticiones distintas
- **THEN** los registros de una tienen un `request_id` distinto del de la otra
- **Regla:** `02` §17

#### Scenario: El cliente propone un identificador de correlación
- **GIVEN** una petición que trae un encabezado de correlación de petición
- **WHEN** el backend la procesa
- **THEN** los registros de esa petición usan ese valor como `request_id`
- **AND** el mismo valor viaja en la respuesta, de modo que el cliente pueda correlacionar
- **Regla:** `02` §17

### Requirement: Contexto de petición en cada registro
Cada registro de una petición DEBE incluir, además del `request_id`, el método, la ruta, el código de estado y la duración de la petición; y DEBE dejar previstos los campos `operation_id`, organización, usuario y dispositivo, que se poblarán cuando existan sesión (change 03) y bus de comandos (change 04) (`02` §17).

#### Scenario: Registro de fin de petición
- **GIVEN** el backend levantado
- **WHEN** una petición termina
- **THEN** se emite un registro con `request_id`, método, ruta, código de estado y duración
- **Regla:** `02` §17 (métricas mínimas en logs: duración)

#### Scenario: Campos aún sin origen
- **GIVEN** una petición sin sesión ni comando asociados
- **WHEN** se emite su registro
- **THEN** los campos `operation_id`, organización, usuario y dispositivo están ausentes o nulos, y su ausencia no rompe el formato JSON
- **Regla:** `02` §17

### Requirement: Datos sensibles fuera de los registros
El backend DEBE NO registrar contraseñas, PIN, tokens ni el contenido completo de comandos con datos personales en nivel INFO (`02` §17, `02` §18).

#### Scenario: Una petición con credenciales
- **GIVEN** una petición cuyo cuerpo o encabezados contienen una credencial o un token
- **WHEN** el backend emite los registros de esa petición
- **THEN** ningún registro contiene el valor de la credencial ni del token
- **Regla:** `02` §17 (nunca se registran contraseñas, PIN ni tokens)

#### Scenario: Un error no filtra secretos
- **GIVEN** un fallo durante el procesamiento de una petición
- **WHEN** se emite el registro del error
- **THEN** el registro incluye el `request_id` y el tipo de error, y no incluye la cadena de conexión, credenciales ni tokens
- **Regla:** `02` §17, `02` §18
