# Administración de Compras — Especificación

## Purpose

Dar al área `/admin` las pantallas para registrar, consultar y anular compras, con vista previa de los importes calculada igual que en el servidor y la oferta de registrar un costo informado cuando el costo de la compra difiere del vigente (CMP-01 a CMP-07, ADR-027).

## Requirements

### Requirement: Las pantallas de compras respetan los permisos

La entrada de menú "Compras" y sus rutas DEBEN mostrarse solo con `REGISTRAR_COMPRA` o `ANULAR_COMPRA`; el botón "Nueva compra" solo con `REGISTRAR_COMPRA`; "Anular" solo con `ANULAR_COMPRA` y sobre una compra `CONFIRMADA`; la oferta de registrar costos solo con `EDITAR_COSTOS` (ADR-027, `design.md` D7, D14). Un 403 del servidor DEBE mostrarse como falta de permiso.

#### Scenario: Usuario con solo anulación
- **GIVEN** un usuario con `ANULAR_COMPRA` y sin `REGISTRAR_COMPRA`
- **WHEN** abre `/admin/compras`
- **THEN** ve el listado y el detalle con "Anular", pero no "Nueva compra"
- **Regla:** `01` §19; ADR-027

#### Scenario: Usuario sin permisos de compra
- **WHEN** un usuario sin `REGISTRAR_COMPRA` ni `ANULAR_COMPRA` navega a `/admin/compras`
- **THEN** no ve la entrada de menú y la ruta muestra el aviso de falta de permiso
- **Regla:** ADR-027

### Requirement: Alta de compra con vista previa de importes

El formulario DEBE pedir proveedor (solo activos), fecha (por defecto hoy en la zona de la organización), ubicación de destino (activas), condición y líneas; el selector de productos DEBE ofrecer solo los productos activos del proveedor elegido, consultados al servidor con el filtro `proveedor_id`, y el de presentaciones solo las activas de compra. Por línea DEBE mostrar cantidad base, costo base e importe neto, y en total el neto, el IVA sugerido y el total de factura (editable, prellenado con neto + IVA), todo con `decimal.js` y el motor compartido de `cmp-02-compra.json`; los importes viajan como string. De contado DEBE pedir medios con la suma igual al total. El envío DEBE usar un `Operation-Id` que se conserva al reintentar tras un error de red y se renueva al cambiar el contenido.

#### Scenario: Vista previa de una línea con IVA
- **WHEN** el usuario carga Caja x12, cantidad 1, valor `18000,00`, con IVA 21%
- **THEN** ve costo base `1.239,669421` e importe neto `14.876,03`, iguales a los del servidor
- **Regla:** CMP-02; CST-02; `02` §10.4

#### Scenario: Medios que no suman el total
- **WHEN** en una compra de contado los medios no suman el total de factura
- **THEN** el botón de confirmar queda deshabilitado con el faltante a la vista
- **Regla:** INV-08; TR-10 (el servidor valida igual)

#### Scenario: Error del servidor por línea
- **WHEN** el servidor rechaza con `CANTIDAD_INVALIDA` en la línea 2
- **THEN** el error se muestra junto a la línea 2 y el resto del formulario se conserva
- **Regla:** TR-10

### Requirement: Resultado de la compra con oferta de costo informado

Tras confirmar, la pantalla DEBE mostrar la compra registrada y, si la respuesta informa líneas con costo distinto del vigente y el usuario tiene `EDITAR_COSTOS`, DEBE ofrecer por línea "Registrar como costo informado", que envía `COSTO_INFORMAR` con presentación, valor, IVA y bonificación de la línea y vigencia desde la fecha de la compra. No DEBE registrarse ningún costo sin esa acción (CMP-04, `design.md` D7).

#### Scenario: El usuario acepta registrar el costo
- **GIVEN** la compra informó `Vino A` con costo base `"1100.000000"` contra `"1000.000000"` vigente
- **WHEN** el usuario elige "Registrar como costo informado" en esa línea
- **THEN** se envía un `COSTO_INFORMAR` y el costo vigente de `Vino A` a esa fecha pasa a `"1100.000000"`
- **Regla:** CMP-04; CST-01; CST-03

#### Scenario: El usuario no hace nada
- **WHEN** el usuario sale de la pantalla sin elegir la acción
- **THEN** no se registró ningún costo informado
- **Regla:** CMP-04

### Requirement: Listado, detalle y anulación desde la pantalla

El listado DEBE paginar por cursor y filtrar por proveedor, estado y fechas, mostrando fecha, proveedor, condición, total de factura y estado. El detalle DEBE mostrar líneas con cantidades en cajas + unidades (CAT-08), el pago con sus medios y, si está anulada, motivo, usuario y momento. "Anular" DEBE pedir un motivo del ámbito `ANULACION_COMPRA` y, si es de contado, si el proveedor devuelve el dinero; las observaciones de la respuesta DEBEN mostrarse al usuario.

#### Scenario: Anulación con observación
- **WHEN** el usuario anula una compra y el servidor responde `ACEPTADO_CON_OBSERVACIONES` con `ANULACION_COMPRA_SIN_RECALCULO`
- **THEN** la pantalla muestra la compra `ANULADA` y un aviso de que el costo promedio no se recalculó
- **Regla:** CMP-06; SYN-04

#### Scenario: Cantidades en cajas y unidades
- **WHEN** el detalle muestra una línea de 31 unidades de `Vino A` (referencia Caja x6)
- **THEN** se ve "5 cajas + 1 unidad"
- **Regla:** CAT-08
