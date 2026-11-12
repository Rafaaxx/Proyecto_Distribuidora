# Propuesta de cambios a `docs/` — change 19 `venta-anulacion`

> Completada en el apply (tarea 15.1) con el texto actual de cada sección y el propuesto, según lo aprobado: D0 a D19 en la opción A (tarea 0.1, 2026-10-24), los textos de ayuda (0.2, 2026-10-24), el orden de bloqueo (7.1, 2026-10-27) y las precisiones del apply de ADR-058. **No se aplica a `docs/`** sin el visto bueno del usuario: `docs/01` a `docs/04` siguen como estaban. Al aplicarla, los textos propuestos reemplazan a los actuales.

## `01-dominio.md`

### §11.3 VTA-21 (D5, D6, D7)

**Actual:** "La anulación ingresa el stock a la ubicación original al costo congelado de cada línea (recalculando el promedio según CST-11) y registra un crédito en la cuenta corriente por el total de la venta."

**Propuesto:** "La anulación ingresa el stock a la ubicación original al costo unitario congelado de cada línea (recalculando el promedio según CST-11) y registra un crédito en la cuenta corriente por el total de la venta. Una línea vendida sin costo ingresa sin recalcular el promedio (CST-12). La ubicación tomada se rige por STK-09: con la ubicación tomada por otra jornada anula solo quien tiene `LIBERAR_UBICACION`; si no, `UBICACION_TOMADA`. Se anula aunque el cliente, el producto o la presentación se hayan desactivado; una ubicación inactiva la rechaza (`UBICACION_INACTIVA`) (ADR-058)."

### §11.3 VTA-22 (D2, D3, D9)

**Actual:** "Al anular se indica si se devuelve el dinero cobrado con la venta. Si se devuelve, se anula también esa cobranza; si no, queda como saldo a favor."

**Propuesto:** "Al anular se indica si se devuelve el dinero cobrado con la venta. Si se devuelve, se anula también esa cobranza, con el motivo y la observación de la venta; si no, queda como saldo a favor. Indicarlo es obligatorio si la venta tiene su cobranza confirmada y no corresponde si no la tiene (`DEVOLUCION_INVALIDA`). Al consumidor final siempre se le devuelve (`CONSUMIDOR_FINAL_SIN_DEVOLUCION`): no tiene cuenta donde dejarle saldo a favor (ADR-058)."

### §11.3 VTA-24 (D1, D19)

**Actual:** "Sin conexión, un vendedor con `ANULAR_VENTA` puede anular solo ventas de su jornada en curso. La anulación es un comando que referencia el `operation_id` de la venta."

**Propuesto:** "Sin conexión, un vendedor con `ANULAR_VENTA` puede anular solo ventas de su jornada en curso. La anulación es un comando que referencia a la venta por su identificador, que el dispositivo genera al confirmarla. Hasta el change 22c `VENTA_ANULAR` solo admite el modo `ONLINE` (ADR-058)."

### §6.2 CST-12 (D5)

**Actual:** "Las transferencias, los ajustes y las rendiciones no modifican el promedio ni dejan historia de costo. Todo movimiento de transferencia o de ajuste, de ingreso o de egreso, y los egresos de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. Un ajuste positivo de un producto sin promedio se rechaza (`PRODUCTO_SIN_COSTO`). Los movimientos inversos de la anulación de una transferencia o de un ajuste repiten el costo del movimiento original, no el promedio del momento (ADR-048)."

**Propuesto:** agregar al final: "El reingreso de una línea de venta sin costo, al anular la venta, sube el stock sin modificar el promedio ni dejar historia, con costo nulo (ADR-058)."

### §20 INV-19 (D4) y cobertura

**Actual (tabla):** "INV-19 | Anular una venta deja el stock y el saldo del cliente como si no se hubiera registrado, sin borrar ningún registro. | Nuevo".

**Propuesto:** agregar una nota debajo de la tabla: "INV-19 (VTA-22): con devolución del dinero, el stock y el saldo del cliente quedan exactamente como antes de la venta; sin devolución, el saldo difiere solo en el importe cobrado, que queda a favor del cliente (ADR-058)." y, junto a las demás notas de cobertura: "INV-01, INV-05, INV-06, INV-10, INV-12, INV-13, INV-19 e INV-21 tienen pruebas que los citan por ID en el change 19, incluidas pruebas de concurrencia con commits reales (dos anulaciones de la misma venta; la anulación con devolución frente a `COBRANZA_ANULAR`; la anulación frente a una venta, a la desactivación del producto y a la apertura de una jornada) y una propiedad con SQL (confirmar y anular con devolución deja stock y saldo como antes, y los libros solo crecen)."

### §21 Efectos de cada evento

Sin cambios: la fila "Anulación de venta" (stock `+`, costo `Recalcula`, cuenta del cliente `− total`) ya describe el efecto.

### §19 Permisos

