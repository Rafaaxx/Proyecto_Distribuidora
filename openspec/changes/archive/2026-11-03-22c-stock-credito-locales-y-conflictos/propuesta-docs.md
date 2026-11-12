# Propuesta de cambios a `docs/` — change 22c `stock-credito-locales-y-conflictos`

> **Propuesta completa (tarea 13.1) con lo aprobado en 0.1 (D0 a D9 en A) y las precisiones del apply. Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-065-conciliacion-local-y-conflictos-en-el-telefono.md`.
>
> Orden: `01` CRE-08, SYN-11, SYN-09, VTA-24 (solo la referencia al change); `02` §6.4, §6.5, §13.2, §13.3, §13.4, §17; `04` §11 y la tabla de dependencias.

---

## `01-dominio.md`

### CRE-08 (conciliación por secuencia procesada y venta rechazada)

**Texto actual**

> | CRE-08 | Sin conexión, el saldo actual es el del bootstrap más los movimientos registrados por el dispositivo durante la jornada que todavía no tienen resultado del servidor (débito de la venta menos lo cobrado). Lo mismo rige para el stock del vehículo (RUT-04). La conciliación con un bootstrap posterior a una sincronización aceptada es del change 22c (ADR-063). | 1 |

**Texto propuesto**

> | CRE-08 | Sin conexión, el saldo actual es el del bootstrap más los movimientos registrados por el dispositivo durante la jornada que el bootstrap todavía no incluye (débito de la venta menos lo cobrado). Lo mismo rige para el stock del vehículo (RUT-04). Un movimiento local ya está incluido cuando la secuencia de su operación en la cola es menor o igual que la **secuencia procesada** del bootstrap (SYN-11); una operación fuera de la cola o un bootstrap sin esa marca cuentan siempre. Una venta **rechazada** sigue contando completa (stock, débito y su cobro en el momento, con el mismo `operation_id`) hasta que termine la jornada: la mercadería ya se entregó. Enviar una operación no la deja de contar: solo la deja de contar un bootstrap posterior que la incluya (ADR-063, ADR-065). | 1 |

### SYN-11 (la secuencia procesada)

**Texto actual**

> | SYN-11 | El bootstrap incluye: productos y presentaciones activos, clientes activos y suspendidos (y el consumidor final) con la cartera del usuario, saldo y datos de crédito, versiones de lista vigentes, programadas y las anteriores permitidas (estas, solo con `USAR_LISTA_ANTERIOR`), reglas de descuento activas no vencidas, stock de la ubicación tomada, permisos, contexto de venta y topes del usuario, medios, motivos y alícuotas activos, credenciales de autorización de supervisores (solo con `VENDER`), numeración del dispositivo y configuración de la organización y de la nota. Se lee en una sola foto de la base. No incluye costos ni utilidades (ADR-062). | 1 |

**Texto propuesto** (cambia el final)

> … numeración del dispositivo, **la secuencia procesada de la jornada** (la mayor `secuencia` de los comandos registrados de la jornada del bootstrap, del usuario y del dispositivo de la sesión; nula si no hay) y configuración de la organización y de la nota. Se lee en una sola foto de la base, la misma del stock y los saldos. No incluye costos ni utilidades (ADR-062, ADR-065). | 1 |

### SYN-09

**Sin cambios.** Lo visible (estados de envío, nada se borra, el bootstrap no toca las operaciones) sigue igual; el detalle de las observaciones y el motivo del rechazo se agregan en `02` §13.3.

### VTA-24 (solo la referencia al change)

**Texto actual**

> … Hasta el change 22c `VENTA_ANULAR` solo admite el modo `ONLINE` (ADR-058).

**Texto propuesto**

> … Hasta el change 22d `VENTA_ANULAR` solo admite el modo `ONLINE` (ADR-058, ADR-065).

---

## `02-arquitectura.md`

### §6.4 — Lote de sincronización (observaciones en el resultado)

**Texto actual**

> - El servidor los procesa en orden y responde un resultado por comando.

**Texto propuesto**

> - El servidor los procesa en orden y responde un resultado por comando: `operation_id`, `estado`, `resultado`, `error_codigo` y la lista `observaciones` (código, tipo e id de la operación y detalle; vacía si no hay), también al reenviar un comando ya procesado (ADR-065). Una venta o cobranza sin conexión nunca se rechaza por una regla de negocio de SYN-05 (INV-17): se acepta con observaciones.

### §6.5 y descripción de `VENTA_ANULAR` — referencia al change

**Texto actual**

> | `VENTA_ANULAR` | ✓ | (change 22c, VTA-24) |
>
> `VENTA_ANULAR` (`ANULAR_VENTA`; solo `ONLINE` hasta el change 22c) lleva …

**Texto propuesto**

> | `VENTA_ANULAR` | ✓ | (change 22d, VTA-24) |
>
> `VENTA_ANULAR` (`ANULAR_VENTA`; solo `ONLINE` hasta el change 22d) lleva …

### §13.2 — Base local (Dexie)

**Texto actual** (filas `sesion`, `movimientos_locales` y `cola`)

> | `sesion` | Usuario, permisos, topes, derivación del PIN, jornada abierta |
> | `movimientos_locales` | Efectos locales sobre stock y saldos (`VENTA_STOCK`, `VENTA_DEBITO`, `COBRANZA_CREDITO`), para calcular disponibles |
> | `cola` | Comandos ordenados por secuencia; `operation_id` único. `estado` es `PENDIENTE` hasta el resultado y luego `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO`, con el código de error y el momento del resultado. Nada se borra; se envían solo los `PENDIENTE` del usuario y del dispositivo de la sesión (ADR-064) |

**Texto propuesto**

> | `sesion` | Usuario, permisos, topes, derivación del PIN, jornada abierta y la **secuencia procesada** del último bootstrap (nula si faltó) |
> | `movimientos_locales` | Efectos locales sobre stock y saldos (`VENTA_STOCK`, `VENTA_DEBITO`, `COBRANZA_CREDITO`), para calcular disponibles. Su `estado_operacion` queda sin uso: qué movimientos cuentan lo decide la secuencia procesada y la secuencia de la operación en `cola` (CRE-08) |
> | `cola` | Comandos ordenados por secuencia; `operation_id` único. `estado` es `PENDIENTE` hasta el resultado y luego `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO`, con el código de error, el momento del resultado y las **observaciones** recibidas (se escriben en la misma transacción que el resultado). Nada se borra; se envían solo los `PENDIENTE` del usuario y del dispositivo de la sesión (ADR-064, ADR-065) |

Y en el párrafo de la versión de Dexie, agregar: «El change 22c no suma versión de Dexie: la marca y las observaciones son campos de filas existentes (ADR-065).»

### §13.3 — Motor de sincronización (detalle traducido)

**Texto actual**

> - Muestra en todo momento, en la cabecera de `/ruta`, … el botón «Sincronizar» y las ventas «Con observaciones» y «Rechazadas» (ADR-064).

**Texto propuesto** (se agrega al final de la viñeta)

> … Cada venta «Con observaciones» o «Rechazada» muestra, en la pantalla «Sincronización» (resumen) y en el detalle de la venta (explicación), el texto de cada observación o el motivo del rechazo, traducidos con una tabla cerrada de códigos (`shared/fixtures/sync/codigos-de-sincronizacion.json`, validada por el servidor y por el teléfono); un código desconocido muestra un texto general y el código. Los nombres (producto, medio, autorizador) salen de la base local; si ya no están se dice «un producto». Una venta enviada antes del 22c, sin observaciones guardadas, lo dice (ADR-065).

### §13.4 — Bootstrap (la marca y qué sigue sin tocarse)

**Texto actual**

> - El bootstrap reemplaza los datos maestros locales, pero **DEBE NO** tocar `ventas`, `cobranzas`, `movimientos_locales` ni `cola`.

**Texto propuesto**

> - El bootstrap reemplaza los datos maestros locales y guarda la **secuencia procesada** en `sesion`, pero **DEBE NO** tocar `ventas`, `cobranzas`, `movimientos_locales` ni `cola`: los movimientos de las operaciones que el bootstrap ya incluye dejan de contarse por la regla de CRE-08, no porque se borren (ADR-065). Stock, Productos y la ficha del cliente muestran los disponibles locales con la leyenda «Incluye tus ventas desde la última actualización» cuando hay ventas que cuentan.

### §17 — Observabilidad (registro de cierre del lote)

**Texto actual**

> - Métricas mínimas en logs: duración por comando, comandos por resultado, reintentos transitorios, tamaño de lotes de sync.

**Texto propuesto**

> - Métricas mínimas en logs: duración por comando, comandos por resultado, reintentos transitorios, tamaño de lotes de sync. Cada lote termina con un registro «Lote de sincronización cerrado» con `lote_tamano`, `lote_procesados`, `lote_aceptados`, `lote_con_observaciones`, `lote_rechazados`, `lote_cortado` (hubo corte por error transitorio) y `lote_duracion_ms`; nunca el contenido de los comandos ni el detalle de las observaciones. Un reenvío del mismo lote registra su propio cierre (ADR-065).

---

## `04-roadmap-changes.md`

### §11 — Fila del 22c y fila nueva del 22d

**Texto actual**

> | 22c | `stock-credito-locales-y-conflictos` | Stock y crédito locales para operar sin señal, anulación offline (VTA-24), pantalla de conflictos y observaciones, métricas de tamaño de lote (`02` §17) | INV-17 (SYN-05) |

**Texto propuesto**

> | 22c | `stock-credito-locales-y-conflictos` | Conciliación del saldo y el stock locales con el bootstrap (secuencia procesada), disponibles locales en Stock, Productos y la ficha, observaciones y rechazos traducidos en «Sincronización» y en el detalle de la venta, registro de cierre del lote (`02` §17) — **terminado (ADR-065)** | INV-17 (SYN-05) |
> | 22d | `anulacion-sin-conexion` | `VENTA_ANULAR` sin conexión (VTA-24): modo `OFFLINE`, anulación local de una venta de la jornada en curso, su efecto en los disponibles locales y su resultado en «Sincronización» (deuda de ADR-058); el teléfono deja de vender cuando, con conexión, se entera de que su jornada ya no está abierta (deuda del 22c) | — |

Párrafo de cierre del 22c (debajo de la tabla, como los de 22a y 22b):

> **Change 22c (`stock-credito-locales-y-conflictos`) archivado (fecha de archivo) — terminado (ADR-065).** Entrega: la secuencia procesada en el bootstrap; el saldo y el stock locales exactos después de actualizar los datos (sin descontar dos veces ni perder lo que el servidor aún no tiene), con la venta rechazada contando completa; las observaciones en el resultado del lote (servidor) y en `cola` (teléfono); los disponibles locales en Stock, Productos y la ficha; las observaciones y los rechazos traducidos (tabla cerrada de códigos con fixture compartido); el registro de cierre del lote; el cierre de INV-17 con una matriz de integración por regla de SYN-05; una clave de ayuda nueva y cuatro revisadas. Sin migración. **Deudas saldadas:** del 22a y del 22b «al 22c» (ADR-063, ADR-064): la conciliación, el detalle de las observaciones, la traducción de los códigos de rechazo y las métricas de lote. **Deudas reasignadas:** la anulación sin conexión (VTA-24, ADR-058 «al 22c») pasa al **22d**. **Deudas nuevas:** al **22d**, `VENTA_ANULAR` sin conexión y el corte de la venta con la jornada liberada; al **23**, la regla de la cobranza suelta sin conexión rechazada; al **25**, la resolución de las ventas rechazadas. **Prueba manual:** 2026-11-03, completa (pasos 1 a 16) y sin errores.
>
> **Deuda nominada por el change 22c para el change 22d (`anulacion-sin-conexion`), decisión del usuario 2026-11-03:** el servidor acepta las ventas de una jornada liberada con `JORNADA_LIBERADA` (RUT-09), pero el teléfono sigue ofreciendo «Vender» hasta que se refresca la página o se vuelve a entrar: tampoco corta cuando «Actualizar datos» responde que no hay jornada abierta. El 22d hace que el teléfono, cuando tiene conexión y se entera de que su jornada ya no está `ABIERTA` (al sincronizar, en la consulta periódica o porque el bootstrap responde `JORNADA_REQUERIDA`), deje de ofrecer «Vender» y avise «Tu jornada fue liberada». Lo ya vendido se sigue enviando. Sin conexión no cambia nada. El 22d registra la decisión en un ADR.
>
> **Deuda nominada por el change 22c para el change 25 (`observaciones-y-revision`), decisión del usuario 2026-11-03:** `docs/` no define cómo se resuelve una venta rechazada (SYN-06, SYN-09): queda en el teléfono, no se reenvía y sigue contando en los disponibles locales hasta el fin de la jornada. El 25 define cómo administración la revisa y la da por resuelta (por ejemplo, vinculándola con la venta que carga con conexión), con su permiso y su ADR, junto con la decisión pendiente sobre los comandos en cuarentena.

### Tabla de dependencias

**Texto actual**

> | 22c stock-credito-locales-y-conflictos | 22b |
> | 23 cobranza-offline | 22a |

**Texto propuesto**

> | 22c stock-credito-locales-y-conflictos | 22b |
> | 22d anulacion-sin-conexion | 22c |
> | 23 cobranza-offline | 22a |

El 22d va antes del 23 en el orden de construcción. En la nota «Change 22 es el más riesgoso …» se agrega: «22d (anulación sin conexión)».

### §11 — Párrafo duplicado del 22b dentro de la tabla

Se **quita** el párrafo «**Change 22b (`motor-sincronizacion`) archivado (fecha de archivo) — terminado (ADR-064).** …» que quedó entre las filas 22b y 22c de la tabla de §11: sobra, porque el párrafo definitivo (con la fecha 2026-11-01) está debajo de la tabla.

### Deudas

- ADR-063 y ADR-064 «al 22c»: **saldadas** (párrafo del 22c).
- ADR-058 «al 22c» (`VENTA_ANULAR` sin conexión): **reasignada al 22d**.
- Nueva, al 22d: el corte de la venta con la jornada liberada (decisión del usuario 2026-11-03, opción A).
- Nueva, al 25: la resolución de las ventas rechazadas (decisión del usuario 2026-11-03).
