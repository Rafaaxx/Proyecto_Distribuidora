# ADR-010 — Precio de referencia por caja y costo cargable en cualquier presentación

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §7.2 y §6.1, `docs/03` §8 |

## Contexto

Los proveedores informan costos en distintas unidades (algunos por botella, otros por caja). Los precios de venta son proporcionales al contenido de la caja.

## Decisión

**Precios:** cada producto tiene un único precio de referencia sobre su presentación de referencia (la caja habitual de venta). Las demás presentaciones se venden a precio proporcional. El importe de una línea se calcula como `precio_referencia × cantidad_base / unidades_referencia`, redondeado a dos decimales una sola vez al final (PRC-22). El precio unitario por presentación se muestra pero nunca se usa para calcular totales.

**Costos:** la carga acepta el valor en cualquier presentación (botella o caja) e indica si incluye IVA. El sistema convierte a costo base por unidad base con 6 decimales. Se guardan tanto lo informado como el costo base derivado.

Las presentaciones de compra y de venta son independientes y están marcadas con `usar_en_compra` y `usar_en_venta`.

## Consecuencias

- No existe tabla de precio por presentación: simplifica el modelo y los reportes.
- Los costos se almacenan con 6 decimales para evitar pérdida de precisión al dividir (ej: $18.000 / 12 = $1.500,000000 exacto; $10.000 / 12 = $833,333333).
- Cambiar las unidades de una presentación usada en operaciones está prohibido; se crea una nueva presentación (CAT-04).
