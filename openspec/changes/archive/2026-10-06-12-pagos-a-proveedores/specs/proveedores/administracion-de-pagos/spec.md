## Purpose

Definir las pantallas de `/admin` para registrar, consultar y anular pagos a proveedores, con los permisos efectivos de `GET /api/v1/yo` (`usePermisos()`, `<SiTienePermiso>`, ADR-027). Escrita con la opción A de `design.md` D3, D7, D8 y D11, pendientes de aprobación (tarea 0.1).

## ADDED Requirements

### Requirement: Las pantallas de pagos respetan los permisos

La entrada de menú "Pagos a proveedores" y sus rutas DEBEN mostrarse solo con `REGISTRAR_PAGO_PROVEEDOR` o `ANULAR_PAGO_PROVEEDOR`; el botón "Nuevo pago" solo con `REGISTRAR_PAGO_PROVEEDOR`; "Anular" solo con `ANULAR_PAGO_PROVEEDOR` y sobre un pago que el servidor admite anular (ADR-027, `design.md` D7). Un 403 del servidor DEBE mostrarse como falta de permiso.

#### Scenario: Usuario con solo anulación
- **GIVEN** un usuario con `ANULAR_PAGO_PROVEEDOR` y sin `REGISTRAR_PAGO_PROVEEDOR`
- **WHEN** abre `/admin/pagos-proveedores`
- **THEN** ve el listado y el detalle con "Anular", pero no "Nuevo pago"
- **Regla:** `01` §19; ADR-027

#### Scenario: Usuario sin permisos de pago
- **WHEN** un usuario sin `REGISTRAR_PAGO_PROVEEDOR` ni `ANULAR_PAGO_PROVEEDOR` navega a `/admin/pagos-proveedores`
- **THEN** no ve la entrada de menú y la ruta muestra el aviso de falta de permiso
- **Regla:** ADR-027

#### Scenario: Pago de una compra vigente
- **GIVEN** un usuario con `ANULAR_PAGO_PROVEEDOR` en el detalle de un pago de origen `COMPRA` cuya compra está `CONFIRMADA`
- **WHEN** mira las acciones
- **THEN** no se ofrece "Anular" y se indica que ese pago se anula anulando la compra, con enlace a ella
- **Regla:** CMP-05; `design.md` D2

### Requirement: Alta de pago con saldo y medios

El formulario DEBE pedir proveedor, fecha (por defecto hoy), importe, uno o más medios activos con su importe y la referencia cuando el medio la exige, y una observación opcional. DEBE mostrar el saldo actual del proveedor con su rótulo ("Le debemos" / "Saldo a nuestro favor") y el saldo resultante, y el faltante o sobrante entre el importe y la suma de los medios, calculados con `decimal.js` sin convertir importes a `number` (INV-03). NO DEBE permitir enviar mientras los medios no sumen el importe. Si el saldo resultante queda a favor de la organización, DEBE pedir una confirmación explícita antes de enviar (`design.md` D3); si el saldo del proveedor no se pudo leer, DEBE avisarlo y pedir esa confirmación igual, y mientras se está leyendo NO DEBE permitir enviar. DEBE generar un `Operation-Id` nuevo por contenido y reutilizarlo en un reintento del mismo envío, avisar que requiere conexión sin encolar nada y mostrar el mensaje del servidor junto al medio que causó un error.

#### Scenario: Saldo actual y resultante
- **GIVEN** `Bodega Sur` con saldo `"153720.00"`
- **WHEN** el usuario la elige y tipea un importe de 100.000
- **THEN** ve "Le debemos $ 153.720,00" y "Saldo después del pago: Le debemos $ 53.720,00"
- **Regla:** PAG-02; CC-04; ADR-034 punto 8

#### Scenario: Faltante de medios
- **WHEN** el importe es $ 152.460,00 y los medios cargados son $ 100.000,00 en efectivo
- **THEN** ve "Faltan $ 52.460,00" y el botón de confirmar está deshabilitado
- **Regla:** INV-08; PAG-01

#### Scenario: Pago que deja saldo a nuestro favor
- **GIVEN** `Bodega Sur` con saldo `"153720.00"`
- **WHEN** el usuario carga un pago de $ 160.000,00 y confirma
- **THEN** ve el aviso "Queda saldo a nuestro favor de $ 6.280,00" y el pago se envía solo si lo acepta
- **Regla:** PAG-02; `design.md` D3

