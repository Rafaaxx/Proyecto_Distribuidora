## Purpose

Entrega al dispositivo del vendedor, al abrir su jornada, todos los datos que necesita para operar sin conexión (SYN-11, ADR-006), en una sola lectura coherente, filtrada por organización, usuario y permisos, y sin datos sensibles que no tengan uso en el teléfono.

## ADDED Requirements

### Requirement: El bootstrap se pide con una jornada abierta en el dispositivo

El sistema DEBE ofrecer `GET /api/v1/sync/bootstrap` a un usuario con sesión habilitada (ADR-028) que tenga una jornada `ABIERTA` propia en el dispositivo del token. Sin esa jornada DEBE responder 409 `JORNADA_REQUERIDA` sin contenido. La organización, el usuario y el dispositivo DEBEN salir del token. El parámetro `since` DEBE aceptarse y ignorarse: la respuesta es siempre el conjunto completo (ADR-006). El bootstrap no DEBE escribir nada en la base (`design.md` D2).

#### Scenario: Bootstrap con la jornada abierta
- **GIVEN** `vendedor` con una jornada `ABIERTA` sobre "Camioneta 1" desde el dispositivo de su sesión
- **WHEN** pide `GET /api/v1/sync/bootstrap`
- **THEN** recibe 200 con todas las secciones y la jornada con su ubicación
- **Regla:** RUT-03; SYN-11

#### Scenario: Sin jornada abierta
- **GIVEN** `vendedor` sin jornada no cerrada, o con su jornada en `EN_RENDICION`, o con su jornada abierta desde otro dispositivo
- **WHEN** pide el bootstrap
- **THEN** recibe 409 `JORNADA_REQUERIDA` y ningún dato
- **Regla:** RUT-03; `design.md` D2

#### Scenario: Usuario o rol inactivos
- **GIVEN** `vendedor` con jornada abierta cuyo usuario fue dado de baja
- **WHEN** pide el bootstrap con un token de la excepción de ADR-028 (solo abre el lote)
- **THEN** se rechaza como cualquier petición autenticada que no es el lote
- **Regla:** ADR-028; INV-21

#### Scenario: `since` se ignora
- **WHEN** se pide el bootstrap con `since=2026-10-01T00:00:00Z` y sin `since`
- **THEN** las dos respuestas tienen el mismo contenido completo
- **Regla:** ADR-006

#### Scenario: Doble pedido
- **GIVEN** una jornada abierta y ningún cambio entre los dos pedidos
- **WHEN** el dispositivo pide el bootstrap dos veces seguidas
- **THEN** las dos respuestas son iguales salvo `generado_en`, y la base no registra ningún comando, auditoría ni cambio
- **Regla:** ADR-006; SYN-02

### Requirement: El bootstrap es una foto coherente de la organización

Todas las secciones DEBEN leerse en una misma foto de la base, de solo lectura, para que el stock, los saldos, los precios y las reglas correspondan al mismo momento (`design.md` D3). La respuesta DEBE incluir `generado_en` (hora del servidor, `core/clock.py`).

#### Scenario: Una venta confirmada durante el bootstrap
- **GIVEN** un bootstrap en curso
- **WHEN** otra sesión confirma una venta al cliente "Almacén Don Pedro" desde la camioneta del vendedor
- **THEN** el bootstrap trae o bien el saldo del cliente y el stock anteriores a la venta, o bien los dos posteriores; nunca uno de cada uno
- **Regla:** INV-12; INV-13; `design.md` D3

### Requirement: El bootstrap filtra por organización y no expone costos

Toda sección DEBE filtrarse por la organización del token. El bootstrap NO DEBE incluir costos, costos promedio, márgenes, utilidades ni costos informados de proveedores, aunque el usuario tenga `VER_COSTOS` (`design.md` D7). Importes, porcentajes y alícuotas DEBEN viajar como string decimal; cantidades en unidad base, como enteros.

#### Scenario: Otra organización
- **GIVEN** las organizaciones A y B con productos, clientes, listas y reglas
- **WHEN** un vendedor de A pide el bootstrap
- **THEN** no recibe ningún dato de B
- **Regla:** INV-21; INV-02

#### Scenario: Sin costos aunque tenga VER_COSTOS
- **GIVEN** `admin` (con `VER_COSTOS`) con una jornada abierta
- **WHEN** pide el bootstrap
- **THEN** ninguna sección trae costo ni margen
- **Regla:** SYN-11; ADR-011; `design.md` D7

#### Scenario: Tipos de los valores
- **WHEN** se lee cualquier importe, porcentaje o cantidad del bootstrap
- **THEN** los importes y porcentajes son strings (`"31250.00"`) y las cantidades en unidad base son enteros
- **Regla:** INV-03; INV-04

### Requirement: El bootstrap trae el catálogo activo para vender

