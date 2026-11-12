## ADDED Requirements

### Requirement: Una venta registra su cobranza de origen VENTA

La cobranza de una venta DEBE registrarse dentro de la transacción de la venta con origen `VENTA` y la venta referenciada por una clave foránea compuesta (`organizacion_id`, `venta_id`); `origen = VENTA` si y solo si `venta_id` no es nulo. Por comando DEBE seguir sin poder registrarse una cobranza de origen `VENTA`, y `COBRANZA_ANULAR` DEBE seguir rechazándola con `COBRANZA_DE_VENTA` (su anulación es la de la venta, VTA-22, change 19) (ADR-052 punto 2, `design.md` D12 del change 18a).

#### Scenario: Cobranza con la venta
- **WHEN** se confirma una venta de `"80000.00"` con `"20000.00"` en efectivo
- **THEN** existe una cobranza `CONFIRMADA` de origen `VENTA` con esa venta, el mismo `occurred_at` y la misma jornada
- **Regla:** VTA-11; COB-01; CC-05

#### Scenario: La base exige que la venta exista
- **WHEN** se inserta por SQL una cobranza con un `venta_id` inexistente o de otra organización
- **THEN** la base la rechaza
- **Regla:** INV-02; `03` §12

#### Scenario: Por comando no hay cobranza de venta
- **WHEN** `COBRANZA_REGISTRAR` intenta indicar una venta
- **THEN** el campo no existe en el esquema y se rechaza (422)
- **Regla:** ADR-052

#### Scenario: No se anula sola
- **WHEN** se envía `COBRANZA_ANULAR` sobre la cobranza de una venta
- **THEN** se rechaza con `COBRANZA_DE_VENTA`
- **Regla:** COB-05; VTA-22