#### Scenario: Saldo del proveedor que no se pudo leer
- **GIVEN** un proveedor elegido cuya lectura de saldo falló (error de red, del servidor o 403)
- **WHEN** el usuario carga un pago y confirma
- **THEN** ve el aviso "No pudimos leer el saldo del proveedor; no podemos avisarte si este pago supera la deuda" y el pago se envía solo si lo acepta; mientras el saldo se está leyendo el botón de confirmar está deshabilitado
- **Regla:** PAG-02; `design.md` D3

#### Scenario: Referencia obligatoria
- **WHEN** el usuario agrega el medio "Transferencia" sin referencia
- **THEN** el campo de referencia se marca obligatorio y no se puede confirmar
- **Regla:** `01` §4; PAG-01

#### Scenario: Error del servidor en un medio
- **WHEN** el servidor responde `MEDIO_PAGO_INACTIVO` para el segundo medio
- **THEN** el mensaje se muestra junto a ese medio y el formulario conserva lo cargado
- **Regla:** TR-10

#### Scenario: Reintento tras error de red
- **WHEN** el envío falla por red y el usuario reintenta sin cambiar nada
- **THEN** se reenvía con el mismo `Operation-Id`
- **Regla:** INV-06; TR-07

### Requirement: Listado, detalle y anulación de pagos desde la pantalla

El listado DEBE paginar por cursor y filtrar por proveedor, estado, origen y fechas, mostrando fecha, proveedor, importe, origen y estado. El detalle DEBE mostrar los medios con importe y referencia, la observación, el enlace a la compra cuando el origen es `COMPRA` y, si está anulado, motivo, usuario y momento. "Anular" DEBE pedir un motivo del ámbito `ANULACION_PAGO` y una confirmación que muestre el saldo resultante del proveedor.

#### Scenario: Listado de la semana
- **GIVEN** un pago de `"100000.00"` a `Bodega Sur` y uno de `"80000.00"` a `Bodega Norte` con fecha de hoy
- **WHEN** el usuario filtra por la fecha de hoy
- **THEN** ve los dos pagos con $ 100.000,00 y $ 80.000,00
- **Regla:** PAG-01; TR-04

#### Scenario: Anulación desde el detalle
- **GIVEN** un usuario con `ANULAR_PAGO_PROVEEDOR` en el detalle de un pago independiente `CONFIRMADA` de `"52460.00"`
- **WHEN** elige "Anular", el motivo "Pago rechazado o devuelto" y confirma
- **THEN** se envía `PAGO_PROVEEDOR_ANULAR` y el detalle muestra el pago anulado con motivo, usuario y momento
- **Regla:** PAG-03

#### Scenario: Rechazo del servidor al anular
- **WHEN** el servidor responde `PAGO_YA_ANULADO`
- **THEN** la pantalla muestra el mensaje y recarga el detalle, que ya figura anulado
- **Regla:** PAG-03; TR-10

### Requirement: El pago se inicia y se sigue desde la cuenta corriente del proveedor

La cuenta corriente de un proveedor DEBE ofrecer "Registrar pago" dentro de `<SiTienePermiso permiso="REGISTRAR_PAGO_PROVEEDOR">`, que abre el alta con ese proveedor precargado, también si el proveedor está inactivo (`design.md` D5, D11). Cada movimiento `PAGO` o `ANULACION_PAGO` DEBE enlazar al detalle de su pago y cada `COMPRA` o `ANULACION_COMPRA` al de su compra, solo para quien tiene permiso de leerlos. Al volver de registrar o anular, el saldo y los movimientos DEBEN verse actualizados.

#### Scenario: Pagar desde la cuenta corriente
- **GIVEN** un usuario con `GESTIONAR_PROVEEDORES` y `REGISTRAR_PAGO_PROVEEDOR` en la cuenta corriente de `Bodega Sur`
- **WHEN** elige "Registrar pago"
- **THEN** se abre el alta con `Bodega Sur` elegida y su saldo a la vista
- **Regla:** PAG-01; ADR-027

#### Scenario: Movimiento enlazado a su pago
- **GIVEN** la cuenta corriente con un movimiento "Pago" de $ 100.000,00
- **WHEN** un usuario con permiso de lectura de pagos lo abre
- **THEN** llega al detalle de ese pago con sus medios
- **Regla:** CC-01 (operación origen); CC-07

#### Scenario: Sin permiso de lectura de pagos
- **GIVEN** un usuario con `GESTIONAR_PROVEEDORES` y sin permisos de pago
- **WHEN** mira la cuenta corriente
- **THEN** ve el movimiento "Pago" sin enlace y no ve "Registrar pago"
- **Regla:** `01` §19; ADR-027; `design.md` D7
