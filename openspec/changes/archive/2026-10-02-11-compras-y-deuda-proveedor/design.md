# Diseño técnico — 11-compras-y-deuda-proveedor

> **Estado: D0 a D16 APROBADAS el 2026-10-02, todas con la opción A (tarea 0.1); D17 y D18 aprobadas el 2026-10-02 durante el apply.** Las specs y las tareas ya estaban escritas con la opción A, así que no requieren `/opsx:update`. Los ADR marcados "ADR pendiente" (ADR-043, ADR-044) se redactan durante el apply. Cada decisión indica si es **de negocio** o **técnica**.

## Context

Ver `proposal.md` (Why). Ya existe lo que una compra necesita escribir:

- `stock/service.py::registrar_movimientos` (09, ADR-039): **único camino** para cambiar stock; bloquea ubicaciones `FOR SHARE`, `costo_producto` y `stock_saldo` en orden; un ingreso `COMPRA` ya recalcula el promedio (CST-11) vía `costeo.aplicar_ingreso`; un egreso de cualquier tipo se valoriza al promedio vigente y **nunca** deja saldo negativo; rechaza productos inactivos para todo tipo.
- `costeo/service.py`: `bloquear_costos`, `aplicar_ingreso`, `aplicar_egreso`. `costo_producto_mov.origen_tipo` ya admite `ANULACION_COMPRA`; la columna `recalculado` existe. No hay función de reversión.
- `cuentas_corrientes/service.py::bloquear_saldo` y `registrar_movimiento`: el catálogo ya admite `COMPRA` (aumenta), `ANULACION_COMPRA` (reduce), `PAGO` (reduce) y `ANULACION_PAGO` (aumenta) (ADR-034 punto 5).
- `proveedores/domain/costo_base.py::calcular_costo_base` (CST-02) y su gemelo TS `frontend/src/domain/proveedores/costoBase.ts`, con fixtures `cst-02-costo-base.json`.
- El bus admite handlers que devuelven observaciones (`sync/service.py::ObservacionProducida`); `ANULACION_COMPRA_SIN_RECALCULO` y `STOCK_NEGATIVO` están en el catálogo de SYN-07.
- Permisos `REGISTRAR_COMPRA`, `ANULAR_COMPRA`, `PERMITIR_STOCK_NEGATIVO` ya sembrados. `motivo.ambito` admite `ANULACION_COMPRA`, pero **ninguna organización tiene motivos de ese ámbito** y no hay API para listar medios de pago ni motivos.

Lo que `docs/` **no** resuelve o resuelve de forma contradictoria:

- **Contradicción 1 (importe de la deuda):** CMP-03 manda registrar la compra en la cuenta del proveedor, pero CMP-02 y `03` §6 solo definen `total_neto` (sin IVA). Nada dice si la deuda incluye IVA. → D1.
- **Contradicción 2 (pago de contado):** CMP-03 y CC-05 piden registrar el pago de una compra de contado en el 11, pero `pago_proveedor` y PAG-01 son del change 12 (`04` §7). Y `03` §6 no vincula un pago con su compra. → D2, D3, D12.
- **Contradicción 3 (stock negativo):** ADR-039 punto 3 y la spec `stock/libro-de-stock` dicen "ningún camino deja saldo negativo", pero CMP-07 admite anular con `PERMITIR_STOCK_NEGATIVO`. → D10 (enmienda ADR-039).
- **Contradicción 4 (inactivos):** `registrar_movimientos` rechaza productos inactivos para todo tipo; CAT-05 solo prohíbe ofrecerlos "en nuevas operaciones". → D11.
- **Ambigüedad CMP-06:** "stock restante" no dice si es de la ubicación o de la organización. Se interpreta como **stock total de la organización**, porque el promedio es por organización (CST-10) y CST-11 usa ese mismo stock. Es lectura, no decisión; se deja escrito en el ADR de D9.
- **Deuda del 09:** qué guarda `costo_producto_mov` en una `ANULACION_COMPRA` con `recalculado = false`. → D9.
- **`03` §6** no congela la alícuota de la línea (sí lo hace `costo_informado.alicuota_aplicada`), y `03` §4 no dice cómo nace un motivo de anulación de compra. → D12, D8.
- `03` §2.2 permite `cantidad numeric(14,3)` en compras, pero la cantidad base es entera (INV-04). → D5.

## Goals / Non-Goals

