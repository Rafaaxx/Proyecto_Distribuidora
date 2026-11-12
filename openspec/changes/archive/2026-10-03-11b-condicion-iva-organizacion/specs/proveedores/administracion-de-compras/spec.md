## MODIFIED Requirements

### Requirement: Alta de compra con vista previa de importes

El formulario DEBE pedir proveedor (solo activos), fecha (por defecto hoy en la zona de la organización), ubicación de destino (activas), condición y líneas; el selector de productos DEBE ofrecer solo los productos activos del proveedor elegido, consultados al servidor con el filtro `proveedor_id`, y el de presentaciones solo las activas de compra. El formulario DEBE leer la configuración fiscal de la organización (`GET /api/v1/configuracion/fiscal`). Si la organización computa crédito fiscal, cada línea ofrece "Incluye IVA" y el total muestra el neto, el IVA sugerido y el total de factura (editable, prellenado con neto + IVA). Si no lo computa, la línea NO DEBE ofrecer "Incluye IVA", rotula el valor como "Valor pagado" y envía `incluye_iva = false`; el total muestra "Total" y el total de factura (editable, prellenado con ese total), sin IVA sugerido (CST-06, `design.md` D5). Por línea DEBE mostrar cantidad base, costo base e importe, todo con `decimal.js` y el motor compartido de `cmp-02-compra.json`; los importes viajan como string. De contado DEBE pedir medios con la suma igual al total. El envío DEBE usar un `Operation-Id` que se conserva al reintentar tras un error de red y se renueva al cambiar el contenido.

#### Scenario: Vista previa de una línea con IVA
- **GIVEN** una organización `RESPONSABLE_INSCRIPTO`
- **WHEN** el usuario carga Caja x12, cantidad 1, valor `18000,00`, con IVA 21%
- **THEN** ve costo base `1.239,669421` e importe neto `14.876,03`, iguales a los del servidor
- **Regla:** CMP-02; CST-02; `02` §10.4

#### Scenario: Vista previa de un monotributista
- **GIVEN** una organización `MONOTRIBUTO`
- **WHEN** el usuario abre el alta y carga Caja x12, cantidad 1, valor pagado `21780,00`
- **THEN** no ve la casilla "Incluye IVA" ni el IVA sugerido
- **AND** ve costo base `1.815,000000`, total `21.780,00` y total de factura prellenado `21.780,00`, iguales a los del servidor
- **Regla:** CMP-02; CST-06; `design.md` D4 y D5

#### Scenario: Medios que no suman el total
- **WHEN** en una compra de contado los medios no suman el total de factura
- **THEN** el botón de confirmar queda deshabilitado con el faltante a la vista
- **Regla:** INV-08; TR-10 (el servidor valida igual)

#### Scenario: Error del servidor por línea
- **WHEN** el servidor rechaza con `CANTIDAD_INVALIDA` o `INCLUYE_IVA_NO_APLICA` en la línea 2
- **THEN** el error se muestra junto a la línea 2 y el resto del formulario se conserva
- **Regla:** TR-10

## ADDED Requirements

### Requirement: El detalle de compra muestra la regla de IVA congelada

El detalle de una compra DEBE mostrar, por línea, si se descontó IVA ("IVA descontado: Sí/No") según el `computa_credito_fiscal` y el `incluye_iva` congelados en la línea, y no según la condición actual de la organización.

#### Scenario: Compra de monotributista vista después de pasar a inscripto
- **GIVEN** una compra confirmada como `MONOTRIBUTO` con una línea de `"21780.00"` y costo base `"1815.000000"`, y la organización ahora es `RESPONSABLE_INSCRIPTO`
- **WHEN** el usuario abre su detalle
- **THEN** la línea muestra "IVA descontado: No" y costo base `1.815,000000`
- **Regla:** TR-06; CST-06; `design.md` D3
