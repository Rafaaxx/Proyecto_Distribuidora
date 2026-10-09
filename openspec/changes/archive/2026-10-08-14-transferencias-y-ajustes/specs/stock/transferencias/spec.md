## Purpose

Mover stock de un producto entre dos ubicaciones de la organización como una sola operación atómica e idempotente, que saca de una y pone en otra la misma cantidad sin cambiar el stock total ni el costo promedio (STK-07, INV-15, CST-12), y anularla por completo cuando se cargó mal (TR-06). Es la base de la carga del vehículo (RUT-02).

## ADDED Requirements

### Requirement: Registrar una transferencia entre ubicaciones

El sistema DEBE registrar el comando `STOCK_TRANSFERIR` (solo `ONLINE`, `02` §6.5) con el permiso `TRANSFERIR_STOCK`, una ubicación de origen y una de destino distintas, de 1 a 200 líneas sin producto repetido, cada una con `cantidad_base` entera mayor que cero, y una observación opcional de hasta 500 caracteres (`design.md` D6). En una sola transacción DEBE crear la transferencia en estado `CONFIRMADA` con sus líneas y, por cada línea, un movimiento `TRANSFERENCIA_SALIDA` por la cantidad negativa en el origen y uno `TRANSFERENCIA_ENTRADA` por la cantidad positiva en el destino, ambos con origen en la transferencia (STK-03, STK-07, `design.md` D8). Ambas ubicaciones DEBEN existir en la organización (si no, 404) y estar activas (`UBICACION_INACTIVA`), y todo producto DEBE existir en la organización (si no, 404) y estar activo (`PRODUCTO_INACTIVO`, `design.md` D4). El `organizacion_id` DEBE salir del token.

#### Scenario: Carga de la camioneta desde el depósito

- **GIVEN** 120 unidades de Vino A en el depósito, stock total 120 y promedio `"1050.000000"`, y la ubicación "Camioneta 1" sin stock
- **WHEN** un Vendedor con `TRANSFERIR_STOCK` transfiere 48 unidades de Vino A del depósito a "Camioneta 1"
- **THEN** el comando queda `ACEPTADO`, existe una transferencia `CONFIRMADA` con una línea de 48, el libro tiene −48 `TRANSFERENCIA_SALIDA` en el depósito y +48 `TRANSFERENCIA_ENTRADA` en la camioneta con costo `"1050.000000"` cada uno, los saldos quedan en 72 y 48, el stock total sigue en 120 y el promedio en `"1050.000000"`
- **Regla:** STK-07; CST-12; INV-15

#### Scenario: Varias líneas en una transferencia

- **GIVEN** stock de Vino A y Agua 500 en el depósito
- **WHEN** se transfieren 48 de Vino A y 24 de Agua 500 a "Camioneta 1"
- **THEN** existen una transferencia con dos líneas y cuatro movimientos con el mismo origen, y cada saldo cambia por su cantidad
- **Regla:** STK-07; INV-01

#### Scenario: Origen y destino iguales

- **GIVEN** un usuario con `TRANSFERIR_STOCK`
- **WHEN** envía una transferencia con el depósito como origen y destino
- **THEN** se rechaza con `UBICACIONES_IGUALES` (422) y no se escribe nada
- **Regla:** STK-07; `03` §9

#### Scenario: Cantidad cero, negativa o fraccionaria

- **GIVEN** un usuario con `TRANSFERIR_STOCK`
- **WHEN** envía una línea con `cantidad_base` 0, −5 o 1.5
- **THEN** la respuesta es `CANTIDAD_INVALIDA` para 0 y −5 y 422 de validación para 1.5, sin escribir nada
- **Regla:** INV-04; STK-01

#### Scenario: Cantidad de líneas fuera de rango o producto repetido

- **GIVEN** un usuario con `TRANSFERIR_STOCK`
- **WHEN** envía una transferencia sin líneas, con 201 líneas o con Vino A dos veces
- **THEN** se rechaza con `LINEAS_INVALIDAS` o `PRODUCTO_REPETIDO` y no se escribe nada
- **Regla:** `design.md` D6

#### Scenario: Ubicación inactiva

- **GIVEN** "Camioneta 2" inactiva
- **WHEN** se transfiere hacia ella o desde ella
- **THEN** se rechaza con `UBICACION_INACTIVA` y no se escribe nada
- **Regla:** STK-02; ADR-038

#### Scenario: Ubicación o producto de otra organización

