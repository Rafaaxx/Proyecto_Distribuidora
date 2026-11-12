## MODIFIED Requirements

### Requirement: Productos y presentaciones se consultan por organización
El sistema DEBE listar productos de la organización con paginación por cursor y límite máximo por página, filtrables por texto (código o nombre), categoría, marca, actividad y proveedor (`proveedor_id`, filtro en el servidor; deuda nominada por el change 06, `design.md` del change 11), y DEBE devolver el detalle de un producto con todas sus presentaciones y cuál es la de referencia. El detalle DEBE incluir el proveedor asignado: `proveedor_id` y `proveedor_nombre`, este último obtenido mediante la consulta de proveedor que registra `proveedores` (`design.md` D9, D13 del change 06; ADR-025), sin que `catalogo` lea la tabla `proveedor` directamente y sin ampliar el permiso de `GET /proveedores/opciones` (D8 del change 06). `proveedor_nombre` se incluye tanto si el proveedor está activo como si está inactivo. Ninguna consulta DEBE devolver datos de otra organización.

#### Scenario: Listado paginado por cursor
- **GIVEN** más productos en A que el tamaño de página pedido
- **WHEN** se piden páginas sucesivas con el cursor devuelto
- **THEN** cada producto aparece exactamente una vez y la última página no devuelve cursor
- **Regla:** `02` §11 (paginación por cursor)

#### Scenario: Filtro por proveedor
- **GIVEN** en A los productos `Vino A` y `Cerveza B` del proveedor P y `Vino C` del proveedor Q
- **WHEN** se listan con `proveedor_id = P` y `activo = true`
- **THEN** se devuelven solo `Vino A` y `Cerveza B`, paginados por cursor
- **Regla:** CAT-06; `02` §11

#### Scenario: Filtro por proveedor de otra organización
- **WHEN** un usuario de A filtra por el `proveedor_id` de un proveedor de B
- **THEN** la respuesta es una lista vacía, sin revelar datos de B
- **Regla:** INV-21

#### Scenario: Detalle con presentación de referencia
- **WHEN** se pide el detalle de `Vino A`
- **THEN** se devuelven sus presentaciones con unidades, usos y actividad, `Caja x6` marcada como referencia, y el proveedor asignado con su nombre
- **Regla:** CAT-02; CAT-03; CAT-06

#### Scenario: Detalle de un producto con proveedor inactivo muestra su nombre
- **WHEN** se pide el detalle de un producto cuyo proveedor actual, `Bodega Sur`, está inactivo (por ejemplo, el proveedor provisorio de la migración, `design.md` D2 del change 06)
- **THEN** la respuesta incluye `proveedor_nombre = "Bodega Sur"` y no un texto genérico
- **Regla:** CAT-06; `design.md` D2, D5, D9 y D13 (opción B, change 06); ADR-025

#### Scenario: Producto de otra organización
- **WHEN** un usuario de A pide el detalle de un producto de B
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07

## ADDED Requirements

### Requirement: Una presentación usada en una compra congela sus unidades

Una presentación que figura en alguna línea de compra, confirmada o anulada, DEBE contar como usada para INV-18: `proveedores` DEBE registrar su verificador de uso en el puerto del catálogo (ADR-023), con el mismo patrón que el del costo informado (deuda nominada por los changes 05 y 06).

#### Scenario: INV-18 — presentación usada en una compra
- **GIVEN** la presentación `Caja x6` de `Vino A` usada en una compra y sin costos informados
- **WHEN** se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** se rechaza con `UNIDADES_CONGELADAS` y conserva 6 unidades
- **Regla:** INV-18; CAT-04; ADR-023

#### Scenario: La anulación no libera las unidades
- **GIVEN** la misma compra anulada
- **WHEN** se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** se rechaza con `UNIDADES_CONGELADAS`
- **Regla:** INV-18; TR-06