La matriz no cambia (`ANULAR_VENTA` ya existe y no se suma ningún permiso).

**Actual (final del primer párrafo de ventas):** "... Con `VENDER` se leen, solo para vender, ... las reglas de descuento aplicables con su nombre (ADR-055)."

**Propuesto:** agregar al final del párrafo: "El detalle de la venta trae, si está anulada, la anulación (momento, usuario y motivo con sus nombres, observación y si se devolvió el dinero) y la marca de si el cliente es el consumidor final; el listado filtra por estado (`CONFIRMADA` o `ANULADA`, REP-02). Anular exige `ANULAR_VENTA` (y `LIBERAR_UBICACION` solo si la ubicación está tomada por otra jornada, STK-09); no exige `PERMITIR_STOCK_NEGATIVO` porque solo ingresa stock (ADR-058)."

## `02-arquitectura.md`

### §6.5 Tipos de comando

**Actual (fila):** "`VENTA_ANULAR` | ✓ | ✓ (VTA-24)".

**Propuesto (fila):** "`VENTA_ANULAR` | ✓ | (change 22c, VTA-24)".

**Actual (párrafo de `COMPRA_ANULAR`):** "Un handler puede devolver, además del resultado, observaciones de negocio (SYN-04, SYN-07): ... `COMPRA_ANULAR` lleva `devuelve_pago` ... (ADR-043, ADR-044). ..."

**Propuesto (párrafo nuevo a continuación):** "`VENTA_ANULAR` (`ANULAR_VENTA`; solo `ONLINE` hasta el change 22c) lleva la venta (`venta_id`, el identificador que generó el dispositivo), un motivo del ámbito `ANULACION_VENTA`, una observación opcional de hasta 500 caracteres y `devuelve_dinero` (booleano estricto: obligatorio si la venta tiene su cobranza confirmada y omitido si no). Errores propios: `VENTA_YA_ANULADA` y `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409) y `DEVOLUCION_INVALIDA` (422); además `MOTIVO_INVALIDO`, `OBSERVACION_INVALIDA`, `UBICACION_TOMADA` y `UBICACION_INACTIVA`. Ruta `POST /api/v1/ventas/{venta_id}/anulacion`. No emite observaciones de SYN-07: el reingreso nunca deja stock negativo. Una fila de auditoría por comando, con el motivo y, en su observación, la cobranza anulada y la constancia de la ubicación tomada (AUD-01, AUD-02, ADR-058)."

### §7.3 Orden global de bloqueo (D10)

**Actual:** "Las filas de la propia operación que el comando corrige o anula se toman **antes** del nivel 1, en este orden: la compra (`FOR UPDATE`) y después su pago (`FOR UPDATE`); o la transferencia o el ajuste (`FOR UPDATE`), que se anula una sola vez."

**Propuesto:** "... en este orden: la compra (`FOR UPDATE`) y después su pago (`FOR UPDATE`); o la venta (`FOR UPDATE`) y después su cobranza (`FOR UPDATE`); o la transferencia o el ajuste (`FOR UPDATE`), que se anula una sola vez."

**Actual (frase sobre cobranzas):** "`COBRANZA_ANULAR` toma la cobranza `FOR UPDATE` antes de `saldo_cuenta`; `COBRANZA_REGISTRAR` parte del nivel 1 y lee la jornada `FOR SHARE` en el nivel 5 (ADR-052)."

**Propuesto (agregar a continuación):** "`VENTA_ANULAR` toma la venta y después su cobranza de origen `VENTA`, antes de `saldo_cuenta` (nivel 1), y luego un ingreso por línea por el mismo `registrar_movimientos` (niveles 2 a 5); anular una venta y `COBRANZA_ANULAR` sobre su cobranza a la vez no se interbloquean y dejan una sola anulación de la cobranza. Precedencia de rechazos de `VENTA_ANULAR`: contenido, venta (404 y `VENTA_YA_ANULADA`), motivo, dinero cobrado (`DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`), ubicación (`UBICACION_INACTIVA`, `UBICACION_TOMADA`) (ADR-058)."

### §7.4 Stock

**Actual (frase final sobre el producto inactivo, si la hubiera, y sobre stock negativo):** "Con el permiso se admite solo para la salida de una transferencia, la anulación de una compra, la de una transferencia y la de un ajuste; **nunca** para un ajuste ni para la corrección de un stock inicial ..."

**Propuesto:** sin cambios en esa frase (la anulación de venta solo ingresa); agregar al final de la sección: "El ingreso `ANULACION_VENTA` se acepta con el producto inactivo, como `ANULACION_COMPRA` (ADR-044 punto 5 enmendado por ADR-058); una ubicación inactiva lo rechaza siempre."

## `03-modelo-de-datos.md`

### §12 `venta` (D11)

