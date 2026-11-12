## ADDED Requirements

### Requirement: El teléfono muestra que administración resolvió un rechazo

Una venta, anulación o cobranza «Rechazada» cuyo `operation_id` está en los rechazos resueltos del último bootstrap DEBE mostrar, junto a «Rechazada», «Resuelta por administración» en «Ventas de hoy», «Cobranzas de hoy», el detalle y «Sincronización», también sin señal. No se reenvía ni cambia su estado de envío (SYN-09, `design.md` D8).

#### Scenario: Rechazo resuelto
- **GIVEN** la cobranza rechazada de Juan, resuelta en la oficina
- **WHEN** Juan actualiza los datos y abre «Cobranzas de hoy»
- **THEN** ve «Rechazada» y «Resuelta por administración»
- **Regla:** SYN-09

#### Scenario: Sin señal después de actualizar
- **GIVEN** la marca ya recibida
- **WHEN** Juan recarga la aplicación sin señal
- **THEN** la sigue viendo
- **Regla:** SYN-09; ADR-062

#### Scenario: Sigue sin reenviarse
- **WHEN** Juan toca «Sincronizar»
- **THEN** la operación rechazada resuelta no se envía
- **Regla:** SYN-09; INV-06
