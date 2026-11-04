## ADDED Requirements

### Requirement: La cobranza del teléfono se acepta por el lote con el contrato fijado

El sobre de `COBRANZA_REGISTRAR` v1 en modo `OFFLINE` que arma el teléfono DEBE coincidir con un fixture de contrato compartido que el esquema del lote acepta y que el teléfono reproduce igual: identificador de la cobranza, cliente, importe como string, de 1 a 20 medios (medio, importe como string y referencia o nula) y la observación o nula, con la jornada de la sesión en el sobre. El servidor DEBE procesarlo con las reglas vigentes de la cobranza sin conexión (ADR-052), sin cambios: rechaza solo lo malformado, lo inexistente o ajeno, el identificador repetido y la jornada del sobre inválida, y acepta todo lo demás con las observaciones que correspondan. Un comando que el teléfono encoló después de una venta del mismo cliente DEBE procesarse después de ella (`design.md` D2).

#### Scenario: Sobre del teléfono aceptado
- **GIVEN** `vendedor` con `REGISTRAR_COBRANZA` y su jornada `ABIERTA` en su teléfono, y Kiosco La Esquina con saldo `"150000.00"`
- **WHEN** el lote trae la cobranza del fixture de `"50000.00"`, con `"30000.00"` en efectivo y `"20000.00"` por transferencia con referencia `"0042"`
- **THEN** responde `ACEPTADO`, el saldo del cliente queda en `"100000.00"` y la cobranza lleva la jornada del sobre
- **Regla:** COB-01; COB-02; COB-03; SYN-01; SYN-05

#### Scenario: Venta y cobranza en el mismo lote
- **GIVEN** un lote con una venta a Kiosco La Esquina (secuencia 7) y una cobranza al mismo cliente (secuencia 8)
- **WHEN** el servidor procesa el lote
- **THEN** procesa la venta y después la cobranza, y el saldo refleja las dos
- **Regla:** SYN-03; CC-05

#### Scenario: Cliente inexistente
- **WHEN** el lote trae una cobranza `OFFLINE` de un cliente que no existe en la organización
- **THEN** se rechaza como dependencia inexistente, sin efectos, y el lote sigue con el ítem siguiente
- **Regla:** SYN-06; INV-21; `02` §6.4

#### Scenario: Medios que no suman el importe
- **WHEN** el lote trae una cobranza `OFFLINE` de `"50000.00"` cuyos medios suman `"49000.00"`
- **THEN** se rechaza con `MEDIOS_NO_SUMAN_IMPORTE` y no queda ningún efecto
- **Regla:** INV-08; SYN-06

#### Scenario: Doble envío
- **WHEN** el lote reenvía la misma cobranza con el mismo `operation_id` y el mismo contenido
- **THEN** devuelve el resultado original con las mismas observaciones y el saldo baja una sola vez
- **Regla:** INV-06; SYN-02

#### Scenario: Lista cerrada de rechazos de la cobranza
- **GIVEN** el fixture de códigos de sincronización
- **WHEN** se recorren los rechazos que el bus y la cobranza pueden devolver a una cobranza `OFFLINE`
- **THEN** cada uno está en la lista de rechazos de la cobranza del fixture, y cada código de la lista existe en el servidor
- **Regla:** SYN-06; SYN-07