**Goals:** una sola operación atómica por compra y por anulación, que reutilice los servicios existentes sin duplicar cálculos (CST-14); reversión exacta de stock y cuenta; ampliación mínima y probada de `stock` y `costeo`.

**Non-Goals:** pagos independientes y su anulación (12); edición de compras; percepciones u otros impuestos discriminados; compras offline; validación de ubicación tomada (STK-09, 15).

## Decisions

### D0 — Tamaño del change · técnica

> **Aprobada 2026-10-02: opción A.**

**Qué hay que decidir.** El alcance (compra, contado, anulación, ampliación de `stock`/`costeo`, pantalla, dos deudas) roza el máximo de tres días de `04` §2.

- **A (recomendada).** Un solo change en tres lotes de apply: (1) migración, cálculo y confirmación a crédito de punta a punta por API; (2) contado, anulación y ampliación de `stock`/`costeo`; (3) pantallas, deudas, cobertura y docs.
- **B.** Dividir en `11a-compras` (crédito + contado) y `11b-anulacion-de-compras`.

**Ejemplo.** Con A, al cerrar el lote 1 ya se puede confirmar por API "10 cajas de Vino A a crédito" y ver stock, promedio y deuda; con B, la anulación espera a que 11a se archive.

### D1 — Importe de la deuda: ¿con IVA? · de negocio · ADR pendiente (ADR-043)

> **Aprobada 2026-10-02: opción A.**

**Qué hay que decidir.** Qué importe entra en la cuenta del proveedor (y se paga de contado). El costo siempre es neto (CST-02, CST-04).

- **A (recomendada). Total de factura informado.** La compra guarda `total_factura` (`numeric(14,2) > 0`), el importe que dice el comprobante del proveedor. La pantalla lo prellena con `total neto + IVA de cada línea` (alícuota del producto) y el usuario lo corrige si la factura trae percepciones, redondeos o el proveedor no factura IVA. La deuda y el pago de contado usan `total_factura`; stock y promedio usan el neto.
- **B. Neto más IVA calculado.** `total = Σ round2(importe neto × (1 + alícuota))`, sin edición. Determinista, pero no sirve si el proveedor no discrimina IVA (monotributista) ni si la factura trae percepciones.
- **C. Total neto.** La deuda es `total_neto`, literal de `03` §6. Solo es correcto si la organización trabaja sin IVA en compras.

**Ejemplo.** 10 cajas de Vino A x6 a $6.000 sin IVA + 60 botellas de Cerveza B a $1.100 sin IVA: neto $126.000. A: sugiere $152.460 (21%); si la factura dice $153.720 por una percepción, la deuda es $153.720 y los promedios siguen en $1.000 y $1.100. B: deuda $152.460 fija. C: deuda $126.000; al pagar la factura real queda un saldo a favor falso de $26.460.

### D2 — Pago de una compra de contado · de negocio · ADR pendiente (ADR-043)

> **Aprobada 2026-10-02: opción A.**

**Qué hay que decidir.** Cómo se registra el pago que exige CMP-03 si el módulo de pagos es del 12.

- **A (recomendada). El 11 crea `pago_proveedor` y `pago_proveedor_medio`** (`03` §6) y la compra de contado genera, en la misma transacción, un pago con `origen = COMPRA` y `compra_id`, por `total_factura`, con **uno o más medios** activos que suman el importe (INV-08) y referencia donde el medio la exige (como COB-02). El 12 agrega el pago independiente y su anulación sobre las mismas tablas.
- **B.** Igual que A pero con **un solo medio**; pagos mixtos se registran como compra a crédito + pago (12).
- **C.** En el 11 solo compras a crédito; el contado llega con el 12.

**Ejemplo.** Contado de $152.460: A acepta $100.000 efectivo + $52.460 transferencia (ref. 0042); B obliga a un único medio; C obliga a registrarla a crédito y esperar al 12 para el pago.

### D3 — Qué pasa con el pago al anular una compra de contado · de negocio · ADR pendiente (ADR-043)

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada). Como VTA-22:** `COMPRA_ANULAR` lleva `devuelve_pago` (obligatorio en contado, prohibido en crédito). `true`: el pago pasa a `ANULADO` y se registra `ANULACION_PAGO`; el saldo vuelve a como estaba. `false`: el pago se mantiene y queda saldo a nuestro favor.
- **B. Siempre se anula el pago** junto con la compra.
- **C. Nunca:** el pago queda y se anula aparte con el 12.

