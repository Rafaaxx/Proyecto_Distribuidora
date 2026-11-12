## MODIFIED Requirements

### Requirement: Un motivo pertenece a un ámbito de la lista cerrada
Un motivo DEBE declarar su ámbito dentro de la lista cerrada `AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`, además de nombre y marca de actividad. Los motivos DEBEN poder listarse filtrados por ámbito (`03` §4). El ámbito `ANULACION_PAGO` es el de la anulación de pagos a proveedores (PAG-03, `design.md` D1 del change 12).

#### Scenario: Los motivos se listan por ámbito
- **GIVEN** la organización inicial con sus motivos de ajuste de stock sembrados
- **WHEN** se listan los motivos del ámbito `AJUSTE_STOCK`
- **THEN** el resultado contiene los seis motivos de ajuste y ninguno de otro ámbito
- **Regla:** `01` §4, `03` §4 (`motivo.ambito`)

#### Scenario: Un ámbito fuera de la lista se rechaza
- **GIVEN** la operación de alta de un motivo
- **WHEN** se la invoca con un ámbito que no está en la lista cerrada
- **THEN** falla con un error explícito y no crea el motivo
- **Regla:** `03` §4 (lista cerrada de `ambito`)

#### Scenario: Motivos de anulación de pago por API
- **GIVEN** la organización A con motivos de `ANULACION_COMPRA` y de `ANULACION_PAGO`
- **WHEN** se piden los motivos del ámbito `ANULACION_PAGO`
- **THEN** se devuelven solo los activos de ese ámbito de A
- **Regla:** PAG-03; TR-09; INV-21

## ADDED Requirements

### Requirement: Toda organización tiene motivos de anulación de pago

Toda organización DEBE contar con motivos activos del ámbito `ANULACION_PAGO` para poder anular pagos a proveedores (PAG-03): la siembra de una organización nueva los crea y la migración del change 12 los agrega a las organizaciones existentes que no tengan ninguno, sin duplicar (`design.md` D1 del change 12).

#### Scenario: Organización nueva
- **WHEN** se siembra una organización nueva
- **THEN** tiene los motivos de anulación de pago aprobados en `design.md` D1 (recomendados: "Error de carga", "Pago rechazado o devuelto", "Otro")
- **Regla:** PAG-03; TR-09

#### Scenario: Organización existente
- **GIVEN** una organización creada antes del change 12 sin motivos de `ANULACION_PAGO`
- **WHEN** se aplica la migración
- **THEN** tiene esos motivos una sola vez, y aplicar `downgrade` y `upgrade` de nuevo no los duplica
- **Regla:** PAG-03; `04` §2.1 punto 4

#### Scenario: Ámbito desconocido en la base
- **WHEN** se intenta insertar un motivo con un ámbito fuera de la lista cerrada directamente en la base
- **THEN** la restricción de la base lo rechaza
- **Regla:** `03` §4 (lista cerrada de `ambito`)
