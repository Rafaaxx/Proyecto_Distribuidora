# ruta/area-de-ruta Specification

## Purpose
Da al vendedor, en el teléfono, su área propia `/ruta`: inicio de sesión, apertura de la jornada, estado de la conexión y de los datos, y las pantallas de consulta de clientes, productos y stock que leen la base local, más su cuenta y su ayuda (RUT-03, SYN-11, `02` §13.1).

## Requirements

### Requirement: El área de ruta tiene su propio inicio de sesión

`/ruta` DEBE ofrecer su propia pantalla de inicio de sesión, con usuario y contraseña, que usa el mismo inicio de sesión del servidor y envía el identificador del dispositivo, sin descargar el código de `/admin`. Sin conexión DEBE indicar que el inicio de sesión requiere conexión. Los rechazos (credenciales, bloqueo por intentos, usuario inactivo) DEBEN mostrarse en palabras simples (`design.md` D12).

#### Scenario: Inicio de sesión correcto
- **GIVEN** `vendedor` en el teléfono, con conexión
- **WHEN** ingresa su usuario y contraseña en `/ruta`
- **THEN** inicia sesión, el dispositivo queda registrado y se le pide definir su PIN si no lo tiene
- **Regla:** SEG-01; SEG-02; SEG-03

#### Scenario: Credenciales incorrectas
- **WHEN** ingresa una contraseña incorrecta
- **THEN** ve el rechazo explicado y sigue en la pantalla de inicio de sesión
- **Regla:** SEG-01; ADR-018

#### Scenario: Sin conexión
- **GIVEN** el teléfono sin señal y sin sesión local
- **WHEN** abre `/ruta`
- **THEN** ve que iniciar sesión requiere conexión
- **Regla:** SEG-01

### Requirement: El inicio muestra la jornada, la conexión y los datos

El inicio de `/ruta` DEBE mostrar: el usuario; la jornada abierta con su ubicación, o "Abrir jornada" si no hay; el estado de la conexión; la fecha y hora del último bootstrap con "Actualizar datos"; la advertencia de almacenamiento si corresponde; y accesos a Clientes, Productos, Stock, Mi cuenta y Ayuda. Con la jornada en `EN_RENDICION`, cerrada o liberada desde administración, DEBE indicarlo al consultar el servidor con conexión.

#### Scenario: Con jornada y datos
- **GIVEN** `vendedor` con su jornada abierta en "Camioneta 1" y un bootstrap de las 7:40
- **WHEN** abre el inicio
- **THEN** ve "Camioneta 1", "Datos de las 7:40", el estado de la conexión y los accesos
- **Regla:** RUT-03; SYN-11

#### Scenario: Jornada liberada desde administración
- **GIVEN** la jornada del vendedor liberada por `sup01`
- **WHEN** el vendedor abre el inicio con conexión
- **THEN** ve que su jornada ya no está abierta y la opción de abrir otra
- **Regla:** RUT-09

### Requirement: La jornada se abre desde el área de ruta

Con conexión y `ABRIR_JORNADA`, el inicio DEBE ofrecer "Abrir jornada" con las ubicaciones activas, con toma y libres. Abrir DEBE usar el mismo comando `JORNADA_ABRIR` del servidor, con reintento con el mismo `Operation-Id`, y encadenar el bootstrap. Los rechazos (`UBICACION_TOMADA`, `USUARIO_CON_JORNADA`, `DISPOSITIVO_CON_JORNADA`, `UBICACION_INACTIVA`, `UBICACION_SIN_TOMA`) DEBEN explicarse. Sin conexión o sin el permiso, la opción NO DEBE ofrecerse (o DEBE estar deshabilitada con su motivo).

#### Scenario: Apertura correcta
- **GIVEN** `vendedor` sin jornada, con conexión y "Camioneta 1" libre
- **WHEN** elige "Camioneta 1" y confirma
- **THEN** la jornada queda abierta, se descarga el bootstrap y el inicio muestra la ubicación
- **Regla:** RUT-01; RUT-03

#### Scenario: Ubicación tomada
- **GIVEN** "Camioneta 1" tomada por la jornada de `vendedor2`
- **WHEN** `vendedor` intenta abrir sobre ella
- **THEN** ve que la ubicación está tomada y no se abre nada
- **Regla:** RUT-01; INV-16

#### Scenario: Doble envío de la apertura
- **GIVEN** la respuesta de la apertura perdida por un corte
- **WHEN** el dispositivo reintenta con el mismo `Operation-Id`
- **THEN** recibe la misma jornada, sin abrir otra
- **Regla:** INV-06; SYN-02

