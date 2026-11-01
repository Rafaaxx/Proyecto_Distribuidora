## MODIFIED Requirements

### Requirement: El inicio muestra las ventas sin enviar

El inicio de `/ruta` DEBE mostrar cuántas ventas del teléfono están sin enviar ("N ventas sin enviar" o "Todo enviado"), la hora de la última sincronización exitosa y el botón «Sincronizar», y DEBE ofrecer "Vender" y "Ventas de hoy" con el permiso y los datos que correspondan. Mientras sincroniza, el botón DEBE quedar deshabilitado con «Enviando…»; si otra pestaña está sincronizando, DEBE decirlo (`design.md` D13 y D14 del 22a; `design.md` D8 del 22b).

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

#### Scenario: Sincronizar a pedido
- **GIVEN** `vendedor` con señal y dos ventas sin enviar
- **WHEN** toca «Sincronizar»
- **THEN** el botón muestra «Enviando…», las ventas se envían y el inicio pasa a "Todo enviado" con la hora de la última sincronización
- **Regla:** `02` §13.3; SYN-04

#### Scenario: Sincronizar sin señal
- **GIVEN** `vendedor` sin señal y una venta sin enviar
- **WHEN** toca «Sincronizar»
- **THEN** se informa que no hay conexión, la venta sigue "1 venta sin enviar" y la última sincronización no cambia
- **Regla:** `02` §13.3; SYN-09

### Requirement: Ventas de hoy desde la base local

"Ventas de hoy" DEBE listar, desde la base local, las ventas del teléfono de la jornada abierta con número, cliente, total y estado de envío («Sin enviar», «Enviada», «Con observaciones» o «Rechazada»), y abrir cada una con su detalle y las acciones de la nota, con o sin conexión (`design.md` D14 del 22a; `design.md` D8 del 22b).

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

#### Scenario: Estados después de sincronizar
- **GIVEN** V03-000142 aceptada, V03-000143 aceptada con observaciones y V03-000144 rechazada
- **WHEN** abre "Ventas de hoy"
- **THEN** ve «Enviada», «Con observaciones» y «Rechazada», respectivamente
- **Regla:** SYN-04; SYN-09

## ADDED Requirements

### Requirement: El estado de la sincronización se ve en todo momento

Toda pantalla de `/ruta` con la sesión desbloqueada DEBE mostrar en la cabecera el estado de la conexión y cuántas ventas quedan sin enviar ("Todo enviado" si ninguna), con un aviso si hay ventas rechazadas; tocarlo DEBE abrir la pantalla «Sincronización» (`design.md` D8; `02` §13.3).

#### Scenario: Cabecera con pendientes
- **GIVEN** `vendedor` sin señal con una venta sin enviar, en la pantalla de Clientes
- **WHEN** mira la cabecera
- **THEN** ve que no hay conexión y "1 sin enviar"
- **Regla:** `02` §13.3

#### Scenario: Cabecera con una rechazada
- **GIVEN** una venta rechazada en la jornada
- **WHEN** el vendedor mira la cabecera
- **THEN** ve el aviso de venta rechazada y, al tocarlo, se abre «Sincronización»
- **Regla:** SYN-09; `02` §13.3

### Requirement: La pantalla de sincronización muestra lo pendiente y lo que volvió con problemas

La pantalla «Sincronización» DEBE mostrar la conexión, las ventas sin enviar, la última sincronización exitosa, el último error con su texto y su código, el botón «Sincronizar» y la lista de ventas «Con observaciones» y «Rechazadas» con número, cliente, total, estado y, en las rechazadas, el código, cada una con su detalle. Una rechazada DEBE decir «El sistema no aceptó esta venta. Sigue guardada en el teléfono; avisá a administración.» (`design.md` D8).

#### Scenario: Lista de ventas con problemas
- **GIVEN** V03-000143 aceptada con observaciones y V03-000144 rechazada con `JORNADA_INEXISTENTE`
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve las dos con su estado y, en V03-000144, el código `JORNADA_INEXISTENTE` y el texto de la rechazada
- **Regla:** SYN-04; SYN-06; SYN-09

#### Scenario: Sesión vencida
- **GIVEN** la última sincronización cortada por sesión vencida
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve «Iniciá sesión con señal para enviar las ventas»
- **Regla:** `02` §12.3

#### Scenario: Sin problemas
- **GIVEN** todas las ventas de la jornada enviadas sin observaciones
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve "Todo enviado", la hora de la última sincronización y la lista vacía
- **Regla:** `02` §13.3

### Requirement: Vender se deshabilita por debajo de la versión mínima

Si la aplicación está por debajo de la última versión mínima conocida, «Vender» DEBE mostrarse deshabilitado en el inicio y en la ficha del cliente con «Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación» y su ayuda, y las demás pantallas y el envío de la cola DEBEN seguir funcionando (`design.md` D7; `02` §6.6).

#### Scenario: Inicio desactualizado
- **GIVEN** la aplicación en 1.2.0 y la mínima conocida 1.3.0
- **WHEN** `vendedor` abre el inicio
- **THEN** «Vender» está deshabilitado con el aviso y «Ventas de hoy» y «Sincronizar» siguen disponibles
- **Regla:** `02` §6.6

#### Scenario: Ficha del cliente desactualizada
- **GIVEN** la aplicación por debajo de la mínima conocida
- **WHEN** `vendedor` abre la ficha de un cliente
- **THEN** «Vender» está deshabilitado con el mismo aviso
- **Regla:** `02` §6.6
