## ADDED Requirements

### Requirement: El resultado de una cobranza se escribe en el teléfono

El resultado del servidor para un `COBRANZA_REGISTRAR` DEBE cambiar, en la misma transacción que el resto de los resultados del lote, el estado de envío de la cobranza (por su `operation_id`) y el de su comando, con las observaciones recibidas o el código de rechazo. NO DEBE tocar ninguna venta. Una `JORNADA_LIBERADA` sobre la cobranza DEBE marcar la jornada como liberada, igual que sobre una venta (`design.md` D5, D7).

#### Scenario: Cobranza aceptada
- **GIVEN** una cobranza «Sin enviar»
- **WHEN** el servidor responde `ACEPTADO`
- **THEN** la cobranza queda «Enviada» y su comando `ACEPTADO`; ninguna venta cambia
- **Regla:** SYN-04; SYN-09

#### Scenario: Cobranza con observaciones
- **WHEN** el servidor responde `ACEPTADO_CON_OBSERVACIONES` con `MEDIO_INACTIVO` sobre la línea 1
- **THEN** la cobranza queda «Con observaciones» y la observación queda guardada en su comando
- **Regla:** SYN-07; SYN-04

#### Scenario: Cobranza rechazada
- **WHEN** el servidor responde `RECHAZADO` con `RECURSO_NO_ENCONTRADO`
- **THEN** la cobranza queda «Rechazada» con el código, no se reenvía sola y se avisa
- **Regla:** SYN-06; SYN-09

#### Scenario: Jornada liberada
- **WHEN** la cobranza vuelve con `JORNADA_LIBERADA`
- **THEN** el teléfono guarda que su jornada fue liberada y corta «Vender», «Anular venta» y «Cobrar»
- **Regla:** RUT-09; SYN-07

#### Scenario: Falla al escribir el resultado
- **WHEN** la escritura falla a mitad del lote
- **THEN** no cambia ningún estado y los comandos siguen «Sin enviar»
- **Regla:** INV-01

#### Scenario: Reenvío
- **WHEN** el servidor devuelve otra vez el mismo resultado de una cobranza ya escrita
- **THEN** el estado y las observaciones no cambian ni se duplican
- **Regla:** INV-06