**Ejemplo.** Contado de $152.460, saldo previo $0. A con `true`: saldo $0, pago anulado; con `false`: saldo −$152.460 ("Saldo a nuestro favor"), que se compensa con la próxima compra. B: siempre $0. C: −$152.460 hasta que exista el 12.

### D4 — Productos de otro proveedor en la compra · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Solo productos cuyo `proveedor_id` es el de la compra (`PROVEEDOR_NO_CORRESPONDE`), igual que los costos informados (D3 del change 06, CAT-06).
- **B.** Cualquier producto; CMP-04 solo se ofrece si el proveedor coincide (porque `COSTO_INFORMAR` exige el proveedor del producto).

**Ejemplo.** Vino A es de Bodega Sur y una vez se compra a Distribuidora Norte. A: hay que cambiar antes el proveedor del producto o comprarlo a Bodega Sur. B: se registra, pero el costo no se puede ofrecer como informado.

### D5 — Cantidades y valores de línea · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** `cantidad > 0` con hasta 3 decimales y `cantidad × unidades` entero (`CANTIDAD_INVALIDA` si no); `valor > 0` con 2 decimales (`VALOR_INVALIDO`); `bonificación` en `[0, 1)` como en CST-02; el mismo producto puede repetirse en varias líneas (caja y suelta), aplicadas en el orden recibido; hasta 200 líneas por compra.
- **B.** Cantidad solo entera.
- **C.** Además, líneas sin cargo (`valor = 0`): exigiría admitir costo cero, que ADR-039 prohíbe (`costo_promedio > 0`).

**Ejemplo.** A: "2,5 cajas x6" = 15 botellas, válido; "2,3 cajas x6" = 13,8, rechazado. La mercadería bonificada se carga como bonificación de la línea paga (12 cajas con 1 de regalo = 13 cajas con bonificación `0.076923`) o en otra línea con valor real.

### D6 — Fecha de la compra y momentos · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** `fecha` es la del comprobante: obligatoria, no posterior a la fecha de negocio de hoy (`FECHA_INVALIDA`), sin límite hacia atrás. Los movimientos de stock y cuenta usan el `occurred_at` del comando (cuándo se registró), así el kardex y el promedio siguen el orden real de proceso; la `fecha` se muestra en listados y en el detalle del movimiento de cuenta.
- **B.** Los movimientos se fechan al inicio del día de `fecha` (zona de la organización): el estado de cuenta queda en orden de factura, pero el kardex mostraría un ingreso "antes" de egresos que en realidad ocurrieron antes de registrarlo.

**Ejemplo.** Factura del 28/09 cargada el 01/10. A: estado de cuenta con la compra el 01/10 y la fecha 28/09 a la vista. B: aparece el 28/09, antes de un pago registrado el 30/09.

### D7 — Oferta de costo informado (CMP-04) · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Se compara el costo base de cada línea con el costo base del costo informado vigente del producto **a la fecha de la compra** (CST-03, cualquier presentación); si difiere o no hay vigente, la respuesta lo lista. Tras confirmar, la pantalla ofrece por línea "Registrar como costo informado" (con `EDITAR_COSTOS`), que envía `COSTO_INFORMAR` con presentación, valor, IVA y bonificación de la línea y `vigencia_desde = fecha de la compra`.
- **B.** Igual, pero con `vigencia_desde = hoy`.
- **C.** La comparación se muestra antes de confirmar (en la vista previa) y no en la respuesta.

**Ejemplo.** Vino A vigente $1.000; compra a $1.100 con fecha 28/09. A: se ofrece; si se acepta, el costo vigente desde el 28/09 es $1.100 (y el 13 lo usará para precios). B: vigente desde el 01/10.

### D8 — Motivos de anulación de compra · de negocio

> **Aprobada 2026-10-02: opción A, con los nombres "Error de carga", "Devolución al proveedor" y "Otro".**

- **A (recomendada).** Sembrar tres motivos del ámbito `ANULACION_COMPRA` — "Error de carga", "Devolución al proveedor", "Otro" — en organizaciones nuevas (`seed`) y, por migración de datos idempotente, en las existentes sin ninguno; más `GET /configuracion/motivos?ambito=` y `GET /configuracion/medios-pago`.
- **B.** Motivo de texto libre en la etapa 1 (contradice `03` §6, `anulacion_motivo_id`).
- **C.** Pantalla de administración de motivos (más alcance).

**Ejemplo.** A: al anular, el usuario elige "Devolución al proveedor" de una lista; los nombres los aprueba el usuario.

