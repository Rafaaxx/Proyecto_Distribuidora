## ADDED Requirements

### Requirement: Una venta de la jornada se anula desde el teléfono

El detalle de una venta del teléfono DEBE ofrecer «Anular venta» solo si el usuario tiene `ANULAR_VENTA` en los datos del día, la venta es de la jornada de la sesión, esa jornada no figura como no abierta, la venta no está anulada ni «Rechazada» y la aplicación no está por debajo de la versión mínima. Con o sin señal, la anulación DEBE pedir un motivo activo del ámbito `ANULACION_VENTA` de los datos del día, una observación opcional de hasta 500 caracteres y, si la venta tuvo cobro en el acto, si se devuelve lo cobrado (al consumidor final, siempre sí y sin poder cambiarlo; sin cobro, no se pregunta), y DEBE pedir confirmación. Confirmada, la venta DEBE mostrarse «Anulada» y la anulación se envía como las ventas (`design.md` D5, D10).

#### Scenario: Anular sin señal
- **GIVEN** `sup01` con `ANULAR_VENTA`, su jornada abierta en el teléfono, sin señal, y la venta V03-000142 de esa jornada
- **WHEN** abre el detalle, toca «Anular venta», elige "Error de carga" y confirma
- **THEN** la venta se ve «Anulada» y la anulación «Sin enviar»
- **Regla:** VTA-24; VTA-20; SYN-09

#### Scenario: Sin el permiso
- **GIVEN** `vendedor`, sin `ANULAR_VENTA`
- **WHEN** abre el detalle de una venta suya
- **THEN** no ve «Anular venta»
- **Regla:** VTA-24; SEG-06

#### Scenario: Venta rechazada
- **WHEN** el vendedor abre una venta «Rechazada»
- **THEN** no ve «Anular venta»
- **Regla:** SYN-06; SYN-09

#### Scenario: Venta de otra jornada
- **WHEN** el vendedor abre una venta de una jornada anterior guardada en el teléfono
- **THEN** no ve «Anular venta»
- **Regla:** VTA-24

#### Scenario: Venta con cobro en el acto
- **GIVEN** una venta a Kiosco La Esquina con $30.000 cobrados
- **WHEN** el vendedor intenta confirmar la anulación sin elegir si devuelve lo cobrado
- **THEN** la anulación no se confirma hasta que lo elija
- **Regla:** VTA-22

#### Scenario: Consumidor final
- **WHEN** el vendedor anula una venta al consumidor final
- **THEN** la devolución figura elegida y no se puede cambiar
- **Regla:** VTA-22; CLI-03

#### Scenario: Sin motivo
- **WHEN** el vendedor intenta confirmar sin elegir motivo, o con una observación de 501 caracteres
- **THEN** la anulación no se confirma y se indica qué falta
- **Regla:** VTA-20

#### Scenario: Doble toque
- **WHEN** el vendedor toca dos veces «Confirmar anulación»
- **THEN** hay una sola anulación y un solo comando
- **Regla:** INV-06

### Requirement: Las anulaciones se ven en las pantallas de ruta

«Ventas de hoy» y el detalle DEBEN mostrar «Anulada» en una venta anulada en el teléfono. El detalle DEBE mostrar la sección de la anulación con el motivo, la devolución, la observación, su estado de envío y, si volvió con observaciones o rechazada, su explicación traducida. «Sincronización» DEBE listar también las anulaciones «Con observaciones» y «Rechazadas», identificadas como anulación de la venta, cada una con su resumen y el acceso al detalle. Lo pendiente DEBE contar ventas y anulaciones sin enviar. La nota de una venta anulada en el teléfono DEBE llevar la marca «ANULADA» con la fecha, el motivo y el destino de lo cobrado, y no llevar saldo (`design.md` D10, D11).

#### Scenario: Ventas de hoy
- **GIVEN** tres ventas de la jornada, una anulada
- **WHEN** el vendedor abre «Ventas de hoy»
- **THEN** ve las tres y la anulada con «Anulada»
- **Regla:** VTA-20; SYN-09

