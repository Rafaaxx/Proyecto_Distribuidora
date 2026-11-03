## ADDED Requirements

### Requirement: Anular una venta local es una sola transacción

Anular una venta en el teléfono DEBE escribir, en una sola transacción de la base local, la anulación (venta, motivo, observación, devolución, jornada, momento y `operation_id` propio), sus movimientos locales inversos y el comando `VENTA_ANULAR` en modo `OFFLINE` con la siguiente secuencia de la cola, y avanzar la última secuencia; si algo falla no DEBE quedar nada y la secuencia NO DEBE avanzar. Los movimientos inversos DEBEN ser: el ingreso de cada línea al stock en unidad base, el crédito del total en la cuenta del cliente y, si se devuelve lo cobrado, el débito del importe cobrado. Anular otra vez la misma venta NO DEBE crear otra anulación ni otro comando (`design.md` D4, D6).

#### Scenario: Anulación local
- **GIVEN** la venta V03-000142 a Kiosco La Esquina por $80.000 con 15 botellas de Vino A, sin cobro, confirmada en el teléfono con secuencia 7
- **WHEN** el vendedor la anula con el motivo "Error de carga"
- **THEN** quedan la anulación, un ingreso de 15 botellas, un crédito de $80.000 y el comando `VENTA_ANULAR` con secuencia 8, todo con el `operation_id` de la anulación
- **Regla:** VTA-24; INV-01; SYN-01

#### Scenario: Falla a mitad de la anulación
- **GIVEN** una venta local de la jornada
- **WHEN** la escritura del comando falla después de escribir los movimientos
- **THEN** no queda la anulación, ningún movimiento ni el comando, y la última secuencia no avanza
- **Regla:** INV-01

#### Scenario: Doble toque
- **GIVEN** una venta ya anulada en el teléfono
- **WHEN** se confirma otra vez su anulación
- **THEN** no se escribe nada nuevo y se muestra la anulación existente
- **Regla:** INV-06; SYN-02

#### Scenario: Anulación de una venta sin enviar
- **GIVEN** una venta «Sin enviar» con secuencia 7
- **WHEN** el vendedor la anula
- **THEN** la anulación queda con secuencia 8, detrás de la venta, y las dos se envían en ese orden
- **Regla:** SYN-03

### Requirement: La anulación local cuenta en el saldo y el stock locales

Los movimientos de una anulación local DEBEN contar en el saldo y el stock locales por la misma regla que una venta: desde que se confirma y hasta que un bootstrap con secuencia procesada mayor o igual que la suya la incluya. Una anulación «Rechazada» NO DEBE contar, salvo que su venta también esté «Rechazada»: entonces cuentan las dos y se compensan. Con devolución, el stock y el saldo locales DEBEN quedar como antes de la venta; sin devolución, el saldo DEBE diferir solo en lo cobrado (`design.md` D7).

#### Scenario: Stock después de anular
- **GIVEN** 63 botellas de Vino A en el bootstrap, una venta local de 15 y su anulación local
- **WHEN** el vendedor abre el producto en otra venta
- **THEN** el disponible es 63 botellas
- **Regla:** RUT-04; INV-19; VTA-21

#### Scenario: Crédito después de anular con devolución
- **GIVEN** un cliente con límite $200.000 y saldo $100.000 en el bootstrap, una venta local de $70.000 con $20.000 cobrados y su anulación con devolución
- **WHEN** se calcula su crédito
- **THEN** el saldo considerado es $100.000 y el disponible $100.000
- **Regla:** CRE-08; VTA-22; INV-19

#### Scenario: Crédito después de anular sin devolución
- **GIVEN** el mismo cliente y la misma venta, anulada sin devolución
- **WHEN** se calcula su crédito
- **THEN** el saldo considerado es $80.000: los $20.000 cobrados quedan a favor
- **Regla:** CRE-08; VTA-22; INV-19

#### Scenario: Venta incluida en el bootstrap y anulación pendiente
- **GIVEN** una venta de 15 botellas con secuencia 7 aceptada, un bootstrap con 48 botellas y secuencia procesada 7, y su anulación local con secuencia 8 sin enviar
- **WHEN** se calcula el stock
- **THEN** el disponible es 63 botellas
- **Regla:** CRE-08; RUT-04; SYN-11

#### Scenario: Anulación incluida en el bootstrap
- **GIVEN** la venta (secuencia 7) y su anulación (secuencia 8) aceptadas, y un bootstrap con 63 botellas y secuencia procesada 8
- **WHEN** se calcula el stock
- **THEN** el disponible es 63 botellas, no 78
- **Regla:** CRE-08; INV-06

#### Scenario: Anulación rechazada
- **GIVEN** una venta aceptada de 15 botellas y su anulación rechazada con `VENTA_YA_ANULADA`, con 63 botellas en el bootstrap que ya incluye la venta y la anulación de administración
- **WHEN** se calcula el stock
- **THEN** la anulación rechazada no cuenta y el disponible es 63 botellas
- **Regla:** SYN-06; CRE-08

#### Scenario: Venta y anulación rechazadas
- **GIVEN** una venta de 15 botellas rechazada y su anulación rechazada con `VENTA_INEXISTENTE`
- **WHEN** se calcula el stock
- **THEN** cuentan las dos y se compensan: el disponible es el del bootstrap
- **Regla:** SYN-06; SYN-09; RUT-04

#### Scenario: Doble sincronización
- **GIVEN** una anulación aceptada e incluida en el bootstrap
- **WHEN** se sincroniza otra vez y el servidor devuelve el mismo resultado
- **THEN** el saldo y el stock locales no cambian
- **Regla:** INV-06; SYN-02
