# Administración de stock — Especificación

## Purpose

Ofrecer en el área `/admin` las pantallas de ubicaciones, stock por ubicación, kardex y stock inicial, mostradas según los permisos efectivos del usuario (ADR-027) y sin lógica de negocio en los componentes.

## Requirements

### Requirement: Sección Stock según permisos

El área `/admin` DEBE mostrar una sección "Stock" con las pantallas de ubicaciones, stock por ubicación, kardex y stock inicial, cada acción visible solo con su permiso (`design.md` D1-D3, D15) usando `usePermisos()` como única fuente (ADR-027). Ocultar una acción NO DEBE reemplazar la validación del servidor (SEG-06).

#### Scenario: Administrador ve todo

- **GIVEN** un Administrador
- **WHEN** abre `/admin`
- **THEN** ve la sección Stock con ubicaciones, stock, kardex y la acción "Registrar stock inicial"
- **Regla:** ADR-027

#### Scenario: Usuario sin permiso de stock inicial

- **GIVEN** un usuario sin el permiso de D1
- **WHEN** abre la pantalla de stock
- **THEN** no ve la acción "Registrar stock inicial"
- **Regla:** ADR-027; SEG-06

### Requirement: Cantidades en cajas y unidades, costos con decimal exacto

Las pantallas DEBEN mostrar las cantidades en cajas + unidades según CAT-08 y manejar costos solo con `decimal.js` y `lib/money.ts`, sin convertirlos a `number` para calcular (`CLAUDE.md` §4). Los costos DEBEN mostrarse solo con `VER_COSTOS`.

#### Scenario: Stock mostrado en cajas

- **GIVEN** 31 unidades de Vino A (caja x6)
- **WHEN** se muestra el stock
- **THEN** se lee "5 cajas + 1 unidad"
- **Regla:** CAT-08

#### Scenario: Stock negativo mostrado con signo

- **GIVEN** −8 unidades de Vino A (caja x6) llegadas de un change posterior
- **WHEN** se muestra el stock
- **THEN** se lee "−(1 caja + 2 unidades)"
- **Regla:** CAT-08

### Requirement: Formulario de stock inicial

El formulario DEBE permitir elegir la ubicación y cargar varias líneas con producto, cantidad escrita en cajas + unidades (convertida a unidad base con aritmética entera) y costo por unidad base; DEBE generar un `operation_id` nuevo por envío y reutilizarlo en el reintento, avisar que requiere conexión sin encolar, mostrar el mensaje del servidor ante un rechazo y, con `VER_COSTOS`, previsualizar el promedio resultante con la misma función que los fixtures de CST-11 (`design.md` D14).

#### Scenario: Envío aceptado

- **GIVEN** un Administrador en el formulario
- **WHEN** carga 10 cajas de Vino A (caja x6) a `"1000.000000"` y envía
- **THEN** se envía `cantidad_base` 60 y, al aceptarse, vuelve al stock de la ubicación
- **Regla:** CAT-08; STK-01

#### Scenario: Rechazo del servidor

- **GIVEN** un Administrador que envía una corrección mayor que el saldo
- **WHEN** el servidor responde `STOCK_INSUFICIENTE`
- **THEN** la pantalla muestra el mensaje y conserva lo cargado
- **Regla:** TR-10

#### Scenario: Reintento con el mismo `operation_id`

- **GIVEN** un envío que falló por red
- **WHEN** el usuario reintenta sin cambiar nada
- **THEN** se reutiliza el mismo `operation_id`
- **Regla:** TR-07; SYN-02

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

### Requirement: Pantallas de jornadas según permiso

