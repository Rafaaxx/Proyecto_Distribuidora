## ADDED Requirements

### Requirement: Las pantallas de ruta explican la anulación y la jornada no abierta

Las pantallas de `/ruta` DEBEN ofrecer ayuda en «Anular venta», en el estado «Rechazada» de una anulación y en el aviso de la jornada no abierta; la pantalla de anulación DEBE reutilizar las ayudas del motivo, de la devolución y del consumidor final de la anulación con conexión. Las ayudas del stock, del crédito, de «Sincronizar» y de la sección de observaciones y rechazos DEBEN nombrar también las anulaciones. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D12).

#### Scenario: Anular venta
- **WHEN** se abre el "(?)" de «Anular venta» en el teléfono
- **THEN** explica que deja sin efecto una venta de la jornada también sin señal, que la mercadería vuelve al vehículo y la cuenta del cliente se acredita, que es entera y una sola vez y que se envía como las ventas
- **Regla:** VTA-20; VTA-21; VTA-24

#### Scenario: Anulación rechazada
- **WHEN** se abre el "(?)" del estado «Rechazada» de una anulación
- **THEN** explica que el motivo está en el detalle, que la venta sigue vigente y el teléfono vuelve a descontarla, que no se reenvía sola y que hay que avisar a administración
- **Regla:** SYN-06; SYN-09; VTA-24

#### Scenario: Jornada no abierta
- **WHEN** se abre el "(?)" del aviso de la jornada no abierta
- **THEN** explica que el sistema avisó que la jornada ya no está abierta, que no se puede vender ni anular, que lo vendido se sigue enviando y que para seguir hay que abrir una jornada nueva con señal
- **Regla:** RUT-09; RUT-03

#### Scenario: Stock y crédito
- **WHEN** se abre el "(?)" del stock o del crédito en el teléfono
- **THEN** nombran lo anulado desde el teléfono además de lo vendido y cobrado
- **Regla:** RUT-04; CRE-08; VTA-24

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva o revisada existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
