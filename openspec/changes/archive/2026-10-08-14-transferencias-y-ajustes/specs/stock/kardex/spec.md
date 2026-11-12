## ADDED Requirements

### Requirement: El kardex muestra el motivo, la operación y su estado en cada movimiento

Cada movimiento del kardex DEBE traer `origen_tipo` y `origen_id` (la transferencia o el ajuste que lo originó) y, si es de tipo `AJUSTE`, el nombre de su motivo (`design.md` D7). Un movimiento con origen `TRANSFERENCIA` o `AJUSTE_STOCK` DEBE traer además el estado de esa operación (`CONFIRMADA` o `ANULADA`), y los movimientos inversos de una anulación DEBEN distinguirse por su origen `ANULACION_TRANSFERENCIA` o `ANULACION_AJUSTE_STOCK`, con el mismo `origen_id` que los originales (`design.md` D5, D5.1). Esos datos NO DEBEN exponer costos ni datos de otra organización, y la lectura sigue exigiendo `TRANSFERIR_STOCK` (ADR-036).

#### Scenario: Ajuste en el kardex

- **GIVEN** un ajuste de −6 de Vino A en el depósito por "Rotura"
- **WHEN** un Vendedor consulta el kardex de Vino A en el depósito
- **THEN** el movimiento aparece como `AJUSTE` −6 con el motivo "Rotura", `origen_tipo` `AJUSTE_STOCK`, el id del ajuste y estado `CONFIRMADA`, sin costo
- **Regla:** STK-08; `01` §19

#### Scenario: Transferencia en el kardex de las dos ubicaciones

- **GIVEN** una transferencia de 48 de Vino A del depósito a "Camioneta 1"
- **WHEN** se consulta el kardex de Vino A en cada ubicación
- **THEN** el depósito muestra `TRANSFERENCIA_SALIDA` −48 y la camioneta `TRANSFERENCIA_ENTRADA` +48, ambos con `origen_tipo` `TRANSFERENCIA` y el mismo `origen_id`, sin motivo
- **Regla:** STK-07; STK-04

#### Scenario: Transferencia anulada en el kardex

- **GIVEN** una transferencia de 60 de Vino A del depósito a "Camioneta 1", anulada
- **WHEN** se consulta el kardex de Vino A en "Camioneta 1"
- **THEN** aparecen `TRANSFERENCIA_ENTRADA` +60 con origen `TRANSFERENCIA` y estado `ANULADA`, y `TRANSFERENCIA_SALIDA` −60 con origen `ANULACION_TRANSFERENCIA`, ambos con el mismo `origen_id`, y el saldo acumulado vuelve al anterior
- **Regla:** STK-04; TR-06; `design.md` D5.1

#### Scenario: Ajuste anulado en el kardex

- **GIVEN** el ajuste de −6 por "Rotura" anulado con "Error de carga"
- **WHEN** se consulta el kardex de Vino A en el depósito
- **THEN** aparecen el `AJUSTE` −6 con el motivo "Rotura" y estado `ANULADA`, y un `AJUSTE` +6 con origen `ANULACION_AJUSTE_STOCK` y el motivo "Error de carga"
- **Regla:** STK-08; TR-06; `design.md` D5.1
