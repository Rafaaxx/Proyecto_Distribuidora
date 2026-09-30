## Purpose

Definir la cuenta corriente de cada cliente y de cada proveedor como un libro de movimientos de solo inserción (CC-01, CC-06), con un saldo que se deriva del libro (CC-04) y se materializa en `saldo_cuenta`, en la misma transacción y con la fila bloqueada (`02` §7.2, §7.3; ADR-015). Es la base que escriben el saldo inicial de este change y, después, compras (11), pagos (12), cobranzas (17) y ventas (18a, 19).

## ADDED Requirements

### Requirement: El libro de cuenta corriente es único y de solo inserción

El sistema DEBE registrar cada movimiento de cuenta corriente en la tabla `cuenta_movimiento`, única para clientes y proveedores, con `organizacion_id`, `cuenta_tipo` (`CLIENTE` o `PROVEEDOR`), `entidad_id`, `tipo`, `sentido` (`AUMENTA` o `REDUCE`), `importe` positivo en `numeric(14,2)`, `origen_tipo`, `origen_id`, `occurred_at`, `registered_at`, `usuario_id`, `dispositivo_id` (`uuid NOT NULL`, FK compuesta a `dispositivo`, `design.md` D14) y `operation_id` (CC-01, `03` §12, `03` §2.3). Un movimiento NO DEBE editarse ni borrarse: el usuario de aplicación (`app_runtime`) DEBE tener solo `SELECT` e `INSERT` sobre la tabla (CC-06, INV-05, ADR-020), y ninguna ruta de la API DEBE modificar ni eliminar movimientos. La tabla NO DEBE tener columna de saldo acumulado (CC-04).

#### Scenario: Un movimiento guarda todos sus datos

- **GIVEN** el cliente `Kiosco La Esquina` en la organización A
- **WHEN** el servicio de cuenta corriente registra un movimiento `SALDO_INICIAL` `AUMENTA` de `"150000.00"`
- **THEN** existe una fila en `cuenta_movimiento` con `cuenta_tipo = CLIENTE`, el `entidad_id` del cliente, el tipo, el sentido, el importe `"150000.00"`, el origen, `occurred_at`, `registered_at` tomado del reloj inyectable, el usuario, el dispositivo del sobre y el `operation_id`
- **Regla:** CC-01; TR-05; `03` §12; `design.md` D14

#### Scenario: El usuario de aplicación no puede modificar ni borrar movimientos

- **GIVEN** la base migrada y una conexión como `app_runtime`
- **WHEN** intenta `UPDATE` o `DELETE` sobre `cuenta_movimiento`
- **THEN** PostgreSQL rechaza la sentencia por falta de permisos y la fila queda intacta
- **Regla:** INV-05; CC-06; ADR-020

#### Scenario: El importe es siempre positivo

- **GIVEN** la base migrada
- **WHEN** se intenta insertar un movimiento con importe `"0.00"` o `"-10.00"`
- **THEN** la restricción `ck_cuenta_movimiento__importe_positivo` lo rechaza
- **Regla:** CC-01; `03` §12

#### Scenario: No existe ruta que edite o borre movimientos

- **GIVEN** todas las rutas registradas de la API
- **WHEN** se buscan rutas `PUT`, `PATCH` o `DELETE` sobre movimientos de cuenta corriente
- **THEN** no existe ninguna
- **Regla:** CC-06; TR-06; INV-05

### Requirement: El saldo se deriva del libro y se materializa en la misma transacción

El saldo de una cuenta DEBE ser la suma de los movimientos que aumentan menos la suma de los que reducen (CC-04). El sistema DEBE mantener `saldo_cuenta` (`organizacion_id`, `cuenta_tipo`, `entidad_id`, `saldo numeric(14,2)`, `actualizado_en`) actualizado en la misma transacción que cada movimiento (`02` §7.2). Un saldo negativo DEBE significar saldo a favor del cliente o de la organización frente al proveedor (`01` §2). El libro es la verdad; `saldo_cuenta` es una materialización verificable (ADR-015). Ningún saldo DEBE calcularse trayendo filas a Python para sumar.

#### Scenario: El saldo es la suma de los movimientos

- **GIVEN** el cliente `Kiosco La Esquina` sin movimientos
- **WHEN** se registran un movimiento `AUMENTA` de `"150000.00"` y otro `REDUCE` de `"20000.00"`
- **THEN** `saldo_cuenta.saldo` vale `"130000.00"` y coincide con la suma calculada en SQL sobre `cuenta_movimiento`
- **Regla:** CC-04; INV-13

#### Scenario: Un saldo negativo es saldo a favor

- **GIVEN** el cliente `Kiosco La Esquina` sin movimientos
- **WHEN** se registra un movimiento `REDUCE` de `"20000.00"`
- **THEN** `saldo_cuenta.saldo` vale `"-20000.00"`
- **Regla:** `01` §2 (Saldo); CC-04

#### Scenario: Propiedad INV-13 sobre secuencias arbitrarias

- **GIVEN** una secuencia arbitraria de movimientos generada por Hypothesis (sentidos e importes válidos, una o varias cuentas)
- **WHEN** se registran todos por el servicio
- **THEN** para cada cuenta, `saldo_cuenta.saldo` es igual a la suma SQL de sus movimientos que aumentan menos los que reducen
- **Regla:** INV-13; `02` §15

#### Scenario: Una falla a mitad de la operación no deja rastro

