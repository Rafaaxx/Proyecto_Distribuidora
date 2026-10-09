# Libro de stock — Especificación

## Purpose

Definir el stock de cada producto y ubicación como un libro de movimientos de solo inserción, con un saldo materializado y bloqueable que se actualiza en la misma transacción que cada movimiento, respetando el orden global de bloqueo (STK-01, STK-03, STK-04, INV-12; `02` §7.2-§7.4; ADR-015). Es la base que escriben el stock inicial y, después, compras, transferencias, ajustes, ventas y rendiciones.

## Requirements

### Requirement: El libro de stock es de solo inserción

El sistema DEBE registrar cada cambio de stock en `stock_movimiento` con `organizacion_id`, `producto_id`, `ubicacion_id`, `cantidad_base` entera con signo y distinta de cero, `tipo` (STK-03), `origen_tipo`, `origen_id`, `costo_unitario` en `numeric(18,6)` cuando corresponde, `jornada_id` y `motivo_id` opcionales, `operation_id`, `usuario_id`, `dispositivo_id` obligatorio, `occurred_at` y `registered_at` (`03` §9, `design.md` D12). Un movimiento NO DEBE editarse ni borrarse: `app_runtime` DEBE tener solo `SELECT` e `INSERT` sobre la tabla (INV-05, ADR-020) y ninguna ruta DEBE modificarlo o eliminarlo.

#### Scenario: Un movimiento guarda todos sus datos

- **GIVEN** el producto Vino A y el depósito de la organización A
- **WHEN** el servicio de stock registra un ingreso `STOCK_INICIAL` de 60 unidades base con costo `"1000.000000"`
- **THEN** existe una fila con cantidad 60, tipo `STOCK_INICIAL`, el origen, el costo, el usuario, el dispositivo del sobre, el `operation_id`, `occurred_at` y `registered_at` del reloj inyectable
- **Regla:** STK-03; TR-05; `03` §9

#### Scenario: El usuario de aplicación no puede modificar ni borrar movimientos

- **GIVEN** la base migrada y una conexión como `app_runtime`
- **WHEN** intenta `UPDATE` o `DELETE` sobre `stock_movimiento`
- **THEN** PostgreSQL rechaza la sentencia por falta de permisos
- **Regla:** INV-05; ADR-020

#### Scenario: La cantidad cero se rechaza

- **GIVEN** la base migrada
- **WHEN** se inserta un movimiento con `cantidad_base = 0`
- **THEN** la restricción `ck_stock_movimiento__cantidad_no_cero` lo rechaza
- **Regla:** STK-03; `03` §9

#### Scenario: Tipo fuera del catálogo

- **GIVEN** la base migrada
- **WHEN** se inserta un movimiento con tipo `DEVOLUCION`
- **THEN** la restricción de catálogo lo rechaza (es un tipo de la etapa 2)
- **Regla:** STK-03; `design.md` D13

#### Scenario: No existe ruta que edite o borre movimientos

- **GIVEN** todas las rutas registradas de la API
- **WHEN** se buscan rutas `PUT`, `PATCH` o `DELETE` sobre movimientos de stock
- **THEN** no existe ninguna
- **Regla:** TR-06; INV-05

### Requirement: Las cantidades de stock son enteras

Toda cantidad en unidad base DEBE ser `integer` en la base y entera en la API; una cantidad no entera DEBE rechazarse antes de tocar la base (INV-04, STK-01).

#### Scenario: Cantidad fraccionaria en la API

- **GIVEN** un usuario con permiso de stock inicial
- **WHEN** envía una línea con `cantidad_base` `1.5`
- **THEN** la respuesta es 422 y no se registra nada
- **Regla:** INV-04; STK-01

#### Scenario: Columnas de cantidad enteras

- **GIVEN** el catálogo de columnas de la base
- **WHEN** se revisan las columnas de cantidad base de `stock_movimiento`, `stock_saldo`, `costo_producto` y `costo_producto_mov`
- **THEN** todas son `integer`
- **Regla:** INV-04; `03` §15

### Requirement: El saldo de stock se materializa con la fila bloqueada

