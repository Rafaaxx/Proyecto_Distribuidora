# Change 18a-venta-online-core

## Qué resuelve este change

Permite confirmar una venta con conexión: pedido en cajas y unidades, precio desde la lista del cliente, cobranza en el acto y confirmación atómica que descuenta stock, congela el costo, debita la cuenta corriente y registra la cobranza, con número de nota por dispositivo (VTA-01 a VTA-12, PRC-20 a PRC-23). Sin descuentos ni evaluación de crédito (18b).

## Why

`04` §9, fila 18a: es el nodo de convergencia del hito 5 y cierra INV-01, INV-07 e INV-14 para la venta. Siete changes le dejaron deudas nominadas (05, 09, 11b, 13, 14, 16, 17) que no se pueden saldar en otro lugar.

## What Changes

- **Módulo `ventas`** (tablas `venta` y `venta_linea`, `03` §12) con `VENTA_CONFIRMAR` v1 por el bus; `cobranza.venta_id` pasa a tener clave foránea compuesta (deuda del 17).
- **Composición** (VTA-02, VTA-03, CAT-07, CAT-08): líneas por producto y presentación de venta; la pantalla arma "cajas + unidades" como dos líneas.
- **Precio** (PRC-20 a PRC-23, VTA-10) por `precios/service.py`: lista aplicable, versión vigente al momento de la venta, otra lista o versión anterior con `USAR_LISTA_ANTERIOR` y motivo; cada línea congela versión, precio y unidades de referencia. Qué pasa con `SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE` y un producto sin precio (D6, D7).
- **Cálculo compartido** (VTA-04, INV-14): `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts` como orquestadores de bruto, descuentos y totales; **fixtures compartidos nuevos `shared/fixtures/calculo/vta-04-totales.json`** sobre el formato de `dsc-05`, escritos antes del código (deuda del 16).
- **Confirmación atómica** (VTA-12, INV-01): stock (`VENTA`), costo congelado (VTA-05), débito `VENTA` en la cuenta (CC-05), cobranza de origen `VENTA` por `cobranzas/service.py::registrar_cobranza` (VTA-11), estado de facturación (VTA-08), observaciones y auditoría, con el orden global de bloqueo.
- **Deudas de costo y stock:** venta de un producto sin costo promedio (D10, deuda del 09) y sobre saldo negativo (D11, deuda del 14).
- **Numeración** `V03-000142` (VTA-06, ADR-008) con el correlativo del dispositivo (D4).
- **Modo impositivo** (D13, deuda del 11b): solo modo `A`; no se lee `modalidad_iva_default`.
- **INV-18** (deuda del 05): verificador de uso `venta_linea`.
- **Modo `OFFLINE` en el servidor** con `permiso_offline = VENDER` (deuda del 17; D1, crítica).
- **Lecturas y pantallas `/admin`:** "Ventas" (nueva venta, listado, detalle) con ayuda contextual (ADR-051).

## Decisiones (bloqueantes)

`design.md` D0 a D22, **aprobadas por el usuario el 2026-10-17, opción A en todas**; las specs y las tareas están escritas con la opción recomendada (A). **Críticas:** D1 (venta sin conexión en el servidor), D4 (numeración) y D17 (transacción y orden de bloqueo). **Altas:** D2, D6, D9, D10, D11, D19 y D20. **De negocio:** D3, D5, D7, D8, D12, D13 y D15. Se registran en **ADR-054** (*Propuesto*). `docs/` tiene vacíos y contradicciones (PRC-23 perdió su texto, versiones "anteriores permitidas" sin definir, versión por línea o por venta, desvío de reloj sin valor): ver `design.md` § Contexto y `propuesta-docs.md`.

## Tamaño

Supera `04` §2. D0 recomienda un change en cinco lotes, con el modo `OFFLINE` aislado y cortable.

## No incluye

Descuentos automáticos y manuales, evaluación de crédito, PIN y snapshot de crédito (18b). Anulación (19). Nota de venta en PDF (20). Bootstrap, Dexie, cola y pantalla de `/ruta` (21 a 23). Modos B y C (etapa 4). Facturación.

## Invariantes

- **INV-01:** una sola transacción del bus; prueba con falla inyectada después de cada efecto.
- **INV-07:** de 1 a 200 líneas, validado en el servicio y comprobado con SQL.
- **INV-14:** total = Σ netos + Σ IVA, con `CHECK` de cabecera, fixtures compartidos y propiedad Hypothesis con SQL.
- **INV-10 (parte 18a):** las columnas congeladas no tienen `UPDATE` para `app_runtime`.
- **INV-12, INV-13:** movimientos y saldos en la misma transacción, con concurrencia real.
- **INV-18:** verificador registrado y presentación leída con el producto tomado.
- **INV-06, INV-17, INV-21:** doble envío, venta sin conexión aceptada con observaciones, aislamiento.

## Capabilities

### New Capabilities

- `ventas/composicion-de-venta`: líneas, presentaciones, precio y congelamiento (VTA-02, VTA-03, VTA-10, PRC-20 a PRC-23).
- `ventas/calculo-de-venta`: orquestador de bruto, descuentos y totales con casos compartidos (VTA-04, INV-14).
- `ventas/confirmacion-de-venta`: comando, efectos atómicos, costo, stock, cuenta, cobranza, numeración y modo sin conexión (VTA-01, VTA-05, VTA-06, VTA-08, VTA-11, VTA-12).
- `ventas/administracion-de-ventas`: lecturas y pantallas.

### Modified Capabilities

- `cobranzas/registro-de-cobranzas`: cobranza de origen `VENTA` y clave foránea a la venta.
- `catalogo/productos-y-presentaciones`: la línea de venta congela las unidades (INV-18).
- `stock/libro-de-stock`: egreso `VENTA`, negativo con permiso o sin conexión.
- `precios/resolucion-de-precio`: precios de una versión elegida y lectura para vender.
- `sync/lote-de-comandos`: `VENTA_CONFIRMAR` sin conexión.
- `cuentas-corrientes/administracion-de-cuentas-corrientes`: el movimiento `VENTA` lleva a la venta.
- `sistema/ayuda-contextual`: pantallas de venta.

## Impact

Backend: módulo `ventas/`; `stock`, `cobranzas`, `precios` y `catalogo` (solo `service.py` y dominio); `clientes/api.py` (lecturas); import-linter; una migración. Frontend: `domain/calculo.ts`, `domain/ventas/`, `areas/admin/ventas/`, `features/ventas/`, `ayuda/textos.ts`. Fixtures: `vta-04-totales.json`. Docs y ADR-054. Gobernanza **media** con piezas **críticas** (D1, D4, D17).
