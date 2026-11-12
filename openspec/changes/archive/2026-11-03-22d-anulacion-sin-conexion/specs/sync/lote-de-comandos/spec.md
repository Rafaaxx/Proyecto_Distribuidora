## ADDED Requirements

### Requirement: VENTA_ANULAR se acepta por el lote sin conexión

El catálogo de tipos DEBE declarar `VENTA_ANULAR` con modos `ONLINE` y `OFFLINE`, el permiso `ANULAR_VENTA` y la venta como operación observable, de modo que `PERMISO_REVOCADO` y `JORNADA_LIBERADA` del bus se anoten sobre la venta anulada. Por REST (`POST /api/v1/ventas/{venta_id}/anulacion`) DEBE seguir siendo solo `ONLINE`. Las reglas de la jornada del sobre (`JORNADA_REQUERIDA`, `JORNADA_AJENA`, `JORNADA_INEXISTENTE`) DEBEN valer igual que para la venta (`design.md` D1, D4).

#### Scenario: Anulación sin conexión por el lote
- **GIVEN** `sup01` con `ANULAR_VENTA` y su jornada `ABIERTA` en su teléfono
- **WHEN** el lote trae `VENTA_ANULAR` en modo `OFFLINE` con su jornada
- **THEN** el ítem se procesa con el handler de la anulación y responde `ACEPTADO` o `ACEPTADO_CON_OBSERVACIONES`
- **Regla:** VTA-24; `02` §6.5

#### Scenario: Por REST sigue siendo con conexión
- **WHEN** llega `POST /api/v1/ventas/{venta_id}/anulacion`
- **THEN** el sobre es `ONLINE` y rige la regla de toma de siempre
- **Regla:** `02` §6.5; STK-09

#### Scenario: Sin jornada
- **WHEN** llega una anulación `OFFLINE` sin jornada en el sobre
- **THEN** se rechaza con `JORNADA_REQUERIDA` y el lote sigue
- **Regla:** SYN-10; SYN-06

#### Scenario: Jornada de otro teléfono
- **WHEN** llega una anulación `OFFLINE` con la jornada de otro usuario o de otro dispositivo
- **THEN** se rechaza con `JORNADA_AJENA` y el lote sigue
- **Regla:** SYN-10; SYN-06

#### Scenario: Un rechazo no corta el lote
- **GIVEN** un lote con una anulación de una venta ya anulada y, después, una venta nueva
- **WHEN** el servidor procesa el lote
- **THEN** la anulación es `RECHAZADO` con `VENTA_YA_ANULADA` y la venta nueva se procesa igual
- **Regla:** `02` §6.4; SYN-04

#### Scenario: Doble envío
- **WHEN** el lote reenvía la misma anulación con el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones, sin efectos nuevos
- **Regla:** INV-06; SYN-02
