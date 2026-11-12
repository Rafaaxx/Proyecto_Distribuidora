## ADDED Requirements

### Requirement: Las pantallas de ruta explican los disponibles locales y las observaciones

Las pantallas de `/ruta` DEBEN ofrecer ayuda en la sección de observaciones y rechazos de «Sincronización» y del detalle de la venta, y en el stock y el crédito locales de Stock, Productos, la ficha del cliente y Vender. Las ayudas del stock y del crédito DEBEN decir que se parte de la última actualización de datos y que lo que el sistema ya tenía no se cuenta dos veces; la de «Rechazada», dónde se ve el motivo y que el teléfono sigue descontando la venta; la de «Con observaciones», dónde se ve lo anotado. Los textos DEBEN vivir en el archivo único, citar su regla o ADR, seguir el estilo de ADR-051 y no llevar ejemplos, con los textos que apruebe el usuario (`design.md` D9).

#### Scenario: Observaciones y rechazos
- **WHEN** se abre el "(?)" de la sección de observaciones y rechazos
- **THEN** explica qué muestra, que administración revisa las observaciones sin que el vendedor haga nada y que una rechazada no se reenvía sola
- **Regla:** SYN-04; SYN-07; SYN-08; SYN-09

#### Scenario: Stock del vehículo
- **WHEN** se abre el "(?)" del stock en Stock, Productos o Vender
- **THEN** explica que parte de la última actualización, resta lo vendido desde el teléfono después, no descuenta dos veces lo ya enviado y bloquea salvo el permiso de stock negativo
- **Regla:** STK-06; RUT-04; ADR-065

#### Scenario: Crédito del cliente
- **WHEN** se abre el "(?)" del crédito en la ficha o en Vender
- **THEN** explica que parte de la deuda de la última actualización, suma lo vendido y resta lo cobrado desde el teléfono después y no cuenta dos veces lo ya enviado
- **Regla:** CRE-08; CRE-09; ADR-065

#### Scenario: Rechazada
- **WHEN** se abre el "(?)" del estado «Rechazada»
- **THEN** explica que fue por un problema de datos, que el motivo está en el detalle, que sigue guardada y no se reenvía sola, que el teléfono la sigue descontando y que hay que avisar a administración
- **Regla:** SYN-06; SYN-09; ADR-065

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave nueva o revisada existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