- **GIVEN** una ubicación y un producto de la organización B
- **WHEN** un usuario de la organización A los usa en una transferencia
- **THEN** la respuesta es 404, igual que para un id inexistente, y no se escribe nada
- **Regla:** INV-21; SEG-07

#### Scenario: Sin permiso

- **GIVEN** un usuario sin `TRANSFERIR_STOCK`
- **WHEN** envía una transferencia
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, sin reserva del `operation_id` ni movimientos
- **Regla:** SEG-06; `01` §19

#### Scenario: Comando fuera de línea

- **GIVEN** un usuario con `TRANSFERIR_STOCK`
- **WHEN** el comando llega con modo `OFFLINE`
- **THEN** se rechaza y no se escribe nada
- **Regla:** `02` §6.5; RUT-02

#### Scenario: Doble envío del mismo comando

- **GIVEN** una transferencia aceptada con un `operation_id`
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido, y después con otro contenido
- **THEN** el primer reenvío devuelve el resultado original sin nuevos movimientos y el segundo se rechaza con `COMANDO_INCONSISTENTE`
- **Regla:** INV-06; SYN-02

### Requirement: Una transferencia no modifica el stock total ni el promedio

Una transferencia NO DEBE cambiar el stock total del producto en la organización ni su costo promedio, ni dejar historia en `costo_producto_mov` (INV-15, CST-12, CST-13). Cada movimiento DEBE guardar como `costo_unitario` el promedio vigente, o nulo si el producto no tiene promedio (`design.md` D3).

#### Scenario: Propiedad sobre secuencias de transferencias

- **GIVEN** cualquier secuencia válida de stocks iniciales y transferencias entre varias ubicaciones registrada contra PostgreSQL real
- **WHEN** termina la secuencia
- **THEN** el stock total de cada producto es igual al anterior a las transferencias, cada saldo es la suma de su libro y el promedio no cambió
- **Regla:** INV-15; INV-12

#### Scenario: Sin historia de costo

- **GIVEN** Vino A con historia de costo de sus compras
- **WHEN** se transfieren 48 unidades
- **THEN** `costo_producto_mov` no tiene filas nuevas
- **Regla:** CST-13; CST-12

### Requirement: La salida de una transferencia respeta el stock disponible

La salida DEBE aplicarse solo si el saldo del origen alcanza; si no alcanza y el usuario no tiene `PERMITIR_STOCK_NEGATIVO`, la transferencia DEBE rechazarse con `STOCK_INSUFICIENTE` sin escribir nada. Con `PERMITIR_STOCK_NEGATIVO` DEBE aplicarse y el comando DEBE quedar `ACEPTADO_CON_OBSERVACIONES` con una observación `STOCK_NEGATIVO` por cada producto y ubicación que quedó bajo cero (STK-05, `design.md` D1).

#### Scenario: Saldo insuficiente sin permiso

- **GIVEN** 48 unidades de Vino A en el depósito y un Supervisor sin `PERMITIR_STOCK_NEGATIVO`
- **WHEN** transfiere 60 a "Camioneta 1"
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y los saldos siguen en 48 y 0
- **Regla:** STK-05; `02` §7.4

#### Scenario: Saldo insuficiente con permiso

- **GIVEN** 48 unidades de Vino A en el depósito y un Administrador con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** transfiere 60 a "Camioneta 1"
- **THEN** los saldos quedan en −12 y 60, el stock total sigue en 48 y el comando queda `ACEPTADO_CON_OBSERVACIONES` con `STOCK_NEGATIVO` sobre la transferencia
- **Regla:** STK-05; SYN-07; INV-15

### Requirement: Una transferencia es atómica

La transferencia, sus líneas y todos sus movimientos DEBEN registrarse completos o no registrarse (INV-01).

#### Scenario: Falla entre la salida y la entrada

- **GIVEN** una transferencia de dos líneas y una falla inyectada después de escribir la primera salida
- **WHEN** se procesa
- **THEN** no queda transferencia, línea, movimiento ni cambio de saldo o de stock total, y el `operation_id` puede reintentarse
- **Regla:** INV-01

### Requirement: Una transferencia rechaza un producto inactivo

Una transferencia con algún producto inactivo DEBE rechazarse con `PRODUCTO_INACTIVO` (409) sin escribir nada: sobre un producto inactivo no se registran movimientos (CAT-05, ADR-038 punto 5, `design.md` D4). Como un producto con stock no puede desactivarse (spec `catalogo/productos-y-presentaciones`), el stock de un producto que se discontinúa se mueve **antes** de desactivarlo.

