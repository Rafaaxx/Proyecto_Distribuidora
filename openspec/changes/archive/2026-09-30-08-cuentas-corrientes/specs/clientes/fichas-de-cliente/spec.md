## MODIFIED Requirements

### Requirement: El estado del cliente sigue la máquina de estados de `01` §18

El sistema DEBE validar cada cambio de estado contra la máquina de `01` §18: `ACTIVO ↔ SUSPENDIDO`, `ACTIVO → INACTIVO` y `SUSPENDIDO → INACTIVO` y, desde `INACTIVO`, la única salida es `INACTIVO → ACTIVO` y solo si el cliente no tiene operaciones (CLI-06, ADR-030); con operaciones es terminal. Un cliente NO DEBE borrarse en ningún caso (CLI-04, INV-05). A partir del change 08, un cliente tiene operaciones si su cuenta corriente tiene al menos un movimiento de cualquier tipo, incluido `SALDO_INICIAL` (`design.md` D8 del change 08, aprobada 2026-09-29); `clientes` lo consulta a `cuentas_corrientes/service.py` dentro de la misma transacción, después de bloquear la fila del cliente, y la reactivación de un cliente con movimientos se rechaza con `CLIENTE_CON_OPERACIONES`. Ventas y cobranzas (changes 17 y 18a) quedan cubiertas por la misma consulta porque también escriben en el libro.

#### Scenario: Suspender y reactivar

- **GIVEN** el cliente `Kiosco La Esquina` `ACTIVO` en A
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = SUSPENDIDO` y luego con `estado = ACTIVO`
- **THEN** el cliente queda suspendido y luego activo, con `actualizado_en` nuevo en cada cambio
- **Regla:** CLI-02; `01` §18

#### Scenario: Inactivar un cliente

- **GIVEN** el cliente `Kiosco La Esquina` `SUSPENDIDO` en A
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = INACTIVO`
- **THEN** el cliente queda `INACTIVO`, sigue existiendo y aparece en el listado con ese estado
- **Regla:** CLI-02; CLI-04

#### Scenario: Reactivar un cliente sin operaciones

- **GIVEN** el cliente `Kiosco La Esquina` `INACTIVO` en A, sin movimientos en su cuenta corriente
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = ACTIVO`
- **THEN** el cliente vuelve a `ACTIVO` y sigue existiendo
- **Regla:** CLI-06; `01` §18; ADR-030

#### Scenario: Reactivar un cliente con movimientos se rechaza

- **GIVEN** el cliente `Kiosco La Esquina` `INACTIVO` en A, con un saldo inicial de `"150000.00"` en su cuenta corriente
- **WHEN** se envía `CLIENTE_MODIFICAR` con `estado = ACTIVO`
- **THEN** se rechaza con `CLIENTE_CON_OPERACIONES` y el cliente sigue `INACTIVO`
- **Regla:** CLI-06; ADR-030; `design.md` D8 del change 08

#### Scenario: Reactivación y saldo inicial concurrentes

- **GIVEN** el cliente `Kiosco La Esquina` `INACTIVO` sin movimientos, y dos transacciones que confirman sus commits: una reactivación y un saldo inicial
- **WHEN** se ejecutan a la vez
- **THEN** nunca termina el cliente `ACTIVO` con un movimiento que la reactivación no vio: o se aplica la reactivación antes del saldo inicial, o la reactivación se rechaza con `CLIENTE_CON_OPERACIONES`
- **Regla:** CLI-06; ADR-030; `design.md` D6 y D8 del change 08

#### Scenario: Estado fuera del catálogo

- **GIVEN** la organización A
- **WHEN** se envía `CLIENTE_MODIFICAR` con un estado que no es `ACTIVO`, `SUSPENDIDO` ni `INACTIVO`
- **THEN** se rechaza con `ESTADO_INVALIDO` y no cambia ninguna fila
- **Regla:** `01` §18; `03` §10

#### Scenario: Cliente de otra organización

- **GIVEN** un cliente de B
- **WHEN** un usuario de A envía `CLIENTE_MODIFICAR` sobre él
- **THEN** la respuesta es 404 y el cliente de B no cambia
- **Regla:** INV-21; SEG-07

#### Scenario: No existe borrado de clientes

- **GIVEN** la API y los permisos de base del usuario de aplicación
- **WHEN** se busca cualquier operación que elimine un cliente
- **THEN** no existe, y el usuario de aplicación no tiene `DELETE` sobre `cliente`
- **Regla:** CLI-04; TR-06; INV-05
