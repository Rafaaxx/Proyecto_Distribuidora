## ADDED Requirements

### Requirement: El inicio muestra las ventas sin enviar

El inicio de `/ruta` DEBE mostrar cuántas ventas del teléfono están sin enviar ("N ventas sin enviar" o "Todo enviado") y DEBE ofrecer "Vender" y "Ventas de hoy" con el permiso y los datos que correspondan (`design.md` D13, D14).

#### Scenario: Con ventas sin enviar
- **GIVEN** `vendedor` con dos ventas confirmadas en el teléfono
- **WHEN** abre el inicio
- **THEN** ve "2 ventas sin enviar"
- **Regla:** SYN-09; `02` §13.3

#### Scenario: Sin datos del día
- **GIVEN** un teléfono con la jornada abierta pero sin bootstrap aplicado
- **WHEN** se abre el inicio
- **THEN** "Vender" no está disponible y se indica que faltan los datos del día
- **Regla:** RUT-03

### Requirement: Ventas de hoy desde la base local

"Ventas de hoy" DEBE listar, desde la base local, las ventas del teléfono de la jornada abierta con número, cliente, total y estado de envío, y abrir cada una con su detalle y las acciones de la nota, con o sin conexión (`design.md` D14).

#### Scenario: Lista sin señal
- **GIVEN** `vendedor` sin señal con las ventas V03-000142 y V03-000143 confirmadas
- **WHEN** abre "Ventas de hoy"
- **THEN** ve las dos con su cliente, su total y "Sin enviar"
- **Regla:** `02` §13.1; SYN-09

#### Scenario: Ventas de otra jornada
- **GIVEN** ventas de una jornada anterior todavía en el teléfono
- **WHEN** abre "Ventas de hoy"
- **THEN** no aparecen en la lista
- **Regla:** RUT-04

### Requirement: Cerrar sesión con ventas sin enviar avisa y no borra

Cerrar sesión o iniciar con otro usuario cuando hay ventas sin enviar DEBE avisar cuántas son y que quedan guardadas, y NO DEBE borrarlas (`design.md` D16).

#### Scenario: Cerrar sesión con pendientes
- **GIVEN** `vendedor` con señal y una venta sin enviar
- **WHEN** toca "Cerrar sesión"
- **THEN** se avisa "Tenés 1 venta sin enviar. Queda guardada en el teléfono y se envía cuando vuelvas a entrar vos." y, si confirma, la sesión se cierra y la venta sigue en el teléfono
- **Regla:** SEG-03; SYN-09

#### Scenario: Otro usuario en el teléfono
- **GIVEN** una venta sin enviar de `vendedor`
- **WHEN** `vendedor2` inicia sesión en ese teléfono
- **THEN** se avisa que hay 1 venta sin enviar de `vendedor` y la venta sigue en el teléfono
- **Regla:** SEG-03; `02` §6.4
