# Change 14-transferencias-y-ajustes

## Qué resuelve este change

Mueve stock entre ubicaciones (transferencia) y corrige stock con motivo (ajuste), ambos como operaciones atómicas e idempotentes sobre el libro de stock del change 09, y permite **anular** una y otro. Es la base de la carga del vehículo (RUT-02, change 15).

## Why

`04` §8 (hito 4). Hoy el stock solo entra por stock inicial y compras: no hay forma de llevar mercadería del depósito al vehículo, ni de registrar una rotura, un vencimiento o una diferencia de inventario, ni de regularizar el stock negativo que puede dejar una anulación de compra (deuda del change 11, ADR-044). Además el catálogo deja desactivar un producto con stock, que después no se puede mover (ADR-038 punto 5). El change 15 (jornadas) depende de este.

## What Changes

- **Comando `STOCK_TRANSFERIR`** (solo `ONLINE`, `02` §6.5, permiso `TRANSFERIR_STOCK`): origen, destino distinto, 1 a 200 líneas de producto y cantidad base positiva. En una transacción escribe `transferencia`, sus líneas y, por línea, `TRANSFERENCIA_SALIDA` en origen y `TRANSFERENCIA_ENTRADA` en destino (STK-07). No cambia el promedio ni el stock total (CST-12, INV-15). Con `PERMITIR_STOCK_NEGATIVO` puede dejar el origen bajo cero, con observación (`design.md` D1).
- **Comando `STOCK_AJUSTAR`** (solo `ONLINE`, permiso `AJUSTAR_STOCK`): ubicación, motivo activo del ámbito `AJUSTE_STOCK` (STK-08, TR-09), observación y 1 a 200 líneas con cantidad con signo. Escribe `ajuste_stock`, sus líneas y un movimiento `AJUSTE` por línea, valorizado al promedio vigente sin recalcularlo (CST-12). **Un ajuste nunca deja stock negativo**, tenga o no el usuario `PERMITIR_STOCK_NEGATIVO` (D1).
- **Comandos `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR`** (solo `ONLINE`, D5): anulación total, una sola vez, con motivo obligatorio de los ámbitos nuevos `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE`. Escriben los movimientos inversos al **mismo costo** que los originales y pasan la cabecera a `ANULADA`. Con `TRANSFERIR_STOCK` se anulan las transferencias propias; las ajenas exigen el **permiso nuevo `ANULAR_TRANSFERENCIA`** (Administrador y Administración). Los ajustes se anulan con `AJUSTAR_STOCK`. Si la anulación dejaría stock negativo se rechaza, salvo `PERMITIR_STOCK_NEGATIVO` (con observación).
- **Catálogo — BREAKING para quien desactiva productos:** `PRODUCTO_MODIFICAR` rechaza con `PRODUCTO_CON_STOCK` (409) la desactivación de un producto con algún saldo distinto de cero (D4). Sobre un producto inactivo no se registra ningún movimiento (ADR-038 punto 5, sin enmendar). Los productos que ya están inactivos con stock no se migran: se reactivan, se vacían y se vuelven a desactivar.
- **Libro y costeo:** la única puerta del libro admite ingresos de transferencia y ajuste sin costo ni recálculo, y toma el producto en modo compartido para serializarse con su desactivación (D4.2); `costeo` suma un ingreso sin recálculo.
- **Auditoría (gobernanza crítica, alcance aprobado y cerrado):** el bus copia a su fila de auditoría el motivo que devuelve el handler en `STOCK_AJUSTAR` y en las dos anulaciones (D10; AUD-02). Sin migración: `auditoria.motivo_id` ya existe. Las anulaciones de compra y de pago no se tocan (deuda nominada).
- **Migración:** las cuatro tablas de `03` §9 con `estado` y columnas de anulación en ambas cabeceras (`UPDATE` de `app_runtime` solo sobre esas columnas), dos ámbitos de motivo con sus motivos sembrados y el permiso `ANULAR_TRANSFERENCIA` en las plantillas.
- **Lecturas y pantallas `/admin`:** listado, alta, detalle y anulación de transferencias y ajustes; estado, motivo y enlace en el kardex; mensaje de `PRODUCTO_CON_STOCK` en el formulario de producto.
- **Fixtures compartidos:** ninguno nuevo ni modificado (el promedio no cambia y el frontend no calcula importes).

## Decisiones

`design.md` D0 a D11, **todas aprobadas por el usuario el 2026-10-07**: D0 (un change, cuatro lotes), **D1 = B** (solo la transferencia deja negativo), D2 = A, D3 = A, **D4 = no se desactiva un producto con stock** (opción propuesta por el usuario), **D5 = B** (anulación), D6 = A, D7 = A, D8 = A (ajustada por D5), D9 = A (ajustada por D1, D4 y D5), **D10 = B** acotada a este change, D11 = A.