### D9 — Reversión del ingreso en `stock` y `costeo` · técnica · ADR pendiente (ADR-044, enmienda ADR-039)

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** `registrar_movimientos` acepta egresos `ANULACION_COMPRA` **con** `costo_unitario` (el costo base de la línea). Para ese tipo, en lugar de `aplicar_egreso`, llama a una función nueva `costeo.revertir_ingreso` (CMP-06, en `costeo/domain`, Hypothesis y fixtures), que devuelve `recalculado` y escribe **siempre** una fila de `costo_producto_mov`: `cantidad` negativa, `costo_ingreso` = costo de la línea, stock anterior/nuevo y `promedio_nuevo = promedio_anterior` cuando no recalcula. Las líneas se revierten en orden inverso. El handler emite `ANULACION_COMPRA_SIN_RECALCULO` con el detalle por producto.
- **B.** Una función `stock.revertir_origen(origen_tipo, origen_id)` que lee los movimientos originales del libro y genera los inversos.
- **C.** Sin fila de historia cuando no recalcula.

**Ejemplo.** Stock 48, promedio $1.050, se anula una compra de 60 a $1.100. A: fila `ANULACION_COMPRA` −60, $1.100, 48 → −12, $1.050 → $1.050, `recalculado = false`; el kardex muestra el egreso a $1.100. C: no queda rastro en la historia de por qué no cambió el promedio (CST-13 lo pide reconstruible).

### D10 — Stock negativo en la anulación · técnica · ADR pendiente (ADR-044)

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** `registrar_movimientos` recibe `permitir_negativo: bool` (el handler lo pasa según `PERMITIR_STOCK_NEGATIVO`) y **solo lo admite para `ANULACION_COMPRA`**; con `true`, el egreso que no alcanza se aplica sin condición y el resultado marca la línea como negativa; el handler emite `STOCK_NEGATIVO`. Sin permiso: `STOCK_INSUFICIENTE`. Modifica la spec `stock/libro-de-stock`.
- **B.** Admitirlo para cualquier egreso desde ya (lo usarán 14 y 18a) — más superficie sin dueño todavía.

**Ejemplo.** Depósito con 48, anulación de 60. A con permiso: −12 y observación; sin permiso: rechazo.

### D11 — Anular con maestros inactivos · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Se puede anular aunque el proveedor, el producto o la presentación se hayan desactivado: revertir no es una operación nueva (CAT-05). La ubicación inactiva sigue bloqueando (y solo se desactiva con saldo cero, `stock/ubicaciones`).
- **B.** Rechazar; hay que reactivar el maestro antes.

**Ejemplo.** Vino A se discontinuó y se desactivó; aparece un error en su última compra. A: se anula directamente. B: reactivar, anular y desactivar de nuevo.

### D12 — Modelo de datos · técnica · ADR pendiente (actualiza `03` §6)

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Sobre `03` §6: `compra` agrega `total_factura` (D1), `numero_comprobante` opcional (D13) y `observacion`; `CHECK` de `condicion`, `estado`, `total_neto >= 0`, `total_factura > 0` y coherencia "anulada ⇔ motivo, momento y usuario". `compra_linea` agrega `orden` y `alicuota_aplicada numeric(9,6)` (congelada, como `costo_informado`), `CHECK (cantidad > 0, valor_presentacion > 0, 0 <= bonificacion < 1, cantidad_base > 0)`. `pago_proveedor` agrega `origen` (`COMPRA`, `INDEPENDIENTE`), `compra_id` (único si no es nulo, FK compuesta), `anulado_en`, `anulado_por_id`, `anulacion_motivo_id` nulable (el 12 decide su motivo). FK compuestas a `proveedor`, `ubicacion`, `producto`, `presentacion`, `medio_pago`, `motivo`, `usuario`, `dispositivo`. `app_runtime`: `SELECT, INSERT, UPDATE` sobre `compra` y `pago_proveedor` (solo estado y anulación), `SELECT, INSERT` sobre líneas y medios; nunca `DELETE` (INV-05).
- **B.** Una tabla `compra_anulacion` aparte (como `venta_anulacion`), sin `UPDATE` sobre `compra`.

**Ejemplo.** Con A, el detalle de una compra anulada sale de una fila; con B, de un join, y `compra` queda inmutable salvo por la existencia de la anulación.

