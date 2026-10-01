## Purpose

Permitir la puesta en marcha cargando el stock inicial valorizado de cada ubicación como movimientos `STOCK_INICIAL` que ingresan stock y recalculan el costo promedio, con corrección de errores de carga sin borrar nada (STK-03, CST-11, `00` §6.1, `01` §21).

## ADDED Requirements

### Requirement: Registrar stock inicial valorizado por ubicación

El sistema DEBE ofrecer el comando `STOCK_INICIAL_REGISTRAR` (solo `ONLINE`, `02` §6.5) con `ubicacion_id` y de 1 a 200 líneas, cada una con `producto_id`, `cantidad_base` entera distinta de cero y `costo_unitario` como string por unidad base (`design.md` D5). Una línea positiva DEBE ingresar stock y recalcular el promedio (CST-11); cada línea DEBE dejar un movimiento `STOCK_INICIAL` con `origen_id` igual al `operation_id` y el costo usado. El comando DEBE exigir el permiso de `design.md` D1, ser atómico (INV-01), idempotente (SYN-02) y quedar auditado una sola vez (AUD-01, ADR-022). El momento es el `occurred_at` del sobre.

#### Scenario: Stock inicial en el depósito

- **GIVEN** un Administrador y el producto Vino A sin movimientos
- **WHEN** envía `STOCK_INICIAL_REGISTRAR` al depósito con 60 unidades a `"1000.000000"`
- **THEN** el saldo del depósito es 60, el stock total 60, el promedio `"1000.000000"`, hay un movimiento `STOCK_INICIAL`, una fila de historia de costo y un registro de auditoría
- **Regla:** STK-03; CST-11; `01` §21

#### Scenario: Stock inicial en otra ubicación recalcula el promedio

- **GIVEN** 60 unidades de Vino A a `"1000.000000"` en el depósito
- **WHEN** se registra stock inicial de 60 unidades a `"1100.000000"` en un vehículo
- **THEN** el promedio es `"1050.000000"` y el stock total 120
- **Regla:** CST-10; CST-11

#### Scenario: Varias líneas en un comando

- **GIVEN** los productos Vino A y Cerveza B sin movimientos
- **WHEN** se registra un comando con una línea para cada uno
- **THEN** ambos quedan con su saldo y su promedio, en una sola operación y una sola auditoría
- **Regla:** INV-01; `design.md` D5

#### Scenario: Doble envío

- **GIVEN** un `STOCK_INICIAL_REGISTRAR` ya aceptado
- **WHEN** se reenvía con el mismo `operation_id` y el mismo contenido
- **THEN** se devuelve el resultado original y el saldo no cambia
- **Regla:** SYN-02; INV-06

#### Scenario: Mismo `operation_id` con otro contenido

