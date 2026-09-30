## Purpose

Definir la consulta del estado de cuenta de un cliente y de un proveedor: los movimientos en orden de `occurred_at` con el saldo acumulado calculado al consultar, en SQL (CC-07, CC-04), filtrable por período y paginada por cursor (`02` §11, `design.md` D9). Las rutas viven con su entidad (`02` §11, grupo Clientes: "clientes, estado de cuenta") y el permiso de lectura sigue las decisiones aprobadas de `design.md` D2 y D7 (2026-09-29).

## ADDED Requirements

### Requirement: El estado de cuenta muestra los movimientos con saldo acumulado

El sistema DEBE exponer `GET /api/v1/clientes/{cliente_id}/cuenta-corriente` y `GET /api/v1/proveedores/{proveedor_id}/cuenta-corriente`, que devuelven el saldo actual (el de `saldo_cuenta`, `"0.00"` si la cuenta no tiene movimientos) y los movimientos ordenados por `occurred_at` y, a igualdad, por `id`, cada uno con tipo, sentido, importe, `occurred_at`, `registered_at`, origen y `saldo_acumulado`. El saldo acumulado DEBE calcularse en la base al consultar (función de ventana), nunca guardarse ni sumarse en Python (CC-04, CC-07). Los importes DEBEN viajar como string.

#### Scenario: Estado de cuenta con dos movimientos

- **GIVEN** el cliente `Kiosco La Esquina` con un movimiento `AUMENTA` de `"150000.00"` y, después, uno `REDUCE` de `"20000.00"`
- **WHEN** se pide su estado de cuenta
- **THEN** los movimientos aparecen en ese orden con saldos acumulados `"150000.00"` y `"130000.00"`, y el saldo actual es `"130000.00"`
- **Regla:** CC-07; CC-04; INV-03

#### Scenario: Un movimiento con `occurred_at` anterior se ordena por su momento

- **GIVEN** el cliente `Kiosco La Esquina` con un movimiento de `"150000.00"` y, registrado después pero con `occurred_at` anterior, otro de `"20000.00"`
- **WHEN** se pide su estado de cuenta
- **THEN** el de `"20000.00"` aparece primero y los saldos acumulados se calculan en ese orden
- **Regla:** CC-07; TR-05

#### Scenario: Dos movimientos con el mismo `occurred_at`

- **GIVEN** dos movimientos del mismo cliente con idéntico `occurred_at`
- **WHEN** se pide el estado de cuenta dos veces
- **THEN** ambas respuestas los ordenan igual, por `id`
- **Regla:** CC-07; `03` §16

#### Scenario: Cuenta sin movimientos

- **GIVEN** el proveedor `Bodega Norte` sin movimientos ni fila de saldo
- **WHEN** se pide su estado de cuenta
- **THEN** la respuesta tiene la lista vacía y saldo actual `"0.00"`
- **Regla:** CC-04

### Requirement: El estado de cuenta se filtra por período y se pagina sin perder el acumulado

La consulta DEBE aceptar `desde` y `hasta` opcionales (fechas de negocio en la zona horaria de la organización, TR-04) y devolver `saldo_anterior`, calculado en SQL con los movimientos anteriores a `desde`, de modo que el primer saldo acumulado del período parta de él. La consulta DEBE paginar por cursor con un límite máximo por página, y el saldo acumulado de cada página DEBE continuar el de la anterior (`02` §11, `design.md` D9).

#### Scenario: Período con saldo anterior

- **GIVEN** el cliente `Kiosco La Esquina` con un movimiento `AUMENTA` de `"150000.00"` en marzo y uno `REDUCE` de `"20000.00"` en abril
- **WHEN** se pide el estado de cuenta desde el 1 de abril
- **THEN** `saldo_anterior` es `"150000.00"`, aparece solo el movimiento de abril y su saldo acumulado es `"130000.00"`
- **Regla:** CC-07; TR-04; `design.md` D9

#### Scenario: La segunda página continúa el acumulado

- **GIVEN** un cliente con más movimientos que el límite de una página
- **WHEN** se pide la primera página y luego la siguiente con el cursor devuelto
- **THEN** el primer saldo acumulado de la segunda página es el último de la primera más o menos el importe de su movimiento, y ningún movimiento se repite ni se omite
- **Regla:** CC-07; `02` §11; `design.md` D9

#### Scenario: Límite por página excedido

- **GIVEN** la organización A
- **WHEN** se pide el estado de cuenta con un límite mayor que el máximo
- **THEN** la respuesta es un error de validación
- **Regla:** `02` §11

### Requirement: El estado de cuenta respeta permisos y organización

La cuenta de un cliente DEBE requerir `GESTIONAR_CLIENTES` y la de un proveedor `GESTIONAR_PROVEEDORES`, un permiso por ruta (`design.md` D2). Una entidad de otra organización o inexistente DEBE responder 404 (SEG-07, INV-21).

#### Scenario: Sin permiso de lectura

- **GIVEN** un usuario sin `GESTIONAR_CLIENTES` (por ejemplo, rol Vendedor)
- **WHEN** pide el estado de cuenta de un cliente
- **THEN** la respuesta es 403 `PERMISO_REQUERIDO`
- **Regla:** `01` §19; SEG-06; `design.md` D2

#### Scenario: Cliente de otra organización

- **GIVEN** el cliente `Kiosco La Esquina` de B con movimientos
- **WHEN** un usuario de A pide su estado de cuenta
- **THEN** la respuesta es 404 y no revela ningún movimiento ni saldo
- **Regla:** INV-21; SEG-07

#### Scenario: Proveedor de otra organización

- **GIVEN** el proveedor `Bodega Norte` de B
- **WHEN** un usuario de A pide su estado de cuenta
- **THEN** la respuesta es 404
- **Regla:** INV-21; SEG-07
