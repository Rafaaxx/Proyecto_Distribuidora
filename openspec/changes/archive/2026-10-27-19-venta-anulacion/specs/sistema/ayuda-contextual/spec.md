## ADDED Requirements

### Requirement: La anulación de una venta explica sus reglas

El diálogo "Anular venta" y el bloque "Anulación" del detalle DEBEN ofrecer ayuda en la anulación, en la devolución del dinero, en el motivo, en el consumidor final, en la ubicación a la que vuelve la mercadería y, solo con `VER_COSTOS`, en el costo de lo que vuelve. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051, con los textos que apruebe el usuario (`design.md` D18). El texto de la anulación de cobranzas DEBE decir que el cobro de una venta se anula anulando la venta.

#### Scenario: Devolución del dinero
- **WHEN** se abre el "(?)" de "¿Devolvés lo que cobraste?"
- **THEN** explica las dos opciones (con devolución el cobro se anula y la cuenta queda como antes de la venta; sin devolución lo pagado le queda a favor), sin ejemplo numérico
- **Regla:** VTA-22; COB-05

#### Scenario: Ubicación tomada
- **WHEN** se abre el "(?)" de adónde vuelve la mercadería
- **THEN** explica que vuelve a la ubicación de donde salió y que, si otra jornada la tiene, la anula quien puede mover una ubicación tomada
- **Regla:** VTA-21; STK-09

#### Scenario: Costo solo con permiso
- **WHEN** un usuario sin `VER_COSTOS` abre el diálogo
- **THEN** no ve el "(?)" del costo de lo que vuelve
- **Regla:** CST-11; `01` §19

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
