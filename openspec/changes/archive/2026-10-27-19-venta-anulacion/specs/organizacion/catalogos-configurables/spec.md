## ADDED Requirements

### Requirement: Toda organización tiene motivos de anulación de venta

Toda organización DEBE contar con motivos activos del ámbito `ANULACION_VENTA` para poder anular ventas (VTA-20): la siembra de una organización nueva los crea y la migración del change 19 los agrega a las organizaciones existentes que no tengan ninguno, sin duplicar. Los motivos activos de ese ámbito DEBEN poder leerse por API con cualquier sesión (`design.md` D12).

#### Scenario: Organización nueva
- **WHEN** se siembra una organización nueva
- **THEN** tiene los motivos de anulación de venta aprobados en `design.md` D12 (recomendados: "Error de carga", "Devolución del cliente", "Otro")
- **Regla:** VTA-20; TR-09

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 19 sin motivos de `ANULACION_VENTA`
- **WHEN** se aplica la migración
- **THEN** tiene esos motivos una sola vez, y aplicar `downgrade` y `upgrade` de nuevo no los duplica
- **Regla:** VTA-20; `04` §2.1 punto 4

#### Scenario: Motivos de anulación de venta por API
- **GIVEN** la organización A con motivos de `ANULACION_COBRANZA` y de `ANULACION_VENTA`
- **WHEN** se piden los motivos del ámbito `ANULACION_VENTA`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** VTA-20; TR-09; INV-21
