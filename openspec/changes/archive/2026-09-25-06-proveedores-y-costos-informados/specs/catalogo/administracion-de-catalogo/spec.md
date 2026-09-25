## MODIFIED Requirements

### Requirement: Alta y edición desde la pantalla usan comandos idempotentes
Cada alta o modificación de la pantalla DEBE enviarse con un `Operation-Id` UUIDv7 nuevo generado en el cliente, que se DEBE conservar si el usuario reintenta la misma operación tras un error de red. Los formularios DEBEN validar en el cliente lo mismo que el servidor puede validar sin datos (campos obligatorios, incluido el proveedor del producto, unidades enteras ≥ 1, exactamente una referencia de venta), sin reemplazar la validación del servidor. Los errores de dominio del servidor DEBEN mostrarse con un mensaje comprensible asociado a su código.

#### Scenario: Alta de producto con presentaciones
- **WHEN** el usuario confirma el formulario de alta con código `VA-001`, nombre `Vino A`, categoría `Vinos`, proveedor `Bodega Andina`, alícuota `21%`, presentaciones `Botella` (1) y `Caja x6` (6, referencia)
- **THEN** se envía un único comando de alta con el proveedor y, al aceptarse, el producto aparece en el listado sin recargar la página
- **Regla:** CAT-01; CAT-02; CAT-03; CAT-06

#### Scenario: El formulario exige proveedor
- **WHEN** el usuario confirma el formulario de alta o edición sin proveedor elegido
- **THEN** el formulario muestra que el proveedor es obligatorio y no envía el comando
- **Regla:** CAT-01; CAT-06

#### Scenario: El formulario impide dos referencias
- **WHEN** el usuario marca dos presentaciones como referencia, o una referencia sin uso en venta
- **THEN** el formulario muestra el error y no envía el comando
- **Regla:** CAT-03

#### Scenario: Reintento tras error de red no duplica
- **WHEN** un alta se envía cuya respuesta no llegó por un corte de red y el usuario reintenta sin cambiar los datos
- **THEN** se reenvía con el mismo `Operation-Id` y existe un solo producto
- **Regla:** INV-06; SYN-02

#### Scenario: Código duplicado informado por el servidor
- **WHEN** el usuario da de alta otro producto con un código que ya existe
- **THEN** la pantalla muestra que el código ya existe junto al campo código, y conserva lo cargado
- **Regla:** CAT-01; TR-10

#### Scenario: Proveedor inactivo informado por el servidor
- **WHEN** el servidor rechaza el alta o la edición con `PROVEEDOR_INACTIVO` porque el proveedor se desactivó mientras el formulario estaba abierto
- **THEN** la pantalla muestra el error junto al campo proveedor y conserva lo cargado
- **Regla:** TR-10; `design.md` D5

#### Scenario: Unidades congeladas informadas por el servidor
- **WHEN** el usuario intenta cambiar las unidades de una presentación usada en operaciones
- **THEN** la pantalla muestra que debe crear una presentación nueva y desactivar la anterior
- **Regla:** CAT-04; INV-18

## ADDED Requirements

### Requirement: El formulario de producto ofrece los proveedores activos de la organización
El formulario de alta y edición de producto DEBE elegir el proveedor de un selector alimentado por el listado reducido de proveedores de la organización del token, que devuelve solo los activos y es accesible con `GESTIONAR_CATALOGO` (`design.md` D8). El selector DEBE ofrecer solo los proveedores activos; en edición DEBE conservar seleccionado el proveedor actual del producto aunque esté inactivo (y por eso no venga en el listado), mostrando su **nombre real** (tomado del detalle de producto, no del listado de opciones) señalado como inactivo. El filtro del cliente no reemplaza la validación del servidor.

#### Scenario: Un proveedor desactivado no se ofrece
- **WHEN** se abre el formulario de alta de producto con `Bodega Andina` activo y `Bodega Sur` desactivado en la organización A
- **THEN** el selector de proveedor ofrece `Bodega Andina` y no `Bodega Sur`
- **Regla:** CAT-05; CAT-06

#### Scenario: Edición de un producto con proveedor inactivo
- **WHEN** se abre la edición de un producto cuyo proveedor actual, `Bodega Sur`, está inactivo
- **THEN** el selector conserva `Bodega Sur` seleccionado con su nombre real, marcado como inactivo, y ofrece además los activos
- **Regla:** CAT-06; `design.md` D2, D5, D9 y D13 (opción B)

#### Scenario: Los proveedores de otra organización no se listan
- **WHEN** un usuario de la organización A abre el selector de proveedor con proveedores existentes en B
- **THEN** no aparece ningún proveedor de B
- **Regla:** INV-21
