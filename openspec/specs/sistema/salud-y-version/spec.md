# Sistema - Salud y Versión

## Purpose

Expone los dos endpoints operativos del grupo Sistema (`02` §11) que permiten comprobar desde fuera que el backend está vivo, que alcanza la base de datos y qué versión de la aplicación está desplegada. Son la base para el healthcheck de Docker Compose y, más adelante, para el despliegue y el runbook.

Nota de trazabilidad: este change no implementa ninguna regla de negocio de `01-dominio.md`, por lo que los escenarios citan las secciones de `02-arquitectura.md` que los originan en lugar de identificadores `VTA-`/`INV-`.

## Requirements

### Requirement: Verificación de salud del servicio
El sistema DEBE exponer `GET /api/v1/salud` sin autenticación, que verifica la conexión con la base de datos antes de responder (`02` §17).

#### Scenario: El servicio y la base responden
- **GIVEN** el backend levantado y PostgreSQL accesible
- **WHEN** un cliente hace `GET /api/v1/salud`
- **THEN** la respuesta es `200` con un cuerpo JSON que indica estado correcto y que la base respondió
- **Regla:** `02` §17 (`GET /api/v1/salud` verifica la conexión con la base)

#### Scenario: La base de datos no responde
- **GIVEN** el backend levantado y PostgreSQL no accesible
- **WHEN** un cliente hace `GET /api/v1/salud`
- **THEN** la respuesta es `503` con un cuerpo JSON que indica que la verificación de base falló
- **AND** el detalle del error no expone credenciales ni la cadena de conexión
- **Regla:** `02` §17, `02` §18 (no se registran ni exponen secretos)

#### Scenario: El endpoint no requiere sesión
- **GIVEN** una petición sin token de acceso
- **WHEN** un cliente hace `GET /api/v1/salud`
- **THEN** la respuesta no es `401` ni `403`
- **Regla:** `02` §17 (el healthcheck del contenedor lo consulta sin credenciales)

### Requirement: Consulta de la versión desplegada
El sistema DEBE exponer `GET /api/v1/version`, que devuelve la versión de la aplicación en ejecución (`02` §11, grupo Sistema).

#### Scenario: Versión inyectada en el entorno
- **GIVEN** el backend levantado con la versión de aplicación configurada en su entorno
- **WHEN** un cliente hace `GET /api/v1/version`
- **THEN** la respuesta es `200` y el cuerpo JSON contiene esa misma versión
- **Regla:** `02` §11 (grupo Sistema)

#### Scenario: Versión no configurada
- **GIVEN** el backend levantado sin versión de aplicación en su entorno
- **WHEN** un cliente hace `GET /api/v1/version`
- **THEN** la respuesta es `200` y el cuerpo JSON informa la versión `dev`
- **AND** la petición no falla
- **Regla:** `02` §11 (supuesto registrado en la proposal: valor por defecto `dev`)

### Requirement: Contrato publicado en el OpenAPI
El sistema DEBE incluir ambos endpoints en el documento OpenAPI que genera el backend, porque ese documento es el contrato del que el frontend deriva sus tipos (`02` §11).

#### Scenario: Los endpoints aparecen en el OpenAPI
- **GIVEN** el backend levantado
- **WHEN** se solicita el documento OpenAPI del backend
- **THEN** contiene las rutas `/api/v1/salud` y `/api/v1/version` con sus esquemas de respuesta
- **Regla:** `02` §11 (el OpenAPI generado por FastAPI es el contrato)

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
