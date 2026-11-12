## Purpose

Fijar por prueba qué puede hacer cada rol de PostgreSQL sobre cada tabla, para que un `GRANT` de más o de menos en una migración futura se detecte antes de llegar a producción (INV-05, ADR-020, `02` §18).

## Requirements

### Requirement: Los privilegios reales coinciden con una matriz declarada

El proyecto DEBE mantener una matriz explícita, tabla por tabla, de los privilegios de `app_runtime`, `app_backup` y `app_mantenimiento` sobre el esquema `public`, con una justificación escrita para cada `DELETE`. Una verificación automática DEBE comparar la matriz con los privilegios reales de la base migrada y fallar nombrando la tabla, el rol y el privilegio que sobra o falta. Una tabla nueva sin entrada en la matriz DEBE hacer fallar la verificación (INV-05; ADR-020; `design.md` D10).

#### Scenario: Un privilegio de más hace fallar la verificación
- **GIVEN** una tabla a la que una migración de prueba le otorga `DELETE` a `app_runtime` sin que la matriz lo declare
- **WHEN** corre la verificación de permisos
- **THEN** falla nombrando la tabla, `app_runtime` y `DELETE`
- **Regla:** INV-05; ADR-020

#### Scenario: Una tabla nueva sin declarar hace fallar la verificación
- **GIVEN** una tabla creada por una migración y ausente de la matriz
- **WHEN** corre la verificación de permisos
- **THEN** falla nombrando la tabla
- **Regla:** ADR-020 (si falta un `GRANT` o sobra un permiso, CI falla)

#### Scenario: Ningún libro admite UPDATE ni DELETE de la aplicación
- **GIVEN** la base migrada
- **WHEN** se leen los privilegios de `app_runtime` sobre `auditoria`, `cuenta_movimiento`, `stock_movimiento`, `costo_producto_mov` e `intento_login`
- **THEN** ninguna tiene `UPDATE` ni `DELETE`
- **Regla:** INV-05

### Requirement: Los roles de la aplicación no tienen atributos de administración

Ningún rol de servicio (`app_runtime`, `app_backup`, `app_mantenimiento`) DEBE ser superusuario, crear roles o bases, saltar la seguridad por filas, ni ser dueño de ninguna tabla, secuencia o del esquema. Solo `app_migrations` DEBE ser dueño del esquema `public` y de sus objetos. `PUBLIC` NO DEBE tener privilegios sobre las tablas de `public` ni `CREATE` en el esquema (ADR-020; `02` §18; `design.md` D10).

#### Scenario: Atributos de los roles
- **GIVEN** la base migrada con los roles del entorno de producción
- **WHEN** se leen los atributos de cada rol de servicio
- **THEN** ninguno tiene `SUPERUSER`, `CREATEROLE`, `CREATEDB` ni `BYPASSRLS`
- **Regla:** ADR-020; `02` §18

#### Scenario: Dueños de los objetos
- **GIVEN** la base migrada
- **WHEN** se listan los dueños de tablas, secuencias y del esquema `public`
- **THEN** todos son `app_migrations`
- **Regla:** ADR-020

#### Scenario: PUBLIC no puede crear ni leer
- **GIVEN** la base migrada
- **WHEN** se leen los privilegios de `PUBLIC`
- **THEN** no tiene privilegios de tabla en `public` ni `CREATE` en el esquema
- **Regla:** `02` §18

### Requirement: El rol de mantenimiento solo puede lo que sus tareas necesitan

`app_mantenimiento` DEBE poder leer las tablas de saldo y de libro que compara la verificación de consistencia, insertar resultados de verificación y borrar filas de `intento_login`; NO DEBE poder insertar, modificar ni borrar en ninguna otra tabla (ADR-018; INV-05; `design.md` D3).

#### Scenario: El rol de mantenimiento no puede tocar un libro
- **GIVEN** la base migrada
- **WHEN** `app_mantenimiento` intenta `DELETE` sobre `auditoria` o `UPDATE` sobre `saldo_cuenta`
- **THEN** PostgreSQL lo rechaza por falta de permiso
- **Regla:** INV-05

#### Scenario: El rol de mantenimiento borra intentos de inicio de sesión
- **GIVEN** filas de `intento_login`
- **WHEN** `app_mantenimiento` ejecuta un `DELETE` sobre `intento_login`
- **THEN** PostgreSQL lo acepta
- **Regla:** ADR-018; ADR-057 punto 9
