## ADDED Requirements

### Requirement: La rotación del PIN de autorización se ejecuta como comando idempotente

La rotación del PIN de autorización DEBE ejecutarse como un comando del pipeline de escritura, con su identificador de operación obligatorio, su verificación de permiso y su registro de auditoría con ese identificador. Ni el PIN en claro ni su derivación DEBEN formar parte del resultado guardado del comando, de la huella registrada en un lugar legible, ni de los registros del sistema (`02` §6.5, `02` §12.4, `02` §17, SEG-03, SEG-05).

#### Scenario: Una rotación sin identificador de operación se rechaza

- **GIVEN** un usuario con el permiso de rotar el PIN
- **WHEN** envía la rotación sin identificador de operación
- **THEN** la petición se rechaza y el PIN anterior sigue vigente
- **Regla:** SYN-01, TR-07

#### Scenario: Reenviar la rotación no vuelve a derivar el PIN

- **GIVEN** una rotación ya aceptada
- **WHEN** se reenvía con el mismo identificador de operación y el mismo contenido
- **THEN** la respuesta es el resultado original y la derivación guardada no cambia
- **Regla:** SYN-02, INV-06

#### Scenario: El resultado del comando no contiene el PIN ni su derivación

- **GIVEN** una rotación aceptada
- **WHEN** se consulta el registro del comando y sus registros del sistema
- **THEN** ninguno contiene el PIN en claro ni su derivación
- **Regla:** `02` §17, `02` §18, SEG-05

#### Scenario: Una rotación sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin el permiso de rotar el PIN
- **WHEN** envía la rotación con un identificador de operación válido
- **THEN** se rechaza y el PIN anterior sigue vigente
- **Regla:** SEG-06