#### Scenario: Transferencia de un producto inactivo

- **GIVEN** "Vino Rosado" inactivo, que quedó con 18 unidades en "Camioneta 1" porque se desactivó antes de que existiera la regla
- **WHEN** se transfieren las 18 al depósito
- **THEN** se rechaza con `PRODUCTO_INACTIVO` y los saldos no cambian
- **Regla:** CAT-05; ADR-038; `design.md` D4

#### Scenario: Reactivar, vaciar y volver a desactivar

- **GIVEN** el mismo producto, reactivado
- **WHEN** se transfieren las 18 al depósito
- **THEN** se acepta y la camioneta queda en 0
- **Regla:** CAT-05; `design.md` D4

### Requirement: Las transferencias se consultan por organización

El sistema DEBE listar las transferencias de la organización, más recientes primero, con filtros opcionales por ubicación (como origen o destino) y por fechas de negocio, con cursor y límite de 1 a 200, y DEBE devolver el detalle con origen, destino, observación, usuario, `occurred_at`, **estado** (`CONFIRMADA` o `ANULADA`) y líneas con código, nombre, cantidad y unidades de referencia del producto (CAT-08). El listado DEBE traer el estado de cada transferencia; el detalle de una anulada DEBE traer el motivo, el usuario y el momento de la anulación. Ambas lecturas DEBEN exigir `TRANSFERIR_STOCK` (`design.md` D7). Una transferencia de otra organización DEBE responderse como 404.

#### Scenario: Listado filtrado por ubicación

- **GIVEN** una transferencia depósito → "Camioneta 1" y otra depósito → "Camioneta 2"
- **WHEN** se lista con el filtro "Camioneta 1"
- **THEN** solo aparece la primera, con su estado
- **Regla:** `design.md` D7

#### Scenario: Detalle de una transferencia

- **GIVEN** la transferencia de 48 de Vino A
- **WHEN** un Vendedor consulta su detalle
- **THEN** recibe origen, destino, estado `CONFIRMADA`, la línea con 48 unidades base y 6 unidades de referencia, sin ningún campo de costo
- **Regla:** CAT-08; `01` §19

#### Scenario: Detalle de una transferencia anulada

- **GIVEN** la transferencia de 60 de Vino A anulada por "Error de carga"
- **WHEN** se consulta su detalle y el listado
- **THEN** ambos la muestran `ANULADA`, y el detalle trae el motivo "Error de carga", quién la anuló y cuándo
- **Regla:** TR-06; `design.md` D5

#### Scenario: Lectura sin permiso o ajena

- **GIVEN** una transferencia de la organización B
- **WHEN** un usuario sin `TRANSFERIR_STOCK` lista, o uno de la organización A pide su detalle
- **THEN** las respuestas son 403 y 404 respectivamente
- **Regla:** INV-21; SEG-06

#### Scenario: Rango o cursor inválidos

- **GIVEN** un usuario con `TRANSFERIR_STOCK`
- **WHEN** lista con `desde` posterior a `hasta` o con un cursor ilegible
- **THEN** la respuesta es `RANGO_DE_FECHAS_INVALIDO` o `CURSOR_INVALIDO`
- **Regla:** `02` §11

### Requirement: Una transferencia no se edita ni se borra

Una transferencia confirmada NO DEBE modificarse ni eliminarse (TR-06): `app_runtime` DEBE tener `SELECT` e `INSERT` sobre `transferencia` y `transferencia_linea`, sin `DELETE` sobre ninguna y sin `UPDATE` sobre las líneas; sobre la cabecera DEBE tener `UPDATE` **solo** del estado y de las columnas de anulación (motivo, momento y usuario), como `compra` (`design.md` D5, D8). Ninguna ruta DEBE editarla o borrarla. Una transferencia mal cargada se corrige anulándola y cargando otra.

#### Scenario: Sin permisos de modificación

- **GIVEN** la base migrada y una conexión como `app_runtime`
- **WHEN** intenta `DELETE` sobre `transferencia` o `transferencia_linea`, `UPDATE` sobre `transferencia_linea`, o `UPDATE` de `ubicacion_destino_id` u `observacion` de `transferencia`
- **THEN** PostgreSQL rechaza cada sentencia
- **Regla:** INV-05; TR-06

