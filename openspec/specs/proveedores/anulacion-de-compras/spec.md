# Anulación de Compras — Especificación

## Purpose

Corregir una compra confirmada solo por anulación total, con permiso y motivo, revirtiendo stock, costo promedio, cuenta corriente del proveedor y, si corresponde, su pago de contado, sin borrar ningún registro (CMP-05 a CMP-07, TR-06, INV-01, INV-05).

## Requirements

### Requirement: Una compra se anula por comando con permiso y motivo

El sistema DEBE anular una compra `CONFIRMADA` con el comando `COMPRA_ANULAR` (solo `ONLINE`), que exige `ANULAR_COMPRA` y un motivo activo del ámbito `ANULACION_COMPRA` (CMP-05, `design.md` D8, D14). La compra DEBE pasar a `ANULADA` con motivo, momento y usuario; ninguna fila de la compra, sus líneas, su pago ni los libros DEBE borrarse (TR-06, INV-05). Una compra ya anulada DEBE rechazarse con `COMPRA_YA_ANULADA` sin efectos.

#### Scenario: Anulación de una compra a crédito
- **GIVEN** una compra a crédito confirmada de 60 unidades de `Vino A` al depósito con total de factura `"72600.00"`
- **WHEN** se envía `COMPRA_ANULAR` con el motivo "Error de carga"
- **THEN** la compra queda `ANULADA`, hay un movimiento de stock `ANULACION_COMPRA` de −60 y un movimiento `ANULACION_COMPRA` que reduce la cuenta del proveedor en `"72600.00"`
- **Regla:** CMP-05; CC-03; `01` §21

#### Scenario: Compra ya anulada
- **WHEN** se envía `COMPRA_ANULAR` con otro `Operation-Id` sobre una compra `ANULADA`
- **THEN** se rechaza con `COMPRA_YA_ANULADA` y no se agrega ningún movimiento
- **Regla:** CMP-05; TR-06

#### Scenario: Doble envío de la anulación
- **WHEN** se reenvía el mismo `COMPRA_ANULAR` con el mismo `Operation-Id`
- **THEN** se devuelve el resultado original y existe una sola anulación
- **Regla:** INV-06; SYN-02

#### Scenario: Motivo de otro ámbito
- **WHEN** se anula con un motivo del ámbito `AJUSTE_STOCK`
- **THEN** se rechaza con `MOTIVO_INVALIDO`
- **Regla:** CMP-05; `03` §4 (`motivo.ambito`)

#### Scenario: Sin permiso de anulación
- **WHEN** un usuario sin `ANULAR_COMPRA` envía `COMPRA_ANULAR`
- **THEN** la respuesta es 403 y la compra sigue `CONFIRMADA`
- **Regla:** `01` §19

#### Scenario: Compra de otra organización
- **WHEN** un usuario de A anula una compra de B
- **THEN** la respuesta es 404
- **Regla:** INV-21

#### Scenario: Dos anulaciones simultáneas
- **WHEN** dos `COMPRA_ANULAR` con distinto `Operation-Id` sobre la misma compra se procesan a la vez con commits reales
- **THEN** una queda `ACEPTADO` y la otra se rechaza con `COMPRA_YA_ANULADA`; hay un solo egreso por línea
- **Regla:** INV-01; `02` §7

### Requirement: La anulación revierte el promedio cuando se puede

Por cada línea, la anulación DEBE calcular, con el stock total de la organización y el promedio vigente, `stock restante = stock total − cantidad base` y `promedio resultante = (stock total × promedio − cantidad base × costo base de la línea) / stock restante`; si el stock restante es mayor que cero y el promedio resultante es positivo, el promedio DEBE pasar al resultante redondeado a 6 decimales; en otro caso DEBE mantenerse el vigente y la anulación DEBE quedar con la observación `ANULACION_COMPRA_SIN_RECALCULO` (CMP-06, SYN-07). Las líneas DEBEN revertirse en orden inverso al de la compra.

#### Scenario: Se recalcula
- **GIVEN** compras de 60 a `"1000.000000"` y 60 a `"1100.000000"` (stock total 120, promedio `"1050.000000"`)
- **WHEN** se anula la segunda compra
- **THEN** el stock total es 60, el promedio vuelve a `"1000.000000"` y la anulación queda `ACEPTADO` sin observaciones
- **Regla:** CMP-06; CST-11 (`01` §6.2)

#### Scenario: Stock restante cero
- **GIVEN** una única compra de 60 a `"1000.000000"` y ningún otro movimiento
- **WHEN** se anula
- **THEN** el stock total es 0, el promedio se mantiene en `"1000.000000"` y la anulación queda `ACEPTADO_CON_OBSERVACIONES` con `ANULACION_COMPRA_SIN_RECALCULO`
- **Regla:** CMP-06; SYN-07

#### Scenario: Promedio resultante no positivo
- **GIVEN** stock inicial de 10 a `"100.000000"`, una compra de 60 a `"2000.000000"` (promedio `"1728.571429"`) y un egreso de 5 (stock total 65)
- **WHEN** se anula la compra
- **THEN** el stock total es 5, el promedio se mantiene en `"1728.571429"` y la anulación queda con `ANULACION_COMPRA_SIN_RECALCULO`
- **Regla:** CMP-06

