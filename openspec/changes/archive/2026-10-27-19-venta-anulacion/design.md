# Diseño técnico — 19-venta-anulacion

> **Estado: D0 a D19 APROBADAS en la opción A por el usuario el 2026-10-24 (tarea 0.1).** *Texto original del propose:* Specs, tareas, `propuesta-docs.md` y el borrador de **ADR-058** (*Propuesto*) están escritos con la opción A de cada decisión. Si el usuario elige otra opción, se revisan los tres artefactos antes del apply (tarea 0.1).
>
> **Gobernanza por dominio.** La anulación mueve dinero y dos libros (stock y cuenta corriente) y anula una cobranza. **CRÍTICO** (borrador mostrado y aprobado antes de escribir el código): **D10** (transacción, orden de bloqueo y precedencia de rechazos). **ALTO** (se propone y se espera revisión): **D1** (contrato del comando), **D4** (INV-19 frente a VTA-22), **D5** (costo del reingreso y líneas sin costo), **D6** (ubicación original tomada), **D9** (anulación de la cobranza desde `ventas`), **D14** (permisos y lecturas), **D15** (auditoría), **D19** (preparación de VTA-24). **MEDIO:** D2, D3, D7, D8, D11, D16. **BAJO:** D0, D12, D13, D17, D18. **De negocio** (el agente no decide; solo recomienda): D2, D3, D4, D5, D6, D7, D12, D13.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Venta** (18a, 18b; ADR-054, ADR-055): tablas `venta` (con `estado` `CONFIRMADA`/`ANULADA` y su `CHECK`, `ubicacion_id`, `jornada_id`, `cliente_id`, `total`, `estado_facturacion`), `venta_linea` (con `cantidad_base`, `costo_unitario numeric(18,6)` y `costo_total numeric(14,2)`, ambos nulos en una línea vendida sin costo, VTA-05, `VENTA_SIN_COSTO`) y `venta_linea_descuento`. `app_runtime` no tiene `UPDATE` sobre `venta` ("el change 19 agrega el `UPDATE` de `estado`", `03` §12). `GET /ventas` y `GET /ventas/{id}` con `VENDER` o `ANULAR_VENTA`; la pantalla de detalle ya muestra el estado y la cobranza con "(anulada)".
- **Stock y costeo** (09, 11, 14, 15): `stock/service.py::registrar_movimientos` es la única puerta del libro; `ANULACION_VENTA` ya está en el catálogo de tipos (STK-03), en `TIPOS_QUE_INGRESAN_CON_COSTO` (recalcula por CST-11 con `costeo.aplicar_ingreso` y deja fila en `costo_producto_mov`, cuyo `origen_tipo` ya admite `ANULACION_VENTA`) y en el `CHECK` de `stock_movimiento`. Hoy un ingreso de ese tipo **exige costo** (sin costo es `COSTO_INVALIDO`) y **exige producto activo** (la exención es solo de `ANULACION_COMPRA`, ADR-044 punto 5). La regla de toma (STK-09, ADR-049) decide por ubicación: libre, de la jornada (jornada `ABIERTA` con el usuario y el dispositivo del comando) o por la excepción de `LIBERAR_UBICACION`; si no, `UBICACION_TOMADA`.
- **Cuenta corriente** (08): `ANULACION_VENTA` está en el catálogo de cliente con sentido `REDUCE` (CC-02); `registrar_movimiento` bloquea `saldo_cuenta`.
- **Cobranzas** (17): `cobranza` (con `venta_id`, `origen`, `estado`), `cobranza_anulacion` (única por cobranza, con `motivo_id`) y `ANULACION_COBRANZA` (`AUMENTA`). `anular_cobranza` exige un motivo de `ANULACION_COBRANZA` y **rechaza** la de origen `VENTA` con `COBRANZA_DE_VENTA` (VTA-22, D7 del 17). `cobranza_de_venta(venta_id)` lee la cobranza de una venta.
- **Configuración**: el ámbito `ANULACION_VENTA` existe en el `CHECK` de `motivo` desde el change 02, **sin motivos sembrados**. `GET /configuracion/motivos?ambito=` con cualquier sesión.
- **Permiso** `ANULAR_VENTA` en el catálogo (plantillas Administrador, Administración y Supervisor comercial; el Vendedor no lo tiene, `01` §19). `02` §6.5 lista `VENTA_ANULAR` como `ONLINE` y `OFFLINE` (VTA-24).

Lo que `docs/` **no** resuelve o resuelve de forma ambigua (cada punto es una decisión):