El bootstrap DEBE incluir los productos activos con su categoría (`categoria_id`), marca (`marca_id`), alícuota de IVA (id y valor), presentación de referencia y sus presentaciones activas con sus unidades. Los productos y presentaciones inactivos NO DEBEN incluirse.

#### Scenario: Producto activo con presentaciones
- **GIVEN** el vino "Malbec 750" activo con presentaciones caja de 6 y unidad
- **WHEN** se pide el bootstrap
- **THEN** figura con su categoría, marca, alícuota y las dos presentaciones con 6 y 1 unidades base
- **Regla:** SYN-11; ADR-050 (alcances por categoría y marca)

#### Scenario: Producto inactivo
- **GIVEN** un producto dado de baja
- **WHEN** se pide el bootstrap
- **THEN** no figura
- **Regla:** SYN-11

### Requirement: El bootstrap trae los clientes con cartera, saldo y crédito

El bootstrap DEBE incluir los clientes `ACTIVO` y `SUSPENDIDO` de la organización (y el consumidor final si la organización lo habilita), con código, nombre, razón social, documento, dirección, teléfono, estado, lista asignada, si es consumidor final, si está en la cartera del usuario, su saldo de cuenta corriente y su crédito resuelto (límite, política y tolerancia aplicables con la herencia de la organización ya aplicada). Si el usuario no tiene ningún cliente asignado, todos DEBEN marcarse en su cartera ("vacía = todos"). Los clientes `INACTIVO` NO DEBEN incluirse. El correo y el vendedor asignado NO DEBEN incluirse (`design.md` D4).

#### Scenario: Cartera del vendedor
- **GIVEN** `vendedor` con dos clientes asignados y `vendedor2` con otro
- **WHEN** `vendedor` pide el bootstrap
- **THEN** recibe los tres clientes (y el consumidor final), con solo sus dos marcados en cartera
- **Regla:** `01` §19; ADR-060; INV-17

#### Scenario: Cartera vacía
- **GIVEN** un vendedor sin clientes asignados
- **WHEN** pide el bootstrap
- **THEN** todos los clientes bajados están marcados en su cartera
- **Regla:** `01` §19; ADR-060

#### Scenario: Saldo y crédito
- **GIVEN** un cliente sin límite propio, con la política de la organización `AUTORIZAR` y tolerancia de la organización de porcentaje `5.00`
- **WHEN** se pide el bootstrap
- **THEN** el cliente trae su saldo igual a la suma de sus movimientos, su límite, la política `AUTORIZAR` y la tolerancia `PORCENTAJE` `"5.00"`
- **Regla:** CRE-01; CRE-03; CRE-06; INV-13

#### Scenario: Cliente inactivo
- **GIVEN** un cliente `INACTIVO`
- **WHEN** se pide el bootstrap
- **THEN** no figura
- **Regla:** SYN-11; CLI-06

### Requirement: El bootstrap trae las versiones de lista que el dispositivo puede usar

El bootstrap DEBE incluir, por lista, su nombre, si es la predeterminada, y las versiones `PUBLICADA` no anuladas con su número, vigencia desde y hasta, y los precios por producto (`precio_referencia` y `unidades_referencia`). Sin `USAR_LISTA_ANTERIOR`: solo las listas aplicables a los clientes bajados (la asignada o la predeterminada), con la versión vigente y las programadas. Con `USAR_LISTA_ANTERIOR`: todas las listas activas con la vigente, las programadas y las históricas elegibles (PRC-21). Ninguna versión en borrador ni anulada DEBE incluirse (`design.md` D5, D6).

#### Scenario: Vendedor sin USAR_LISTA_ANTERIOR
- **GIVEN** la lista predeterminada con la versión 3 vigente, la 2 histórica y la 4 programada para mañana a las 8:00
- **WHEN** `vendedor2` (sin `USAR_LISTA_ANTERIOR`) pide el bootstrap
- **THEN** recibe las versiones 3 y 4 con sus vigencias, y no la 2
- **Regla:** PRC-20; `design.md` D5, D6

#### Scenario: Con USAR_LISTA_ANTERIOR
- **GIVEN** la misma lista y otra lista activa no asignada a ningún cliente
- **WHEN** `vendedor` (con `USAR_LISTA_ANTERIOR`) pide el bootstrap
- **THEN** recibe las dos listas con sus versiones vigentes, programadas e históricas
- **Regla:** PRC-21; `design.md` D5

#### Scenario: Unidades de referencia
- **WHEN** se lee un precio del bootstrap
- **THEN** trae `precio_referencia` como string y `unidades_referencia` como entero
- **Regla:** PRC-22; PRC-23; INV-03

#### Scenario: Versión anulada o borrador
- **GIVEN** una versión anulada y un borrador en la lista predeterminada
- **WHEN** se pide el bootstrap
- **THEN** ninguno de los dos figura
- **Regla:** PRC-21; INV-11