#### Scenario: Sin conexión
- **GIVEN** el teléfono sin señal y sin jornada
- **WHEN** el vendedor mira el inicio
- **THEN** "Abrir jornada" está deshabilitado y dice que requiere conexión
- **Regla:** RUT-03

### Requirement: Clientes desde la base local con cartera primero

La pantalla Clientes DEBE listar primero los clientes de la cartera del usuario y el consumidor final, y DEBE permitir buscar por nombre, código o documento en todos los clientes bajados. La ficha DEBE mostrar los datos de contacto, el estado (con la marca de suspendido), la lista aplicable, el saldo y el crédito disponible locales (el saldo del bootstrap más lo que cuenta según la conciliación de la cola local), con la fecha de los datos y, si hay operaciones que cuentan, la leyenda «Incluye tus ventas desde la última actualización» (`design.md` D6; D19 del 21).

#### Scenario: Cartera primero
- **GIVEN** `vendedor` con dos clientes asignados entre 200
- **WHEN** abre Clientes
- **THEN** ve primero el consumidor final y sus dos clientes, y al buscar encuentra cualquiera de los 200
- **Regla:** `01` §19; ADR-060; INV-17

#### Scenario: Ficha con saldo y crédito
- **GIVEN** un cliente con límite `"500000.00"` y saldo `"125000.00"` en el bootstrap y ninguna operación local que cuente
- **WHEN** el vendedor abre su ficha
- **THEN** ve el saldo `$ 125.000,00`, el disponible `$ 375.000,00` y la hora de los datos, sin la leyenda
- **Regla:** CRE-01; INV-03

#### Scenario: Ficha con ventas del teléfono
- **GIVEN** un cliente con límite $200.000 y saldo $100.000 en el bootstrap y una venta local por $70.000 con $20.000 cobrados que el bootstrap no incluye
- **WHEN** el vendedor abre su ficha
- **THEN** ve el saldo `$ 150.000,00`, el disponible `$ 50.000,00` y la leyenda «Incluye tus ventas desde la última actualización»
- **Regla:** CRE-08; COB-04; INV-03

#### Scenario: Cliente suspendido
- **GIVEN** un cliente `SUSPENDIDO`
- **WHEN** aparece en la lista
- **THEN** lleva la marca de suspendido
- **Regla:** CLI-02

### Requirement: Productos y stock desde la base local

La pantalla Productos DEBE listar los productos con búsqueda por nombre o código, mostrando por presentación el precio de la versión vigente ahora de la lista predeterminada (o "Sin precio") y el stock local de la camioneta convertido a cajas y unidades. La pantalla Stock DEBE listar el stock local de la ubicación tomada por producto en cajas y unidades, sin costos. El stock local es el del bootstrap menos lo que cuenta según la conciliación de la cola local; con operaciones que cuentan, las pantallas DEBEN mostrar la leyenda «Incluye tus ventas desde la última actualización». Un stock local negativo DEBE mostrarse como tal. Los importes DEBEN calcularse con el motor compartido y formatearse sin pasar por `number` (`design.md` D6; D19 del 21).

#### Scenario: Precio por presentación
- **GIVEN** "Malbec 750" con precio de referencia `"48000.00"` por caja de 6 en la versión vigente
- **WHEN** el vendedor abre Productos
- **THEN** ve la caja a `$ 48.000,00` y la unidad a `$ 8.000,00`
- **Regla:** PRC-22; ADR-010; INV-03

#### Scenario: Versión programada que entra en vigencia
- **GIVEN** la versión 4 programada para las 14:00 en el bootstrap
- **WHEN** el vendedor abre Productos a las 14:05 sin señal
- **THEN** ve los precios de la versión 4
- **Regla:** PRC-20; `design.md` D6 del 21

#### Scenario: Stock en cajas y unidades
- **GIVEN** 20 unidades base de "Malbec 750" (caja de 6) en el bootstrap y ninguna operación local que cuente
- **WHEN** abre Stock
- **THEN** ve "3 cajas y 2 unidades", sin la leyenda
- **Regla:** CAT-08; INV-04

#### Scenario: Stock con ventas del teléfono
- **GIVEN** 63 botellas de Vino A en el bootstrap y una venta local de 15 que el bootstrap no incluye
- **WHEN** el vendedor abre Stock y Productos
- **THEN** las dos pantallas muestran 48 botellas y la leyenda
- **Regla:** RUT-04; INV-04

#### Scenario: Stock después de actualizar
- **GIVEN** la misma venta ya incluida en un bootstrap posterior con 48 botellas
- **WHEN** el vendedor abre Stock
- **THEN** ve 48 botellas, no 33
- **Regla:** RUT-04; CRE-08

