## ADDED Requirements

### Requirement: El servidor publica la versión mínima de aplicación

El servidor DEBE publicar, junto con la versión desplegada, la versión mínima de aplicación que admite para confirmar operaciones nuevas. Un dispositivo por debajo de esa versión DEBE poder sincronizar su cola pendiente, pero NO DEBE poder enviar comandos generados por una aplicación desactualizada como operaciones nuevas hasta actualizarse (`02` §6.6).

#### Scenario: La versión mínima se consulta sin sesión

- **GIVEN** el backend levantado
- **WHEN** un cliente consulta la versión
- **THEN** la respuesta incluye la versión mínima de aplicación admitida
- **Regla:** `02` §6.6 (el servidor publica la versión mínima de la aplicación)

#### Scenario: La versión mínima aparece en el contrato publicado

- **GIVEN** el backend levantado
- **WHEN** se solicita el documento OpenAPI
- **THEN** el esquema de la respuesta de versión incluye la versión mínima de aplicación
- **Regla:** `02` §11 (el OpenAPI generado es el contrato)

#### Scenario: Una aplicación desactualizada puede vaciar su cola

- **GIVEN** un dispositivo cuya versión de aplicación es anterior a la mínima publicada
- **WHEN** envía un lote con comandos que ya tenía encolados
- **THEN** esos comandos se procesan
- **Regla:** `02` §6.6 (puede sincronizar su cola pero no confirmar operaciones nuevas)