La sección Stock de `/admin` DEBE ofrecer "Jornadas" (listado con filtros de ubicación, usuario, estado y fechas, y detalle) a quien tenga `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, con `usePermisos()` como única fuente (ADR-027; `design.md` D15, D16). Cada acción DEBE mostrarse solo con su permiso y en el estado que la admite: "Abrir jornada" con `ABRIR_JORNADA`; "Rendir" con `RENDIR_JORNADA` sobre una jornada `ABIERTA`; "Cerrar" con `RENDIR_JORNADA` sobre una `EN_RENDICION`; "Liberar" con `LIBERAR_UBICACION` sobre una `ABIERTA` o `EN_RENDICION`. Ocultar una acción NO DEBE reemplazar la validación del servidor (SEG-06).

#### Scenario: Un Vendedor ve sus acciones

- **GIVEN** un Vendedor (`ABRIR_JORNADA`, sin `RENDIR_JORNADA` ni `LIBERAR_UBICACION`)
- **WHEN** abre la sección Stock
- **THEN** ve "Jornadas" y "Abrir jornada"
- **AND** en el detalle de una jornada `ABIERTA` no ve "Rendir", "Cerrar" ni "Liberar"
- **Regla:** ADR-027; `01` §19

#### Scenario: Una Supervisora ve todas las acciones

- **GIVEN** una Supervisora (`ABRIR_JORNADA`, `RENDIR_JORNADA` y `LIBERAR_UBICACION`)
- **WHEN** abre el detalle de una jornada `ABIERTA`
- **THEN** ve "Rendir" y "Liberar", y no ve "Cerrar"
- **Regla:** ADR-027; `01` §18

#### Scenario: Administración rinde y cierra pero no libera ni abre

- **GIVEN** un usuario del rol Administración (`RENDIR_JORNADA`, sin `ABRIR_JORNADA` ni `LIBERAR_UBICACION`)
- **WHEN** abre la sección y el detalle de una jornada `EN_RENDICION`
- **THEN** ve "Jornadas" y "Cerrar", y no ve "Abrir jornada" ni "Liberar"
- **Regla:** ADR-027; `01` §19

#### Scenario: Una jornada terminada no ofrece acciones

- **GIVEN** una jornada `CERRADA` o `LIBERADA`
- **WHEN** una Supervisora abre su detalle
- **THEN** ve su estado y sus datos, y ninguna acción
- **Regla:** `01` §18; TR-06

#### Scenario: Un usuario sin permisos de jornada

- **GIVEN** un usuario del rol Consulta
- **WHEN** abre `/admin`
- **THEN** no ve "Jornadas"
- **Regla:** ADR-027; SEG-06

### Requirement: Abrir, rendir, cerrar y liberar desde las pantallas

La pantalla de apertura DEBE ofrecer para elegir solo las ubicaciones activas que requieren toma y no están tomadas, avisar que la operación requiere conexión y reutilizar el mismo `operation_id` al reintentar tras un error de red. "Liberar" DEBE pedir un motivo obligatorio del ámbito `LIBERACION_JORNADA` y admitir una observación. El detalle de una jornada `ABIERTA` DEBE ofrecer "Cargar vehículo", que lleva al alta de transferencia con el destino precargado (RUT-02). Los mensajes del servidor (`UBICACION_TOMADA`, `USUARIO_CON_JORNADA`, `DISPOSITIVO_CON_JORNADA`, `JORNADA_ESTADO_INVALIDO`, `MOTIVO_INVALIDO`) DEBEN mostrarse al usuario. Los componentes NO DEBEN contener lógica de negocio.

#### Scenario: Elegir la ubicación al abrir

- **GIVEN** "Camioneta 1" tomada, "Camioneta 2" libre, "Camioneta 3" inactiva y "Depósito central" sin toma
- **WHEN** un Vendedor abre la pantalla "Abrir jornada"
- **THEN** solo puede elegir "Camioneta 2"
- **Regla:** RUT-01; RUT-03

#### Scenario: Otro la tomó mientras tanto

- **GIVEN** un Vendedor con "Camioneta 2" elegida, que otro vendedor acaba de tomar
- **WHEN** confirma la apertura
- **THEN** ve el mensaje de `UBICACION_TOMADA` y sigue en la pantalla de apertura
- **Regla:** INV-16

#### Scenario: Reintento tras un error de red

- **GIVEN** una apertura cuyo envío falló por la red
- **WHEN** el Vendedor vuelve a confirmar sin cambiar la ubicación
- **THEN** se envía con el mismo `operation_id`
- **Regla:** SYN-02; INV-06

#### Scenario: Liberar exige motivo

- **GIVEN** una Supervisora en el diálogo "Liberar" de una jornada `ABIERTA`
- **WHEN** intenta confirmar sin elegir motivo
- **THEN** el diálogo no envía nada y le pide el motivo
- **Regla:** RUT-09

#### Scenario: Después de liberar

- **GIVEN** una Supervisora que libera una jornada con el motivo "Vendedor ausente"
- **WHEN** el servidor acepta
- **THEN** el detalle pasa a "Liberada" con el motivo, quién y cuándo, y desaparecen las acciones
- **Regla:** RUT-09

#### Scenario: Cargar vehículo desde la jornada

- **GIVEN** Juan en el detalle de su jornada `ABIERTA` sobre "Camioneta 1"
- **WHEN** elige "Cargar vehículo"
- **THEN** llega al alta de transferencia con "Camioneta 1" como destino
- **Regla:** RUT-02

### Requirement: La ubicación tomada se ve en las pantallas de stock

El listado de ubicaciones y el stock por ubicación DEBEN indicar qué ubicaciones están tomadas, por quién y desde cuándo. El alta de transferencia, el alta de ajuste y sus anulaciones DEBEN mostrar el mensaje del servidor ante `UBICACION_TOMADA` y conservar lo cargado. El formulario de ubicación DEBE mostrar ese mismo mensaje al intentar desactivar o cambiar una ubicación tomada (STK-09; `design.md` D14, D16).

#### Scenario: Marca de ubicación tomada

- **GIVEN** "Camioneta 1" tomada por la jornada de Juan desde las 8:00
- **WHEN** un usuario con `TRANSFERIR_STOCK` abre el listado de ubicaciones
- **THEN** "Camioneta 1" aparece marcada como tomada por Juan desde las 8:00 y las demás, sin marca
- **Regla:** STK-09; RUT-01

#### Scenario: Transferencia rechazada por toma

- **GIVEN** un Vendedor que carga una transferencia hacia "Camioneta 1", tomada por otro
- **WHEN** confirma y el servidor responde `UBICACION_TOMADA`
- **THEN** ve el mensaje correspondiente y el formulario conserva las líneas cargadas
- **Regla:** STK-09

#### Scenario: Desactivar una ubicación tomada desde el formulario

- **GIVEN** un Administrador en el formulario de "Camioneta 2", tomada
- **WHEN** la desactiva y el servidor responde `UBICACION_TOMADA`
- **THEN** ve el mensaje y el formulario conserva lo cargado
- **Regla:** `design.md` D14