### Requirement: Mi cuenta en el área de ruta

"Mi cuenta" DEBE ofrecer: "Mi contraseña" (cambiar la propia contraseña con la actual, con conexión, igual que en `/admin`), "Cambiar PIN" y "Cerrar sesión". Sin conexión, "Mi contraseña" y "Cerrar sesión" DEBEN estar deshabilitados con su motivo.

#### Scenario: Cambiar la contraseña desde el teléfono
- **GIVEN** `vendedor` con conexión
- **WHEN** cambia su contraseña con la actual correcta
- **THEN** la contraseña cambia y la sesión del teléfono sigue abierta
- **Regla:** ADR-060

#### Scenario: Contraseña actual incorrecta
- **WHEN** ingresa una contraseña actual incorrecta
- **THEN** ve el rechazo explicado y nada cambia
- **Regla:** ADR-060; ADR-018

#### Scenario: Sin conexión
- **GIVEN** el teléfono sin señal
- **WHEN** abre Mi cuenta
- **THEN** "Mi contraseña" y "Cerrar sesión" están deshabilitados y "Cambiar PIN" funciona
- **Regla:** SEG-03; ADR-060

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

La pantalla «Sincronización» DEBE mostrar la conexión, las ventas sin enviar, la última sincronización exitosa, el último error con su texto y su código, el botón «Sincronizar» y la lista de ventas «Con observaciones» y «Rechazadas» con número, cliente, total y estado; en las observadas, el texto de la primera observación y cuántas más hay; en las rechazadas, el texto del motivo y el código. Cada fila DEBE abrir el detalle de la venta. Una rechazada DEBE decir además «Sigue guardada en el teléfono; avisá a administración.» (`design.md` D4 y D5; D8 del 22b).

#### Scenario: Lista de ventas con problemas
- **GIVEN** V03-000143 aceptada con `LISTA_NO_VIGENTE` y `STOCK_NEGATIVO`, y V03-000144 rechazada con `JORNADA_INEXISTENTE`
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve en V03-000143 «Los precios no eran los de la versión vigente de la lista en ese momento.» y «1 más», y en V03-000144 «La jornada de la venta no existe en el sistema.», el código `JORNADA_INEXISTENTE` y «Sigue guardada en el teléfono; avisá a administración.»
- **Regla:** SYN-04; SYN-06; SYN-07; SYN-09

#### Scenario: Código sin texto
- **GIVEN** una venta rechazada con un código que el teléfono no conoce
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve «El sistema no aceptó esta venta.» con el código
- **Regla:** SYN-06

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

### Requirement: El detalle de una venta explica sus observaciones o su rechazo

El detalle de una venta local («Venta guardada») DEBE mostrar, sin conexión, la sección «Observaciones» con todas las observaciones guardadas de su comando, cada una con su texto (con el producto, el medio o el autorizador del detalle tomados de la base local, o «un producto», «un medio» o «un supervisor» si ya no están), o la sección «Motivo del rechazo» con el texto del código, el código y «Sigue guardada en el teléfono; avisá a administración.». Una venta «Con observaciones» sin observaciones guardadas DEBE decir «El detalle no está en el teléfono; consultalo con administración.» (`design.md` D3, D4 y D5).

#### Scenario: Observaciones con detalle
- **GIVEN** V03-000143 aceptada con `MEDIO_INACTIVO` sobre el medio "Transferencia" y `VENTA_SIN_COSTO` de "Malbec 750"
- **WHEN** el vendedor abre su detalle sin señal
- **THEN** ve «El medio Transferencia estaba dado de baja cuando llegó el cobro.» y «Malbec 750 no tenía costo; la línea quedó sin costo.»
- **Regla:** SYN-07; `02` §13.1

#### Scenario: Producto que ya no está en la base local
- **GIVEN** una observación `STOCK_NEGATIVO` de un producto que no figura en el último bootstrap
- **WHEN** el vendedor abre el detalle
- **THEN** ve «Quedó stock negativo de un producto.»
- **Regla:** SYN-07

#### Scenario: Motivo del rechazo
- **GIVEN** V03-000144 rechazada con `TOTALES_INCONSISTENTES`
- **WHEN** el vendedor abre su detalle
- **THEN** ve «Los importes de la venta no cierran con el cálculo del sistema.», el código y «Sigue guardada en el teléfono; avisá a administración.»
- **Regla:** SYN-05; SYN-06

