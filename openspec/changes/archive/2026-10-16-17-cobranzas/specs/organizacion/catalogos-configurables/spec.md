## ADDED Requirements

### Requirement: Toda organización tiene motivos de anulación de cobranza

Toda organización DEBE contar con motivos activos del ámbito `ANULACION_COBRANZA` para poder anular cobranzas (COB-05): la siembra de una organización nueva los crea y la migración del change 17 los agrega a las organizaciones existentes que no tengan ninguno, sin duplicar (`design.md` D6 del change 17). Los motivos activos de ese ámbito DEBEN poder leerse por API con cualquier sesión.

#### Scenario: Organización nueva
- **WHEN** se siembra una organización nueva
- **THEN** tiene los motivos de anulación de cobranza aprobados en `design.md` D6 (recomendados: "Error de carga", "Pago rechazado o no acreditado", "Otro")
- **Regla:** COB-05; TR-09

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 17 sin motivos de `ANULACION_COBRANZA`
- **WHEN** se aplica la migración
- **THEN** tiene esos motivos una sola vez, y aplicar `downgrade` y `upgrade` de nuevo no los duplica
- **Regla:** COB-05; `04` §2.1 punto 4

#### Scenario: Motivos de anulación de cobranza por API
- **GIVEN** la organización A con motivos de `ANULACION_PAGO` y de `ANULACION_COBRANZA`
- **WHEN** se piden los motivos del ámbito `ANULACION_COBRANZA`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** COB-05; TR-09; INV-21