#### Scenario: Anulación rechazada en Sincronización
- **GIVEN** una anulación rechazada con `VENTA_YA_ANULADA`
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve la anulación de esa venta como «Rechazada», con el texto del rechazo, el código y el aviso, y al tocarla abre el detalle
- **Regla:** SYN-06; SYN-09

#### Scenario: Anulación con observaciones
- **GIVEN** una anulación aceptada con `JORNADA_LIBERADA`
- **WHEN** el vendedor abre el detalle de la venta
- **THEN** la sección de la anulación dice «Con observaciones» y explica que la jornada había sido liberada cuando llegó la anulación
- **Regla:** SYN-07; RUT-09

#### Scenario: Pendientes
- **GIVEN** dos ventas y una anulación sin enviar
- **WHEN** el vendedor mira el inicio
- **THEN** ve «2 ventas y 1 anulación sin enviar»
- **Regla:** SYN-09

#### Scenario: Nota de una venta anulada
- **GIVEN** una venta anulada en el teléfono con devolución de lo cobrado
- **WHEN** el vendedor comparte la nota sin señal
- **THEN** la nota lleva «ANULADA» en cada página y la línea con la fecha, el motivo y «Se devolvió lo cobrado.», sin saldo
- **Regla:** VTA-13; VTA-22

#### Scenario: Doble sincronización
- **WHEN** se sincroniza dos veces con una anulación aceptada
- **THEN** «Ventas de hoy», el detalle y «Sincronización» muestran lo mismo
- **Regla:** INV-06

### Requirement: Vender y anular se cortan cuando la jornada ya no está abierta

Cuando el teléfono tiene guardado que la jornada de la sesión ya no está abierta, el inicio DEBE avisarlo con el texto de su estado (liberada, en rendición, cerrada o desconocido) y que lo vendido se sigue enviando; «Vender» DEBE quedar deshabilitado en el inicio y en la ficha del cliente; «Confirmar venta» NO DEBE confirmar (el carrito abierto sigue y se muestra el aviso); y «Anular venta» NO DEBE ofrecerse. Stock, Clientes, Productos, «Ventas de hoy», las notas y «Sincronización» DEBEN seguir disponibles, y con señal el inicio DEBE ofrecer abrir una jornada nueva. Sin ese dato guardado, nada cambia (`design.md` D9).

#### Scenario: Jornada liberada
- **GIVEN** el teléfono guardó que la jornada J1 está `LIBERADA`
- **WHEN** el vendedor mira el inicio
- **THEN** ve «Tu jornada fue liberada.» y «Lo que ya vendiste se sigue enviando.», y «Vender» deshabilitado
- **Regla:** RUT-09

#### Scenario: Carrito abierto
- **GIVEN** un carrito con líneas y el teléfono se entera de que J1 está `LIBERADA`
- **WHEN** el vendedor toca «Confirmar venta»
- **THEN** la venta no se confirma, el carrito sigue y se muestra el aviso
- **Regla:** RUT-09; INV-01

#### Scenario: Jornada en rendición
- **GIVEN** el teléfono guardó que la jornada está `EN_RENDICION`
- **WHEN** el vendedor mira el inicio
- **THEN** ve «Tu jornada está en rendición.» y «Vender» deshabilitado
- **Regla:** RUT-05; RUT-09

#### Scenario: Sigue sin señal
- **GIVEN** el teléfono guardó que J1 está `LIBERADA` y pierde la señal
- **WHEN** el vendedor recarga la aplicación
- **THEN** «Vender» sigue deshabilitado con el mismo aviso
- **Regla:** RUT-09

#### Scenario: Sin dato guardado
- **GIVEN** J1 liberada en el servidor y el teléfono sin señal desde antes
- **WHEN** el vendedor vende
- **THEN** la venta se confirma como siempre
- **Regla:** RUT-09; SYN-05

#### Scenario: Anular con la jornada liberada
- **GIVEN** el teléfono guardó que J1 está `LIBERADA`
- **WHEN** `sup01` abre el detalle de una venta de J1
- **THEN** no ve «Anular venta»
- **Regla:** VTA-24; RUT-09
