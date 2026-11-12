## MODIFIED Requirements

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

## ADDED Requirements

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
