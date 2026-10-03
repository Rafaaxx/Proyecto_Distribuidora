# Change 11-compras-y-deuda-proveedor

## Qué resuelve este change

Registra compras a proveedores con líneas en cualquier presentación de compra: en una sola transacción ingresa stock, recalcula el costo promedio, deja la deuda en la cuenta del proveedor y, si es de contado, el pago. Permite anular una compra revirtiendo todo, sin borrar nada.

## Why

`04` §7 (hito 3) y el criterio 2 de `00` §9: "compra a crédito de vino por caja y de cerveza por unidad; stock, promedio y deuda correctos". Los libros ya existen (08 y 09); hasta ahora el único ingreso con costo es el stock inicial. Dependen de este change el 12 (pagos) y, en la práctica, toda venta con costo real.

## What Changes

- **Tablas** `compra`, `compra_linea`, `pago_proveedor` y `pago_proveedor_medio` (`03` §6) con FK compuestas, `numeric` en importes y costos, `integer` en cantidades base, y los agregados que propone `design.md` D12.
- **Comandos** `COMPRA_CONFIRMAR` y `COMPRA_ANULAR` (solo `ONLINE`, CMP-08, `02` §6.5), en el módulo `proveedores` (`02` §5.1), usando solo los `service.py` de `catalogo`, `stock`, `costeo`, `cuentas_corrientes` y `configuracion`.
- **Confirmar** (CMP-01 a CMP-03): cantidad base y costo base por línea con CST-02, total neto (CMP-02), ingreso de stock (`COMPRA`), recálculo del promedio (CST-11), `COMPRA` en la cuenta del proveedor y, de contado, un pago con sus medios (CC-05). Orden de bloqueo `saldo_cuenta → costo_producto → stock_saldo` (`02` §7.3).
- **CMP-04**: la respuesta informa las líneas cuyo costo base difiere del costo informado vigente; la pantalla ofrece registrarlo con `COSTO_INFORMAR`. Nunca automático.
- **Anular** (CMP-05 a CMP-07): egreso `ANULACION_COMPRA`, reversión del promedio u observación `ANULACION_COMPRA_SIN_RECALCULO`, `ANULACION_COMPRA` en la cuenta y, según D3, el pago. Stock negativo solo con `PERMITIR_STOCK_NEGATIVO` y observación `STOCK_NEGATIVO`.
- **`stock` y `costeo`** se amplían (D9, D10): egreso que revierte un ingreso y egreso que admite negativo con permiso. Responde la deuda del 09: qué guarda `costo_producto_mov` sin recálculo.
- **Deudas saldadas**: verificador de uso de presentaciones `_presentacion_tiene_compra` (INV-18, deuda del 05/06) y filtro `proveedor_id` en `GET /catalogo/productos`, adoptado por `CostosCargaScreen` (deuda del 06).
- **Lecturas** de compras (listado y detalle), de medios de pago y de motivos por ámbito.
- **Pantallas** `/admin`: listado, alta con vista previa, detalle y anulación.
- **Fixtures compartidos**: se **agrega** `shared/fixtures/calculo/cmp-02-compra.json` (líneas y totales, D15) antes del código; CST-02 y CST-11 no cambian.

## Decisiones abiertas (bloquean la implementación)

`design.md` D0 a D16, con opción A recomendada y ejemplo. Son **de negocio**: D1 (importe de la deuda: el IVA), D2 (pago de contado), D3 (qué pasa con el pago al anular), D4 (proveedor del producto), D5 (cantidades y valores de línea), D6 (fecha), D7 (CMP-04), D8 (motivos), D11 (anular con maestros inactivos), D13 (número de comprobante), D14 (permisos), D16 (ubicación de destino). Son **técnicas**: D0, D9, D10, D12, D15. D1–D3 y D9–D10 requieren ADR (desde ADR-043).

## No incluye

Pagos independientes y su anulación (12), órdenes de compra, recepción parcial, vencimientos y notas de crédito/débito (CMP-09, etapa 2), compras offline (CMP-08), validación de ubicación tomada STK-09 (15), percepciones o impuestos aparte del IVA, edición de compras (TR-06).

## Invariantes

- **INV-01**: compra y anulación atómicas (falla inyectada después del stock, antes de la cuenta).
- **INV-07**: compra sin líneas rechazada en el servicio, dentro de la transacción.
- **CST-11 / CMP-06**: fixtures y casos de `01` §6.2; Hypothesis: confirmar y anular deja el promedio previo cuando se recalcula.
- **INV-12 / INV-13**: propiedad contra PostgreSQL real tras compras y anulaciones aleatorias.
- **INV-08**: medios del pago de contado = importe (D2).
- **INV-05**: `app_runtime` sin `DELETE` sobre compras y pagos; los libros siguen siendo de solo inserción.
- **INV-06 / INV-18 / INV-21**: idempotencia, unidades congeladas, 404 para lo ajeno.

## Capabilities

### New Capabilities

- `proveedores/compras`: registro de compras, deuda y pago de contado (CMP-01 a CMP-04, CMP-08, CC-05, INV-07).
- `proveedores/anulacion-de-compras`: anulación con reversión (CMP-05 a CMP-07, INV-01).
- `proveedores/administracion-de-compras`: pantallas `/admin` de compras.

### Modified Capabilities

- `stock/libro-de-stock`: egreso negativo con permiso y reversiones sobre maestros inactivos.
- `costeo/costo-promedio`: reversión del promedio al anular una compra e historia sin recálculo.
- `catalogo/productos-y-presentaciones`: filtro por proveedor; la compra congela unidades.
- `organizacion/catalogos-configurables`: lectura de medios y motivos; motivos de anulación de compra.

## Impact

`backend/app/modules/proveedores/` (compras y pagos), ampliaciones en `stock`, `costeo`, `catalogo` y `configuracion`, una migración, dos comandos, import-linter, ratchets. Frontend en `areas/admin/compras/`, `features/compras/` y `domain/compras/`. Docs `01`, `02`, `03`, `04` y ADR-043 en adelante al cierre.
