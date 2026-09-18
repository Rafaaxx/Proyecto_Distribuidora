# ADR-006 — Estrategia de bootstrap offline

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-09-16 |
| Referenciado en | `docs/00` §12, `docs/01` §13, `docs/02` §13.4 |

## Contexto

Al abrir la jornada, el dispositivo necesita descargar todos los datos necesarios para operar sin conexión (catálogo, clientes, precios, stock, permisos).

## Decisión

Descarga completa al abrir la jornada. El endpoint `GET /api/v1/sync/bootstrap` devuelve el conjunto completo definido en SYN-11. El parámetro `since` está en el contrato pero el servidor lo ignora en la etapa 1 y siempre devuelve el conjunto completo.

El bootstrap reemplaza los datos maestros locales pero no toca ventas, cobranzas, movimientos locales ni la cola de comandos pendientes.

## Consecuencias

- Con ~100 productos y ~200 clientes, la descarga completa es trivial para IndexedDB.
- El parámetro `since` preparado permite implementar bootstrap incremental en la etapa 4 sin cambiar el contrato del cliente.
- Si el catálogo crece significativamente antes de la etapa 4, se puede activar el incremental sin romper nada.

## Alternativas consideradas

- **Bootstrap incremental desde el inicio:** más complejo de implementar y de depurar. El beneficio no justifica el costo con el volumen inicial.