#### Scenario: Estado y anulación coherentes en la base

- **GIVEN** la base migrada
- **WHEN** se intenta dejar una transferencia `ANULADA` sin motivo, o `CONFIRMADA` con momento de anulación, o con un estado distinto de los dos
- **THEN** la base lo rechaza
- **Regla:** `01` §18; `design.md` D8

### Requirement: Anular una transferencia

El sistema DEBE registrar el comando `STOCK_TRANSFERENCIA_ANULAR` (solo `ONLINE`) sobre una transferencia `CONFIRMADA` de la organización, con un motivo activo del ámbito `ANULACION_TRANSFERENCIA` (`MOTIVO_INVALIDO`, 422, si está inactivo o es de otro ámbito; 404 si es ajeno). La anulación DEBE ser total y única: en una sola transacción DEBE tomar la transferencia con bloqueo exclusivo, escribir por cada línea un movimiento `TRANSFERENCIA_SALIDA` por la cantidad negativa en el **destino** y uno `TRANSFERENCIA_ENTRADA` por la cantidad positiva en el **origen**, con origen `ANULACION_TRANSFERENCIA` y el id de la transferencia, y pasarla a `ANULADA` con su motivo, momento y usuario (TR-06, `01` §18, `design.md` D5, D5.1). Cada movimiento inverso DEBE guardar el **mismo `costo_unitario`** que su movimiento original (nulo si era nulo); la anulación NO DEBE cambiar el stock total ni el promedio ni dejar historia de costo (INV-15, CST-12, CST-13). Una transferencia ya anulada DEBE rechazarse con `TRANSFERENCIA_YA_ANULADA` (409). Una transferencia inexistente o de otra organización DEBE responderse como 404.

#### Scenario: Anular una transferencia mal cargada

- **GIVEN** una transferencia propia de 60 de Vino A del depósito (queda en 60) a "Camioneta 1" (queda en 60), hecha con promedio `"1050.000000"`, y el promedio de hoy en `"1100.000000"`
- **WHEN** quien la creó la anula con el motivo "Error de carga"
- **THEN** el comando queda `ACEPTADO`, el libro suma −60 `TRANSFERENCIA_SALIDA` en la camioneta y +60 `TRANSFERENCIA_ENTRADA` en el depósito, ambos a `"1050.000000"` y con origen `ANULACION_TRANSFERENCIA`, los saldos quedan en 0 y 120, el stock total y el promedio (`"1100.000000"`) no cambian, y la transferencia queda `ANULADA` con el motivo, el usuario y el momento
- **Regla:** TR-06; INV-15; CST-12; `design.md` D5

#### Scenario: Segunda anulación

- **GIVEN** una transferencia `ANULADA`
- **WHEN** se la anula otra vez con otro `operation_id`
- **THEN** se rechaza con `TRANSFERENCIA_YA_ANULADA` y no se escribe nada
- **Regla:** `01` §18; `design.md` D5

#### Scenario: Motivo inválido o ajeno

- **GIVEN** un motivo activo del ámbito `AJUSTE_STOCK`, uno inactivo de `ANULACION_TRANSFERENCIA` y uno de la organización B
- **WHEN** se anula una transferencia con cada uno
- **THEN** los dos primeros se rechazan con `MOTIVO_INVALIDO` y el tercero con 404, sin escribir nada
- **Regla:** TR-09; INV-21

#### Scenario: Transferencia de otra organización

- **GIVEN** una transferencia de la organización B
- **WHEN** un usuario de la organización A la anula
- **THEN** la respuesta es 404, igual que para un id inexistente
- **Regla:** INV-21; SEG-07

#### Scenario: Doble envío y comando fuera de línea

- **GIVEN** una anulación aceptada con un `operation_id`
- **WHEN** se reenvía con el mismo `operation_id` y contenido, y aparte llega otra en modo `OFFLINE`
- **THEN** el reenvío devuelve el resultado original sin nuevos movimientos y la `OFFLINE` se rechaza
- **Regla:** INV-06; `02` §6.5

#### Scenario: Falla en medio de la anulación

- **GIVEN** una transferencia de dos líneas y una falla inyectada después del primer movimiento inverso
- **WHEN** se procesa la anulación
- **THEN** no queda ningún movimiento inverso ni cambio de saldo y la transferencia sigue `CONFIRMADA`
- **Regla:** INV-01

### Requirement: Quién puede anular una transferencia