- **GIVEN** un `STOCK_INICIAL_REGISTRAR` ya aceptado
- **WHEN** se reenvía con el mismo `operation_id` y otra cantidad
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` sin efectos
- **Regla:** SYN-02

#### Scenario: Sin `Operation-Id`

- **GIVEN** un Administrador
- **WHEN** envía la petición sin el encabezado `Operation-Id`
- **THEN** la respuesta es 422 y no se registra nada
- **Regla:** TR-07

#### Scenario: Sin permiso

- **GIVEN** un usuario sin el permiso de D1
- **WHEN** envía `STOCK_INICIAL_REGISTRAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO` y no se registra nada
- **Regla:** SEG-06

#### Scenario: Modo OFFLINE rechazado

- **GIVEN** un lote de sincronización
- **WHEN** incluye `STOCK_INICIAL_REGISTRAR` en modo `OFFLINE`
- **THEN** queda `RECHAZADO` con `MODO_NO_ADMITIDO_PARA_TIPO` sin efectos
- **Regla:** `02` §6.5

#### Scenario: Ubicación o producto ajenos o inexistentes

- **GIVEN** una ubicación o un producto de la organización B
- **WHEN** un Administrador de A los usa en `STOCK_INICIAL_REGISTRAR`
- **THEN** la respuesta es 404 y no se registra nada
- **Regla:** INV-21; SEG-07

#### Scenario: Ubicación o producto inactivos

- **GIVEN** una ubicación inactiva o un producto inactivo
- **WHEN** se usan en `STOCK_INICIAL_REGISTRAR`
- **THEN** se rechaza con `UBICACION_INACTIVA` o `PRODUCTO_INACTIVO` sin efectos
- **Regla:** CAT-05; `design.md` D8

#### Scenario: Contenido inválido

- **GIVEN** un Administrador
- **WHEN** envía cero líneas, más de 200, un producto repetido, una cantidad cero o no entera, o campos extra
- **THEN** se rechaza (422 o `PRODUCTO_REPETIDO`) sin efectos
- **Regla:** INV-04; `design.md` D5

### Requirement: El costo del ingreso es positivo y exacto

El `costo_unitario` de una línea positiva DEBE ser mayor que cero, con hasta 6 decimales sin redondear y dentro de `numeric(18,6)`; si no, `COSTO_INVALIDO` (`design.md` D6, TR-02). Una línea negativa NO DEBE traer costo (`design.md` D5).

#### Scenario: Costo cero

- **GIVEN** un Administrador
- **WHEN** envía una línea positiva con `costo_unitario` `"0"`
- **THEN** se rechaza con `COSTO_INVALIDO`
- **Regla:** `design.md` D6

#### Scenario: Costo con más de 6 decimales

- **GIVEN** un Administrador
- **WHEN** envía `costo_unitario` `"1000.0000001"`
- **THEN** se rechaza con `COSTO_INVALIDO` sin redondear
- **Regla:** TR-02; TR-03

#### Scenario: Costo como número JSON

- **GIVEN** un Administrador
- **WHEN** envía `costo_unitario` como número y no como string
- **THEN** se rechaza sin efectos
- **Regla:** INV-03; `02` §10.2

### Requirement: Un stock inicial se corrige con otro en sentido contrario

Un producto DEBE admitir varios `STOCK_INICIAL` por ubicación. Una línea negativa DEBE egresar al promedio vigente sin recalcularlo (CST-12) y NO DEBE dejar negativo el saldo de la ubicación (`STOCK_INSUFICIENTE`). Los `STOCK_INICIAL` DEBEN admitirse solo mientras el producto no tenga en la organización movimientos de otro tipo (`PRODUCTO_CON_OPERACIONES`), comprobado con la fila de costo del producto bloqueada (`design.md` D4).

#### Scenario: Corregir una cantidad cargada de más

- **GIVEN** 60 unidades de Vino A a `"1000.000000"` en el depósito cuando debían ser 48
- **WHEN** se registra stock inicial de −12 unidades
- **THEN** el saldo es 48, el promedio sigue en `"1000.000000"` y los dos movimientos quedan en el kardex
- **Regla:** TR-06; CST-12; `design.md` D4

#### Scenario: Corregir un costo mal cargado

- **GIVEN** 60 unidades de Vino A a `"10000.000000"` como único stock del producto, cuando el costo era `"1000.000000"`
- **WHEN** se registra −60 y luego +60 a `"1000.000000"`
- **THEN** el promedio es `"1000.000000"` porque el stock total previo era cero
- **Regla:** CST-11; `design.md` D4

#### Scenario: Corrección que dejaría negativo

- **GIVEN** 10 unidades en el depósito
- **WHEN** se registra stock inicial de −11
- **THEN** se rechaza con `STOCK_INSUFICIENTE` sin efectos
- **Regla:** STK-05; `design.md` D4

#### Scenario: Producto con operaciones de otro tipo

- **GIVEN** un producto con un movimiento de otro tipo registrado por el servicio
- **WHEN** se registra un stock inicial de ese producto
- **THEN** se rechaza con `PRODUCTO_CON_OPERACIONES` sin efectos
- **Regla:** `design.md` D4
