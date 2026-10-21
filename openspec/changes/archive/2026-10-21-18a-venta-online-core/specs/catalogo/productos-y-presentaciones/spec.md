## ADDED Requirements

### Requirement: Una presentación usada en una venta congela sus unidades

Una presentación que figura en alguna línea de venta, de cualquier estado, DEBE contar como usada para INV-18: `ventas` DEBE registrar su verificador de uso en el puerto del catálogo (ADR-023), y la venta DEBE leer las unidades de la presentación con el producto ya tomado en modo compartido, de modo que una modificación simultánea espere o la venta vea las unidades nuevas (deuda nominada por el change 05; `design.md` D17 y D18 del change 18a).

#### Scenario: INV-18 — presentación usada en una venta
- **GIVEN** la presentación `Caja x6` de `Vino A` usada en una venta y sin compras ni costos informados
- **WHEN** se envía `PRESENTACION_MODIFICAR` con 12 unidades
- **THEN** se rechaza con `UNIDADES_CONGELADAS` y conserva 6 unidades
- **Regla:** INV-18; CAT-04; ADR-023

#### Scenario: Venta y modificación simultáneas
- **WHEN** una venta de `Caja x6` y una modificación a 12 unidades de esa presentación (aún sin usar) se procesan a la vez con commits reales
- **THEN** o la venta congela 6 y la modificación se rechaza con `UNIDADES_CONGELADAS`, o la modificación termina primero y la venta congela 12; nunca una línea con 6 y la presentación con 12
- **Regla:** INV-18; PRC-23
