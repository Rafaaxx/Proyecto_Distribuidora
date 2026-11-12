# ADR-002 — Estrategia de costeo: promedio ponderado móvil

| Campo | Valor |
| --- | --- |
| Estado | Vigente (matizado por ADR-039, 2026-09-30: el promedio es nulo hasta el primer ingreso con costo) |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §6.2, `docs/03` §7 |

## Contexto

Cada venta necesita un costo asignado para calcular utilidad. Los productos pueden comprarse en distintos momentos a distintos costos. La organización inicial tiene un solo proveedor por producto.

## Decisión

Promedio ponderado móvil por producto y organización. Cada compra o ingreso recalcula el promedio: si el stock total previo es mayor que cero, `(stock × promedio + cantidad × costo) / (stock + cantidad)`; si es cero o negativo, el promedio pasa a ser el costo del ingreso.

El cálculo vive encapsulado en el módulo `costeo`. Ninguna otra parte del sistema calcula costos de venta. Cada línea de venta congela el costo al confirmar (el promedio vigente al procesar en el servidor).

## Consecuencias

- Sin tabla de capas: modelo más simple, sin bloqueos al consumir capas.
- Sin problema de costo pendiente por stock negativo: siempre hay un promedio vigente.
- Devoluciones usan el costo congelado de la línea, no el promedio actual.
- Con inflación, el promedio queda entre el costo viejo y el actual: más cercano a la realidad de reposición que FIFO.
- Atribución de costo por proveedor: con un solo proveedor por producto, se agrupa por el proveedor del producto sin necesidad de capas.

## Alternativas consideradas

- **FIFO:** permite atribución exacta cuando un producto tiene varios proveedores. Descartado para la etapa 1 porque la organización inicial tiene un solo proveedor por producto. El encapsulamiento permite agregar FIFO desde una fecha de corte en la etapa 4 sin modificar costos históricos.
- **Último costo:** no refleja lo que realmente se pagó. Descartado.