Con `TRANSFERIR_STOCK`, un usuario DEBE poder anular solo las transferencias que él mismo creó. Para anular la transferencia de otro usuario DEBE tener además el permiso `ANULAR_TRANSFERENCIA`, que las plantillas dan a Administrador y Administración; sin él, la respuesta DEBE ser 403 `PERMISO_REQUERIDO`, sin movimientos ni cambio de estado (`design.md` D5, D5.4; `01` §19). Sin `TRANSFERIR_STOCK` la anulación DEBE responder 403.

#### Scenario: Vendedor anula la transferencia de otro

- **GIVEN** una transferencia creada por la Vendedora Marta y el Vendedor Pedro con `TRANSFERIR_STOCK` y sin `ANULAR_TRANSFERENCIA`
- **WHEN** Pedro la anula
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y la transferencia sigue `CONFIRMADA`
- **Regla:** SEG-06; `design.md` D5

#### Scenario: Administración anula la transferencia de otro

- **GIVEN** la misma transferencia y un usuario de Administración con `TRANSFERIR_STOCK` y `ANULAR_TRANSFERENCIA`
- **WHEN** la anula
- **THEN** se acepta y la anulación registra a ese usuario
- **Regla:** `01` §19; `design.md` D5

#### Scenario: Sin permiso de transferir

- **GIVEN** un usuario sin `TRANSFERIR_STOCK`
- **WHEN** anula una transferencia
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** SEG-06; `design.md` D5.4

### Requirement: La anulación de una transferencia respeta el stock y los inactivos

Si la anulación dejaría bajo cero el saldo del destino, DEBE rechazarse con `STOCK_INSUFICIENTE` sin escribir nada, salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`: entonces DEBE aplicarse y el comando DEBE quedar `ACEPTADO_CON_OBSERVACIONES` con una observación `STOCK_NEGATIVO` por cada producto y ubicación bajo cero (STK-05, ADR-044, `design.md` D5). Si algún producto o alguna de las dos ubicaciones está inactivo, la anulación DEBE rechazarse con `PRODUCTO_INACTIVO` o `UBICACION_INACTIVA` (ADR-038 punto 5, `design.md` D4).

#### Scenario: El destino ya vendió parte, sin permiso

- **GIVEN** una transferencia de 60 de Vino A a "Camioneta 1", que ahora tiene 50, y su creadora sin `PERMITIR_STOCK_NEGATIVO`
- **WHEN** la anula
- **THEN** se rechaza con `STOCK_INSUFICIENTE`, los saldos no cambian y la transferencia sigue `CONFIRMADA`
- **Regla:** STK-05; `design.md` D5

#### Scenario: El destino ya vendió parte, con permiso

- **GIVEN** la misma situación y un Administrador con `PERMITIR_STOCK_NEGATIVO`
- **WHEN** la anula
- **THEN** la camioneta queda en −10, el comando queda `ACEPTADO_CON_OBSERVACIONES` con `STOCK_NEGATIVO` sobre la transferencia y esta queda `ANULADA`
- **Regla:** STK-05; SYN-07; ADR-044

#### Scenario: Producto o ubicación inactivos

- **GIVEN** una transferencia cuyo producto se desactivó después, y otra cuyo origen se desactivó después
- **WHEN** se anula cada una
- **THEN** se rechazan con `PRODUCTO_INACTIVO` y `UBICACION_INACTIVA` y nada cambia
- **Regla:** CAT-05; ADR-038; `design.md` D5

### Requirement: La anulación de una transferencia se audita con su motivo

Cada anulación DEBE dejar una sola fila de auditoría del comando con acción `STOCK_TRANSFERENCIA_ANULAR`, usuario, dispositivo, `operation_id` y, en `motivo_id`, el motivo de la anulación que el handler devuelve y el bus copia (AUD-02, ADR-022, `design.md` D10). La fila de auditoría de `STOCK_TRANSFERIR` NO DEBE llevar motivo.

#### Scenario: Auditoría de la anulación

- **GIVEN** una transferencia anulada con "Error de carga"
- **WHEN** se consulta la auditoría
- **THEN** existe una sola fila `STOCK_TRANSFERENCIA_ANULAR` con ese `operation_id` y `motivo_id` igual al de "Error de carga", y la fila `STOCK_TRANSFERIR` original tiene `motivo_id` nulo
- **Regla:** AUD-02; ADR-022; `design.md` D10
