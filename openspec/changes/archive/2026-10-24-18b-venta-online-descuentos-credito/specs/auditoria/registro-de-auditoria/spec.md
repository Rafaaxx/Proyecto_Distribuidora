## ADDED Requirements

### Requirement: El descuento manual y la autorización de crédito de una venta quedan auditados

Además de la fila del comando, una venta con descuento manual DEBE dejar una fila de auditoría del descuento manual (porcentaje máximo, tope aplicado, resolución, motivo y autorizador), y una venta cuya resolución de crédito no es `SIN_EXCESO` DEBE dejar una fila de autorización de crédito (el snapshot y el autorizador), las dos con el `operation_id` de la venta. Ninguna fila DEBE contener el PIN. Una venta rechazada NO DEBE dejar ninguna de las dos.

#### Scenario: Venta con descuento y crédito autorizados por personas distintas

- **GIVEN** una venta con 10 % autorizado por Marta y exceso autorizado por Luis
- **WHEN** se confirma
- **THEN** quedan una fila de descuento manual con Marta y una de autorización de crédito con Luis, con el mismo `operation_id`
- **Regla:** AUD-01; AUD-02; DSC-06; CRE-05

#### Scenario: Venta sin descuento manual ni exceso

- **WHEN** se confirma una venta sin descuento manual y sin exceso
- **THEN** solo queda la fila del comando
- **Regla:** AUD-01

#### Scenario: Venta sin conexión

- **GIVEN** una venta sin conexión con descuento manual y exceso de crédito autorizados por Marta
- **WHEN** se sincroniza
- **THEN** quedan las mismas filas de descuento manual y de autorización de crédito, con `modo = OFFLINE` en el dato posterior, la resolución que declaró el dispositivo y el tope vigente al sincronizar
- **Regla:** AUD-01; AUD-02; SYN-05

#### Scenario: Venta rechazada

- **WHEN** una venta se rechaza por `AUTORIZACION_REQUERIDA`
- **THEN** no queda ninguna fila de descuento manual ni de crédito
- **Regla:** AUD-01; INV-01
