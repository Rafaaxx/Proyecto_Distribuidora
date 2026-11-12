## ADDED Requirements

### Requirement: La nota de una venta del teléfono se arma con sus datos congelados y sin señal

Al confirmar una venta en `/ruta`, el teléfono DEBE congelar en la venta local todos los datos que la nota muestra (organización, cliente, número, fecha y hora, vendedor, modo impositivo, líneas con sus nombres e importes, totales, cobranza con sus medios y, si corresponde, el saldo resultante) y DEBE generar la nota con la misma función de armado que la administración, sin conexión. Una reimpresión DEBE ser idéntica a la original aunque un bootstrap posterior cambie los datos maestros (`design.md` D15; ADR-059).

#### Scenario: Compartir sin señal
- **GIVEN** `vendedor` con la red cortada y la venta V03-000142 recién confirmada, en un teléfono que comparte archivos
- **WHEN** toca "Compartir nota"
- **THEN** se abre el menú de compartir con `nota-de-venta-V03-000142.pdf`
- **Regla:** VTA-13; `00` §9 criterio 7

#### Scenario: Reimpresión tras un bootstrap
- **GIVEN** la venta V03-000142 de "Kiosco La Esquina" y un bootstrap posterior que cambió la razón social del cliente
- **WHEN** el vendedor descarga otra vez la nota desde "Ventas de hoy"
- **THEN** la nota muestra la razón social del momento de la venta
- **Regla:** VTA-13; ADR-059

#### Scenario: Saldo en la nota
- **GIVEN** una organización con "mostrar saldo" activo y una venta de $80.000 con $20.000 cobrados a un cliente con saldo considerado de $150.000
- **WHEN** se genera la nota
- **THEN** muestra un saldo de $210.000,00
- **Regla:** VTA-13; CRE-02

#### Scenario: Consumidor final
- **GIVEN** "mostrar saldo" activo y una venta al consumidor final
- **WHEN** se genera la nota
- **THEN** dice "Consumidor final" y no muestra saldo
- **Regla:** VTA-13
