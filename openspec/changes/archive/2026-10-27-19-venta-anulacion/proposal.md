# Change 19-venta-anulacion

## Qué resuelve este change

Permite anular por completo, con conexión, una venta confirmada: con permiso y motivo, devuelve el stock a la ubicación original al costo congelado, acredita el total en la cuenta del cliente y resuelve qué pasa con el dinero cobrado en el acto (VTA-20 a VTA-22). Cierra INV-19.

## Why

`04` §9, fila 19. Deudas nominadas: del 17, anular la cobranza de una venta (VTA-22, ADR-052 punto 79); del 18a, el `UPDATE` de `venta.estado` y esa misma cobranza (ADR-054 punto 4). Hoy una venta mal cargada solo se compensa con un ajuste de stock y su cobranza no se puede anular (`COBRANZA_DE_VENTA`).

## What Changes

- **Comando `VENTA_ANULAR` v1** por el bus, solo `ONLINE`, permiso `ANULAR_VENTA`; ruta `POST /api/v1/ventas/{venta_id}/anulacion` (D1). Contenido: venta, motivo del ámbito `ANULACION_VENTA`, observación opcional y `devuelve_dinero` (D2).
- **Efectos atómicos** (VTA-21, INV-01, INV-19): ingreso `ANULACION_VENTA` por línea en la ubicación original al costo unitario congelado, que recalcula el promedio por CST-11 y deja historia (D5); movimiento `ANULACION_VENTA` (reduce) por el total; venta `ANULADA` y fila en `venta_anulacion`; auditoría con el motivo (AUD-01, AUD-02).
- **Dinero cobrado** (VTA-22): con devolución, la cobranza de la venta queda `ANULADA` con `ANULACION_COBRANZA`, por una función nueva de `cobranzas/service.py` (D9); sin devolución, el cobro queda como saldo a favor. Consumidor final (D3) e interpretación de INV-19 frente a VTA-22 (D4).
- **Reglas de borde:** línea vendida sin costo (D5), ubicación original tomada por una jornada (STK-09, D6), maestros inactivos (D7), jornada de la anulación (D8), facturación (VTA-23, D13).
- **Migración:** tabla `venta_anulacion`, `UPDATE (estado)` de `venta` para `app_runtime`, motivos sembrados de `ANULACION_VENTA` (D11, D12).
- **Fixtures compartidos antes del código** (D17): casos de anulación de venta en `cst-11-costo-promedio.json` y nuevo `vta-22-anulacion.json` (efecto en el saldo).
- **Pantallas `/admin`:** "Anular venta" en el detalle, bloque de anulación, filtro por estado en el listado (D14, D16) y ayuda contextual (D18).

## Decisiones (bloqueantes)

`design.md` D0 a D19, **pendientes de aprobación**; specs y tareas están escritas con la opción recomendada (A). **Críticas:** D10 (transacción y orden de bloqueo). **Altas:** D1, D4, D5, D6, D9, D14, D15, D19. **De negocio:** D2, D3, D4, D5, D6, D7, D12, D13. Borrador **ADR-058** (*Propuesto*). Cambios a `docs/`: `propuesta-docs.md`.

## No incluye

Anulación sin conexión (VTA-24, change 22c; el contrato la deja posible, D19). Devolución parcial (etapa 2). Bloqueo por factura (VTA-23, facturación). Nota de venta (20), rendición (24), reportes (26), `/ruta`.

## Invariantes

- **INV-19:** integración y propiedad que comparan, con SQL, stock por ubicación y saldo antes de la venta y después de anularla con devolución; ninguna fila borrada.
- **INV-01:** una transacción; falla inyectada después de cada efecto.
- **INV-05:** `UPDATE` solo de `venta.estado`, sin `DELETE`; anulación única por `venta_id`.
- **INV-06, INV-10, INV-21:** doble envío; valores congelados intactos; 404 entre organizaciones.
- **INV-12, INV-13:** stock y saldo iguales a sus movimientos, con concurrencia real (dos anulaciones simultáneas: una gana).

## Capabilities

### New Capabilities

- `ventas/anulacion-de-venta`: comando, efectos, dinero cobrado, reglas de borde, auditoría, orden de bloqueo.

### Modified Capabilities

- `ventas/administracion-de-ventas`: detalle con la anulación, botón y filtro por estado.
- `cobranzas/anulacion-de-cobranzas`: la cobranza de una venta se anula con la venta.
- `stock/libro-de-stock`: ingreso `ANULACION_VENTA` (con y sin costo, producto inactivo, ubicación tomada).
- `costeo/costo-promedio`: el reingreso recalcula con el costo congelado.
- `organizacion/catalogos-configurables`: motivos de `ANULACION_VENTA`.
- `sistema/pipeline-de-comandos`: tipo `VENTA_ANULAR` en el catálogo.
- `sistema/ayuda-contextual`: textos de la anulación.

## Impact

Backend: `ventas/`, `cobranzas/service.py`, `stock` (dominio y servicio), una migración. Frontend: `areas/admin/ventas/`, `features/ventas/`, `domain/ventas/`, `ayuda/textos.ts`. Fixtures `cst-11` y `vta-22`. Docs y ADR-058. Gobernanza **media/alta** (dinero y libros); D10 **crítica**.