#### Scenario: Venta enviada antes de guardar observaciones
- **GIVEN** una venta «Con observaciones» cuyo resultado llegó sin la lista de observaciones
- **WHEN** el vendedor abre su detalle
- **THEN** ve «El detalle no está en el teléfono; consultalo con administración.»
- **Regla:** SYN-04

#### Scenario: Venta enviada sin observaciones
- **GIVEN** una venta «Enviada»
- **WHEN** el vendedor abre su detalle
- **THEN** no ve ninguna de las dos secciones
- **Regla:** SYN-04

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

### Requirement: Se cobra a un cliente desde el teléfono

Con `REGISTRAR_COBRANZA` en los permisos de los datos del día, el área de ruta DEBE ofrecer «Cobrar» en el inicio (con selector de cliente, la cartera primero) y en la ficha del cliente, con o sin señal. Se DEBE poder cobrar a clientes `ACTIVO` y `SUSPENDIDO` de los datos del día, de la cartera o no; al consumidor final NO (no aparece en el selector y su ficha no ofrece «Cobrar»). La pantalla DEBE mostrar el saldo local actual y el resultante, pedir el importe, de 1 a 20 medios activos de los datos del día con su importe y la referencia donde el medio la exige, y una observación opcional de hasta 500 caracteres. «Confirmar cobranza» NO DEBE confirmar si el importe no es mayor que cero o tiene más de dos decimales, si la suma de los medios no es el importe, si falta una referencia exigida o si la observación es más larga; DEBE pedir la confirmación «¿Registrar la cobranza de {importe} a {cliente}?» y, si el saldo resultante queda a favor del cliente, avisar «El cliente queda con {importe} a favor.» antes de guardar. Con datos cargados, salir de la pantalla DEBE pedir «¿Descartar la cobranza?» y la versión nueva de la aplicación DEBE esperar a que termine. Sin permiso, «Cobrar» NO DEBE aparecer (`design.md` D3, D4, D8).

#### Scenario: Cobrar sin señal
- **GIVEN** `vendedor` sin señal, con su jornada abierta y Kiosco La Esquina debiendo $150.000
- **WHEN** cobra $50.000 con $30.000 en efectivo y $20.000 por transferencia n.º 0042 y confirma
- **THEN** ve «Cobranza guardada» «Sin enviar» y la ficha del cliente muestra saldo $100.000
- **Regla:** COB-01; COB-02; COB-04; CRE-08

#### Scenario: Medios que no suman el importe
- **WHEN** el importe es $50.000 y los medios suman $49.000
- **THEN** «Confirmar cobranza» no confirma y se indica la diferencia
- **Regla:** INV-08; COB-02

#### Scenario: Referencia exigida
- **WHEN** un medio que exige referencia queda sin ella o con solo espacios
- **THEN** «Confirmar cobranza» no confirma y se pide la referencia
- **Regla:** COB-02

#### Scenario: Importe inválido
- **WHEN** el importe es cero, negativo o tiene tres decimales
- **THEN** «Confirmar cobranza» no confirma
- **Regla:** COB-01; INV-03

#### Scenario: Saldo a favor
- **GIVEN** Kiosco La Esquina debe $150.000 según el teléfono
- **WHEN** el vendedor cobra $160.000
- **THEN** antes de guardar se avisa «El cliente queda con $10.000 a favor.» y solo se guarda si lo confirma
- **Regla:** COB-01; CC-04

#### Scenario: Consumidor final
- **WHEN** el vendedor abre la ficha del consumidor final o el selector de cliente de «Cobrar»
- **THEN** la ficha no ofrece «Cobrar» y el consumidor final no está en el selector
- **Regla:** COB-01; CLI-03

#### Scenario: Cliente suspendido o fuera de la cartera
- **WHEN** el vendedor cobra a un cliente suspendido o que no está en su cartera
- **THEN** la cobranza se guarda sin aviso
- **Regla:** COB-01; `01` §19

#### Scenario: Sin permiso
- **GIVEN** un usuario sin `REGISTRAR_COBRANZA` en los datos del día
- **WHEN** abre el inicio o la ficha de un cliente
- **THEN** no ve «Cobrar»
- **Regla:** SYN-10; SEG-06

#### Scenario: Salir con datos cargados
- **GIVEN** la pantalla de cobro con un importe cargado
- **WHEN** el vendedor toca el menú inferior
- **THEN** se pregunta «¿Descartar la cobranza?» y, si no confirma, sigue en la pantalla con los datos
- **Regla:** `02` §13.5

### Requirement: Las cobranzas se ven en las pantallas de ruta

