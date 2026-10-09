## ADDED Requirements

### Requirement: Pantallas de transferencias según permiso

El área `/admin` DEBE ofrecer en la sección Stock la pantalla "Transferencias" (listado con filtros de ubicación y fechas, alta y detalle) solo con `TRANSFERIR_STOCK`, usando `usePermisos()` como única fuente (ADR-027, `design.md` D11). El alta DEBE permitir elegir origen y destino activos y distintos, elegir productos **del stock del origen** (`design.md` D7), cargar cada cantidad en cajas + unidades (convertida a unidad base con aritmética entera, CAT-08) y mostrar por línea el saldo actual y el resultante en origen y destino, marcando un resultado negativo. DEBE generar un `operation_id` nuevo por contenido y reutilizarlo en el reintento, avisar que requiere conexión sin encolar y mostrar el mensaje del servidor ante un rechazo conservando lo cargado. El listado y el detalle DEBEN mostrar el estado de cada transferencia.

#### Scenario: Vendedor carga la camioneta

- **GIVEN** un Vendedor con `TRANSFERIR_STOCK` y 120 unidades de Vino A (caja x6) en el depósito
- **WHEN** elige depósito → "Camioneta 1", carga 8 cajas de Vino A y confirma
- **THEN** antes de confirmar ve "Depósito: 12 cajas" y "Camioneta 1: 8 cajas" como resultado, se envía `cantidad_base` 48 y, al aceptarse, ve el detalle de la transferencia en estado "Confirmada"
- **Regla:** STK-07; CAT-08

#### Scenario: Usuario sin permiso de transferir

- **GIVEN** un usuario sin `TRANSFERIR_STOCK`
- **WHEN** abre `/admin`
- **THEN** no ve "Transferencias" en el menú
- **Regla:** ADR-027; SEG-06

#### Scenario: Rechazo por stock insuficiente

- **GIVEN** un Supervisor que transfiere más de lo que hay en el origen
- **WHEN** el servidor responde `STOCK_INSUFICIENTE`
- **THEN** la pantalla muestra el mensaje junto a la línea y conserva lo cargado
- **Regla:** STK-05; TR-10

#### Scenario: Reintento con el mismo `operation_id`

- **GIVEN** un envío que falló por red
- **WHEN** el usuario reintenta sin cambiar nada
- **THEN** se reutiliza el mismo `operation_id`; si cambia una cantidad, se genera uno nuevo
- **Regla:** TR-07; SYN-02

#### Scenario: Producto sin stock en el origen

- **GIVEN** un Administrador con `PERMITIR_STOCK_NEGATIVO`, 48 unidades de Vino A en el depósito y ninguna fila de saldo de "Agua 500" en el depósito
- **WHEN** abre el selector de productos de una transferencia desde el depósito
- **THEN** puede elegir Vino A y cargar 60 (resultado −12 marcado), pero "Agua 500" no aparece en el selector
- **Regla:** STK-05; `design.md` D7

### Requirement: Pantallas de ajustes según permiso

El área `/admin` DEBE ofrecer en la sección Stock la pantalla "Ajustes" (listado con filtros de ubicación, motivo y fechas, alta y detalle) solo con `AJUSTAR_STOCK` (`design.md` D11). El alta DEBE pedir ubicación, motivo de los activos del ámbito `AJUSTE_STOCK`, observación opcional y líneas con signo en cajas + unidades, mostrar por línea el saldo actual y el resultante y marcar un resultado negativo, que el servidor rechaza siempre (`design.md` D1). Los costos DEBEN mostrarse solo con `VER_COSTOS`, sin calcular importes en el frontend. Mismo manejo de `operation_id`, conexión y errores que la transferencia. El listado y el detalle DEBEN mostrar el estado de cada ajuste.

#### Scenario: Registrar una rotura

- **GIVEN** un usuario de Administración con `AJUSTAR_STOCK` y 120 unidades de Vino A (caja x6) en el depósito
- **WHEN** elige el depósito, el motivo "Rotura", carga −1 caja de Vino A y confirma
- **THEN** ve como resultado "19 cajas", se envía `cantidad_base` −6 y, al aceptarse, ve el detalle del ajuste en estado "Confirmada"
- **Regla:** STK-08; CAT-08

#### Scenario: Vendedor sin permiso de ajustar

- **GIVEN** un Vendedor con `TRANSFERIR_STOCK` y sin `AJUSTAR_STOCK`
- **WHEN** abre la sección Stock
- **THEN** no ve "Ajustes" ni la acción "Ajustar"
- **Regla:** STK-08; ADR-027

#### Scenario: Ajuste positivo de un producto sin costo