- VTA-24 dice que la anulación "referencia el `operation_id` de la venta"; la venta ya tiene un identificador generado por el dispositivo. → D1, D19.
- VTA-22 no dice si indicar la devolución es obligatorio, ni qué pasa si la venta no tuvo cobranza. → D2.
- El consumidor final no tiene cuenta (CC-08, CLI-03): sin devolución, ¿a quién le queda el saldo a favor? → D3.
- INV-19 ("deja el saldo del cliente como si no se hubiera registrado") choca con VTA-22 sin devolución, donde el cobro queda como saldo a favor. → D4.
- VTA-21 dice "al costo congelado de cada línea": el costo congelado es un total redondeado a 2 decimales; y una línea vendida sin conexión puede no tener costo (`VENTA_SIN_COSTO`, ADR-054). → D5.
- VTA-21 dice "a la ubicación original", pero esa ubicación puede estar tomada por otra jornada (STK-09). → D6.
- Nada dice si se anula una venta cuyo producto, presentación, cliente o ubicación se desactivaron. → D7.
- Nada dice qué jornada lleva la anulación con conexión ni si se anula una venta de una jornada ya cerrada. → D8.
- `cobranza_anulacion.motivo_id` es obligatorio y la validación exige el ámbito `ANULACION_COBRANZA`; la anulación de la venta trae un motivo de `ANULACION_VENTA`. → D9.
- `02` §7.3 no tiene la fila de la venta entre "las filas de la propia operación". → D10.
- `03` §12 define `venta_anulacion` con "columnas de operación", sin decir si lleva jornada ni qué vale `devuelve_dinero` sin cobranza. → D11.
- No hay motivos sembrados de `ANULACION_VENTA`. → D12.
- VTA-23 (factura) es de la etapa de facturación. → D13.

## Goals / Non-Goals

**Goals:** anulación total con conexión por el bus, en una sola transacción, con los dos libros revertidos y el promedio recalculado; anulación de la cobranza en el acto desde la misma transacción; pantalla en `/admin`; contrato que el 22c pueda recibir sin conexión sin cambiar de versión.

**Non-Goals:** anulación sin conexión (22c); devolución parcial (etapa 2); notas de crédito o reembolsos como operación propia; imputación del saldo a favor; efectos en la nota de venta (20), la rendición (24) y los reportes (26), salvo dejar los datos que esos changes necesitan.

## Decisions

### D0 — Tamaño y lotes · técnica · BAJO

**Contexto.** `04` §2 pide de medio día a tres días. El change suma un comando, una tabla, una función de cobranzas, dos ajustes del libro de stock, lecturas y una pantalla.

- **A (recomendada). Un change en cuatro lotes**, sin frenar entre lotes salvo en los puntos de control: **Lote 1** fixtures compartidos (`cst-11`, `vta-22`) y dominio puro de la anulación (Python y TypeScript); **Lote 2** migración, modelos, siembra de motivos, ajustes de `stock` (D5, D7) y `cobranzas/service.py::anular_cobranza_de_venta` (D9); **Lote 3 (CRÍTICO)** `VENTA_ANULAR` con su transacción (D10), auditoría (D15) y lecturas (D14); **Lote 4** pantallas, ayuda, concurrencia, propiedades, cobertura, ADR, docs y prueba manual. Consecuencia: entra en el tamaño de `04` §2 o lo pasa por poco; si lo pasa, se anota como excepción.
- **B. Dividir en `19a` (backend) y `19b` (pantalla).** Consecuencia: el 19a se archiva sin flujo en el navegador (`04` §2.1 punto 5).
- **C. Sumar ya la anulación sin conexión (VTA-24).** Consecuencia: adelanta el 22c sin cola ni Dexie, sin forma de probarla de punta a punta.

### D1 — Contrato de `VENTA_ANULAR` · contrato · ALTO

**Contexto.** VTA-20, VTA-22, VTA-24, `02` §6.5, patrón de `COBRANZA_ANULAR` (`POST /cobranzas/{id}/anulacion`) y `COMPRA_ANULAR` (`devuelve_pago`).