- **GIVEN** una transacción que registra un movimiento y actualiza el saldo
- **WHEN** se inyecta una falla después de insertar el movimiento y antes del commit
- **THEN** no queda ni el movimiento ni el cambio de saldo
- **Regla:** INV-01; INV-13

### Requirement: Todo movimiento bloquea primero la fila de saldo de su cuenta

El servicio DEBE bloquear la fila de `saldo_cuenta` de la cuenta (`SELECT ... FOR UPDATE`) antes de insertar el movimiento y actualizar el saldo, como primer nivel del orden global de bloqueo (`02` §7.3, ADR-015). Si la fila no existe, DEBE crearse con saldo cero sin carrera entre transacciones concurrentes (`design.md` D10). Los handlers NO DEBEN bloquear filas directamente: usan la función del servicio.

#### Scenario: Dos movimientos concurrentes sobre la misma cuenta

- **GIVEN** el proveedor `Bodega Norte` con saldo `"0.00"` y dos transacciones independientes que confirman sus commits
- **WHEN** ambas registran a la vez un movimiento `AUMENTA` de `"80000.00"` sobre esa cuenta
- **THEN** las dos se confirman, hay dos movimientos y el saldo final es `"160000.00"`
- **Regla:** INV-13; `02` §7.3; ADR-015

#### Scenario: La primera fila de saldo se crea una sola vez bajo concurrencia

- **GIVEN** el cliente `Kiosco La Esquina` sin fila en `saldo_cuenta`
- **WHEN** dos transacciones concurrentes registran su primer movimiento
- **THEN** existe una única fila de saldo para esa cuenta y su valor es la suma de los dos movimientos
- **Regla:** INV-13; `design.md` D10

#### Scenario: Cuentas distintas no se esperan entre sí

- **GIVEN** dos clientes distintos de la organización A
- **WHEN** dos transacciones concurrentes registran un movimiento cada una sobre un cliente distinto
- **THEN** ninguna espera el bloqueo de la otra
- **Regla:** `02` §7.3

### Requirement: Los tipos de movimiento respetan el catálogo de cada cuenta

El sistema DEBE aceptar en una cuenta de cliente solo los tipos de CC-02 y en una cuenta de proveedor solo los de CC-03, y la base DEBE rechazar cualquier combinación incoherente de `cuenta_tipo` y `tipo` (`design.md` D12). En este change el único tipo que escribe un comando es `SALDO_INICIAL`; los demás los escriben los changes que crean sus operaciones.

#### Scenario: Un tipo de proveedor en una cuenta de cliente se rechaza

- **GIVEN** el cliente `Kiosco La Esquina`
- **WHEN** se intenta registrar en su cuenta un movimiento de tipo `COMPRA`
- **THEN** se rechaza con `TIPO_MOVIMIENTO_INVALIDO` y no cambia ni el libro ni el saldo
- **Regla:** CC-02; CC-03

#### Scenario: Un sentido fuera del catálogo se rechaza

- **GIVEN** la base migrada
- **WHEN** se intenta insertar un movimiento con `sentido = SUMA`
- **THEN** la restricción de verificación lo rechaza
- **Regla:** CC-01; `03` §2.2

### Requirement: La cuenta pertenece a una entidad de la misma organización

Todo movimiento y toda fila de saldo DEBEN referenciar un cliente o un proveedor existente de la misma organización, y la base DEBE garantizarlo con claves foráneas compuestas que incluyan `organizacion_id` según `cuenta_tipo` (`03` §2.4, `design.md` D6). Una referencia a una entidad de otra organización, inexistente o del tipo equivocado DEBE rechazarse y la API DEBE responder 404 (SEG-07, INV-21).

#### Scenario: Un movimiento sobre un cliente de otra organización se rechaza

- **GIVEN** el cliente `Kiosco La Esquina` de la organización B
- **WHEN** se intenta registrar un movimiento sobre él con `organizacion_id` de A
- **THEN** la clave foránea compuesta lo rechaza y no queda ninguna fila en A ni en B
- **Regla:** INV-02; INV-21; `03` §2.4

#### Scenario: El identificador de un proveedor no sirve como cuenta de cliente

- **GIVEN** el proveedor `Bodega Norte` de la organización A
- **WHEN** se intenta registrar un movimiento con `cuenta_tipo = CLIENTE` y el id del proveedor
- **THEN** se rechaza como entidad inexistente
- **Regla:** INV-02; `design.md` D6

### Requirement: La consistencia entre saldo y libro se puede verificar sin corregir

El servicio DEBE exponer una consulta SQL que compare cada fila de `saldo_cuenta` con la suma de su libro y devuelva las diferencias, sin corregirlas (`02` §7.6, ADR-015). La tarea diaria que la ejecuta y notifica es del change 28.

#### Scenario: Sin diferencias después de operar

- **GIVEN** varias cuentas con movimientos registrados por el servicio
- **WHEN** se ejecuta la verificación de consistencia
- **THEN** no devuelve ninguna diferencia
- **Regla:** INV-13; `02` §7.6

#### Scenario: Una diferencia se informa y no se corrige

- **GIVEN** una fila de `saldo_cuenta` alterada a mano en la prueba (con el usuario de migraciones) para que no coincida con su libro
- **WHEN** se ejecuta la verificación de consistencia
- **THEN** devuelve esa cuenta con el saldo materializado y la suma del libro, y la fila de saldo sigue sin cambios
- **Regla:** ADR-015; `02` §7.6