El sistema DEBE mantener `stock_saldo` (clave `(organizacion_id, producto_id, ubicacion_id)`, sin `id`, ADR-035 punto 6) y `costo_producto.stock_total` actualizados en la misma transacción que cada movimiento, con las filas bloqueadas en el orden global: primero `costo_producto` por `producto_id` ascendente, después `stock_saldo` por `(producto_id, ubicacion_id)` ascendentes (`02` §7.3, ADR-015, `design.md` D9). Las filas nacen de forma perezosa con el primer movimiento, sin duplicarse ante concurrencia (`design.md` D10). El saldo de cada producto y ubicación DEBE ser igual a la suma de sus movimientos, y `stock_total` igual a la suma de los saldos del producto (INV-12, STK-04).

#### Scenario: El saldo es la suma de los movimientos

- **GIVEN** ingresos de 60 y 60 unidades de Vino A en el depósito
- **WHEN** se consulta el saldo
- **THEN** `stock_saldo.cantidad_base` es 120, igual a la suma SQL del libro, y `stock_total` es 120
- **Regla:** INV-12; STK-04

#### Scenario: Propiedad sobre secuencias arbitrarias

- **GIVEN** cualquier secuencia válida de movimientos sobre varios productos y ubicaciones registrada por el servicio contra PostgreSQL real
- **WHEN** termina la secuencia
- **THEN** cada `stock_saldo` es igual a la suma de su libro, cada `stock_total` es la suma de sus saldos y la consulta de consistencia no informa diferencias
- **Regla:** INV-12; `02` §7.6

#### Scenario: Movimientos concurrentes sobre el mismo producto

- **GIVEN** dos transacciones con commits reales que registran ingresos del mismo producto en la misma ubicación a la vez
- **WHEN** ambas confirman
- **THEN** el saldo es la suma de las dos cantidades y existe una sola fila de saldo
- **Regla:** INV-12; `02` §7.4

#### Scenario: Orden inverso de productos no produce deadlock

- **GIVEN** dos transacciones concurrentes que tocan los productos P1 y P2 enviados en orden inverso
- **WHEN** ambas se ejecutan
- **THEN** las dos confirman sin deadlock porque el servicio bloquea por clave ascendente
- **Regla:** `02` §7.3; ADR-015

#### Scenario: Falla a mitad de operación

- **GIVEN** un comando con dos líneas y una falla inyectada después de escribir el primer movimiento
- **WHEN** se procesa
- **THEN** no queda ningún movimiento, saldo, `stock_total` ni historia de costo de esa operación
- **Regla:** INV-01

### Requirement: Un egreso deja stock negativo solo con permiso

Un egreso de stock DEBE aplicarse con la condición de saldo suficiente de `02` §7.4 y, si no alcanza, DEBE rechazarse con `STOCK_INSUFICIENTE` sin cambios. Las excepciones en la etapa actual son el egreso de una anulación de compra (CMP-07), la salida de una transferencia (`design.md` D1 del change 14) y los egresos inversos de una anulación de transferencia o de ajuste (`design.md` D5 del change 14): si quien los registra tiene `PERMITIR_STOCK_NEGATIVO`, el egreso DEBE aplicarse sin condición y el resultado DEBE informar qué saldos quedaron negativos para que la operación quede con la observación `STOCK_NEGATIVO` (STK-05, `design.md` D10 del change 11). Un egreso `AJUSTE` que no es el inverso de una anulación NO tiene excepción: nunca deja el saldo negativo. Las correcciones de stock inicial siguen sin excepción (STK-10).

#### Scenario: Egreso mayor que el saldo
- **GIVEN** 10 unidades de Vino A en el depósito
- **WHEN** se registra un egreso de 11
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 10
- **Regla:** STK-05; `02` §7.4

#### Scenario: Egreso de anulación de compra con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `ANULACION_COMPRA` de 60 con permiso de stock negativo
- **THEN** el saldo queda en −12, el stock total baja 60 y el resultado informa el saldo negativo
- **Regla:** CMP-07; STK-05

#### Scenario: Egreso de anulación de compra sin permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `ANULACION_COMPRA` de 60 sin permiso de stock negativo
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 48
- **Regla:** CMP-07; STK-05

#### Scenario: Salida de transferencia con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `TRANSFERENCIA_SALIDA` de 60 con permiso de stock negativo
- **THEN** el saldo queda en −12 y el resultado informa el saldo negativo
- **Regla:** STK-05; `design.md` D1 del change 14

#### Scenario: Ajuste negativo con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `AJUSTE` de 60 con origen `AJUSTE_STOCK` y permiso de stock negativo
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 48
- **Regla:** STK-05; `design.md` D1 del change 14

