## MODIFIED Requirements

### Requirement: Métricas mínimas de comando en los registros

El backend DEBE emitir, por cada comando procesado, la duración del comando, su resultado y la cantidad de reintentos transitorios que necesitó; y por cada lote de sincronización, un registro al recibirlo con la cantidad de comandos que contenía y un registro de cierre con esa cantidad, los procesados, los aceptados, los aceptados con observaciones, los rechazados, si se cortó por un error transitorio y la duración del lote. El contenido del comando NO DEBE registrarse en nivel INFO (`02` §17, `02` §18; `design.md` D7).

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

#### Scenario: El cierre del lote informa el reparto por resultado
- **GIVEN** un lote de cuatro comandos: uno aceptado, uno con observaciones, uno rechazado y uno aceptado
- **WHEN** termina de procesarse
- **THEN** su registro de cierre informa tamaño 4, procesados 4, aceptados 2, con observaciones 1, rechazados 1, sin corte, y la duración
- **Regla:** `02` §17

#### Scenario: El cierre del lote informa el corte
- **GIVEN** un lote de tres comandos que se corta en el segundo por un error transitorio
- **WHEN** termina
- **THEN** su registro de cierre informa tamaño 3, procesados 1 y que se cortó por un error transitorio
- **Regla:** `02` §17; `02` §6.4

#### Scenario: Reenvío del mismo lote
- **GIVEN** un lote ya procesado que el dispositivo envía otra vez
- **WHEN** termina
- **THEN** su registro de cierre informa los mismos resultados, sin efectos duplicados
- **Regla:** `02` §17; INV-06

#### Scenario: El contenido del comando no llega a los registros
- **GIVEN** un comando cuyo contenido incluye datos personales de un cliente
- **WHEN** se emiten sus registros en nivel INFO, incluido el cierre del lote
- **THEN** ninguno contiene el contenido del comando ni el detalle de sus observaciones
- **Regla:** `02` §17, `02` §18 (nunca se registra el contenido completo de comandos con datos personales)
