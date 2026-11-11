## ADDED Requirements

### Requirement: Los intentos de inicio de sesión se conservan 24 horas

Una tarea diaria DEBE borrar las filas de `intento_login` creadas hace más de 24 horas respecto de la hora del reloj del sistema, incluidas las marcas de desbloqueo manual, con un rol de base distinto de `app_runtime`. NO DEBE borrar filas más recientes, porque los límites de intentos y el bloqueo de 15 minutos se calculan con ellas. La limpieza NO DEBE tocar la auditoría: los bloqueos siguen registrados allí. `app_runtime` DEBE seguir sin `DELETE` sobre `intento_login` (ADR-018; ADR-057 punto 9; AUD-01; AUD-03; INV-05; `design.md` D3, D7).

#### Scenario: Se borran solo las filas de más de 24 horas
- **GIVEN** intentos fallidos creados hace 25 horas y hace 10 minutos
- **WHEN** corre la limpieza
- **THEN** quedan solo los de hace 10 minutos
- **Regla:** ADR-018 (limpieza de registros de más de 24 horas)

#### Scenario: La limpieza no levanta un bloqueo vigente
- **GIVEN** un par de organización y usuario bloqueado por 5 fallos en los últimos 15 minutos
- **WHEN** corre la limpieza
- **THEN** el siguiente intento con ese par sigue respondiendo 429 con la misma hora de desbloqueo
- **Regla:** ADR-018 enmendado (bloqueo de 15 minutos desde el último fallo); ADR-057

#### Scenario: La auditoría de bloqueos se conserva
- **GIVEN** un bloqueo de hace dos días registrado en la auditoría y sus intentos en `intento_login`
- **WHEN** corre la limpieza
- **THEN** los intentos se borran y el registro de auditoría del bloqueo sigue
- **Regla:** AUD-01; AUD-03

#### Scenario: La aplicación no puede borrar intentos
- **GIVEN** la base migrada
- **WHEN** `app_runtime` intenta `DELETE` sobre `intento_login`
- **THEN** PostgreSQL lo rechaza por falta de permiso
- **Regla:** INV-05; ADR-057 punto 9
