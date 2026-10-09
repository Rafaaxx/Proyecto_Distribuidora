# Propuesta de cambios a `docs/` — change 14 (tarea 16.2)

> **Estado: APROBADA por el usuario y APLICADA a `docs/` el 2026-10-08.** Se aplicaron todas las secciones a `docs/01`, `docs/02`, `docs/03` y `docs/04`, y ADR-048 pasó a *Vigente*; los ADR-022, ADR-038, ADR-039 y ADR-044 siguen sin tocar. Dos excepciones decididas por el usuario: en `03` §15 no se agregó la fila opcional de INV-15, y la nota **[a decidir]** de AUD-02 no se copió a `docs/01` (esa deuda queda en `04` §8, changes 26 y 28). Las secciones que siguen conservan el texto actual y el propuesto como registro. Todo recoge lo aprobado en `design.md` D0 a D11 y en ADR-048.
>
> Enmiendas a ADR anteriores (se describen en ADR-048, sección "Enmiendas a ADR anteriores", y **no** se editan esos ADR): ADR-039 (consecuencias: "un ingreso de otro tipo se rechaza"), ADR-044 punto 4 (stock negativo solo en la anulación de compra), ADR-022 (la fila de auditoría del bus lleva el motivo en tres comandos) y `02` §7.3 (el producto entra al orden de bloqueo). **ADR-038 punto 5 queda sin enmendar.**

---

## `docs/01-dominio.md`

### §5 Catálogo (CAT-05)

**Texto actual**

| CAT-05 | Un producto o presentación usado en operaciones no se elimina: se desactiva. Los inactivos no se ofrecen en nuevas operaciones. | 1 |

**Texto propuesto**

| CAT-05 | Un producto o presentación usado en operaciones no se elimina: se desactiva. Los inactivos no se ofrecen en nuevas operaciones. Un producto con stock distinto de cero en alguna ubicación de la organización (también negativo) no se desactiva (`PRODUCTO_CON_STOCK`); se vacía primero. Reactivar no tiene esa condición (ADR-048). | 1 |

### §6.2 Costo promedio (CST-12)

**Texto actual**

| CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio. Los egresos por ajuste, y los de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. | 1 |

**Texto propuesto**

| CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio ni dejan historia de costo. Todo movimiento de transferencia o de ajuste, de ingreso o de egreso, y los egresos de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. Un ajuste positivo de un producto sin promedio se rechaza (`PRODUCTO_SIN_COSTO`). Los movimientos inversos de la anulación de una transferencia o de un ajuste repiten el costo del movimiento original, no el promedio del momento (ADR-048). | 1 |

### §8.1 Stock (STK-03, STK-05, STK-07, STK-08)

**Texto actual**

