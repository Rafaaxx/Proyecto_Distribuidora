# Saldo inicial — Especificación

## Purpose

Definir el comando de puesta en marcha que carga la deuda previa de un cliente o proveedor como movimiento `SALDO_INICIAL` de su cuenta corriente (CC-02, CC-03, `00` §5 "Puesta en marcha", `01` §21). Es la única escritura de negocio de este change y la que reutiliza la importación del change 10 fila por fila. Los permisos, la cantidad admitida, los estados admitidos y la forma del contenido siguen las decisiones aprobadas de `design.md` D1, D3, D4 y D5 (2026-09-29).

## Requirements

### Requirement: El saldo inicial se registra con un comando propio

El sistema DEBE registrar un saldo inicial con el comando `SALDO_INICIAL_REGISTRAR` (`ONLINE`, `admite_offline = false`, `operation_id` obligatorio en el encabezado `Operation-Id`, permiso `IMPORTAR_DATOS`, `design.md` D1), cuyo contenido lleva `cuenta_tipo` (`CLIENTE` o `PROVEEDOR`), `entidad_id`, `importe` (string con hasta dos decimales, mayor que cero) y `sentido` (`AUMENTA` o `REDUCE`) (`design.md` D5). El comando DEBE insertar un movimiento `SALDO_INICIAL` con `origen_tipo = SALDO_INICIAL` y `origen_id` igual al `operation_id`, `occurred_at` del sobre, actualizar `saldo_cuenta` con la fila bloqueada y dejar una única fila de auditoría del bus con el `operation_id` (`01` §21, ADR-022). El comando NO DEBE aceptar campos fuera de su esquema.

#### Scenario: Saldo inicial deudor de un cliente

- **GIVEN** el cliente `Kiosco La Esquina` `ACTIVO` en A, sin movimientos
- **WHEN** un usuario con `IMPORTAR_DATOS` envía `SALDO_INICIAL_REGISTRAR` con `cuenta_tipo = CLIENTE`, `importe = "150000.00"` y `sentido = AUMENTA`
- **THEN** el comando queda `ACEPTADO`, existe un movimiento `SALDO_INICIAL` `AUMENTA` de `"150000.00"`, el saldo del cliente es `"150000.00"` y hay una fila de auditoría con el `operation_id`
- **Regla:** CC-02; CC-04; `01` §21; AUD-02

#### Scenario: Saldo inicial de un proveedor

- **GIVEN** el proveedor `Bodega Norte` activo en A, sin movimientos
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` con `cuenta_tipo = PROVEEDOR`, `importe = "80000.00"` y `sentido = AUMENTA`
- **THEN** el comando queda `ACEPTADO` y la organización le debe `"80000.00"` al proveedor
- **Regla:** CC-03; CC-04; `01` §21

#### Scenario: Saldo inicial a favor del cliente

- **GIVEN** el cliente `Kiosco La Esquina` sin movimientos
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` con `importe = "20000.00"` y `sentido = REDUCE`
- **THEN** el saldo del cliente es `"-20000.00"`, es decir, saldo a favor
- **Regla:** `01` §2 (Saldo); `01` §21 (+ / −)

#### Scenario: Doble envío del saldo inicial

- **GIVEN** un `SALDO_INICIAL_REGISTRAR` aceptado con `operation_id` X
- **WHEN** se reenvía con `operation_id` X y el mismo contenido
- **THEN** se devuelve el resultado original, hay un solo movimiento, el saldo no cambia y hay una sola fila de auditoría
- **Regla:** INV-06; SYN-02

#### Scenario: Mismo `operation_id` con contenido distinto

- **GIVEN** un `SALDO_INICIAL_REGISTRAR` aceptado con `operation_id` X e importe `"150000.00"`
- **WHEN** se reenvía con `operation_id` X e importe `"90000.00"`
- **THEN** se rechaza con `COMANDO_INCONSISTENTE` y el saldo sigue en `"150000.00"`
- **Regla:** SYN-02

#### Scenario: Sin `Operation-Id` se rechaza

- **GIVEN** la organización A
- **WHEN** se envía `POST /api/v1/cuentas-corrientes/saldos-iniciales` sin el encabezado `Operation-Id`
- **THEN** la respuesta es un error de validación y no se inserta ningún movimiento
- **Regla:** TR-07; `02` §6.2

#### Scenario: Sin permiso se rechaza sin efectos

