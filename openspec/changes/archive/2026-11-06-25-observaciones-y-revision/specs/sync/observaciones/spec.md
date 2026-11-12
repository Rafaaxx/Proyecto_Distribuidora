## ADDED Requirements

### Requirement: La resolución de una observación no se edita ni se borra

Una observación DEBE pasar solo de `PENDIENTE` a `RESUELTA`. La base DEBE garantizar que una observación `RESUELTA` tiene usuario, momento y comentario de 1 a 500 caracteres, y que una `PENDIENTE` no tiene ninguno de los tres; la aplicación solo DEBE poder actualizar esas columnas y el estado, nunca el código, el detalle, la operación ni el comando, y nunca borrar (SYN-08, INV-05, `design.md` D2).

#### Scenario: La aplicación no cambia el detalle
- **GIVEN** una observación registrada
- **WHEN** la aplicación intenta cambiar su código, su detalle o la operación
- **THEN** la base lo impide
- **Regla:** INV-05; SYN-08

#### Scenario: Resuelta sin comentario
- **WHEN** se intenta guardar una observación `RESUELTA` sin comentario o sin usuario
- **THEN** la base lo impide
- **Regla:** SYN-08

#### Scenario: Las de antes del change siguen pendientes
- **GIVEN** observaciones registradas antes de la migración
- **WHEN** se aplica
- **THEN** siguen `PENDIENTE`, sin resolución, y la migración sube y baja limpia
- **Regla:** `04` §2.1 punto 4

### Requirement: Una venta sin conexión de un producto desactivado se acepta con observación

Una venta sin conexión con una línea cuyo producto o presentación está desactivado al sincronizar DEBE aceptarse (SYN-05, INV-17) con una observación `PRODUCTO_DESACTIVADO` por línea afectada (detalle: línea, producto, presentación y cuál está inactivo), además de las que ya correspondan. `PRODUCTO_DESACTIVADO` DEBE pertenecer al catálogo de SYN-07 (`design.md` D10). Con conexión, el rechazo sigue igual.

#### Scenario: Producto desactivado después del bootstrap
- **GIVEN** un producto que la oficina desactivó después de que el teléfono de Juan bajó los datos
- **WHEN** llega una venta sin conexión con ese producto
- **THEN** se acepta con `PRODUCTO_DESACTIVADO` sobre esa línea y descuenta el stock
- **Regla:** SYN-05; SYN-07; INV-17; ADR-054

#### Scenario: Presentación desactivada
- **WHEN** llega una venta sin conexión con una presentación desactivada de un producto activo
- **THEN** se acepta con `PRODUCTO_DESACTIVADO` que indica la presentación
- **Regla:** SYN-07; INV-17

#### Scenario: Doble envío
- **GIVEN** la venta ya aceptada con `PRODUCTO_DESACTIVADO`
- **WHEN** llega otra vez con el mismo `operation_id`
- **THEN** devuelve el resultado original sin duplicar la observación
- **Regla:** SYN-02; INV-06