| STK-03 | Todo cambio de stock es un movimiento con producto, ubicación, cantidad con signo, tipo y operación origen. Tipos: STOCK_INICIAL, COMPRA, ANULACION_COMPRA, VENTA, ANULACION_VENTA, TRANSFERENCIA_SALIDA, TRANSFERENCIA_ENTRADA, AJUSTE, DIFERENCIA_RENDICION. | 1 (DEVOLUCION, RECUENTO: 2) |
| STK-05 | Con conexión, una operación que deje stock negativo se rechaza salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`; en ese caso se acepta con observación. | 1 |
| STK-07 | Una transferencia genera, en la misma transacción, una salida en origen y una entrada en destino por la misma cantidad. No modifica costos. | 1 |
| STK-08 | Un ajuste requiere `AJUSTAR_STOCK` y un motivo del catálogo de la organización. | 1 |

**Texto propuesto**

| STK-03 | Todo cambio de stock es un movimiento con producto, ubicación, cantidad con signo, tipo y operación origen. Tipos: STOCK_INICIAL, COMPRA, ANULACION_COMPRA, VENTA, ANULACION_VENTA, TRANSFERENCIA_SALIDA, TRANSFERENCIA_ENTRADA, AJUSTE, DIFERENCIA_RENDICION. Los movimientos inversos de la anulación de una transferencia o de un ajuste reutilizan los tipos `TRANSFERENCIA_SALIDA`, `TRANSFERENCIA_ENTRADA` y `AJUSTE` con signo contrario, y se distinguen por su operación origen (`ANULACION_TRANSFERENCIA`, `ANULACION_AJUSTE_STOCK`). | 1 (DEVOLUCION, RECUENTO: 2) |
| STK-05 | Con conexión, una operación que deje stock negativo se rechaza salvo que el usuario tenga `PERMITIR_STOCK_NEGATIVO`; en ese caso se acepta con observación. Excepción: los ajustes y las correcciones de stock inicial (STK-10) nunca dejan stock negativo, tenga o no el usuario el permiso (`STOCK_INSUFICIENTE`). La salida de una transferencia y las anulaciones (de compra, de transferencia y de ajuste) sí pueden, con el permiso (ADR-048). | 1 |
| STK-07 | Una transferencia genera, en la misma transacción, una salida en origen y una entrada en destino por la misma cantidad, para de 1 a 200 productos distintos, con origen y destino distintos. No modifica el promedio ni el stock total del producto (INV-15); ambos movimientos se valorizan al promedio vigente. No se edita ni se borra: se corrige por anulación total con motivo (TR-06). Con conexión solamente. | 1 |
| STK-08 | Un ajuste requiere `AJUSTAR_STOCK` y un motivo activo del ámbito `AJUSTE_STOCK` de la organización, uno por ajuste. Lleva de 1 a 200 líneas con cantidad con signo distinta de cero (se admiten signos mezclados) sobre una sola ubicación, y una observación opcional. Un ajuste positivo de un producto sin costo promedio se rechaza (`PRODUCTO_SIN_COSTO`). No se edita ni se borra: se corrige por anulación total con motivo del ámbito `ANULACION_AJUSTE`, una sola vez. Con conexión solamente. | 1 |

### §15 Auditoría (AUD-01)

**Texto actual**

| AUD-01 | Se auditan: inicio de sesión, cambios de usuarios, roles, permisos y dispositivos; costos informados; publicación y anulación de versiones de lista; uso de lista no asignada o versión anterior; descuentos manuales y autorizaciones; autorizaciones de crédito; ventas, compras, cobranzas y pagos anulados; ajustes de stock; diferencias de rendición; liberación forzada de ubicaciones; cambios de límite y política de crédito; cambios de configuración; resolución de observaciones; comandos rechazados o en cuarentena. | 1 |

**Texto propuesto**

| AUD-01 | Se auditan: inicio de sesión, cambios de usuarios, roles, permisos y dispositivos; costos informados; publicación y anulación de versiones de lista; uso de lista no asignada o versión anterior; descuentos manuales y autorizaciones; autorizaciones de crédito; ventas, compras, cobranzas y pagos anulados; transferencias y ajustes de stock y sus anulaciones (la fila de `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` lleva el motivo, AUD-02); diferencias de rendición; liberación forzada de ubicaciones; cambios de límite y política de crédito; cambios de configuración; resolución de observaciones; comandos rechazados o en cuarentena. | 1 |

AUD-02 no cambia. **[a decidir]** El motivo en la fila de auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` queda como deuda nominada (ADR-048): hasta entonces esas filas llevan `motivo_id` nulo y el motivo está en la cabecera de la operación.

### §18 Máquinas de estado

**Texto actual**

| Compra | Operativa | CONFIRMADA → ANULADA | 1 |
| Cobranza / Pago | Operativa | CONFIRMADA → ANULADA | 1 |

**Texto propuesto** (se agregan dos filas a continuación de "Cobranza / Pago")

| Transferencia | Operativa | CONFIRMADA → ANULADA | 1 |
| Ajuste de stock | Operativa | CONFIRMADA → ANULADA | 1 |

### §19 Permisos y roles

La columna del rol Administración de la tabla es `GES`. El catálogo pasa de 39 a 40 permisos.

**Texto actual**

| TRANSFERIR_STOCK | Transferencias; ver ubicaciones, stock por ubicación y kardex (sin costos) | ✓ | ✓ | ✓ | ✓ | |
| AJUSTAR_STOCK | Ajustes | ✓ | ✓ | | | |

**Texto propuesto** (se agrega la fila `ANULAR_TRANSFERENCIA` entre las dos)

| TRANSFERIR_STOCK | Transferencias; anular las propias; ver el listado y el detalle de transferencias, ubicaciones, stock por ubicación y kardex (sin costos) | ✓ | ✓ | ✓ | ✓ | |
| ANULAR_TRANSFERENCIA | Anular transferencias de otros usuarios (exige además `TRANSFERIR_STOCK`) | ✓ | ✓ | | | |
| AJUSTAR_STOCK | Ajustes; anularlos (propios o ajenos); ver el listado y el detalle de ajustes | ✓ | ✓ | | | |

