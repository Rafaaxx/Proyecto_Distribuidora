# ADR-007 — Facturación como módulo independiente

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §16 |

## Contexto

La distribuidora necesita emitir comprobantes internos (notas de venta) para operar, pero la facturación fiscal electrónica es opcional, compleja y puede ser necesaria para unos clientes y no para otros.

## Decisión

La facturación es un módulo separado dentro del mismo backend (monolito modular), con su propio roadmap. El núcleo expone un contrato al módulo (ventas pendientes por cliente, efecto fiscal registrado por el núcleo a pedido del módulo). El módulo nunca escribe directamente en cuenta corriente ni en utilidad (FAC-10).

La integración con organismos fiscales electrónicos (ARCA/AFIP) queda fuera del alcance hasta que una organización lo requiera.

Las ventas registran su estado de facturación desde la etapa 1 para que las pendientes queden identificadas cuando llegue el módulo.

## Consecuencias

- Hasta que el módulo esté en producción, la distribuidora factura por fuera del sistema.
- El módulo puede desarrollarse en paralelo a la etapa 2 sin bloquear la operación.
- Validar nombre y leyenda del comprobante interno con el contador de la organización antes de implementarlo.
