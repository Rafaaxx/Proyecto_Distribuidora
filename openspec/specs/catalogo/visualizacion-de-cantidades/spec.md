# Visualización de Cantidades Specification

## Purpose

Define cómo se muestra una cantidad en unidad base como cajas + unidades según la presentación de referencia del producto, con el mismo resultado en el servidor y en el dispositivo, para que stock, rendición, ventas y reportes hablen el mismo idioma que el vendedor (CAT-08, `02` §10.4).

## Requirements

### Requirement: Una cantidad base se muestra como cajas más unidades
Dada una cantidad base entera `q` y las unidades `u` (entero ≥ 1) de la presentación de referencia, el sistema DEBE mostrarla como `floor(|q| / u)` cajas y `|q| mod u` unidades, con signo negativo aplicado al conjunto si `q < 0`. El cálculo DEBE ser exacto sobre enteros.

#### Scenario: Vino A, caja x6, 31 unidades
- **WHEN** un producto con referencia de 6 unidades existe y se visualiza la cantidad base 31
- **THEN** el resultado es 5 cajas y 1 unidad
- **Regla:** CAT-08

#### Scenario: Cerveza B, caja x12, 31 unidades
- **WHEN** un producto con referencia de 12 unidades existe y se visualiza la cantidad base 31
- **THEN** el resultado es 2 cajas y 7 unidades
- **Regla:** CAT-08

#### Scenario: Cantidad negativa
- **WHEN** un producto con referencia de 6 unidades existe y se visualiza la cantidad base −8
- **THEN** el resultado es negativo, con 1 caja y 2 unidades: −(1 caja + 2 unidades)
- **Regla:** CAT-08

#### Scenario: Cantidad cero y referencia de una unidad
- **WHEN** se visualiza la cantidad base 0 con referencia de 6, o la cantidad base 7 con referencia de 1
- **THEN** el primero es 0 cajas y 0 unidades, sin signo; el segundo es 7 cajas y 0 unidades
- **Regla:** CAT-08

#### Scenario: Unidades de referencia inválidas
- **WHEN** se pide visualizar con unidades de referencia 0 o negativas
- **THEN** la función falla con un error explícito en lugar de devolver un resultado
- **Regla:** CAT-02 (unidades base, entero ≥ 1)

### Requirement: La visualización es idéntica en servidor y dispositivo
La visualización DEBE existir como función pura en el backend y en el frontend, y ambos DEBEN ejecutar los mismos casos compartidos de `shared/fixtures/calculo/`, que incluyen los tres ejemplos de `01` §5. Una divergencia DEBE hacer fallar la suite de la implementación que diverge.

#### Scenario: Los ejemplos de CAT-08 corren en ambas suites
- **WHEN** el archivo de casos compartidos de CAT-08 con los ejemplos 31/6, 31/12 y −8/6 existe y se ejecutan pytest y Vitest
- **THEN** ambas suites ejecutan cada caso con su `id` visible y producen el mismo resultado
- **Regla:** CAT-08; `02` §10.4; ADR-016

#### Scenario: Propiedad de reconstrucción
- **WHEN** se visualiza cualquier entero `q` como `s × (c cajas + r unidades)` con `s` en {+1, −1} y cualquier `u ≥ 1`
- **THEN** `s × (c × u + r) = q` y `0 ≤ r < u`
- **Regla:** CAT-08; INV-04