#### Scenario: Inverso de una anulación de ajuste con permiso
- **GIVEN** 5 unidades de Vino A en el depósito
- **WHEN** se registra un egreso `AJUSTE` de 12 con origen `ANULACION_AJUSTE_STOCK`, con y sin permiso de stock negativo
- **THEN** con permiso el saldo queda en −7 y el resultado informa el saldo negativo; sin permiso se rechaza con `STOCK_INSUFICIENTE`
- **Regla:** STK-05; `design.md` D5 del change 14

#### Scenario: Corrección de stock inicial con permiso
- **GIVEN** 48 unidades de Vino A en el depósito
- **WHEN** se registra una corrección `STOCK_INICIAL` de −60 con permiso de stock negativo
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 48
- **Regla:** STK-10

### Requirement: El libro y el saldo son de su organización

Toda fila de `stock_movimiento` y `stock_saldo` DEBE referenciar producto, ubicación, usuario y dispositivo de su misma organización mediante claves foráneas compuestas; una referencia ajena o inexistente DEBE rechazarla la base y responderse como 404 (INV-02, INV-21, ADR-035 punto 4).

#### Scenario: Producto de otra organización

- **GIVEN** la base migrada
- **WHEN** se inserta un movimiento de la organización A con un producto de la organización B
- **THEN** la clave foránea compuesta lo rechaza
- **Regla:** INV-02

#### Scenario: Clave de saldo que empieza por la organización

- **GIVEN** la prueba genérica de aislamiento del esquema
- **WHEN** revisa `stock_saldo` y `costo_producto`
- **THEN** ambas tienen clave primaria compuesta que empieza por `organizacion_id`
- **Regla:** INV-02; ADR-035

### Requirement: El egreso de una anulación de compra revierte su ingreso

Un movimiento `ANULACION_COMPRA` DEBE ser un egreso que lleva el costo base de la línea de compra que revierte; DEBE quedar en el libro con ese costo y DEBE delegar en `costeo` la reversión del promedio (CMP-06), en lugar de valorizarse al promedio vigente. Un egreso `ANULACION_COMPRA` sin costo DEBE rechazarse con `COSTO_INVALIDO` (`design.md` D9 del change 11).

#### Scenario: Costo del egreso en el kardex
- **GIVEN** una compra de 60 unidades de Vino A a costo base `"1100.000000"`
- **WHEN** se anula
- **THEN** el kardex muestra un movimiento `ANULACION_COMPRA` de −60 con costo `"1100.000000"`
- **Regla:** CMP-06; STK-03; CST-13

### Requirement: Una reversión de compra admite un producto inactivo

Un movimiento `ANULACION_COMPRA` DEBE registrarse aunque el producto esté inactivo, porque revierte una operación existente (CAT-05, `design.md` D11 del change 11). Los demás tipos siguen rechazando un producto inactivo (`PRODUCTO_INACTIVO`). Una ubicación inactiva sigue rechazando todo movimiento (`UBICACION_INACTIVA`).

#### Scenario: Reversión con producto inactivo
- **GIVEN** Vino A inactivo con 60 unidades en el depósito
- **WHEN** se registra un egreso `ANULACION_COMPRA` de 60
- **THEN** se acepta y el saldo queda en 0
- **Regla:** CAT-05; `design.md` D11

#### Scenario: Otro tipo con producto inactivo
- **GIVEN** Vino A inactivo
- **WHEN** se registra un ingreso `COMPRA`
- **THEN** se rechaza con `PRODUCTO_INACTIVO`
- **Regla:** CAT-05

### Requirement: Los ingresos de transferencia y de ajuste no llevan costo

Un movimiento positivo de tipo `TRANSFERENCIA_ENTRADA` o `AJUSTE` DEBE registrarse sin costo de entrada (con costo es `COSTO_INVALIDO`), NO DEBE recalcular el promedio y DEBE guardar como `costo_unitario` el promedio vigente del producto, o nulo si no tiene (CST-12, `design.md` D3, D9). La única excepción son los movimientos inversos de una anulación (requisito siguiente). Un ingreso de tipo `DIFERENCIA_RENDICION` sigue rechazándose con `TIPO_MOVIMIENTO_INVALIDO` hasta el change 24. Los ingresos que recalculan siguen siendo `STOCK_INICIAL`, `COMPRA` y `ANULACION_VENTA` (CST-11).

#### Scenario: Entrada de transferencia valorizada al promedio