Y, a continuación de la tabla de roles, una oración: "El listado y el detalle de transferencias se leen con `TRANSFERIR_STOCK`; los de ajustes, con `AJUSTAR_STOCK`, y sus costos solo con `VER_COSTOS`. `ANULAR_TRANSFERENCIA` solo agrega el alcance sobre las transferencias de otros usuarios y no abre ninguna lectura; sin ese permiso, anular la transferencia de otro responde 403. Quien tiene `PERMITIR_STOCK_NEGATIVO` puede, además, dejar stock negativo con la salida de una transferencia y con la anulación de una transferencia o de un ajuste (ADR-048)."

### §21 Efectos de cada evento

**Texto actual**

| Transferencia | − origen / + destino | — | — | — | — | Sí |
| Ajuste de stock | + / − | — | — | — | — | Sí |

**Texto propuesto** (se aclara la valorización y se agregan dos filas de anulación)

| Transferencia | − origen / + destino | No cambia (valoriza al promedio vigente) | — | — | — | Sí |
| Anulación de transferencia | + origen / − destino | No cambia (costo original) | — | — | — | Sí |
| Ajuste de stock | + / − | No cambia (valoriza al promedio vigente) | — | — | — | Sí |
| Anulación de ajuste | − / + (inverso) | No cambia (costo original) | — | — | — | Sí |

---

## `docs/02-arquitectura.md`

### §5.3 Dependencias permitidas entre módulos

**Texto actual**

```
stock ──► catalogo, costeo
catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)
```

**Texto propuesto**

```
stock ──► catalogo, costeo, configuracion (motivos, solo por service.py, ADR-048)
catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)
```

Y, a continuación de la nota sobre `precios` y `clientes`: "Nota: `catalogo` no depende de `stock`: este registra en `catalogo` un verificador de stock (`registrar_verificador_de_stock`, patrón de ADR-023 y ADR-025, que falla cerrado) para que un producto con stock no se desactive, y no hay ciclo. El contrato de import-linter `stock-solo-por-service-ajeno` permite a `stock` alcanzar `configuracion` solo por su `service.py`, y `catalogo-solo-por-service-ajeno` prohíbe a `catalogo` importar `stock` (ADR-048)."

### §6.5 Tipos de comando de la etapa 1

**Texto actual**

| `STOCK_TRANSFERIR`, `STOCK_AJUSTAR`, `STOCK_INICIAL_REGISTRAR` | ✓ | |

**Texto propuesto**

| `STOCK_TRANSFERIR`, `STOCK_AJUSTAR`, `STOCK_INICIAL_REGISTRAR` | ✓ | |
| `STOCK_TRANSFERENCIA_ANULAR`, `STOCK_AJUSTE_ANULAR` | ✓ | |

Y un párrafo nuevo a continuación del de pagos: "`STOCK_TRANSFERIR` lleva origen, destino distinto y de 1 a 200 líneas de producto y cantidad base positiva, y exige `TRANSFERIR_STOCK`; `STOCK_AJUSTAR` lleva una ubicación, un motivo del ámbito `AJUSTE_STOCK` y de 1 a 200 líneas con cantidad con signo, y exige `AJUSTAR_STOCK`; ambos admiten una observación de hasta 500 caracteres. `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` llevan la operación (en la ruta) y un motivo de los ámbitos `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE`; anulan todas las líneas, una sola vez, con movimientos inversos al costo original; la primera exige `TRANSFERIR_STOCK` y, si la transferencia es de otro usuario, además `ANULAR_TRANSFERENCIA`, y la segunda `AJUSTAR_STOCK`. Emiten `STOCK_NEGATIVO` cuando el usuario con `PERMITIR_STOCK_NEGATIVO` deja un saldo bajo cero. Los errores propios son `UBICACIONES_IGUALES`, `OBSERVACION_INVALIDA` y `MOTIVO_INVALIDO` (422) y `PRODUCTO_SIN_COSTO`, `PRODUCTO_CON_STOCK`, `TRANSFERENCIA_YA_ANULADA` y `AJUSTE_YA_ANULADO` (409). Las lecturas son `GET /stock/transferencias` y `/{id}` (con `TRANSFERIR_STOCK`) y `GET /stock/ajustes` y `/{id}` (con `AJUSTAR_STOCK`, costos con `VER_COSTOS`), con cursor y límite; el kardex agrega el motivo, la operación de origen y su estado. Los cuatro comandos son solo online. El bus copia el motivo a su fila de auditoría únicamente en `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` (ADR-022, ADR-048)."

