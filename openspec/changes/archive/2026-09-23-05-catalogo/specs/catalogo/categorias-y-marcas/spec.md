## Purpose

Define las categorías y marcas como datos maestros de cada organización, creados y modificados solo por comandos del bus, con nombre único por organización y desactivación en lugar de borrado, para que los productos puedan clasificarse sin valores fijos en el código (CAT-01, TR-09, `03` §5).

## ADDED Requirements

### Requirement: Las categorías y marcas se crean por comando
El sistema DEBE crear una categoría con el comando `CATEGORIA_CREAR` y una marca con `MARCA_CREAR`, ambos en modo `ONLINE`, con `operation_id` obligatorio y el permiso `GESTIONAR_CATALOGO`. La nueva entidad DEBE pertenecer a la organización del token, nacer activa y registrar quién y cuándo la actualizó por última vez.

#### Scenario: Alta de una categoría
- **GIVEN** un usuario con `GESTIONAR_CATALOGO` de la organización A
- **WHEN** envía `CATEGORIA_CREAR` con nombre `Vinos` y un `operation_id` nuevo
- **THEN** el comando queda `ACEPTADO` y la categoría `Vinos` existe en A, activa
- **AND** queda un único registro de auditoría con `origen = COMANDO` y ese `operation_id`
- **Regla:** CAT-01 (categoría del producto); TR-07; TR-09

#### Scenario: Alta de una marca
- **GIVEN** un usuario con `GESTIONAR_CATALOGO` de la organización A
- **WHEN** envía `MARCA_CREAR` con nombre `Bodega Norte`
- **THEN** la marca `Bodega Norte` existe en A, activa
- **Regla:** CAT-01 (marca opcional del producto)

#### Scenario: Doble envío del mismo alta no duplica
- **GIVEN** un `CATEGORIA_CREAR` ya aceptado con `operation_id` X y nombre `Vinos`
- **WHEN** se reenvía el mismo comando con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original y sigue existiendo una sola categoría `Vinos`
- **Regla:** INV-06; SYN-02

#### Scenario: Sin permiso se rechaza sin efectos
- **GIVEN** un usuario sin `GESTIONAR_CATALOGO` (por ejemplo, rol VEN)
- **WHEN** envía `CATEGORIA_CREAR` o `MARCA_CREAR`
- **THEN** la petición se rechaza con el código `PERMISO_REQUERIDO` y no se crea ninguna fila ni queda reservado el `operation_id`
- **Regla:** `01` §19 (GESTIONAR_CATALOGO: ADM y GES); SEG-06

### Requirement: El nombre es único por organización
El nombre de una categoría DEBE ser único entre las categorías de su organización, y el de una marca entre las marcas de su organización, sin importar si están activas. El nombre se DEBE guardar sin espacios al inicio ni al final y NO DEBE quedar vacío. Organizaciones distintas PUEDEN repetir nombres.

#### Scenario: Nombre repetido en la misma organización
- **GIVEN** la categoría `Vinos` en la organización A
- **WHEN** se envía `CATEGORIA_CREAR` con nombre `Vinos` en A
- **THEN** el comando se rechaza con el código `NOMBRE_DUPLICADO`, no se crea ninguna fila y el `operation_id` puede reintentarse con otro contenido
- **Regla:** `03` §5 (`UNIQUE (organizacion_id, nombre)`); `02` §6.3 (un fallo ONLINE revierte la reserva)

#### Scenario: El mismo nombre en otra organización es válido
- **GIVEN** la categoría `Vinos` en la organización A
- **WHEN** la organización B envía `CATEGORIA_CREAR` con nombre `Vinos`
- **THEN** el comando queda `ACEPTADO` en B
- **Regla:** TR-08; INV-02

#### Scenario: Nombre vacío o solo espacios
- **WHEN** se envía `MARCA_CREAR` con nombre `"   "`
- **THEN** el comando se rechaza con el código `NOMBRE_INVALIDO` y no se crea ninguna fila
- **Regla:** TR-10 (toda validación se ejecuta en el servidor)

### Requirement: Las categorías y marcas se modifican y desactivan por comando
El sistema DEBE modificar nombre y estado de actividad con `CATEGORIA_MODIFICAR` y `MARCA_MODIFICAR`, cuyo contenido es el estado completo deseado. Una categoría o marca NO DEBE borrarse: se desactiva (CAT-05, TR-06). Una categoría NO DEBE desactivarse mientras tenga productos activos. Una categoría o marca inactiva NO DEBE poder asignarse a un producto en un alta ni en una modificación, pero los productos que ya la tienen la conservan.

#### Scenario: Renombrar una marca
- **GIVEN** la marca `Bodega Norte` en la organización A
- **WHEN** se envía `MARCA_MODIFICAR` con nombre `Bodega del Norte` y activa
- **THEN** la marca queda con el nuevo nombre y `actualizado_en` avanza
- **Regla:** CAT-01

#### Scenario: Desactivar una categoría con productos activos
- **GIVEN** la categoría `Vinos` con el producto activo `Vino A`
- **WHEN** se envía `CATEGORIA_MODIFICAR` con `activo = false`
- **THEN** el comando se rechaza con el código `CATEGORIA_CON_PRODUCTOS_ACTIVOS` y la categoría sigue activa
- **Regla:** CAT-01 (todo producto tiene categoría); CAT-05

#### Scenario: Una categoría inactiva no se asigna a productos nuevos
- **GIVEN** la categoría `Licores` inactiva
- **WHEN** se envía `PRODUCTO_CREAR` con esa categoría
- **THEN** el comando se rechaza con el código `CATEGORIA_INACTIVA`
- **Regla:** CAT-05 (los inactivos no se ofrecen en nuevas operaciones)

#### Scenario: Categoría de otra organización
- **GIVEN** la categoría `Vinos` de la organización B
- **WHEN** un usuario de A envía `CATEGORIA_MODIFICAR` sobre su identificador
- **THEN** la respuesta es 404 y la categoría de B no cambia
- **Regla:** INV-21; SEG-07

### Requirement: Las categorías y marcas se consultan por organización
El sistema DEBE listar las categorías y las marcas de la organización del token, ordenadas por nombre, con filtro opcional por actividad. Ninguna consulta DEBE devolver filas de otra organización.

#### Scenario: Listado filtrado por activas
- **GIVEN** en A las categorías `Vinos` (activa) y `Licores` (inactiva)
- **WHEN** se listan las categorías activas de A
- **THEN** se devuelve solo `Vinos`
- **Regla:** CAT-05

#### Scenario: Listado aislado por organización
- **GIVEN** la marca `Bodega Norte` en A y la marca `Cervecería Sur` en B
- **WHEN** un usuario de A lista marcas
- **THEN** solo ve `Bodega Norte`
- **Regla:** INV-21; TR-08