- **GIVEN** Vino A con stock total 120 y promedio `"1050.000000"`
- **WHEN** el servicio de stock registra un egreso `TRANSFERENCIA_SALIDA` de 48 en el depósito y un ingreso `TRANSFERENCIA_ENTRADA` de 48 en "Camioneta 1", sin costo
- **THEN** los dos movimientos guardan `"1050.000000"`, el stock total sigue en 120 y el promedio no cambia
- **Regla:** STK-07; CST-12; INV-15

#### Scenario: Ingreso de transferencia con costo

- **GIVEN** el servicio de stock
- **WHEN** se registra un ingreso `TRANSFERENCIA_ENTRADA` o `AJUSTE` con origen `TRANSFERENCIA` o `AJUSTE_STOCK` y costo `"1000.000000"`
- **THEN** se rechaza con `COSTO_INVALIDO` y no se escribe nada
- **Regla:** CST-12; `design.md` D9

#### Scenario: Ingreso de rendición todavía no admitido

- **GIVEN** el servicio de stock
- **WHEN** se registra un ingreso `DIFERENCIA_RENDICION`
- **THEN** se rechaza con `TIPO_MOVIMIENTO_INVALIDO`
- **Regla:** ADR-039; RUT-06

### Requirement: Los movimientos inversos de una anulación guardan el costo original

Un movimiento `TRANSFERENCIA_SALIDA`, `TRANSFERENCIA_ENTRADA` o `AJUSTE` con origen `ANULACION_TRANSFERENCIA` o `ANULACION_AJUSTE_STOCK` DEBE llevar el `costo_unitario` del movimiento que revierte (que puede ser nulo) y el servicio de stock DEBE guardarlo tal cual, sin valorizarlo al promedio vigente, sin recalcular el promedio y sin historia de costo; el stock total DEBE moverse por la cantidad (CST-12, CST-13, `design.md` D5, D5.1, D5.2). Los inversos reutilizan los tipos de STK-03: NO se agregan tipos de movimiento.

#### Scenario: Inverso de un ajuste a su costo original

- **GIVEN** Vino A con promedio vigente `"1100.000000"` y un ajuste anterior de −6 registrado a `"1050.000000"`
- **WHEN** el servicio de stock registra un ingreso `AJUSTE` de 6 con origen `ANULACION_AJUSTE_STOCK` y costo `"1050.000000"`
- **THEN** el movimiento guarda `"1050.000000"`, el stock total sube 6, el promedio sigue en `"1100.000000"` y no hay fila nueva en `costo_producto_mov`
- **Regla:** CST-12; CST-13; `design.md` D5.2

#### Scenario: Inverso de un movimiento sin costo

- **GIVEN** una transferencia de un producto sin promedio, cuyos movimientos guardaron costo nulo
- **WHEN** se registran sus inversos con origen `ANULACION_TRANSFERENCIA` y costo nulo
- **THEN** se aceptan y guardan costo nulo
- **Regla:** ADR-039; `design.md` D5.2

### Requirement: Un movimiento toma su producto en modo compartido

El servicio de stock DEBE tomar cada producto de las líneas con bloqueo compartido, por id ascendente, después de las ubicaciones y antes de `costo_producto` y `stock_saldo`, para que un movimiento y la desactivación de ese producto se esperen entre sí: nunca DEBE quedar un movimiento nuevo sobre un producto recién desactivado (ADR-038 punto 5, `design.md` D4, D4.2; enmienda `02` §7.3). El resto del orden global de bloqueo NO cambia.

#### Scenario: Movimiento y desactivación simultáneos del mismo producto

- **GIVEN** "Vino Rosado" activo sin stock, un ingreso de 6 en "Camioneta 1" y, a la vez, su desactivación
- **WHEN** las dos transacciones confirman
- **THEN** o el ingreso falla con `PRODUCTO_INACTIVO` y el producto queda inactivo sin stock, o la desactivación falla con `PRODUCTO_CON_STOCK` y el producto queda activo con 6; nunca queda un producto inactivo con stock
- **Regla:** CAT-05; ADR-038; `design.md` D4.2

#### Scenario: Stock inicial y compras no cambian su resultado

- **GIVEN** las suites de stock inicial, compras e importación previas a este change
- **WHEN** se ejecutan con el bloqueo compartido del producto
- **THEN** pasan sin cambios
- **Regla:** `02` §7.3; `design.md` D4.2
