## ADDED Requirements

### Requirement: La entrega del día se procesa detrás de todo lo anterior del dispositivo

El lote DEBE aceptar `JORNADA_ENTREGAR` v1 en modo `OFFLINE` y procesarlo en su lugar por secuencia, como cualquier comando; un error transitorio de un comando anterior DEBE cortar el lote antes de la entrega, de modo que la entrega solo se procese cuando todo lo anterior del dispositivo ya tiene resultado (RUT-05, SYN-03; `design.md` D1). En modo `ONLINE` DEBE rechazarse con `MODO_NO_ADMITIDO_PARA_TIPO`.

#### Scenario: Entrega detrás de ventas y cobranzas
- **GIVEN** un lote con dos ventas (secuencias 10 y 11), una cobranza (12) y la entrega (13) de la jornada de Juan
- **WHEN** se procesa
- **THEN** las cuatro tienen resultado en ese orden y la jornada queda entregada con la secuencia 13
- **Regla:** RUT-05; SYN-03

#### Scenario: Error transitorio antes de la entrega
- **GIVEN** un lote donde la venta de secuencia 11 sufre un error transitorio agotado
- **WHEN** se procesa
- **THEN** la entrega no se procesa y la jornada sigue sin entrega
- **Regla:** RUT-05; `02` §6.4

#### Scenario: Un rechazo anterior no impide la entrega
- **GIVEN** un lote donde la venta de secuencia 11 vuelve rechazada
- **WHEN** se procesa
- **THEN** la entrega se procesa y la jornada queda entregada
- **Regla:** SYN-06; RUT-05

#### Scenario: Entrega en modo ONLINE
- **WHEN** llega un `JORNADA_ENTREGAR` en modo `ONLINE`
- **THEN** se rechaza con `MODO_NO_ADMITIDO_PARA_TIPO` sin cambios
- **Regla:** `02` §6.5

#### Scenario: Doble sincronización de la entrega
- **GIVEN** un lote con la entrega ya procesado
- **WHEN** el teléfono reenvía el mismo lote
- **THEN** cada comando devuelve su resultado original y la entrega no cambia
- **Regla:** SYN-02; INV-06
