## MODIFIED Requirements

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

## ADDED Requirements

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