### §7.3 Orden global de bloqueo

**Texto actual**

1. `saldo_cuenta` (cliente o proveedor de la operación)
2. `costo_producto` (por `producto_id` ascendente)
3. `stock_saldo` (por `producto_id` y `ubicacion_id` ascendentes)
4. `jornada` (si la operación la valida)

Las filas de la propia operación que el comando corrige o anula se toman **antes** del nivel 1, en este orden: la compra (`FOR UPDATE`) y después su pago (`FOR UPDATE`). `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` usan el mismo orden (compra, pago, `saldo_cuenta`), así que anular una compra y anular su pago a la vez no se interbloquean y dejan una sola `ANULACION_PAGO`. `PAGO_PROVEEDOR_REGISTRAR` parte del nivel 1 (`saldo_cuenta` del proveedor) (ADR-043 punto 15, ADR-046).

**Texto propuesto**

1. `saldo_cuenta` (cliente o proveedor de la operación)
2. `producto` (`FOR SHARE`, por `producto_id` ascendente; todo movimiento de stock lo toma, y la desactivación de un producto lo toma `FOR UPDATE`)
3. `costo_producto` (por `producto_id` ascendente)
4. `stock_saldo` (por `producto_id` y `ubicacion_id` ascendentes)
5. `jornada` (si la operación la valida)

Las filas de la propia operación que el comando corrige o anula se toman **antes** del nivel 1, en este orden: la compra (`FOR UPDATE`) y después su pago (`FOR UPDATE`); o la transferencia o el ajuste (`FOR UPDATE`), que se anula una sola vez. `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` usan el mismo orden (compra, pago, `saldo_cuenta`), así que anular una compra y anular su pago a la vez no se interbloquean y dejan una sola `ANULACION_PAGO`. `PAGO_PROVEEDOR_REGISTRAR` parte del nivel 1 (`saldo_cuenta` del proveedor) (ADR-043 punto 15, ADR-046). Las ubicaciones se toman `FOR SHARE` al comienzo del movimiento, como hasta ahora (ADR-038). Con el producto como nivel previo a `costo_producto`, un movimiento y la desactivación del mismo producto se esperan: o el movimiento ve el producto inactivo, o la desactivación ve el saldo (`PRODUCTO_CON_STOCK`) (ADR-048).

### §7.4 Stock

**Texto actual**

- **ONLINE:** `UPDATE stock_saldo SET cantidad = cantidad - :q WHERE … AND cantidad >= :q`. Si no afecta filas y el usuario no tiene `PERMITIR_STOCK_NEGATIVO`, se rechaza (STK-05).

**Texto propuesto**

- **ONLINE:** `UPDATE stock_saldo SET cantidad = cantidad - :q WHERE … AND cantidad >= :q`. Si no afecta filas y el usuario no tiene `PERMITIR_STOCK_NEGATIVO`, se rechaza (STK-05). Con el permiso se admite solo para la salida de una transferencia, la anulación de una compra, la de una transferencia y la de un ajuste; **nunca** para un ajuste ni para la corrección de un stock inicial, que se rechazan con `STOCK_INSUFICIENTE` tenga o no el permiso (ADR-044 punto 4 enmendado por ADR-048).

La primera viñeta de §7.4 ("Todo movimiento de un producto bloquea su fila de `costo_producto` y la de `stock_saldo`") se completa con: "y toma el producto `FOR SHARE` antes de ambas".

---

## `docs/03-modelo-de-datos.md`

### §4 `motivo` y siembra

**Texto actual** (fila de `motivo` y párrafo siguiente)

| `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`), `nombre`, `activo` |

Las organizaciones nuevas nacen con tres motivos del ámbito `ANULACION_COMPRA` ("Error de carga", "Devolución al proveedor" y "Otro") y tres del ámbito `ANULACION_PAGO` ("Error de carga", "Pago rechazado o devuelto" y "Otro"); la migración del change 11 agrega los primeros y la del change 12 (`d1e2f3a4b5c6`) los segundos, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito. Los medios de pago y los motivos activos se leen por API (`GET /configuracion/medios-pago` y `GET /configuracion/motivos?ambito=`) (ADR-043).

