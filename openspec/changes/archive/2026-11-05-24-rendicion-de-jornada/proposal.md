# Change 24-rendicion-de-jornada

## Qué resuelve este change

El vendedor termina el día en el teléfono; el supervisor cuenta el vehículo en `/admin`, el sistema registra las diferencias contra el stock esperado, muestra el resumen de la jornada (stock, ventas, anulaciones y cobranzas por medio de pago), devuelve el remanente al depósito y cierra.

## Why

`04` §11 (fila 24; RUT-05). Desde el change 15 la rendición solo cambia el estado (ADR-049 punto 3). Quedan deudas «al 24»: el conteo como versión nueva de `JORNADA_RENDIR`, RUT-05, las jornadas cerradas sin conteo y el orden de bloqueo (ADR-049, deuda 3); las diferencias y el remanente por la única puerta con la valorización de CST-12 (ADR-048 punto 9); las anulaciones por `venta_anulacion.jornada_id` (ADR-058, ADR-066); las cobranzas en el resumen y la cobranza que llega con la jornada en rendición o cerrada (ADR-052 deuda 4, ADR-067).

## What Changes

- **Teléfono** (D1, D10): «Terminar el día» encola `JORNADA_ENTREGAR` detrás de todo lo pendiente; al procesarse, el servidor sabe que la cola de esa jornada quedó vacía (RUT-05). El teléfono deja de vender, anular y cobrar.
- **Rendición** (D2, D3, D5): `JORNADA_RENDIR` v2 exige la entrega y el conteo físico por producto; escribe `rendicion`, `rendicion_linea` y un `DIFERENCIA_RENDICION` por producto con diferencia, al promedio vigente y sin recalcularlo, en un orden de bloqueo sin ciclos. v1 se retira.
- **Resumen** (D4, D8): `GET /stock/jornadas/{id}/resumen` con stock al abrir, ingresos, ventas, anulaciones, otros, esperado, contado y diferencias (congelados al rendir), y ventas, anulaciones y cobranzas por medio de la jornada; también para jornadas sin conteo.
- **Cierre con remanente** (D6): `JORNADA_CERRAR` v2 admite devolver el remanente a un depósito como una transferencia normal, en la misma transacción.
- **Tardíos** (D7): una venta, anulación o cobranza de una jornada ya rendida se acepta con la observación nueva `JORNADA_RENDIDA`.
- **Pantallas `/admin`** (D9): conteo, resumen y cierre en el detalle de la jornada. **Textos y ayuda** (D11, D12).
- **Migración** de Alembic; **sin Dexie nuevo** y **sin permisos nuevos**. **ADR-068** (*Propuesto*) y `propuesta-docs.md`.

## Decisiones

`design.md` D0 a D12, pendientes (tarea 0.1). **CRÍTICAS: D1 (RUT-05) y D3 (bloqueo).** ALTAS: D2, D4, D5, D7. **Bloqueante:** sin 0.1 y 0.2 no empieza el apply. Conviene mirar primero **D1**, después D5 (diferencias sin motivo y sin costo), D7 y D6.

## No incluye

Rendición de efectivo con caja y tesorería (RUT-10, etapa 2); recuento fuera de la jornada (etapa 2); reabrir una jornada entregada o rendida; rendir sin la entrega del teléfono (se libera, RUT-09); el resumen en el teléfono; resolver las observaciones (25); el reporte de rendición por vendedor (26).

## Reglas e invariantes

- **RUT-04 a RUT-09, STK-03, STK-04, STK-09, CST-12, CST-13, SYN-02, SYN-03, SYN-05, SYN-07, AUD-01; `01` §18, §19, §21; `02` §7.3.**
- **INV-01**: rendición y cierre con remanente, todo o nada. **INV-04**: conteo entero. **INV-05**: `rendicion` y `rendicion_linea` sin `UPDATE` ni `DELETE`; `jornada` con `UPDATE` acotado. **INV-06**: doble envío de entrega, rendición y cierre. **INV-12**: tras la rendición el stock es la suma de los movimientos y vale lo contado (propiedad con SQL). **INV-16**: el cierre libera. **INV-17**: los tardíos nunca se rechazan. **INV-21**: jornada ajena, 404. **INV-03**: costos como string.
- **Fixture compartido nuevo** `shared/fixtures/calculo/rut-06-rendicion.json` (conjunto a contar, esperado y diferencia), antes del cálculo; `codigos-de-sincronizacion.json` se amplía.

## Capabilities

### New Capabilities

- `stock/rendicion-de-jornada`: entrega, conteo, diferencias, resumen y remanente.

### Modified Capabilities

- `stock/jornadas`: la rendición con conteo y el cierre con remanente.
- `stock/toma-de-ubicacion`: la excepción de la rendición.
- `stock/libro-de-stock`: `DIFERENCIA_RENDICION` por la única puerta.
- `sync/lote-de-comandos`: `JORNADA_ENTREGAR` por el lote.
- `sync/observaciones`: `JORNADA_RENDIDA`.
- `ruta/area-de-ruta`: «Terminar el día».
- `sistema/ayuda-contextual`: claves nuevas y revisadas.

## Impact

Backend: `stock/` (`rendicion_*` por área, ADR-049 punto 2; `service.py`; `jornadas_*`), `ventas` y `cobranzas` (observación tardía), `sync` (catálogo de observaciones), migración. Frontend: `areas/admin/stock/`, `features/stock/`, `domain/stock/`, `areas/ruta/` (inicio), `sync/` (sobre, resultados, estado de jornada), `domain/ruta/`, `ayuda/textos.ts`. `shared/fixtures/`. Docs al archivar.
