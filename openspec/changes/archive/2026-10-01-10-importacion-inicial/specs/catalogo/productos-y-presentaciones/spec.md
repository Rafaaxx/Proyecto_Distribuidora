## ADDED Requirements

### Requirement: Los textos obligatorios del producto no pueden quedar vacíos

El alta y la modificación de un producto DEBEN rechazar un `nombre` vacío o de solo espacios con `NOMBRE_INVALIDO` (422), una `unidad_base` vacía o de solo espacios con `VALOR_OBLIGATORIO` (422) y, en el alta de un producto o al agregar o modificar una presentación, un nombre de presentación vacío o de solo espacios con `NOMBRE_INVALIDO` (422). Los textos válidos DEBEN guardarse recortados. Un rechazo en cualquier presentación DEBE rechazar el producto entero sin escribir nada (INV-01). La regla vive en el dominio de catálogo: la importación de productos (change 10) la hereda sin repetirla (TR-10). Agregado por el change 10 (grupo 12) para cerrar una laguna del alta por pantalla.

#### Scenario: Nombre de producto en blanco

- **GIVEN** la organización A con categoría, proveedor y alícuota activos
- **WHEN** un usuario con `GESTIONAR_CATALOGO` envía `PRODUCTO_CREAR` con `nombre` = `   `
- **THEN** responde 422 con `NOMBRE_INVALIDO` y no se crea ningún producto
- **Regla:** CAT-01; INV-01

#### Scenario: Unidad base vacía

- **GIVEN** el mismo contexto
- **WHEN** se envía `PRODUCTO_CREAR` con `unidad_base` = ` `
- **THEN** responde 422 con `VALOR_OBLIGATORIO` y no se crea ningún producto
- **Regla:** CAT-01

#### Scenario: Nombre de presentación vacío

- **GIVEN** el mismo contexto y un producto con dos presentaciones, la segunda con nombre `  `
- **WHEN** se envía `PRODUCTO_CREAR`
- **THEN** responde 422 con `NOMBRE_INVALIDO` y no se crea el producto ni ninguna presentación
- **Regla:** CAT-02; INV-01