**Actual:** "`app_runtime`: `SELECT, INSERT` en `venta` y `venta_linea`, sin `UPDATE` ni `DELETE` (el change 19 agrega `UPDATE` de `venta.estado`). `venta_linea_descuento` llega con el 18b y `venta_anulacion` con el 19 (ADR-054)."

**Propuesto:** "`app_runtime`: `SELECT, INSERT` en `venta` y `venta_linea`; `UPDATE` solo de `venta.estado` (que pasa de `CONFIRMADA` a `ANULADA`, una sola vez) y nunca `DELETE` (INV-05). `venta_linea` no tiene `UPDATE`. `venta_linea_descuento` llegó con el 18b y `venta_anulacion` con el 19 (ADR-054, ADR-058)."

### §12 `venta_anulacion` (D11)

**Actual:** "`id`, `organizacion_id`, `venta_id` (único), `motivo_id`, `observacion`, `devuelve_dinero` `boolean` (VTA-22), columnas de operación."

**Propuesto:** "`id`, `organizacion_id`, `venta_id`, `motivo_id`, `observacion` (opcional, hasta 500), `devuelve_dinero` `boolean` (VTA-22; nulo si y solo si la venta no tenía cobranza confirmada), `jornada_id` (nulable: la jornada `ABIERTA` del usuario y el dispositivo sobre la ubicación de la venta, STK-09), columnas de operación. Claves foráneas compuestas a `venta`, `motivo`, `jornada`, `usuario` y `dispositivo`; `UNIQUE (organizacion_id, venta_id)` (una sola anulación por venta) e índice por `(organizacion_id, venta_id)`. `app_runtime` tiene `SELECT, INSERT` y nunca `UPDATE` ni `DELETE` (INV-05). Migración `d9e0f1a2b3c4`: el `downgrade` aborta con un mensaje claro si hay una venta `ANULADA` (ADR-058)."

### §4 `motivo` (D12)

**Actual (final del párrafo de motivos):** "... Las organizaciones nuevas nacen también con tres motivos del ámbito `LISTA_ANTERIOR` ("Precio acordado con el cliente", "Error en la lista vigente" y "Otro", aprobados el 2026-10-17); la migración del change 18a (`a2b3c4d5e6f7`) los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-054)."

**Propuesto (agregar al final):** "Las organizaciones nuevas nacen también con tres motivos del ámbito `ANULACION_VENTA` ("Error de carga", "Devolución del cliente" y "Otro"); la migración del change 19 (`d9e0f1a2b3c4`) los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-058)."

### §15 INV-05

**Actual (final de la fila):** "... y de cobranzas (`UPDATE` solo del estado; anulación única por `cobranza_anulacion.cobranza_id`) y de `venta` y `venta_linea` (sin `UPDATE` ni `DELETE`)".

**Propuesto:** "... y de cobranzas (`UPDATE` solo del estado; anulación única por `cobranza_anulacion.cobranza_id`), de `venta` (`UPDATE` solo de `estado`, sin `DELETE`), de `venta_linea` (sin `UPDATE` ni `DELETE`) y de `venta_anulacion` (solo `SELECT` e `INSERT`; anulación única por `venta_anulacion.venta_id`)".

## `04-roadmap-changes.md`

### §9 Hito 5 — fila del change 19

**Actual:** "19 | `venta-anulacion` | Anulación con motivo, reversión de stock y cuenta corriente, decisión sobre el dinero cobrado | INV-19".

**Propuesto:** sin cambios en la fila; la lista de invariantes con pruebas citadas está en `01` §20.

### §9 Nota al archivar el change 19 (deudas)

**Propuesto (párrafo nuevo después de las notas de los changes 18a y 18b):** "**Change 19 (`venta-anulacion`) — deudas saldadas (ADR-058):** del 18a, el `UPDATE` de `venta.estado` y la anulación de la cobranza de la venta con la venta (ADR-054 deuda 4; ADR-052 deuda 1; VTA-22). **Deudas nuevas:** al **20** (`nota-de-venta`), decidir si la nota de una venta anulada lleva una marca; al **22c**, habilitar `VENTA_ANULAR` sin conexión sin una v2 del comando (VTA-24: la regla de la jornada en curso, con la venta y la anulación con la misma jornada del sobre, `JORNADA_AJENA` si no, y la venta inexistente como dependencia inexistente); al **24** (rendición), contar las anulaciones en la rendición (RUT-07) con `venta_anulacion`; al **26** (reportes), excluir las ventas anuladas e informarlas aparte (REP-02), con el filtro por estado que el 19 ya dejó en el listado; **al roadmap de facturación**, VTA-23 (no se anula una venta con estado de facturación `PARCIAL` o `FACTURADA` sin anular antes la factura; el módulo de facturación agrega la regla) y excluir las anuladas de lo facturable; **a quien lo necesite**, un producto inactivo puede quedar con stock tras una anulación (se reactiva para moverlo) y la pantalla de anulación no nombra quién tiene la ubicación tomada (el error no lo informa)."
