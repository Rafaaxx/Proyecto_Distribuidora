# integracion-continua Specification

## Purpose

Define qué verifica automáticamente el proyecto en cada push y con qué base de datos, de modo que ningún cambio que rompa lint, tipos, límites entre módulos, pruebas o build llegue a la rama principal (`02` §15).

Nota de trazabilidad: los escenarios citan `02-arquitectura.md` §15 (estrategia de pruebas y pasos de CI) por no haber reglas de negocio de `01-dominio.md` involucradas, salvo INV-03.

## Requirements

### Requirement: Verificación automática en cada push
En cada push el proyecto DEBE ejecutar, y fallar si alguno falla: lint, formato y tipos del backend y del frontend; los límites entre módulos (import-linter); las pruebas unitarias, de propiedades y de cálculo compartido; las pruebas de integración, de infraestructura y de concurrencia contra PostgreSQL real; y el build de producción del frontend (`02` §15; `design.md` D12 del 28).

#### Scenario: Un cambio limpio pasa todas las verificaciones
- **GIVEN** un cambio que respeta lint, formato, tipos y pruebas
- **WHEN** se hace push de la rama
- **THEN** todos los pasos de verificación terminan en éxito
- **Regla:** `02` §15 (CI en cada push, pasos 1, 2, 4, 5 y 6)

#### Scenario: El tipado del backend falla
- **GIVEN** un cambio que introduce un error de tipos en el backend
- **WHEN** se hace push
- **THEN** la verificación falla en el paso de tipos y ningún paso posterior reporta éxito global
- **Regla:** `02` §15 (paso 1: lint, formato y tipos)

#### Scenario: Un módulo importa el interior de otro
- **GIVEN** un cambio donde un módulo importa modelos o repositorios de otro módulo en lugar de su `service.py`
- **WHEN** se hace push
- **THEN** la verificación de límites entre módulos falla nombrando el contrato violado
- **Regla:** `02` §15 (paso 2: import-linter)

#### Scenario: El build del frontend falla
- **GIVEN** un cambio que rompe el build de producción del frontend
- **WHEN** se hace push
- **THEN** la verificación falla en el paso de build aunque las pruebas hayan pasado
- **Regla:** `02` §15 (paso 6: build del frontend)

#### Scenario: Las pruebas de concurrencia corren en cada push
- **GIVEN** la verificación automática configurada
- **WHEN** se hace push
- **THEN** corren las pruebas de `tests/concurrency` contra PostgreSQL real, en un paso propio, y una falla hace fallar la verificación
- **Regla:** `02` §15 (paso 5: integración y concurrencia con Testcontainers)

### Requirement: Las pruebas de integración usan PostgreSQL real
Las pruebas de integración DEBEN ejecutarse contra una instancia real de PostgreSQL levantada automáticamente para la corrida, con las migraciones aplicadas. NO DEBE usarse SQLite ni ningún sustituto en memoria (`02` §15).

#### Scenario: La integración corre sin base preexistente
- **GIVEN** un entorno sin base de datos levantada previamente
- **WHEN** se ejecutan las pruebas de integración
- **THEN** el arnés levanta una instancia real de PostgreSQL, aplica las migraciones y ejecuta las pruebas contra ella
- **Regla:** `02` §15 (las pruebas de integración usan PostgreSQL real; no se usa SQLite)

#### Scenario: No hay motor de contenedores disponible
- **GIVEN** un entorno donde no es posible levantar contenedores
- **WHEN** se ejecutan las pruebas de integración
- **THEN** fallan con un mensaje que explica que se requiere un motor de contenedores, y no caen en un sustituto en memoria
- **Regla:** `02` §15 (no se usa SQLite)

#### Scenario: Cada prueba de integración queda aislada
- **GIVEN** dos pruebas de integración que escriben en la misma tabla
- **WHEN** se ejecutan en la misma corrida
- **THEN** ninguna observa los datos escritos por la otra
- **Regla:** `02` §15 (las pruebas de integración aíslan con una transacción revertida al final de cada prueba)

### Requirement: Cobertura declarada de invariantes
Cada invariante de `01` §20 que un change cierra DEBE tener al menos una prueba que lo cite por identificador y que se ejecute en la verificación automática (`02` §15).

#### Scenario: INV-03 se verifica en cada push
- **GIVEN** la verificación automática configurada
- **WHEN** se ejecuta sobre una base migrada
- **THEN** corre la prueba que recorre el catálogo de columnas y cita INV-03, y falla si aparece una columna de punto flotante binario
- **Regla:** INV-03; `02` §15 (cada invariante de `01` §20 tiene al menos una prueba que lo cite por identificador)

### Requirement: La suite de aceptación corre en la rama principal
En cada push a la rama principal el proyecto DEBE levantar el entorno de aceptación con Docker Compose, correr la suite de Playwright y fallar si alguna prueba falla, conservando las trazas de las pruebas fallidas para revisarlas (`02` §15; `design.md` D16).

#### Scenario: Una prueba de aceptación falla en la principal
- **GIVEN** un cambio que rompe el criterio 8 de `00` §9
- **WHEN** se hace push a la rama principal
- **THEN** el paso de aceptación falla nombrando la prueba y deja su traza como artefacto
- **Regla:** `02` §15 (en la rama principal, suite de Playwright contra el entorno levantado con Docker Compose)

### Requirement: Cada invariante de la etapa 1 está citado por una prueba que corre en la verificación
Una verificación automática DEBE recorrer los invariantes de `01` §20 que corresponden a la etapa 1 (todos salvo INV-09 e INV-20, del módulo de facturación según `04` §13) y fallar nombrando el invariante si ninguna prueba de una carpeta que corre la verificación automática lo cita por identificador. La lista de exentos DEBE ser explícita (`02` §15; `04` §12, fila 28; `design.md` D12).

#### Scenario: Un invariante sin prueba hace fallar la verificación
- **GIVEN** un invariante de la etapa 1 que ninguna prueba cita
- **WHEN** corre la verificación de cobertura de invariantes
- **THEN** falla nombrando el invariante
- **Regla:** `02` §15 (cada invariante de `01` §20 tiene al menos una prueba que lo cite por identificador)

#### Scenario: Los invariantes de facturación quedan exentos por nombre
- **GIVEN** INV-09 e INV-20 sin pruebas
- **WHEN** corre la verificación
- **THEN** no falla por ellos, porque están en la lista explícita de exentos con su razón
- **Regla:** `04` §13