**Texto propuesto**

| `motivo` | `id`, `organizacion_id`, `ambito` (`AJUSTE_STOCK`, `ANULACION_VENTA`, `ANULACION_COMPRA`, `ANULACION_COBRANZA`, `ANULACION_PAGO`, `ANULACION_TRANSFERENCIA`, `ANULACION_AJUSTE`, `DESCUENTO_MANUAL`, `LISTA_ANTERIOR`, `LIBERACION_JORNADA`), `nombre`, `activo` |

El párrafo se completa al final: "Las organizaciones nuevas nacen también con dos motivos del ámbito `ANULACION_TRANSFERENCIA` ("Error de carga" y "Otro") y dos del ámbito `ANULACION_AJUSTE` ("Error de carga" y "Otro"); la migración del change 14 (`f3a4b5c6d7e8`) los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-048)." El catálogo de `permiso` (§4, `rol_permiso`) suma `ANULAR_TRANSFERENCIA`, que la misma migración asigna a las plantillas Administrador y Administración.

### §9 `transferencia`, `ajuste_stock` y sus líneas

**Texto actual**

| Tabla | Columnas |
| --- | --- |
| `transferencia` | `id`, `organizacion_id`, `ubicacion_origen_id`, `ubicacion_destino_id`, `estado`, columnas de operación; `CHECK (origen <> destino)` |
| `transferencia_linea` | `id`, `organizacion_id`, `transferencia_id`, `producto_id`, `cantidad_base` `CHECK (> 0)` |
| `ajuste_stock` | `id`, `organizacion_id`, `ubicacion_id`, `motivo_id`, `observacion`, columnas de operación |
| `ajuste_stock_linea` | `id`, `organizacion_id`, `ajuste_id`, `producto_id`, `cantidad_base` (con signo), `costo_unitario` `numeric(18,6)` |

**Texto propuesto**

| Tabla | Columnas |
| --- | --- |
| `transferencia` | `id`, `organizacion_id`, `ubicacion_origen_id`, `ubicacion_destino_id`, `observacion`, `estado` (`CONFIRMADA`, `ANULADA`; `CHECK` de catálogo), `anulacion_motivo_id`, `anulada_en`, `anulada_por_id`, columnas de operación; `CHECK (origen <> destino)` y `CHECK` de coherencia de anulación (las tres columnas no nulas si y solo si `estado = 'ANULADA'`) |
| `transferencia_linea` | `id`, `organizacion_id`, `transferencia_id`, `orden` `integer`, `producto_id`, `cantidad_base` `CHECK (> 0)`; `UNIQUE (organizacion_id, transferencia_id, orden)` |
| `ajuste_stock` | `id`, `organizacion_id`, `ubicacion_id`, `motivo_id`, `observacion`, `estado` (`CONFIRMADA`, `ANULADA`), `anulacion_motivo_id`, `anulado_en`, `anulado_por_id`, columnas de operación; mismo `CHECK` de coherencia |
| `ajuste_stock_linea` | `id`, `organizacion_id`, `ajuste_id`, `orden` `integer`, `producto_id`, `cantidad_base` (con signo) `CHECK (<> 0)`, `costo_unitario` `numeric(18,6)` (nulable); `UNIQUE (organizacion_id, ajuste_id, orden)` |

Y debajo de la tabla: "`UNIQUE (organizacion_id, id)` y claves foráneas compuestas a `ubicacion`, `producto`, `motivo`, `usuario` y `dispositivo`. Sin `UNIQUE` sobre `operation_id`: INV-06 lo garantiza la reserva en `comando`. Índices de listado `(organizacion_id, occurred_at DESC, id DESC)` en ambas cabeceras. El usuario de aplicación tiene `SELECT` e `INSERT` en las cuatro tablas y `UPDATE` **solo** sobre `estado` y las tres columnas de anulación de cada cabecera; las líneas no tienen `UPDATE` y ninguna tiene `DELETE` (INV-05). Los movimientos de stock de una transferencia usan `origen_tipo = 'TRANSFERENCIA'`, los de un ajuste `'AJUSTE_STOCK'` y los de sus anulaciones `'ANULACION_TRANSFERENCIA'` y `'ANULACION_AJUSTE_STOCK'`, con `origen_id` igual al id de la cabecera; los inversos repiten el `costo_unitario` del original (ADR-048)."

