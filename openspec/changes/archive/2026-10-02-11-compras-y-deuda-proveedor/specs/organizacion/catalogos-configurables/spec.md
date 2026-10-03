## ADDED Requirements

### Requirement: Los medios de pago y los motivos activos se consultan por API

El sistema DEBE exponer, para usuarios autenticados de la organización, la lista de medios de pago activos (con `requiere_referencia`) y la de motivos activos filtrada por un ámbito obligatorio de la lista cerrada, sin datos de otra organización. Un ámbito fuera de la lista DEBE responder 422 (`AMBITO_INVALIDO`) (`design.md` D2 y D8 del change 11).

#### Scenario: Motivos de anulación de compra
- **GIVEN** la organización A con motivos de `AJUSTE_STOCK` y de `ANULACION_COMPRA`
- **WHEN** se piden los motivos del ámbito `ANULACION_COMPRA`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** `03` §4; TR-09; INV-21

#### Scenario: Medios de pago de la organización
- **WHEN** un usuario de A pide los medios de pago
- **THEN** recibe solo los activos de A con su indicador de referencia obligatoria
- **Regla:** `01` §4; TR-08

#### Scenario: Ámbito inválido
- **WHEN** se piden los motivos del ámbito `CUALQUIERA`
- **THEN** la respuesta es 422 con `AMBITO_INVALIDO`
- **Regla:** `03` §4 (lista cerrada de `ambito`)

### Requirement: Toda organización tiene motivos de anulación de compra

Toda organización DEBE contar con motivos activos del ámbito `ANULACION_COMPRA` para poder anular compras (CMP-05): la siembra de una organización nueva los crea y la migración del change 11 los agrega a las organizaciones existentes que no tengan ninguno, sin duplicar (`design.md` D8 del change 11).

#### Scenario: Organización nueva
- **WHEN** se siembra una organización nueva
- **THEN** tiene los motivos de anulación de compra aprobados en `design.md` D8 (recomendados: "Error de carga", "Devolución al proveedor", "Otro")
- **Regla:** CMP-05; TR-09

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 11 sin motivos de `ANULACION_COMPRA`
- **WHEN** se aplica la migración
- **THEN** tiene esos motivos una sola vez, y aplicar `downgrade` y `upgrade` de nuevo no los duplica
- **Regla:** CMP-05; `03` §17
