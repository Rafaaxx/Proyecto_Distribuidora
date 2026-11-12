## ADDED Requirements

### Requirement: La cuarentena se revisa y se resuelve sin reenviarse

Un comando en cuarentena DEBE poder revisarse con `REVISAR_OBSERVACIONES` en la lista de rechazos (origen «Teléfono dado de baja») y resolverse con `RECHAZO_RESOLVER`: queda con el usuario que lo revisó, el momento, un comentario de 1 a 500 caracteres y, opcional, el vínculo a la operación cargada con conexión que lo corrige. Un comando en cuarentena NO DEBE reenviarse, reprocesarse ni ejecutarse nunca, ni por su teléfono ni desde `/admin`; la corrección es una operación nueva (SYN-06, SYN-08, `design.md` D7).

#### Scenario: Revisar la venta de un teléfono dado de baja
- **GIVEN** una venta de Juan en cuarentena porque su teléfono se dio de baja
- **WHEN** la Supervisora la resuelve con un comentario y el vínculo a la venta que cargó con conexión
- **THEN** la cuarentena queda revisada con su usuario, momento, comentario y vínculo
- **AND** no se crea ninguna venta por la cuarentena
- **Regla:** SYN-06; SYN-08

#### Scenario: El teléfono dado de baja reenvía
- **GIVEN** una cuarentena ya resuelta
- **WHEN** el teléfono dado de baja vuelve a enviar el mismo comando
- **THEN** se responde RECHAZADO con `DISPOSITIVO_REVOCADO`, sigue habiendo un solo registro y su resolución no cambia
- **Regla:** SYN-06; INV-06

#### Scenario: Ya revisada
- **WHEN** se intenta resolver una cuarentena ya revisada
- **THEN** se rechaza con `RECHAZO_YA_RESUELTO` (409)
- **Regla:** `01` §18

#### Scenario: Cuarentena de otra organización
- **WHEN** un usuario de la organización A intenta resolver una cuarentena de la organización B
- **THEN** responde 404
- **Regla:** INV-21

#### Scenario: Solo cambian las columnas de la revisión
- **WHEN** la aplicación intenta cambiar el contenido, el tipo o el motivo de una cuarentena
- **THEN** la base lo impide
- **Regla:** INV-05; SYN-06 (no se pierden)