### D13 — Número de comprobante del proveedor · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Campo opcional, informativo y buscable en el listado; sin unicidad.
- **B.** Único por proveedor entre compras confirmadas (evita cargar dos veces la misma factura, pero bloquea casos legítimos como dos remitos con igual número).
- **C.** No se registra en la etapa 1.

**Ejemplo.** "A-0003-00012345": A lo guarda y el listado lo encuentra; B rechazaría una segunda compra con ese número a ese proveedor.

### D14 — Permisos · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** `COMPRA_CONFIRMAR` (también de contado): `REGISTRAR_COMPRA`. `COMPRA_ANULAR` (también con `devuelve_pago`): `ANULAR_COMPRA`; si deja stock negativo, además `PERMITIR_STOCK_NEGATIVO` (CMP-07). Leer compras: `REGISTRAR_COMPRA` o `ANULAR_COMPRA`, sin ocultar costos (la compra es el documento de costo). Ofrecer CMP-04: `EDITAR_COSTOS`. Medios y motivos: cualquier usuario autenticado. Sin permisos nuevos.
- **B.** Contado exige además `REGISTRAR_PAGO_PROVEEDOR` y devolver el pago, `ANULAR_PAGO_PROVEEDOR`.

**Ejemplo.** En las plantillas de `01` §19 ADM y GES tienen todos; la diferencia aparece si una organización arma un rol que compra pero no paga: con A puede registrar contado, con B no.

### D15 — Vista previa y fixtures compartidos · técnica

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Motor compartido (ADR-016): `shared/fixtures/calculo/cmp-02-compra.json` con casos de línea (cantidad base, costo base, importe neto, `CANTIDAD_INVALIDA`), total neto e IVA sugerido (D1), ejecutados por pytest y Vitest **antes** del código; casos de reversión (D9) agregados a `cst-11-costo-promedio.json`. La pantalla calcula con `decimal.js` reutilizando `costoBase.ts`.
- **B.** Endpoint de simulación en el servidor (un viaje por cambio de línea).
- **C.** Sin vista previa; los importes se ven recién en la respuesta.

**Ejemplo.** Caja x12 a $18.000 con IVA: A muestra $1.239,669421 y $14.876,03 al tipear, iguales al servidor por construcción.

### D16 — Ubicación de destino · de negocio

> **Aprobada 2026-10-02: opción A.**

- **A (recomendada).** Cualquier ubicación activa, incluidos vehículos; la regla de ubicación tomada (STK-09) la agrega el change 15 sin cambiar este comando.
- **B.** Solo ubicaciones `DEPOSITO`.

**Ejemplo.** Un proveedor entrega directo en la camioneta: A lo permite hoy; B obliga a ingresar al depósito y transferir (14).

### D17 — Lectura de productos para el formulario de compra · de negocio

> **Aprobada 2026-10-02.** Surgió en el lote 2: `GET /api/v1/catalogo/productos` exigía solo `GESTIONAR_CATALOGO`, y un usuario con solo `REGISTRAR_COMPRA` no podía llenar el selector de productos. Se abre la **lectura** a `GESTIONAR_CATALOGO` **o** `REGISTRAR_COMPRA` (con `requiere_algun_permiso`); editar el catálogo sigue exigiendo `GESTIONAR_CATALOGO`. Se implementa en el lote 3 y se documenta en ADR-043 junto con los códigos de error nuevos del lote 2.

### D18 — Lecturas de apoyo del formulario de compra · de negocio

> **Aprobada 2026-10-02** (revisión de los grupos 11 y 12). Corolario de D17: el formulario de compra necesita, además de los productos, más lecturas que hoy exigen otro permiso. Se abren **solo las lecturas**, con `requiere_algun_permiso`, conservando el permiso que ya las abría; ninguna escritura cambia.

1. **`GET /api/v1/configuracion/alicuotas`** acepta `GESTIONAR_CATALOGO` (o el que ya exigía) **o** `REGISTRAR_COMPRA`: la vista previa de la línea necesita la alícuota del producto. Ya implementado en el lote 2.
2. **`GET /api/v1/proveedores/opciones`** (antes `GESTIONAR_CATALOGO`) y **`GET /api/v1/stock/ubicaciones`** (antes `TRANSFERIR_STOCK`) aceptan además `REGISTRAR_COMPRA`: el formulario ofrece los proveedores activos y las ubicaciones de destino. Implementado en el lote 3 con prueba de integración primero (`test_compras_api.py::test_lecturas_de_apoyo_de_la_compra_aceptan_registrar_compra`); crear o modificar ubicaciones y proveedores sigue exigiendo su permiso (`test_abrir_las_lecturas_de_apoyo_no_abre_escrituras`). Los ratchets de permiso por ruta (`test_ratchet_permiso_por_ruta`, `test_inv21_ratchet_rutas`) no requirieron cambios: reconocen el marcador `permiso_requerido` de `requiere_algun_permiso` (unido con ` o `) y la ruta sigue filtrando por la organización del token (INV-21).

