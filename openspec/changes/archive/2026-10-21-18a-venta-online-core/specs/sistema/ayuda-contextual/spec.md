## ADDED Requirements

### Requirement: Las pantallas de venta explican sus reglas

"Nueva venta" DEBE ofrecer ayuda en la carga de cajas y unidades, en el precio, en la elección de otra lista o versión, en la cobranza, en el consumidor final, en el stock y en el número; el detalle, en el costo (solo con `VER_COSTOS`) y en las observaciones, con un tema "Ver más" `ventas-observaciones`. Los textos DEBEN vivir en el archivo único, citar su regla y seguir el estilo de ADR-051 y el aprobado en el change 16b (`design.md` D22 del change 18a).

#### Scenario: Cajas y unidades
- **GIVEN** la pantalla "Nueva venta"
- **WHEN** se abre el "(?)" de la carga de cajas y unidades
- **THEN** explica que se cobra en proporción al precio de la caja, con el ejemplo "2 cajas + 3 botellas de Vino A (caja x6 a $12.500) = 15 botellas → $31.250"
- **Regla:** CAT-07; VTA-02; PRC-22

#### Scenario: Cobranza
- **WHEN** se abre el "(?)" de la cobranza
- **THEN** explica que puede ser nada, una parte, todo o más, con el ejemplo "venta de $80.000 con $20.000 en efectivo y un saldo de $150.000 → queda debiendo $210.000"
- **Regla:** VTA-11; CC-05

#### Scenario: Otra lista o versión
- **WHEN** quien tiene `USAR_LISTA_ANTERIOR` abre el "(?)" de la elección de lista
- **THEN** explica que pide permiso y motivo y que queda registrado quién lo hizo
- **Regla:** PRC-21; AUD-01

#### Scenario: Observaciones de una venta
- **GIVEN** el detalle de una venta con `STOCK_NEGATIVO`
- **WHEN** se abre el "(?)" de las observaciones
- **THEN** explica que la venta se tomó igual porque la mercadería ya se entregó y lleva al tema "Ver más" con el significado de cada aviso
- **Regla:** SYN-05; SYN-07; STK-06

#### Scenario: Trazabilidad
- **WHEN** corre la prueba de trazabilidad de la ayuda
- **THEN** toda clave `ventas.*` usada existe y todo ID citado existe en `01-dominio.md` o en `docs/adr/`
- **Regla:** ADR-051