- **A (recomendada).** `VENTA_ANULAR` v1, permiso `ANULAR_VENTA`, `admite_online=True`, `admite_offline=False` (D19). Contenido (`extra="forbid"`): `venta_id` (el identificador de la venta, que genera el dispositivo al confirmarla, `02` §9), `motivo_id`, `observacion` opcional (hasta 500 caracteres, `OBSERVACION_INVALIDA`) y `devuelve_dinero` (booleano estricto, opcional según D2). Ruta `POST /api/v1/ventas/{venta_id}/anulacion` (el `venta_id` de la ruta entra al contenido y a la huella, como en cobranzas). Resultado: `venta_id`, `estado` (`ANULADA`), `saldo` del cliente después (string), `cobranza_id` y `cobranza_anulada` (booleano). Se propone precisar VTA-24: "referencia a la venta por su identificador, que el dispositivo genera junto con su `operation_id`". Consecuencia: un solo identificador en todo el sistema; el 22c lo tiene en Dexie.
- **B. Referenciar por `venta_operation_id`.** Consecuencia: literal con VTA-24, pero obliga a una búsqueda por `operation_id` que hoy no existe en `venta` (no hay índice) y a dos identificadores para el mismo recurso en la API.
- **C. Llevar los dos.** Consecuencia: redundancia y un error nuevo cuando no coinciden.

### D2 — Indicar si se devuelve el dinero · negocio · MEDIO

**Contexto.** VTA-22; ADR-043 punto 3 (`devuelve_pago`: obligatorio en contado, prohibido en crédito, `CONDICION_INVALIDA`).

- **A (recomendada). Obligatorio si la venta tiene cobranza `CONFIRMADA`; prohibido si no la tiene** (venta sin cobro). Faltante o sobrante es `DEVOLUCION_INVALIDA` (422). Mismo criterio que compras. Consecuencia: nadie anula sin pensar en el dinero; la pantalla solo pregunta cuando hubo cobro.
- **B. Opcional, por defecto "no se devuelve".** Consecuencia: un olvido deja saldo a favor sin que nadie lo haya decidido.
- **C. Siempre obligatorio, también sin cobranza.** Consecuencia: una pregunta sin sentido en las ventas sin cobro.

### D3 — Consumidor final · negocio · MEDIO

**Contexto.** CLI-03 y VTA-11 (al consumidor final se le vende solo de contado), CC-08 y COB-01 (no tiene cuenta propia: `CONSUMIDOR_FINAL_SIN_CUENTA`). Sin devolución, el saldo a favor quedaría en una cuenta anónima que nadie puede usar.

