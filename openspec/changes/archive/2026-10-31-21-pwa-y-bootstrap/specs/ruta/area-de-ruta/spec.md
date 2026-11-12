## Purpose

Da al vendedor, en el teléfono, su área propia `/ruta`: inicio de sesión, apertura de la jornada, estado de la conexión y de los datos, y las pantallas de consulta de clientes, productos y stock que leen la base local, más su cuenta y su ayuda (RUT-03, SYN-11, `02` §13.1).

## ADDED Requirements

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

La pantalla Clientes DEBE listar primero los clientes de la cartera del usuario y el consumidor final, y DEBE permitir buscar por nombre, código o documento en todos los clientes bajados. La ficha DEBE mostrar los datos de contacto, el estado (con la marca de suspendido), la lista aplicable, el saldo y el crédito disponible del bootstrap, con su fecha (`design.md` D19).

#### Scenario: Cartera primero
- **GIVEN** `vendedor` con dos clientes asignados entre 200
- **WHEN** abre Clientes
- **THEN** ve primero el consumidor final y sus dos clientes, y al buscar encuentra cualquiera de los 200
- **Regla:** `01` §19; ADR-060; INV-17

#### Scenario: Ficha con saldo y crédito
- **GIVEN** un cliente con límite `"500000.00"` y saldo `"125000.00"` en el bootstrap
- **WHEN** el vendedor abre su ficha
- **THEN** ve el saldo `$ 125.000,00`, el disponible `$ 375.000,00` y la hora de los datos
- **Regla:** CRE-01; INV-03

#### Scenario: Cliente suspendido
- **GIVEN** un cliente `SUSPENDIDO`
- **WHEN** aparece en la lista
- **THEN** lleva la marca de suspendido
- **Regla:** CLI-02

### Requirement: Productos y stock desde la base local

La pantalla Productos DEBE listar los productos con búsqueda por nombre o código, mostrando por presentación el precio de la versión vigente ahora de la lista predeterminada (o "Sin precio") y el stock de la camioneta convertido a cajas y unidades. La pantalla Stock DEBE listar el stock de la ubicación tomada por producto en cajas y unidades, sin costos. Los importes DEBEN calcularse con el motor compartido y formatearse sin pasar por `number` (`design.md` D19).

#### Scenario: Precio por presentación
- **GIVEN** "Malbec 750" con precio de referencia `"48000.00"` por caja de 6 en la versión vigente
- **WHEN** el vendedor abre Productos
- **THEN** ve la caja a `$ 48.000,00` y la unidad a `$ 8.000,00`
- **Regla:** PRC-22; ADR-010; INV-03

#### Scenario: Versión programada que entra en vigencia
- **GIVEN** la versión 4 programada para las 14:00 en el bootstrap
- **WHEN** el vendedor abre Productos a las 14:05 sin señal
- **THEN** ve los precios de la versión 4
- **Regla:** PRC-20; `design.md` D6

#### Scenario: Stock en cajas y unidades
- **GIVEN** 20 unidades base de "Malbec 750" (caja de 6)
- **WHEN** abre Stock
- **THEN** ve "3 cajas y 2 unidades"
- **Regla:** CAT-08; INV-04

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