- **GIVEN** un usuario que ajusta +24 de un producto sin compras
- **WHEN** el servidor responde `PRODUCTO_SIN_COSTO`
- **THEN** la pantalla explica que ese stock se carga con stock inicial o con una compra
- **Regla:** `design.md` D3

#### Scenario: Ajuste que dejaría el saldo negativo

- **GIVEN** un Administrador con `PERMITIR_STOCK_NEGATIVO` y 10 unidades de Vino A en el depósito
- **WHEN** carga −11 y el servidor responde `STOCK_INSUFICIENTE`
- **THEN** la pantalla muestra junto a la línea que un ajuste no puede dejar stock negativo y conserva lo cargado
- **Regla:** STK-05; `design.md` D1

### Requirement: Anular una transferencia o un ajuste desde su detalle

El detalle de una transferencia o de un ajuste `CONFIRMADA` DEBE ofrecer "Anular" solo a quien puede hacerlo: en una transferencia, a su creador con `TRANSFERIR_STOCK` o a quien tenga además `ANULAR_TRANSFERENCIA`; en un ajuste, a quien tenga `AJUSTAR_STOCK` (`design.md` D5, D11). "Anular" DEBE abrir un diálogo que pide un motivo activo del ámbito `ANULACION_TRANSFERENCIA` o `ANULACION_AJUSTE`, avisar que requiere conexión sin encolar, reutilizar el `operation_id` en el reintento y mostrar el mensaje del servidor ante un rechazo. El detalle de una operación `ANULADA` DEBE mostrar el motivo, el usuario y el momento de la anulación y NO DEBE ofrecer "Anular".

#### Scenario: Vendedora anula su transferencia

- **GIVEN** una Vendedora en el detalle de una transferencia `CONFIRMADA` que ella creó
- **WHEN** toca "Anular", elige "Error de carga" y confirma
- **THEN** el detalle pasa a "Anulada" con el motivo, su nombre y el momento, y el botón desaparece
- **Regla:** TR-06; `design.md` D5

#### Scenario: Transferencia de otro usuario

- **GIVEN** un Vendedor sin `ANULAR_TRANSFERENCIA` y un usuario de Administración con ese permiso, en el detalle de una transferencia creada por un tercero
- **WHEN** ven el detalle
- **THEN** el Vendedor no ve "Anular" y el usuario de Administración sí
- **Regla:** ADR-027; `01` §19; `design.md` D5

#### Scenario: Anulación rechazada por stock insuficiente

- **GIVEN** un usuario que anula una transferencia cuyo destino ya no tiene las unidades
- **WHEN** el servidor responde `STOCK_INSUFICIENTE`
- **THEN** el diálogo muestra el mensaje y la transferencia sigue "Confirmada"
- **Regla:** STK-05; TR-10

#### Scenario: Anulación de un ajuste

- **GIVEN** un usuario de Administración con `AJUSTAR_STOCK` en el detalle de un ajuste `CONFIRMADA` cargado por otro
- **WHEN** toca "Anular", elige "Error de carga" y confirma
- **THEN** el detalle pasa a "Anulada" y el listado lo muestra con ese estado
- **Regla:** TR-06; `design.md` D5

### Requirement: Acciones de transferencia y ajuste desde el stock por ubicación

El stock por ubicación DEBE ofrecer "Transferir desde acá" (con `TRANSFERIR_STOCK`) y "Ajustar" (con `AJUSTAR_STOCK`), y DEBE marcar los saldos negativos; sobre un saldo negativo, "Ajustar" DEBE precargar la cantidad positiva que lo lleva a cero, editable (`design.md` D2, D11). El kardex DEBE mostrar el motivo de un ajuste, el estado de la operación de origen y los movimientos de una anulación como tales, y DEBE enlazar al detalle de la transferencia o del ajuste solo si el usuario tiene el permiso de lectura correspondiente.

#### Scenario: Regularizar un saldo negativo

- **GIVEN** un Administrador y −12 unidades de Vino A en el depósito
- **WHEN** elige "Ajustar" sobre esa línea
- **THEN** el formulario abre con el depósito y Vino A +12 precargados, y el saldo resultante en 0
- **Regla:** STK-05; `design.md` D2

#### Scenario: Enlace del kardex según permiso

- **GIVEN** un movimiento `AJUSTE` en el kardex
- **WHEN** lo ven un Administrador y un Vendedor
- **THEN** ambos ven el motivo; solo el Administrador ve el enlace al ajuste
- **Regla:** ADR-027; `design.md` D7

#### Scenario: Operación anulada en el kardex

- **GIVEN** una transferencia anulada
- **WHEN** un Vendedor ve el kardex del producto en el destino
- **THEN** ve la entrada marcada "Anulada" y la salida rotulada "Anulación de transferencia", las dos con enlace al mismo detalle
- **Regla:** TR-06; `design.md` D5.1