- **GIVEN** un usuario sin `IMPORTAR_DATOS` (por ejemplo, rol Administración)
- **WHEN** envía `SALDO_INICIAL_REGISTRAR`
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`, no se inserta ningún movimiento y no queda reserva del `operation_id`
- **Regla:** `01` §19 (`IMPORTAR_DATOS`); SEG-06; `design.md` D1

#### Scenario: Entidad de otra organización o inexistente

- **GIVEN** un cliente de la organización B
- **WHEN** un usuario de A envía `SALDO_INICIAL_REGISTRAR` sobre él, o sobre un id que no existe
- **THEN** la respuesta es 404, no se inserta ningún movimiento en A ni en B y el `operation_id` puede reintentarse con contenido corregido
- **Regla:** INV-21; SEG-07; `02` §6.3

#### Scenario: Importe inválido

- **GIVEN** la organización A
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` con `importe = "0.00"`, `"-100.00"`, `"100.005"` o un número JSON en lugar de string
- **THEN** se rechaza con `IMPORTE_INVALIDO` y no cambia ninguna fila
- **Regla:** INV-03; CC-01; `core/money.py`

#### Scenario: Sentido o tipo de cuenta fuera del catálogo

- **GIVEN** la organización A
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` con `sentido = SUMA` o con `cuenta_tipo = EMPLEADO`
- **THEN** se rechaza como malformado y no cambia ninguna fila
- **Regla:** CC-01; `03` §12

#### Scenario: Campos fuera del esquema

- **GIVEN** la organización A
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` cuyo contenido incluye `organizacion_id` o `saldo`
- **THEN** se rechaza como malformado y no cambia ninguna fila
- **Regla:** `02` §6.2 (organización desde el token); CC-04

#### Scenario: No se admite sin conexión

- **GIVEN** un lote de sincronización con un `SALDO_INICIAL_REGISTRAR` en modo `OFFLINE`
- **WHEN** el servidor lo procesa
- **THEN** lo rechaza como comando no admitido sin conexión y no inserta ningún movimiento
- **Regla:** `02` §6.5 (solo online); SYN-06

### Requirement: Una cuenta admite varios saldos iniciales solo durante la puesta en marcha

Una cuenta DEBE admitir más de un `SALDO_INICIAL`, cada uno con su sentido, de modo que un saldo inicial equivocado se corrige con otro en sentido inverso, sin editar ni borrar el primero (TR-06, CC-06, `design.md` D3). El sistema DEBE rechazar un `SALDO_INICIAL_REGISTRAR` si la cuenta ya tiene algún movimiento de otro tipo, con `CUENTA_CON_OPERACIONES`. En este change ningún módulo escribe otros tipos, así que la restricción queda latente y se prueba insertando un movimiento de otro tipo por el servicio.

#### Scenario: Corregir un saldo inicial equivocado

- **GIVEN** el cliente `Kiosco La Esquina` con un saldo inicial `AUMENTA` de `"150000.00"` que debía ser `"130000.00"`
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` con `importe = "20000.00"` y `sentido = REDUCE`
- **THEN** los dos movimientos existen, ninguno fue modificado y el saldo es `"130000.00"`
- **Regla:** TR-06; CC-06; CC-04; `design.md` D3

#### Scenario: Una cuenta con operaciones ya no admite saldo inicial

- **GIVEN** el cliente `Kiosco La Esquina` con un movimiento de tipo `VENTA` registrado por el servicio en la prueba
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` sobre su cuenta
- **THEN** se rechaza con `CUENTA_CON_OPERACIONES` y el saldo no cambia
- **Regla:** `design.md` D3

### Requirement: El saldo inicial se admite en cualquier estado salvo el consumidor final

El sistema DEBE aceptar un saldo inicial sobre un cliente `ACTIVO`, `SUSPENDIDO` o `INACTIVO` y sobre un proveedor activo o inactivo, porque la deuda previa existe con independencia del estado. El sistema DEBE rechazar un saldo inicial sobre el cliente consumidor final de la organización con `CONSUMIDOR_FINAL_SIN_CUENTA` (CLI-03, `design.md` D4).

#### Scenario: Saldo inicial de un cliente suspendido

- **GIVEN** el cliente `Kiosco La Esquina` `SUSPENDIDO` en A
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` con `importe = "150000.00"` y `sentido = AUMENTA`
- **THEN** el comando queda `ACEPTADO` y el estado del cliente no cambia
- **Regla:** CLI-02; `design.md` D4

#### Scenario: Saldo inicial de un proveedor inactivo

- **GIVEN** el proveedor `Bodega Norte` inactivo en A
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` sobre su cuenta
- **THEN** el comando queda `ACEPTADO` y el proveedor sigue inactivo
- **Regla:** `design.md` D4

#### Scenario: El consumidor final no tiene saldo inicial

- **GIVEN** la organización A con el consumidor final habilitado
- **WHEN** se envía `SALDO_INICIAL_REGISTRAR` sobre el cliente consumidor final
- **THEN** se rechaza con `CONSUMIDOR_FINAL_SIN_CUENTA` y no se inserta ningún movimiento
- **Regla:** CLI-03; ADR-029; `design.md` D4