**Subdecisiones abiertas (bloquean la implementación, tarea 0.2):** técnicas **D4.1** (puerto de registro para que `catalogo` consulte el stock sin ciclo), **D4.2** (serialización de la desactivación con un movimiento; enmienda `02` §7.3), **D5.1** (movimientos inversos con los tipos existentes y otro `origen_tipo`, sin migrar el libro), **D5.2** (costo original por la única puerta), **D10.1** (cómo le llega el motivo al bus); de negocio **D4.3** (anulación de compra de un producto inactivo), **D5.3** (motivos sembrados en los ámbitos nuevos) y **D5.4** (`ANULAR_TRANSFERENCIA` sin `TRANSFERIR_STOCK`). Cada una trae opciones, recomendación y ejemplo.

Requieren **ADR-048**, que enmienda ADR-039 (consecuencias), ADR-044 (punto 4), ADR-022 (motivo en la fila de auditoría de tres comandos) y `02` §7.3 (si D4.2 = A). ADR-038 punto 5 queda sin enmendar.

## Tamaño

Cuatro lotes de apply. **Supera lo previsto en `04` §2** (hasta tres días): el usuario aceptó el 2026-10-07 que el change crezca en lugar de dividirlo (`design.md` D0).

## No incluye

Validación de toma de ubicación por jornada (STK-09) y carga del vehículo en la apertura (RUT-02): change 15. Diferencia de rendición (RUT-06) y remanente (RUT-08): change 24. Recuento o inventario completo (`RECUENTO`, etapa 2). Transferencias en dos pasos (en tránsito). Anulación parcial o repetida. Operación offline. Alta y edición de motivos (catálogo existente). Reportes de ajustes (change 26). Motivo en la auditoría de las anulaciones de compra y de pago (deuda nominada, D10). Migración de productos ya inactivos con stock (D4).

## Invariantes

- **INV-15** (lo cierra este change): dominio, propiedad Hypothesis contra PostgreSQL real e integración; también la anulación de una transferencia.
- **INV-12:** la propiedad de secuencias aleatorias suma transferencias, ajustes y sus anulaciones.
- **INV-01:** falla inyectada entre la salida y la entrada, entre dos líneas de ajuste y en medio de una anulación.
- **INV-04:** cantidades enteras en API y base.
- **INV-05:** `app_runtime` sin `DELETE` sobre las cuatro tablas nuevas, sin `UPDATE` sobre las líneas y con `UPDATE` solo sobre el estado y las columnas de anulación de las cabeceras; el libro y la auditoría siguen de solo inserción.
- **INV-06 / INV-21:** idempotencia y 404 para lo ajeno.
- **INV-02 / INV-03:** FK compuestas y `numeric(18,6)` en las tablas nuevas.

## Capabilities

### New Capabilities

- `stock/transferencias`: transferencia atómica entre ubicaciones, su anulación y consultas (STK-07, INV-15, TR-06).
- `stock/ajustes-de-stock`: ajuste con motivo, valorización, anulación, auditoría con motivo y consultas (STK-08, CST-12, AUD-01, AUD-02).

### Modified Capabilities

- `stock/libro-de-stock`: ingresos de transferencia y ajuste sin costo; stock negativo con permiso también en la salida de una transferencia y en las anulaciones (no en el ajuste); movimientos inversos con el costo original; producto tomado en modo compartido.
- `costeo/costo-promedio`: un ingreso sin costo no modifica el promedio ni deja historia.
- `stock/kardex`: motivo, operación de origen, su estado y los movimientos inversos.
- `stock/administracion-de-stock`: pantallas de transferencias y ajustes, con anulación y estado.
- `catalogo/productos-y-presentaciones`: un producto con stock no se desactiva (`PRODUCTO_CON_STOCK`).
- `sistema/pipeline-de-comandos` y `auditoria/registro-de-auditoria`: **sin spec delta propia**; el cambio del bus (motivo en la fila de auditoría de tres comandos) queda especificado en los requisitos de auditoría de `stock/ajustes-de-stock` y `stock/transferencias`, por tener el alcance cerrado a este change (D10).

## Impact

`backend/app/modules/stock/` y `costeo/`; `catalogo/service.py` (puerto y regla de desactivación); `sync/service.py` y `app/commands/` (motivo de auditoría); `identidad/domain/permisos.py` y `configuracion/domain/valores.py` (permiso y ámbitos); `app/seed.py`; una migración; cuatro tipos de comando; `pyproject.toml` (contrato de import-linter); ratchets. Frontend en `areas/admin/stock/`, `features/stock/`, `domain/stock/` y el formulario de producto de `areas/admin/catalogo/`. Docs `01`–`04` y ADR-048 al cierre (último lote). Gobernanza **media-alta** (stock y costos) con dos piezas **críticas** aprobadas explícitamente (auditoría y permiso nuevo): nada se implementa sin la tarea 0.2.