### §15 Restricciones que la base garantiza

**Texto actual**

| INV-05 | Permisos del usuario de aplicación sobre tablas de libro |

**Texto propuesto**

| INV-05 | Permisos del usuario de aplicación sobre tablas de libro y sobre las líneas y cabeceras de transferencias y ajustes (`UPDATE` acotado por columna en las cabeceras) |

Y se agrega la fila `| INV-15 | (se garantiza en los servicios; propiedad con PostgreSQL real) |` si se quiere dejarla explícita; hoy el párrafo posterior ya la incluye entre las que se garantizan en los servicios.

---

## `docs/04-roadmap-changes.md`

### §2 Convenciones de change (tamaño)

**Texto actual**

- **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide.

**Texto propuesto**

- **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide. Excepción aceptada por el usuario: el change 14 (`transferencias-y-ajustes`) se implementó en cuatro lotes con revisión entre cada uno, en lugar de dividirse (ADR-048, punto 1).

### §8 Hito 4 — Operación de ruta

**Texto actual** (deuda del change 11)

**Deuda nominada por el change 11 (`compras-y-deuda-proveedor`) para el change 14 (`transferencias-y-ajustes`) y el 18a (`venta-online-core`):** el stock puede quedar negativo por una anulación de compra con `PERMITIR_STOCK_NEGATIVO` (ADR-044, enmienda del punto 3 de ADR-039); el 14 decide cómo se regulariza (ajuste) y el 18a cómo costea y valida una venta sobre un saldo negativo. `registrar_movimientos` solo admite `permitir_negativo` para `ANULACION_COMPRA`.

**Texto propuesto**

**Deuda del change 11 saldada por el change 14 (`transferencias-y-ajustes`, ADR-048):** un saldo negativo se regulariza con cualquier ingreso (compra, transferencia entrante o ajuste positivo), con la acción "Ajustar" del stock por ubicación; los ajustes nunca dejan negativo. `registrar_movimientos` admite `permitir_negativo` para `ANULACION_COMPRA` y `TRANSFERENCIA_SALIDA`, y para el inverso de un ajuste. Queda para el 18a cómo costea y valida una venta sobre un saldo negativo.

Y, en la tabla del hito 4, la fila del change 14 queda como está (`INV-15` en "Invariantes que cierra"): este change lo cierra con dominio, propiedad contra PostgreSQL real e integración. Se agregan las deudas nuevas siguientes, a continuación de las del change 04 y del 05:

**Deuda nominada por el change 14 (`transferencias-y-ajustes`) para el change 15 (`jornadas`):** (1) aplicar STK-09 también a `STOCK_TRANSFERIR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` con vehículos tomados; hoy se puede transferir a un vehículo sin jornada y anular esa transferencia. (2) La carga del vehículo en la apertura (RUT-02) reutiliza `STOCK_TRANSFERIR`.

**Deuda nominada por el change 14 para el change 24 (`rendicion`):** las diferencias de rendición (RUT-06) y el remanente (RUT-08) se escriben como movimientos `DIFERENCIA_RENDICION` por la única puerta; el motivo y la valorización siguen la regla de CST-12 (ADR-048).

**Deuda nominada por el change 14 para los changes 26 y 28 (reportes y auditoría):** (1) llevar el motivo a la fila de auditoría de `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (hoy `motivo_id` nulo; el bus solo lo copia en tres comandos de stock). (2) Reportes de ajustes y pérdidas por motivo y consulta de auditoría con motivo. (3) Un mecanismo común para los tres puertos de registro de `catalogo` (ADR-023, ADR-025, verificador de stock).

**Deuda nominada por el change 14 para el change 17 (`cobranzas`):** a la deuda ya nominada sobre la firma de `registro.HandlerFuncion` se suma que los handlers de stock tampoco funcionan por el despacho por lote (`_procesar_item_de_lote` no les pasa `sesion` ni `reloj`); hoy no hay efecto porque son solo online.

**[aceptado por el usuario el 2026-10-08, queda como deuda nominada]** Acceso a Ajustes desde el menú de `/admin`: hoy es un enlace dentro de la sección Stock (que se ofrece con `TRANSFERIR_STOCK`), así que un rol a medida con `AJUSTAR_STOCK` y sin `TRANSFERIR_STOCK` no llega desde el menú. Se deja así por ahora.
