## Purpose

Definir cómo se compone una venta: sus líneas por producto y presentación de venta, la lista y la versión de la que sale el precio, los valores que cada línea congela y qué pasa cuando el precio no se puede resolver (VTA-02, VTA-03, VTA-10, PRC-20 a PRC-23, CAT-07). Escrita con las opciones recomendadas (A) de `design.md` D2, D5 a D9, pendientes de aprobación.

## ADDED Requirements

### Requirement: Una venta tiene de 1 a 200 líneas por producto y presentación de venta

Cada línea DEBE indicar un producto activo, una presentación activa con uso en venta de ese producto y una cantidad entera mayor que cero en esa presentación; la cantidad base DEBE ser `cantidad × unidades de la presentación` (VTA-02, CAT-02, CAT-05). Una venta sin líneas o con más de 200 DEBE rechazarse (`VENTA_SIN_LINEAS`, `LINEAS_INVALIDAS`, 422; INV-07). El mismo producto en la misma presentación dos veces DEBE rechazarse con `LINEA_DUPLICADA` (422); el mismo producto en dos presentaciones son dos líneas (`design.md` D8).

#### Scenario: Cajas y unidades son dos líneas
- **GIVEN** Vino A con presentaciones "Caja x6" (referencia) y "Botella" (1 unidad), ambas de venta
- **WHEN** se confirma una venta con 2 "Caja x6" y 3 "Botella"
- **THEN** la venta tiene dos líneas con cantidad base 12 y 3 (15 en total)
- **Regla:** VTA-02; CAT-07; CAT-08

#### Scenario: Sin líneas
- **WHEN** se envía `VENTA_CONFIRMAR` con la lista de líneas vacía, y otra con 201 líneas
- **THEN** ambas se rechazan (422) y no queda venta, movimiento ni cobranza
- **Regla:** INV-07; INV-01

#### Scenario: Línea repetida
- **WHEN** la venta trae dos líneas de Vino A en "Caja x6"
- **THEN** se rechaza con `LINEA_DUPLICADA`
- **Regla:** VTA-02; `design.md` D8

#### Scenario: Presentación no vendible
- **GIVEN** Vino A con una presentación "Pallet" con `usar_en_venta = false`, y otra presentación de venta inactiva
- **WHEN** se envía una línea con cada una
- **THEN** cada venta se rechaza con `PRESENTACION_NO_VENDIBLE` (409)
- **Regla:** CAT-02; CAT-05

#### Scenario: Unidades sueltas sin presentación de una unidad
- **GIVEN** Cerveza B que solo tiene "Caja x12"
- **WHEN** la pantalla intenta componer 7 unidades sueltas
- **THEN** no ofrece unidades sueltas para ese producto y el servidor no tiene presentación que aceptar
- **Regla:** CAT-07

#### Scenario: Producto inactivo o ajeno
- **WHEN** una línea nombra un producto inactivo, y otra un producto de otra organización
- **THEN** la primera se rechaza con `PRODUCTO_INACTIVO` (409) y la segunda responde como inexistente (404)
- **Regla:** CAT-05; INV-21

#### Scenario: Cantidad no entera
- **WHEN** la cantidad de una línea es `0`, negativa o `2.5`
- **THEN** se rechaza (422) sin ningún efecto
- **Regla:** INV-04

### Requirement: El precio sale de la lista aplicable vigente al momento de la venta

Sin elección del usuario, la lista DEBE ser la asignada al cliente o la predeterminada de la organización, y la versión la vigente al `occurred_at` de la venta (PRC-20). El bruto de cada línea DEBE calcularse con PRC-22 sobre las unidades de referencia guardadas en el precio. Si no hay lista aplicable, si no hay versión vigente o si algún producto no tiene precio en la versión, con conexión la venta entera DEBE rechazarse con `SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE` o `PRODUCTO_SIN_PRECIO` (409, con los productos en el detalle) (VTA-10, `design.md` D7).

#### Scenario: Precio de la lista del cliente
- **GIVEN** Kiosco La Esquina sin lista asignada, la lista predeterminada "General" con Vino A a $12.500 la "Caja x6" (unidades de referencia 6)
- **WHEN** se venden 15 botellas
- **THEN** el bruto es `"31250.00"`
- **Regla:** PRC-20; PRC-22

#### Scenario: Una unidad suelta
- **GIVEN** Vino A a $8.600 la caja x6
- **WHEN** se vende 1 botella
- **THEN** el bruto es `"1433.33"`
- **Regla:** PRC-22; TR-03

#### Scenario: Sin lista aplicable
- **GIVEN** un cliente sin lista y la organización sin lista predeterminada, y otro cliente con una lista asignada inactiva
- **WHEN** se confirma una venta a cada uno
- **THEN** ambas se rechazan con `SIN_LISTA_APLICABLE` sin ningún efecto (la asignada inactiva no cae a la predeterminada)
- **Regla:** PRC-20; VTA-10

#### Scenario: Sin versión vigente
- **GIVEN** la lista del cliente con su única versión programada para mañana
- **WHEN** se confirma una venta hoy
- **THEN** se rechaza con `LISTA_SIN_VERSION_VIGENTE`
- **Regla:** PRC-20; PRC-03

#### Scenario: Producto sin precio
- **GIVEN** la versión vigente con precio para Vino A y sin precio para Cerveza B
- **WHEN** se confirma una venta con los dos
- **THEN** se rechaza con `PRODUCTO_SIN_PRECIO` y el detalle nombra a Cerveza B; no se vende Vino A solo
- **Regla:** VTA-10; PRC-10; INV-01

### Requirement: Usar otra lista o una versión anterior requiere permiso y motivo