El área de ruta DEBE mostrar «Cobranzas de hoy» con las cobranzas independientes de la jornada (cliente, importe, hora y estado de envío) y el detalle de cada una («Cobranza guardada»: cliente, importe, medios, observación, momento, estado y la explicación de sus observaciones o su rechazo con los textos de la tabla de códigos). «Sincronización» DEBE listar las cobranzas «Con observaciones» y «Rechazadas» como «Cobranza a {cliente}». Lo pendiente DEBE decirse uniendo las partes que no son cero («N ventas, M anulaciones y K cobranzas sin enviar»), en el inicio y en los avisos de cierre de sesión y de pendientes de otro usuario. No hay comprobante de cobranza (`design.md` D8, D9, D10, D11).

#### Scenario: Cobranzas de hoy
- **GIVEN** dos cobranzas de la jornada, una «Enviada» y otra «Sin enviar»
- **WHEN** el vendedor abre «Cobranzas de hoy»
- **THEN** ve las dos con cliente, importe, hora y estado
- **Regla:** SYN-09

#### Scenario: Cobranza con observaciones
- **GIVEN** una cobranza aceptada con `MEDIO_INACTIVO` sobre "Billetera"
- **WHEN** el vendedor abre su detalle
- **THEN** ve «Con observaciones» y «El medio Billetera estaba dado de baja cuando llegó el cobro.»
- **Regla:** SYN-07

#### Scenario: Cobranza rechazada en Sincronización
- **GIVEN** una cobranza a Kiosco La Esquina rechazada con `RECURSO_NO_ENCONTRADO`
- **WHEN** el vendedor abre «Sincronización»
- **THEN** ve «Cobranza a Kiosco La Esquina» con «El sistema no tiene el cliente o el medio de pago de la cobranza.» y el aviso de que el teléfono ya no la descuenta, con acceso al detalle
- **Regla:** SYN-06; SYN-09

#### Scenario: Código desconocido
- **WHEN** una cobranza vuelve rechazada con un código que no está en la tabla
- **THEN** se muestra el texto general de la cobranza y el código
- **Regla:** SYN-06

#### Scenario: Pendientes
- **GIVEN** dos ventas, una anulación y una cobranza sin enviar
- **WHEN** el vendedor mira el inicio o cierra sesión
- **THEN** lee «2 ventas, 1 anulación y 1 cobranza sin enviar»
- **Regla:** SYN-09

#### Scenario: Solo cobranzas pendientes
- **GIVEN** tres cobranzas sin enviar y nada más
- **WHEN** otro usuario inicia sesión en el teléfono
- **THEN** el aviso dice «Hay 3 cobranzas sin enviar de {vendedor}.»
- **Regla:** SYN-09; INV-05

#### Scenario: Doble sincronización
- **GIVEN** una cobranza «Enviada»
- **WHEN** se sincroniza otra vez
- **THEN** «Cobranzas de hoy» y «Sincronización» no cambian
- **Regla:** INV-06

### Requirement: Cobrar se corta con la jornada no abierta y por debajo de la versión mínima

Cuando el teléfono guardó que su jornada ya no está abierta, o la aplicación está por debajo de la versión mínima, «Cobrar» DEBE quedar deshabilitado en el inicio y en la ficha, con el aviso correspondiente, y «Confirmar cobranza» NO DEBE confirmar (el formulario sigue). La cola DEBE seguir enviándose. Vale sin señal y después de recargar. El aviso de la jornada DEBE terminar con «Lo que ya vendiste y cobraste se sigue enviando.» (`design.md` D7).

#### Scenario: Jornada liberada
- **GIVEN** el teléfono guardó que su jornada fue liberada
- **WHEN** el vendedor abre el inicio o la ficha
- **THEN** «Cobrar» está deshabilitado y se lee «Tu jornada fue liberada. Lo que ya vendiste y cobraste se sigue enviando.»
- **Regla:** RUT-09

#### Scenario: Formulario abierto cuando se corta
- **GIVEN** la pantalla de cobro con datos cargados
- **WHEN** el teléfono se entera de que la jornada no está abierta y el vendedor toca «Confirmar cobranza»
- **THEN** no se guarda nada, los datos siguen y se muestra el aviso
- **Regla:** RUT-09; INV-01

#### Scenario: Versión por debajo de la mínima
- **WHEN** la aplicación está por debajo de la versión mínima conocida
- **THEN** «Cobrar» está deshabilitado con el aviso de versión y las cobranzas guardadas se siguen enviando
- **Regla:** `02` §6.6

#### Scenario: Sin dato guardado
- **WHEN** el teléfono no tiene marcada la jornada como no abierta y la versión está al día
- **THEN** «Cobrar» funciona como siempre
- **Regla:** RUT-09
