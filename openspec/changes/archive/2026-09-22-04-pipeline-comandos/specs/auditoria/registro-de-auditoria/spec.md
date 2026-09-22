## ADDED Requirements

### Requirement: Un registro de auditoría originado en un comando lleva su identificador de operación

Todo registro de auditoría producido por un comando DEBE llevar el `operation_id` de ese comando, y la base DEBE impedir que se registre sin él. Un evento auditable que no se origina en un comando —el inicio de sesión, la renovación y el cierre de sesión, que ocurren fuera del bus por definición— DEBE quedar auditado igualmente, declarando su origen, y NO DEBE llevar un identificador de operación inventado (AUD-01, AUD-02, TR-07, ADR-012).

#### Scenario: La auditoría de un comando referencia su identificador de operación

- **GIVEN** un comando aceptado que produce un cambio auditable
- **WHEN** se consulta su registro de auditoría
- **THEN** lleva el mismo identificador de operación que el comando
- **Regla:** AUD-02, TR-07

#### Scenario: Un registro de origen comando sin identificador de operación no llega a la base

- **GIVEN** un intento de registrar auditoría declarada de origen comando sin identificador de operación
- **WHEN** se intenta insertar
- **THEN** la base rechaza la inserción
- **Regla:** AUD-02, INV-06

#### Scenario: El inicio de sesión sigue auditado y sin identificador de operación

- **GIVEN** un inicio de sesión exitoso
- **WHEN** se consulta su registro de auditoría
- **THEN** existe, declara origen distinto de comando y no tiene identificador de operación
- **Regla:** AUD-01 (el inicio de sesión se audita), ADR-012 (los endpoints de sesión quedan fuera del bus)

#### Scenario: Los registros de auditoría anteriores al bus no se pierden

- **GIVEN** registros de auditoría existentes sin identificador de operación
- **WHEN** se aplica la migración que impone la obligatoriedad
- **THEN** la migración sube limpia y ninguno de esos registros se borra ni se modifica en sus datos de evento
- **Regla:** INV-05 (la auditoría no se modifica ni se borra), TR-06