**Desvíos aceptados (sin decisión nueva, quedan registrados):** (a) la fecha por defecto del formulario es la fecha local del navegador, porque `/yo` no entrega la zona horaria de la organización; el servidor sigue validando `FECHA_INVALIDA` contra su fecha de negocio (D6); (b) las cantidades de las pantallas se muestran como "5 cajas + 1 un." con el formateador de stock existente (CAT-08); (c) la condición por defecto es "A crédito". Los puntos 1 y 2 y los códigos de error nuevos se documentan en ADR-043.

## Detalles derivados (no requieren decisión)

- **Módulo:** compras y pagos viven en `proveedores` (`02` §5.1, `03` §3), con `domain/compras.py`; `proveedores → catalogo, stock, costeo, cuentas_corrientes, configuracion` solo por `service.py` (`02` §5.3; `configuracion` está permitido para todos). Contrato de import-linter actualizado.
- **Orden de bloqueo:** confirmar = proveedor `FOR SHARE` → `saldo_cuenta` del proveedor (`cuentas_corrientes.bloquear_saldo`) → `stock.registrar_movimientos` (costo, saldos) → movimientos de cuenta. Anular = compra `FOR UPDATE` (rechazo `COMPRA_YA_ANULADA` con la fila tomada) → mismo orden.
- **Validación antes de escribir:** forma (pura), referencias, cálculo de líneas y totales; recién después bloqueos y escrituras (INV-01).
- **Auditoría:** una por comando, la del bus (ADR-022, AUD-01).
- **Endpoints:** `POST /api/v1/compras`, `POST /api/v1/compras/{id}/anulacion`, `GET /api/v1/compras`, `GET /api/v1/compras/{id}`, `GET /api/v1/configuracion/medios-pago`, `GET /api/v1/configuracion/motivos?ambito=`; filtro `proveedor_id` en `GET /api/v1/catalogo/productos`. Rutas en los ratchets de aislamiento y permisos.
- **Resultado de `COMPRA_CONFIRMAR`:** `{compra_id, total_neto, total_factura, pago_id?, diferencias_de_costo: [...]}`; de `COMPRA_ANULAR`: `{compra_id, estado, pago_anulado}` más observaciones.
- **INV-18:** `proveedores/service.py` registra `_presentacion_tiene_compra` al importarse.

## Risks / Trade-offs

- [Reversión del promedio no exactamente inversa por dos redondeos a 6 decimales] → la propiedad de la spec admite `0.000001 × (S+q)/S`; documentado en el ADR de D9.
- [Anular una compra vieja después de muchas otras cambia el promedio "hacia atrás"] → es lo que pide CMP-06; la historia deja la fila con `recalculado` y la observación cuando no aplica.
- [Ampliar `registrar_movimientos` rompe a sus llamadores] → parámetros nuevos con valor por defecto que conserva el comportamiento del 09; la suite del 09 corre como red de seguridad.
- [Pago creado por el 11 sobre tablas que diseña el 12] → D12 deja `origen`, `compra_id` y anulación; el 12 agrega sin migrar lo existente.
- [Migración de datos de motivos] → idempotente (`WHERE NOT EXISTS`), probada con `downgrade`/`upgrade`.

## Migration Plan

Una revisión de Alembic: crea `compra`, `compra_linea`, `pago_proveedor`, `pago_proveedor_medio` con FK compuestas, `CHECK` e índices `(organizacion_id, fecha DESC, id)`, `(organizacion_id, proveedor_id, fecha DESC)`, `compra_linea (organizacion_id, presentacion_id)` (verificador INV-18) y `pago_proveedor (organizacion_id, compra_id)`; `GRANT` según D12; inserta los motivos de D8 donde falten. `downgrade` borra las tablas (sin datos en producción) y los motivos sembrados sin uso. No toca libros ni saldos existentes.

## Open Questions

Ninguna: D0 a D16 aprobadas el 2026-10-02 (tarea 0.1); D17 y D18 aprobadas durante el apply.
