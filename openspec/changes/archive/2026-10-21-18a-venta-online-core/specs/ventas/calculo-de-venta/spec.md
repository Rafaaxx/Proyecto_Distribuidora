## Purpose

Definir el motor de cálculo de la venta, compartido por el servidor y el dispositivo: orquesta el bruto de línea (PRC-22), los descuentos (DSC-05) y los totales (VTA-04, INV-14) con casos de prueba únicos. Escrita con las opciones recomendadas (A) de `design.md` D13 y D14, pendientes de aprobación.

## ADDED Requirements

### Requirement: El motor de venta calcula bruto, descuentos, neto, IVA y total

El motor DEBE ser una función pura con la misma entrada y salida en Python y TypeScript: por línea calcula el bruto con PRC-22, aplica los descuentos que entrega el motor de descuentos con las reglas y el descuento manual recibidos, y deriva neto = bruto − descuentos; en modo `A` el IVA de cada línea es cero y el total es la suma de netos (VTA-04). DEBE devolver `total_neto`, `total_iva` y `total` con `total = total_neto + total_iva` (INV-14). Ningún valor intermedio se redondea (TR-03).

#### Scenario: Una línea en modo A
- **GIVEN** 15 botellas de Vino A, precio de referencia `"12500.00"`, unidades de referencia 6, alícuota `"0.210000"`, sin reglas ni descuento manual
- **WHEN** se calcula la venta en modo `A`
- **THEN** bruto `"31250.00"`, descuento `"0.00"`, neto `"31250.00"`, IVA `"0.00"` y total `"31250.00"`
- **Regla:** VTA-04; PRC-22; INV-14

#### Scenario: Varias líneas
- **GIVEN** 12 botellas de Vino A y 3 botellas de Vino A en otra presentación, y 1 botella a $8.600 la caja x6
- **WHEN** se calcula la venta
- **THEN** los brutos son `"25000.00"`, `"6250.00"` y `"1433.33"`, y el total es `"32683.33"`
- **Regla:** VTA-04; PRC-22; INV-14

#### Scenario: La orquestación aplica las reglas que recibe
- **GIVEN** la misma línea de 15 botellas y una regla "cajas equivalentes ≥ 2 → 5 %"
- **WHEN** se calcula la venta con esa regla
- **THEN** el descuento es `"1562.50"`, el neto `"29687.50"` y el total `"29687.50"` (el resultado del motor de descuentos, sin recalcularlo)
- **Regla:** DSC-05; VTA-04; ADR-050

#### Scenario: Modos B y C no soportados
- **WHEN** se calcula una venta en modo `B` o `C`
- **THEN** las dos implementaciones rechazan con el error `MODO_IMPOSITIVO_NO_SOPORTADO`
- **Regla:** VTA-04 (B y C: etapa 4); `design.md` D13

### Requirement: Los totales de venta tienen casos compartidos

Los casos de VTA-04 DEBEN vivir una sola vez en `shared/fixtures/calculo/vta-04-totales.json` con `"motor": "vta04"`, sobre el formato de `dsc-05` más `modo_impositivo`, `alicuota` e `iva` por línea y los tres totales, y DEBEN ejecutarse en pytest y en Vitest; los casos se agregan antes del código del motor (`02` §10.4).

#### Scenario: Ambas suites ejecutan los casos
- **WHEN** corren `python -m pytest backend/tests/fixtures_compartidos/` y `npm run test -- tests/unit/calculo`
- **THEN** cada caso `vta04` es una prueba identificable por su `id` en las dos suites y ninguna se omite
- **Regla:** ADR-016; `02` §10.4

#### Scenario: Una divergencia hace fallar CI
- **GIVEN** un caso `vta04` cuyo total esperado no coincide con lo que calcula una de las implementaciones
- **WHEN** corre CI
- **THEN** la suite de esa implementación falla
- **Regla:** ADR-016