### Requirement: El bootstrap trae las reglas de descuento y el contexto de venta

El bootstrap DEBE incluir las reglas de descuento `ACTIVA` cuya vigencia no terminó, incluidas las que empiezan más tarde, con sus alcances, prioridad, acumulable y vigencia (`design.md` D6). Con `VENDER` DEBE incluir el contexto de venta del usuario: descuento manual habilitado, motivo obligatorio, si tiene el permiso, su tope aplicable (el propio o el del rol), si puede autorizar, si puede superar el crédito; y los motivos, medios de pago y alícuotas activos.

#### Scenario: Regla programada para la tarde
- **GIVEN** una regla `ACTIVA` con vigencia desde hoy a las 14:00 y otra cuya vigencia terminó ayer
- **WHEN** se pide el bootstrap a las 8:00
- **THEN** la primera figura con su vigencia y la segunda no
- **Regla:** DSC-01; `design.md` D6

#### Scenario: Tope del vendedor
- **GIVEN** `vendedor` con tope propio de 5 %
- **WHEN** pide el bootstrap
- **THEN** el contexto de venta trae el tope `"0.050000"` y el permiso del descuento manual
- **Regla:** DSC-06; ADR-055; ADR-060

#### Scenario: Catálogos activos
- **GIVEN** un medio de pago, un motivo y una alícuota dados de baja
- **WHEN** se pide el bootstrap
- **THEN** ninguno de los tres figura y los activos de todos los ámbitos sí
- **Regla:** TR-09; ADR-053; ADR-061

### Requirement: El bootstrap trae los autorizadores con la derivación de su PIN

Con `VENDER`, el bootstrap DEBE incluir los usuarios activos con rol activo, distintos de quien pide, que tengan algún permiso de autorización de excepciones y un PIN de autorización definido, con su nombre, los permisos de autorización que tienen y la derivación PBKDF2 de su PIN (hash, sal e iteraciones). NUNCA DEBE incluir el PIN ni la contraseña de nadie. Sin `VENDER` la sección DEBE venir vacía (`design.md` D8).

#### Scenario: Supervisor con PIN
- **GIVEN** `sup01` con `AUTORIZAR_DESCUENTO` y PIN definido, y `admin` sin PIN definido
- **WHEN** `vendedor` pide el bootstrap
- **THEN** figura `sup01` con su derivación y sus permisos de autorización, y `admin` no figura
- **Regla:** `02` §12.4; ADR-011; SEG-05

#### Scenario: La derivación es verificable en el dispositivo
- **GIVEN** el vector de prueba compartido (PIN, sal, iteraciones y hash)
- **WHEN** se deriva el PIN con la misma sal e iteraciones en el servidor y en el navegador
- **THEN** los dos obtienen el mismo hash
- **Regla:** `02` §12.4; `design.md` D8

### Requirement: El bootstrap trae sesión, configuración, stock y numeración

El bootstrap DEBE incluir: el usuario (id, nombre, usuario) y sus permisos efectivos; la jornada (id, ubicación y su nombre, apertura); el stock de la ubicación tomada por producto en unidad base; la numeración del dispositivo (prefijo y último correlativo); y la configuración de la organización necesaria en el teléfono (moneda, zona horaria, condición frente al IVA y modo impositivo, política y tolerancia de crédito por defecto, consumidor final, estado de facturación por defecto, `intentos_pin_max`, motivo obligatorio de lista, nombre y CUIT de la organización, y los tres parámetros de la nota).

#### Scenario: Stock de la camioneta
- **GIVEN** "Camioneta 1" con 120 unidades de "Malbec 750" según sus movimientos
- **WHEN** el vendedor de esa jornada pide el bootstrap
- **THEN** recibe 120 para ese producto y ningún saldo de otra ubicación
- **Regla:** RUT-04; INV-12; INV-04

#### Scenario: Numeración del dispositivo
- **GIVEN** el dispositivo con prefijo `V03` y último correlativo 142
- **WHEN** pide el bootstrap
- **THEN** recibe el prefijo `V03` y el correlativo 142
- **Regla:** VTA-06; ADR-008

#### Scenario: Permisos del momento
- **GIVEN** un rol al que se le quitó `VENDER` antes del bootstrap
- **WHEN** el usuario pide el bootstrap
- **THEN** sus permisos no incluyen `VENDER` y las secciones que lo requieren vienen vacías
- **Regla:** SYN-10; ADR-027

#### Scenario: Datos de la nota
- **GIVEN** la organización con nombre, CUIT, domicilio y "mostrar saldo" activo
- **WHEN** se pide el bootstrap
- **THEN** la configuración trae los cuatro valores
- **Regla:** VTA-13; ADR-059
