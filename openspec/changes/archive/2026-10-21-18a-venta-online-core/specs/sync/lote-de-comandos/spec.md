## ADDED Requirements

### Requirement: VENTA_CONFIRMAR se acepta por el lote sin conexión

El catálogo de tipos DEBE declarar `VENTA_CONFIRMAR` con modos `ONLINE` y `OFFLINE`, `permiso_offline = VENDER` y la venta como operación observable, de modo que `PERMISO_REVOCADO` y `JORNADA_LIBERADA` del bus se anoten sobre la venta (ADR-052, `design.md` D1 del change 18a). Por REST DEBE seguir siendo solo `ONLINE`.

#### Scenario: Venta sin conexión de un vendedor sin el permiso
- **GIVEN** Juan, a quien le quitaron `VENDER` después de abrir su jornada
- **WHEN** el lote trae su venta en modo `OFFLINE` con su jornada
- **THEN** se acepta con `PERMISO_REVOCADO` anotada sobre la venta (permiso `VENDER`, motivo `PERMISO_QUITADO`)
- **Regla:** SYN-10; INV-17

#### Scenario: Jornada liberada
- **GIVEN** la jornada de Juan liberada por un Supervisor
- **WHEN** llega su venta sin conexión
- **THEN** se acepta con `JORNADA_LIBERADA` sobre la venta
- **Regla:** RUT-09

#### Scenario: Ubicación tomada al sincronizar
- **GIVEN** la ubicación de la jornada de Juan tomada al sincronizar (su jornada en `EN_RENDICION`, o liberada y retomada por otra)
- **WHEN** llega su venta sin conexión
- **THEN** se acepta con `UBICACION_TOMADA_AL_SINCRONIZAR` sobre la venta (junto a `JORNADA_LIBERADA` si corresponde) y no con `UBICACION_TOMADA`
- **Regla:** SYN-05; SYN-07; INV-17; STK-09

#### Scenario: Sin jornada
- **WHEN** llega una venta `OFFLINE` sin jornada en el sobre
- **THEN** se rechaza con `JORNADA_REQUERIDA` y el lote sigue
- **Regla:** SYN-10; SYN-06

#### Scenario: Doble envío
- **WHEN** el lote reenvía la misma venta con el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones
- **Regla:** INV-06; SYN-02