- **A (recomendada). Al anular una venta del consumidor final, la devolución es obligatoria:** `devuelve_dinero = false` es `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409). La pantalla no ofrece la opción. Si la venta llegó sin conexión con cobranza distinta del total (`CONSUMIDOR_FINAL_CON_DEUDA`) o sin cobranza, rige D2 igual (con cobranza, se devuelve). Consecuencia: la cuenta del consumidor final vuelve a cero.
- **B. Permitir "no se devuelve".** Consecuencia: saldo a favor en el consumidor final, sin dueño ni forma de usarlo (no admite cobranza independiente ni saldo inicial).
- **C. Ignorar el valor y devolver siempre.** Consecuencia: el comando miente sobre lo que pidió el usuario.

### D4 — INV-19 frente a VTA-22 · negocio · ALTO

**Contexto.** INV-19: "Anular una venta deja el stock y el saldo del cliente como si no se hubiera registrado". VTA-22: sin devolución, el cobro "queda como saldo a favor". `01` §21: la anulación de venta es "− total" en la cuenta. CC-05: la venta y su cobranza son movimientos distintos.

- **A (recomendada). INV-19 se refiere a los efectos de la venta; la cobranza es una operación propia.** La anulación revierte siempre el débito `VENTA` (con `ANULACION_VENTA` por el total) y todo el stock; con devolución revierte también la cobranza y el saldo queda exactamente como antes de la venta; sin devolución el saldo queda como antes de la venta **menos lo cobrado**. Las pruebas de INV-19 comparan con devolución (igualdad exacta) y sin devolución (igualdad salvo el importe de la cobranza). Se propone precisar INV-19 en `01`. Consecuencia: ninguna regla cambia; se explicita la lectura.
- **B. Leer INV-19 al pie de la letra y devolver siempre.** Consecuencia: deroga VTA-22 (decisión del cliente que no le toca al agente).

**Ejemplo (`01` §9.2).** Saldo $150.000, venta $80.000 con cobranza de $20.000 → saldo $210.000. Anulación con devolución: −$80.000 + $20.000 → $150.000. Sin devolución: −$80.000 → $130.000 ($20.000 a favor respecto de antes de la venta).

### D5 — Costo del reingreso y línea vendida sin costo · negocio y costeo · ALTO

**Contexto.** VTA-21 ("al costo congelado de cada línea, recalculando el promedio según CST-11"), VTA-05 (costo total redondeado a 2 decimales), CST-11, CST-13, ADR-054 punto sobre `VENTA_SIN_COSTO` (línea con costo nulo), CST-12 (un ingreso sin costo no recalcula).

- **A (recomendada).** Cada línea ingresa `cantidad_base` unidades con tipo `ANULACION_VENTA`, origen `VENTA`/`venta_id`, a su **`costo_unitario` congelado** (el promedio de 6 decimales con que salió, no `costo_total / cantidad`, que arrastraría el redondeo a 2 decimales); recalcula el promedio por CST-11 y deja una fila en `costo_producto_mov`. **Una línea con costo nulo** ingresa **sin recalcular** el promedio y sin fila de historia, con el movimiento a costo nulo (el mismo con que salió), como un ingreso sin costo (CST-12); `stock_total` sube igual. Las líneas se aplican en el orden de la venta; un mismo producto en dos presentaciones son dos ingresos. Fixtures en `cst-11` antes del código (D17).
- **B. Línea sin costo valorizada al promedio vigente, sin recalcular.** Consecuencia: el kardex muestra un costo que la venta nunca tuvo; el promedio queda igual que en A.
- **C. Rechazar la anulación si alguna línea no tiene costo.** Consecuencia: una venta sin conexión con `VENTA_SIN_COSTO` no se puede corregir nunca.

**Ejemplo (`01` §6, CST-11).** Después de "Compra 60 a $1.200" (stock 108, promedio $1.133,333333) se anula la "Venta 72 (costo congelado $75.600,00)", cuyo costo unitario es $1.050,000000: (108 × 1.133,333333 + 72 × 1.050) / 180 = $1.100,000000 (redondeo a 6 decimales). Si el stock total previo fuera 0, el promedio pasa a $1.050,000000.

### D6 — Ubicación original tomada por una jornada · negocio · ALTO

**Contexto.** VTA-21 ("a la ubicación original"), STK-09 (solo la jornada que tomó la ubicación la mueve, salvo `LIBERAR_UBICACION`), RUT-04. La plantilla Administración tiene `ANULAR_VENTA` pero no `LIBERAR_UBICACION`.

- **A (recomendada). STK-09 rige igual.** Si la ubicación de la venta está tomada por una jornada que no es la del comando, anula solo quien tiene `LIBERAR_UBICACION` (sin `jornada_id` en el movimiento y con la constancia en la auditoría, como cualquier movimiento por excepción); el resto recibe `UBICACION_TOMADA` (409) y espera a que la jornada cierre o pide a un supervisor. Consecuencia: ninguna regla nueva; una oficina sin supervisor espera al cierre.
- **B. La anulación de venta queda exceptuada de STK-09** (como la venta sin conexión), con constancia. Consecuencia: el stock del vehículo sube mientras otro vendedor lo usa y su rendición no lo explica.
- **C. El usuario elige la ubicación de reingreso.** Consecuencia: contradice VTA-21 y exige cambiarla.

**Ejemplo.** Juan vendió ayer desde la camioneta 2; hoy la camioneta 2 la tiene Pedro. `ges01` (Administración) anula: `UBICACION_TOMADA`. `sup01` (Supervisor, con `LIBERAR_UBICACION`) anula: la mercadería vuelve a la camioneta 2 y la auditoría nombra la jornada de Pedro.

### D7 — Maestros inactivos · negocio · MEDIO

**Contexto.** CMP-05 y ADR-043 punto 8 / ADR-044 punto 5 (una compra se anula con proveedor, producto o presentación inactivos; una ubicación inactiva bloquea), COB-05 (se anula con el cliente inactivo), CAT-05.

- **A (recomendada). Se anula aunque el cliente esté suspendido o inactivo, o el producto o la presentación estén inactivos; una ubicación inactiva rechaza** (`UBICACION_INACTIVA`, 409). El libro de stock suma `ANULACION_VENTA` a la exención de producto activo. Consecuencia: igual que compras; un producto inactivo puede quedar con stock y se reactiva para venderlo o ajustarlo.
- **B. Rechazar con producto inactivo** (`PRODUCTO_INACTIVO`). Consecuencia: hay que reactivar el producto para anular; la anulación depende de un maestro.
- **C. Admitir también la ubicación inactiva.** Consecuencia: stock en una ubicación que no se puede usar ni listar entre las activas.

### D8 — Jornada de la anulación · negocio · MEDIO

**Contexto.** RUT-04, RUT-07 ("ventas, anulaciones" en el resumen de rendición, change 24), STK-09, VTA-24 (sin conexión, solo ventas de la jornada en curso), D3 del 18a.

- **A (recomendada). La anulación con conexión no elige jornada:** si el usuario y el dispositivo tienen una jornada `ABIERTA` cuya ubicación es la de la venta, el reingreso es "de la jornada" y la anulación guarda esa `jornada_id`; en cualquier otro caso queda sin jornada. Una venta de una jornada cerrada, liberada o en rendición **se anula igual** con conexión (la regla de la jornada en curso es solo de VTA-24). `venta_anulacion.jornada_id` deja al 24 contar las anulaciones de la jornada y a la venta su propia jornada. Consecuencia: una sola regla, la de STK-09.
- **B. La anulación nunca lleva jornada.** Consecuencia: el 24 no distingue una anulación hecha por el vendedor en ruta.
- **C. Con conexión, solo ventas de una jornada no cerrada.** Consecuencia: una venta mal cargada ayer no se corrige más.

### D9 — Anulación de la cobranza desde `ventas` · arquitectura · ALTO

**Contexto.** `02` §5.3 (`ventas ──► cobranzas` solo por `service.py`), COB-05, VTA-22, ADR-046 punto 2 ("un pago anulado junto con su compra lleva el motivo de la compra").

- **A (recomendada). Función nueva `cobranzas/service.py::anular_cobranza_de_venta(venta_id, motivo_id, observacion, …)`** que ventas llama dentro de su transacción, con la cobranza ya tomada `FOR UPDATE` por `cobranzas/service.py::tomar_cobranza_de_venta` (D10): deja la cobranza `ANULADA`, inserta `cobranza_anulacion` **con el motivo de la venta** (ámbito `ANULACION_VENTA`) y la observación de la anulación, y registra `ANULACION_COBRANZA` `AUMENTA` por el importe completo. `anular_cobranza` (el comando `COBRANZA_ANULAR`) **sigue** rechazando la de origen `VENTA` con `COBRANZA_DE_VENTA`. Consecuencia: un solo lugar escribe cobranzas; ventas no toca sus tablas.
- **B. Generalizar `anular_cobranza` con un parámetro "desde la venta".** Consecuencia: el comando público queda a un booleano de anular cobranzas de venta por su cuenta.
- **C. Exigir un segundo motivo del ámbito `ANULACION_COBRANZA`.** Consecuencia: dos motivos para una misma decisión en la pantalla.

### D10 — Transacción, orden de bloqueo y precedencia · arquitectura · CRÍTICO

**Contexto.** VTA-12 (análogo), INV-01, `02` §7.3 ("las filas de la propia operación que el comando corrige o anula se toman antes del nivel 1"), `COBRANZA_ANULAR` (cobranza `FOR UPDATE` antes de `saldo_cuenta`), `COMPRA_ANULAR` (compra y después su pago).

- **A (recomendada).** En la transacción del bus, `ventas/service.py::anular_venta`: **(0)** valida en puro el contenido (observación); **(1)** lee la venta sin bloquear (404 si no es de la organización, INV-21) y la toma `FOR UPDATE`; revalida con la fila tomada que esté `CONFIRMADA` (`VENTA_YA_ANULADA`, 409); **(2)** toma `FOR UPDATE` su cobranza de origen `VENTA`, si existe, por `cobranzas/service.py`; **(3)** valida el motivo (404 / `MOTIVO_INVALIDO`) y `devuelve_dinero` (D2, D3); **(4)** nivel 1: `saldo_cuenta` del cliente; **(5)** niveles 2 a 5 por `stock/service.py::registrar_movimientos` con los ingresos de D5 (productos `FOR SHARE`, `costo_producto`, `stock_saldo`, jornada `FOR SHARE`; `UBICACION_INACTIVA`, `UBICACION_TOMADA` con D6 y D7); **(6)** escrituras: `venta_anulacion`, `UPDATE venta SET estado = 'ANULADA'`, `ANULACION_VENTA` `REDUCE` por el total y, con devolución, la anulación de la cobranza (D9); **(7)** resultado y dato de auditoría (D15) al bus, que confirma. Cualquier error revierte todo, también la reserva del `operation_id`. **Precedencia de rechazos:** contenido, venta (404, `VENTA_YA_ANULADA`), motivo, devolución (`DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`), ubicación (`UBICACION_INACTIVA`, `UBICACION_TOMADA`). Se enmienda `02` §7.3: "la venta (`FOR UPDATE`) y después su cobranza (`FOR UPDATE`)". Consecuencia: dos anulaciones simultáneas de la misma venta se serializan en la venta (la segunda ve `ANULADA`); `COBRANZA_ANULAR` sobre la misma cobranza toma solo la cobranza y no cierra ciclo; una venta y una anulación de otra venta del mismo cliente se esperan en `saldo_cuenta`, como dos ventas.
- **B. Tomar `saldo_cuenta` antes que la venta.** Consecuencia: contradice `02` §7.3; la revalidación del estado quedaría después del nivel 1 y una anulación repetida bloquearía al cliente sin necesidad.
- **C. Tomar la venta `FOR SHARE` y apoyarse en el `UNIQUE (venta_id)` de `venta_anulacion`.** Consecuencia: la segunda anulación falla por violación de la restricción después de haber movido stock y cuenta en su transacción (se revierte, pero con un error 500 en vez de `VENTA_YA_ANULADA`).

### D11 — Modelo de datos y privilegios · datos · MEDIO

**Contexto.** `03` §12 (`venta_anulacion`: `id`, `organizacion_id`, `venta_id` único, `motivo_id`, `observacion`, `devuelve_dinero`, columnas de operación), INV-05.

- **A (recomendada).** Una revisión de Alembic sobre `c8d9e0f1a2b3`: tabla `venta_anulacion` con `id`, `organizacion_id`, `venta_id` (`UNIQUE (organizacion_id, venta_id)`), `motivo_id`, `observacion text` nulable (500 en el esquema y el contenido, sin `CHECK`, como cobranzas), `devuelve_dinero boolean` **nulable: nulo si y solo si la venta no tenía cobranza `CONFIRMADA`** (no hay `CHECK` que cruce tablas: lo garantiza el servicio y una prueba), `jornada_id` nulable (D8), `operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`, `registered_at`; FK compuestas a `venta`, `motivo`, `jornada`, `usuario`, `dispositivo`; `UNIQUE (organizacion_id, id)`; índice `(organizacion_id, occurred_at DESC, id DESC)`. `app_runtime`: `SELECT, INSERT` en `venta_anulacion`; `GRANT UPDATE (estado) ON venta`; sin `DELETE`. Siembra idempotente de D12. `downgrade`: aborta con mensaje claro si hay ventas `ANULADA` (no puede dejarlas sin su anulación); si no, revoca el `UPDATE`, borra la tabla y los motivos sembrados no usados. "`ANULADA` ⇔ existe su `venta_anulacion`" se verifica con una prueba y con la consulta de consistencia.
- **B. Columnas de anulación en `venta`** (como `compra`). Consecuencia: contradice `03` §12 y amplía el `UPDATE` a cinco columnas.
- **C. `devuelve_dinero NOT NULL` (falso sin cobranza).** Consecuencia: "no devolvió" y "no había qué devolver" se confunden en reportes y en la rendición.

### D12 — Motivos sembrados de `ANULACION_VENTA` · negocio · BAJO

- **A (recomendada). Tres motivos: "Error de carga", "Devolución del cliente" y "Otro"**, para las organizaciones nuevas y, por la migración, para las existentes que no tengan ninguno de ese ámbito (idempotente), como los changes 11, 12, 14, 15 y 17.
- **B. Cuatro, sumando "Venta duplicada".** Consecuencia: más precisión; la alta y baja de motivos sigue sin pantalla (deuda del 17b).
- **C. Sin siembra.** Consecuencia: ninguna organización puede anular hasta cargar motivos a mano (no hay pantalla).

### D13 — Venta facturada (VTA-23) · negocio · BAJO

**Contexto.** VTA-23 es de la etapa de facturación; en la etapa 1 `estado_facturacion` nunca llega a `PARCIAL` ni `FACTURADA`.

- **A (recomendada). No adelantarla.** La anulación lee `estado_facturacion` con la venta tomada y el módulo de facturación agregará la regla en ese punto (deuda al roadmap de facturación, junto con excluir las anuladas de lo facturable). Una venta `PENDIENTE` anulada conserva su estado de facturación. Consecuencia: ninguna regla de otra etapa entra al código.
- **B. Rechazar ya `PARCIAL` y `FACTURADA` con `VENTA_FACTURADA`.** Consecuencia: código y pruebas para un estado inalcanzable.

### D14 — Permisos y lecturas · seguridad · ALTO

**Contexto.** `01` §19 (`ANULAR_VENTA`), `01` §19 párrafo de ventas (listado y detalle con `VENDER` o `ANULAR_VENTA`), ADR-056 (permiso por tipo en todo camino).

- **A (recomendada). Sin permisos nuevos.** `VENTA_ANULAR` declara `permisos=("ANULAR_VENTA",)`; no exige `PERMITIR_STOCK_NEGATIVO` (solo ingresa stock); `LIBERAR_UBICACION` solo para D6. `GET /ventas/{id}` suma el bloque `anulacion` (momento, usuario con su nombre, motivo con su nombre, observación, `devuelve_dinero`) para quien ya lee el detalle. **Alcance extra:** `GET /ventas` suma el filtro `estado` (`CONFIRMADA` o `ANULADA`), para encontrar las anuladas que REP-02 manda informar aparte. Los motivos se leen con cualquier sesión (sin cambio). Consecuencia: el Vendedor no ve el botón (no tiene el permiso).
- **B. Sin filtro por estado.** Consecuencia: las anuladas solo se distinguen por la etiqueta del listado.
- **C. Exigir también `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA` para devolver el dinero.** Consecuencia: un permiso de cobranzas decide sobre una venta; VTA-22 no lo pide.

### D15 — Auditoría y observaciones · auditoría · ALTO

**Contexto.** AUD-01 ("ventas, compras, cobranzas y pagos anulados"), AUD-02 (motivo en la fila), ADR-022 (una fila por comando), STK-09 (constancia de la jornada en la observación de la fila).

- **A (recomendada). Una sola fila de auditoría del comando `VENTA_ANULAR`** con el motivo (AUD-02) y, en su observación, la cobranza anulada (si la hubo) y la constancia de la ubicación tomada (si se usó la excepción de `LIBERAR_UBICACION`). No se emite ninguna observación de SYN-07 nueva (el reingreso nunca deja stock negativo). Las observaciones pendientes de la venta original siguen pendientes y se resuelven en la bandeja (SYN-08). Consecuencia: la cobranza anulada se encuentra por su `cobranza_anulacion` y por la fila del comando.
- **B. Dos filas (venta y cobranza).** Consecuencia: rompe "una fila por comando" (ADR-022) sin ganancia de trazabilidad.

### D16 — Pantalla · interfaz · MEDIO

- **A (recomendada).** En el detalle de la venta, botón **"Anular venta"** solo con `ANULAR_VENTA` y la venta `CONFIRMADA`. El diálogo pide motivo (obligatorio, del ámbito `ANULACION_VENTA`), observación opcional y, solo si hubo cobranza confirmada, "¿Devolvés el dinero cobrado?" (Sí / No; en el consumidor final, fijo en Sí con su explicación, D3). Muestra el efecto antes de confirmar, calculado con `domain/ventas/anulacion.ts` (casos `vta-22`): mercadería que vuelve por línea y a qué ubicación, "la cuenta del cliente baja $total" y, con devolución, "y sube $cobranza por el cobro devuelto"; no muestra el saldo absoluto (quien solo tiene `ANULAR_VENTA` no lee saldos). Después de confirmar muestra el saldo que devuelve el comando. El detalle anulado muestra el bloque "Anulación" (fecha, quién, motivo, observación, si devolvió el dinero). El listado ya marca "Anulada" y suma el filtro por estado (D14). Errores con su texto: `VENTA_YA_ANULADA`, `UBICACION_TOMADA` (con el nombre de quien la tiene), `UBICACION_INACTIVA`, `MOTIVO_INVALIDO`. Consecuencia: el flujo de compras y cobranzas, aplicado a la venta.
- **B. Anular desde el listado.** Consecuencia: se anula sin ver la venta.

### D17 — Fixtures compartidos · técnica · BAJO

**Contexto.** `CLAUDE.md` §4 ("todo cambio en una regla de cálculo actualiza los fixtures compartidos antes de tocar el código"), ADR-016, ADR-044 punto 6.

- **A (recomendada).** Antes del código: (1) casos `ANULACION_VENTA` en `shared/fixtures/calculo/cst-11-costo-promedio.json` (el ejemplo de D5; stock total previo 0; stock total previo negativo; línea sin costo que no recalcula) que corren pytest y Vitest; (2) fixture nuevo `shared/fixtures/calculo/vta-22-anulacion.json` (`"motor": "vta22"`) con el efecto en la cuenta: venta sin cobro, con cobro parcial con y sin devolución, cobro mayor que el total, consumidor final; corre contra `ventas/domain/anulacion.py` y `frontend/src/domain/ventas/anulacion.ts`. Consecuencia: el resumen de la pantalla y el servidor no pueden diferir.
- **B. Solo los casos de `cst-11`.** Consecuencia: el resumen de la pantalla se prueba solo en TypeScript.

### D18 — Ayuda contextual · interfaz · BAJO · ADR-051

Textos aprobados por el usuario el 2026-10-24 (tarea 0.2), **sin ejemplos** (el usuario los quitó: se entienden sin ellos):

1. **`ventas.anulacion`** — *Anular una venta.* "Deja la venta sin efecto: la mercadería vuelve a la ubicación de donde salió y al cliente se le descuenta de su cuenta el total de la venta. No se borra: queda como anulada, con el motivo y quién la anuló. Se anula entera y una sola vez." Reglas: VTA-20, VTA-21, INV-19, TR-06.
2. **`ventas.devolverDinero`** — *¿Devolvés lo que cobraste?* "Si le devolvés al cliente lo que pagó con esta venta, el cobro también se anula y su cuenta queda como antes de la venta. Si no se lo devolvés, ese pago le queda a favor para lo próximo que compre." Reglas: VTA-22, COB-05, ADR-058.
3. **`ventas.motivoAnulacion`** — *Motivo.* "Elegí por qué anulás. Queda guardado en la venta y en la auditoría." Reglas: VTA-20, AUD-01, AUD-02.
4. **`ventas.consumidorFinalAnulacion`** — *Consumidor final.* "Al cliente sin nombre siempre se le devuelve lo que pagó: no tiene cuenta donde dejarle saldo a favor." Reglas: CLI-03, VTA-22, ADR-058.
5. **`ventas.reingresoUbicacion`** — *Adónde vuelve la mercadería.* "Vuelve a la ubicación de donde salió. Si esa camioneta está ahora en la jornada de otro vendedor, solo puede anular quien tiene permiso para mover una ubicación tomada." Reglas: VTA-21, STK-09, ADR-058.
6. **`ventas.costoAnulacion`** (solo con `VER_COSTOS`) — *Costo de lo que vuelve.* "La mercadería vuelve al mismo costo con que salió en la venta, y el costo promedio del producto se recalcula como en una compra." Reglas: VTA-21, CST-11, CST-13.

Se revisa además el texto `cobranzas.anulacion` (dice "Se anula entera"; se suma: "El cobro de una venta se anula anulando la venta."), que cita COB-05.

### D19 — Preparación de la anulación sin conexión (VTA-24) · sync · ALTO

**Contexto.** VTA-24, SYN-03 (la anulación se procesa después de su venta), SYN-06 (dependencia inexistente), `02` §6.5, change 22c.

- **A (recomendada). Nada sin conexión en este change; el contrato no cambia cuando llegue.** `VENTA_ANULAR` v1 queda `admite_offline=False`; el 22c lo pasa a `True` con `permisos=("ANULAR_VENTA",)`, la regla de la jornada en curso (la venta y la anulación con la misma jornada del sobre, `JORNADA_AJENA` si no) y la venta inexistente como dependencia inexistente. Como el reingreso nunca deja stock negativo y la ubicación es la de la jornada, no hace falta otra regla de stock. Se deja anotado como deuda del 22c. Consecuencia: el 22c no necesita una v2 del comando.
- **B. Declarar ya `admite_offline=True`.** Consecuencia: el servidor acepta un camino que ningún cliente puede generar ni probar (no hay cola).

## Risks / Trade-offs

- [El reingreso a costo viejo mueve el promedio] → Es lo que pide CST-11; queda historia en `costo_producto_mov` (CST-13) y el ejemplo de D5 en los fixtures.
- [Una venta con 200 líneas toma 200 productos] → Mismo costo que confirmarla; el orden global evita interbloqueos; prueba de concurrencia con dos anulaciones y una venta del mismo producto.
- [`UBICACION_TOMADA` frena a Administración (D6)] → Mensaje con quién tiene la ubicación y texto de ayuda; un supervisor la anula.
- [Producto inactivo con stock después de anular (D7)] → Visible en el stock; se reactiva para venderlo o ajustarlo.
- [El `downgrade` no puede bajar con ventas anuladas] → Mensaje explícito; la prueba de ida y vuelta usa una base con ventas confirmadas sin anular, y otra que verifica que aborta.
- [Facturación futura sobre ventas anuladas `PENDIENTE`] → Deuda explícita al roadmap de facturación (D13).

## Migration Plan

Una revisión (`d9e0f1a2b3c4`, nombre provisional) sobre `c8d9e0f1a2b3`: crea `venta_anulacion`, otorga `UPDATE (estado)` sobre `venta`, siembra motivos. Sube y baja limpia sobre una base con ventas confirmadas (`04` §2.1 punto 4). Al levantar Docker: `docker compose exec -T backend alembic upgrade head`.

## Open Questions

- La nota de venta reimpresa de una venta anulada, ¿lleva la marca "ANULADA"? Lo decide el change 20 (deuda nueva).
- El resumen de rendición (RUT-07, change 24) ¿cuenta las anulaciones por la jornada de la venta o por la de la anulación? Quedan las dos columnas; lo decide el 24.