La venta DEBE poder usar otra lista activa de la organización o una versión publicada, no anulada, de la lista elegida cuya vigencia desde no sea posterior al momento de la venta, solo si el usuario tiene `USAR_LISTA_ANTERIOR` (403 si no) y, si la organización exige motivo, con un motivo activo del ámbito `LISTA_ANTERIOR` (`MOTIVO_INVALIDO`, 422). Una versión programada o anulada DEBE rechazarse con `VERSION_NO_PERMITIDA` y una lista inactiva con `LISTA_INACTIVA` (409). La venta DEBE guardar la lista, la versión y el motivo (PRC-21, `design.md` D6).

#### Scenario: Versión anterior con motivo
- **GIVEN** la lista "General" con la versión 3 (Vino A $8.600) y la vigente 4 (Vino A $9.000), y la organización que exige motivo
- **WHEN** un Supervisor confirma una venta a Almacén Don Pedro con la versión 3 y el motivo "Precio acordado con el cliente"
- **THEN** la venta guarda la versión 3 y ese motivo, y cada línea congela el precio $8.600
- **Regla:** PRC-21; PRC-23

#### Scenario: Sin permiso
- **GIVEN** un Vendedor sin `USAR_LISTA_ANTERIOR`
- **WHEN** envía la venta con la versión 3
- **THEN** recibe 403 y no queda ningún efecto
- **Regla:** PRC-21; SEG-06

#### Scenario: Motivo faltante cuando la organización lo exige
- **WHEN** un Supervisor elige la versión 3 sin motivo, y otro con un motivo de otro ámbito
- **THEN** ambas se rechazan con `MOTIVO_INVALIDO`
- **Regla:** PRC-21; `01` §4

#### Scenario: Sin motivo cuando la organización no lo exige
- **GIVEN** `motivo_obligatorio_lista = false`
- **WHEN** un Supervisor elige la versión 3 sin motivo
- **THEN** la venta se confirma con el motivo nulo
- **Regla:** PRC-21

#### Scenario: Versión programada o anulada
- **WHEN** se elige una versión que rige desde mañana, y otra anulada
- **THEN** ambas se rechazan con `VERSION_NO_PERMITIDA`
- **Regla:** PRC-21; PRC-05; `design.md` D6

#### Scenario: Otra lista inactiva
- **WHEN** se elige una lista inactiva
- **THEN** se rechaza con `LISTA_INACTIVA`
- **Regla:** PRC-20; PRC-21

### Requirement: Cada línea congela su precio, sus unidades y su versión

Cada línea DEBE guardar cantidad en la presentación, unidades de la presentación, cantidad base, versión de lista, precio de referencia, unidades de referencia, bruto, descuento, neto, alícuota, IVA y costo, y NINGUNO de esos valores DEBE cambiar después (VTA-03, PRC-23, INV-10). El usuario de aplicación NO DEBE tener `UPDATE` ni `DELETE` sobre la venta ni sus líneas.

#### Scenario: Publicar una versión nueva no cambia la venta
- **GIVEN** una venta de 15 botellas de Vino A a $12.500
- **WHEN** se publica una versión con Vino A a $13.000
- **THEN** la línea sigue con precio `"12500.00"`, unidades de referencia 6 y bruto `"31250.00"`
- **Regla:** PRC-23; INV-10

#### Scenario: Cambiar la referencia del producto no cambia la venta
- **GIVEN** la misma venta
- **WHEN** la referencia de Vino A pasa a una "Caja x12"
- **THEN** la línea conserva unidades de referencia 6
- **Regla:** PRC-04; PRC-23

#### Scenario: La base impide editar
- **WHEN** `app_runtime` intenta `UPDATE` o `DELETE` de una venta o de una línea
- **THEN** la base lo rechaza por privilegios
- **Regla:** INV-05; INV-10; TR-06

### Requirement: Con conexión se confirma el precio que vio el usuario

El comando DEBE traer, por línea, la versión, el precio de referencia, las unidades de referencia y el bruto esperados, y el total esperado. Con conexión, si cualquier valor que el servidor resuelve difiere del esperado, la venta DEBE rechazarse con `PRECIO_DIFIERE` (409) y los valores del servidor en el detalle (`design.md` D2).

#### Scenario: Se publicó una versión entre la pantalla y la confirmación
- **GIVEN** la pantalla mostró Vino A a $12.500 (bruto `"31250.00"`)
- **WHEN** se publica una versión a $13.000 y después se confirma la venta con los valores mostrados
- **THEN** se rechaza con `PRECIO_DIFIERE`, el detalle trae precio `"13000.00"` y bruto `"32500.00"`, y no queda ningún efecto
- **Regla:** PRC-20; TR-10; `design.md` D2

#### Scenario: Total manipulado
- **WHEN** el total esperado es `"1.00"` para una venta de bruto `"31250.00"`
- **THEN** se rechaza con `PRECIO_DIFIERE`
- **Regla:** TR-10; INV-14

### Requirement: El momento de una venta con conexión está cerca del reloj del servidor

Con conexión, si el `occurred_at` difiere del reloj del servidor en más que `desvio_reloj_max_segundos` de la organización (300 segundos si no está definido), la venta DEBE rechazarse con `MOMENTO_FUERA_DE_RANGO` (422); dentro del margen, la versión se resuelve al `occurred_at` (`design.md` D9).

#### Scenario: Reloj atrasado un día
- **WHEN** una venta con conexión llega con `occurred_at` de ayer
- **THEN** se rechaza con `MOMENTO_FUERA_DE_RANGO` sin ningún efecto
- **Regla:** PRC-20; TR-05; `design.md` D9

#### Scenario: Dentro del margen
- **WHEN** llega con `occurred_at` 2 minutos antes del reloj del servidor
- **THEN** se acepta y la versión es la vigente en ese `occurred_at`
- **Regla:** PRC-20
