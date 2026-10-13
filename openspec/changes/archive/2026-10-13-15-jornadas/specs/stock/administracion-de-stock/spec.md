## ADDED Requirements

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
