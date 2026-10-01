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

### Requirement: Un egreso no deja stock negativo en este change

Un egreso de stock DEBE aplicarse con la condición de saldo suficiente de `02` §7.4 y, si no alcanza, DEBE rechazarse con `STOCK_INSUFICIENTE` sin cambios. En este change ningún camino admite stock negativo (`design.md` D4).

#### Scenario: Egreso mayor que el saldo

- **GIVEN** 10 unidades de Vino A en el depósito
- **WHEN** se registra un egreso de 11
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y el saldo sigue en 10
- **Regla:** STK-05; `02` §7.4

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
