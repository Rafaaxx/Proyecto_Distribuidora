# Sistema - Logging Estructurado

## Purpose

Define el formato y el contenido de los registros del backend: una línea JSON por evento, correlacionada por `request_id`, con las restricciones sobre datos sensibles que exige `02` §17. Es transversal a todos los changes posteriores, que solo agregan campos al contexto ya existente.

Nota de trazabilidad: este change no implementa ninguna regla de negocio de `01-dominio.md`, por lo que los escenarios citan las secciones de `02-arquitectura.md` que los originan.

## Requirements

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
Cada registro de una petición DEBE incluir, además del `request_id`, el método, la ruta, el código de estado y la duración de la petición. Cuando la petición ejecuta un comando, sus registros DEBEN incluir además el `operation_id`, la organización, el usuario y el dispositivo de ese comando. Cuando la petición no tiene sesión ni comando asociados, esos campos DEBEN estar ausentes o nulos sin romper el formato (`02` §17).

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

#### Scenario: Una petición que ejecuta un comando registra su contexto completo
- **GIVEN** un usuario autenticado que envía un comando
- **WHEN** se emiten los registros de esa petición
- **THEN** llevan el `operation_id` del comando, su organización, su usuario y su dispositivo, además del `request_id`
- **Regla:** `02` §17, `04` §5 (logging de contexto de comando)

#### Scenario: Cada comando de un lote lleva su propio identificador de operación
- **GIVEN** un lote de sincronización con varios comandos
- **WHEN** se emiten los registros de su procesamiento
- **THEN** los registros de cada comando llevan su propio `operation_id`
- **AND** todos comparten el `request_id` del lote
- **Regla:** `02` §17, `02` §6.4

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

### Requirement: Métricas mínimas de comando en los registros

El backend DEBE emitir, por cada comando procesado, la duración del comando, su resultado y la cantidad de reintentos transitorios que necesitó; y por cada lote de sincronización, la cantidad de comandos que contenía. El contenido del comando NO DEBE registrarse en nivel INFO (`02` §17, `02` §18).

#### Scenario: El registro de un comando informa duración, resultado y reintentos
- **GIVEN** un comando procesado
- **WHEN** se emite su registro de cierre
- **THEN** informa la duración, el resultado y la cantidad de reintentos transitorios
- **Regla:** `02` §17 (duración por comando, comandos por resultado, reintentos transitorios)

#### Scenario: El registro de un lote informa su tamaño
- **GIVEN** un lote de sincronización con varios comandos
- **WHEN** se emite su registro
- **THEN** informa la cantidad de comandos del lote
- **Regla:** `02` §17 (tamaño de lotes de sync)

#### Scenario: El contenido del comando no llega a los registros
- **GIVEN** un comando cuyo contenido incluye datos personales de un cliente
- **WHEN** se emiten sus registros en nivel INFO
- **THEN** ninguno contiene el contenido del comando
- **Regla:** `02` §17, `02` §18 (nunca se registra el contenido completo de comandos con datos personales)