### Requirement: La anulación que deja stock negativo exige permiso

El egreso de la anulación DEBE aplicarse con la condición de saldo suficiente en la ubicación de destino de la compra. Si el saldo no alcanza y el usuario no tiene `PERMITIR_STOCK_NEGATIVO`, DEBE rechazarse con `STOCK_INSUFICIENTE` sin efectos; si lo tiene, DEBE aplicarse y quedar con la observación `STOCK_NEGATIVO` (CMP-07, STK-05, `design.md` D10).

#### Scenario: Sin permiso y sin stock suficiente
- **GIVEN** compras de 60 a `"1000.000000"` y 60 a `"1100.000000"` y un egreso de 72 (quedan 48 en el depósito, promedio `"1050.000000"`)
- **WHEN** un usuario sin `PERMITIR_STOCK_NEGATIVO` anula la segunda compra
- **THEN** se rechaza con `STOCK_INSUFICIENTE` y la compra sigue `CONFIRMADA`
- **Regla:** CMP-07; STK-05

#### Scenario: Con permiso
- **GIVEN** la misma situación
- **WHEN** un usuario con `PERMITIR_STOCK_NEGATIVO` anula la segunda compra
- **THEN** el depósito queda en −12, el promedio se mantiene en `"1050.000000"` y la anulación queda con `STOCK_NEGATIVO` y `ANULACION_COMPRA_SIN_RECALCULO`
- **Regla:** CMP-07; CMP-06; STK-05

### Requirement: La anulación de una compra de contado indica si se devuelve el pago

Al anular una compra `CONTADO` DEBE indicarse si el proveedor devuelve el dinero (`devuelve_pago`). Si lo devuelve, el pago de la compra DEBE quedar `ANULADO` con un movimiento `ANULACION_PAGO` que aumenta la cuenta por su importe; si no, el pago se mantiene y la anulación deja saldo a favor de la organización (`design.md` D3). En una compra `CREDITO` el indicador NO DEBE enviarse (`CONDICION_INVALIDA`).

#### Scenario: Se devuelve el pago
- **GIVEN** una compra de contado de `"152460.00"` con su pago y saldo previo 0 del proveedor
- **WHEN** se anula con `devuelve_pago = true`
- **THEN** la cuenta tiene `ANULACION_COMPRA` `"152460.00"` y `ANULACION_PAGO` `"152460.00"`, el saldo vuelve a `"0.00"` y el pago queda `ANULADO`
- **Regla:** CMP-05; CC-03; `design.md` D3

#### Scenario: No se devuelve el pago
- **GIVEN** la misma compra de contado
- **WHEN** se anula con `devuelve_pago = false`
- **THEN** la cuenta tiene solo `ANULACION_COMPRA` y el saldo es `"-152460.00"` ("Saldo a nuestro favor")
- **Regla:** CMP-05; ADR-034 punto 8; `design.md` D3

### Requirement: La anulación se admite con maestros inactivos

La anulación DEBE admitirse aunque el proveedor, el producto o la presentación de la compra se hayan desactivado después de confirmarla, porque revierte una operación existente y no es una operación nueva (CAT-05, `design.md` D11).

#### Scenario: Producto desactivado después de la compra
- **GIVEN** una compra de `Vino A` y `Vino A` desactivado después
- **WHEN** se anula la compra
- **THEN** queda `ANULADA` con el egreso de `Vino A` registrado
- **Regla:** CAT-05; `design.md` D11

### Requirement: Anular una compra es una operación atómica

Todos los efectos de `COMPRA_ANULAR` DEBEN registrarse en una sola transacción o ninguno (INV-01), con las filas bloqueadas en el orden compra, `saldo_cuenta`, `costo_producto`, `stock_saldo` (`02` §7.3). Tras confirmar y anular una compra que se pudo recalcular, el stock de cada ubicación y el saldo del proveedor DEBEN quedar como antes de la compra (INV-12, INV-13).

#### Scenario: INV-01 — falla en la cuenta
- **GIVEN** una falla inyectada después del egreso de stock y antes del movimiento de cuenta
- **WHEN** se procesa la anulación
- **THEN** la compra sigue `CONFIRMADA` y no queda ningún egreso, historia de costo ni movimiento de cuenta de la anulación
- **Regla:** INV-01

#### Scenario: Propiedad — confirmar y anular deja todo como estaba
- **GIVEN** stock, promedio y saldo aleatorios válidos
- **WHEN** se confirma una compra aleatoria y se la anula sin movimientos intermedios
- **THEN** el stock por ubicación, el stock total y el saldo del proveedor vuelven exactamente a sus valores previos y, cuando el stock previo era mayor que cero, el promedio difiere del previo a lo sumo en `0.000001 × (stock previo + cantidad) / stock previo` (dos redondeos a 6 decimales, TR-03)
- **Regla:** INV-12; INV-13; CMP-06
