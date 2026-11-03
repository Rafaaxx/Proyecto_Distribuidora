# Propuesta de cambios a `docs/` — change 22d `anulacion-sin-conexion`

> **Propuesta completa (tarea 17.1) con lo aprobado en 0.1 (D0 a D13 en A) y las precisiones del apply. Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-066-anulacion-sin-conexion-y-jornada-no-abierta.md` (pasa de *Propuesto* a *Vigente* al archivar).
>
> Orden: `01` VTA-24, SYN-06, SYN-07, STK-09, RUT-09, CRE-08; `02` §6.5 (fila y párrafo de `VENTA_ANULAR`), §13.2, §13.3; `03` `venta_anulacion`; `04` §11 (fila del 22d y deudas saldadas).

---

## `01-dominio.md`

### VTA-24 (modo `OFFLINE` habilitado)

**Texto actual**

> | VTA-24 | Sin conexión, un vendedor con `ANULAR_VENTA` puede anular solo ventas de su jornada en curso. La anulación es un comando que referencia a la venta por su identificador, que el dispositivo genera al confirmarla. Hasta el change 22d `VENTA_ANULAR` solo admite el modo `ONLINE` (ADR-058, ADR-065). | 1 |

**Texto propuesto**

> | VTA-24 | Sin conexión, un vendedor con `ANULAR_VENTA` puede anular solo ventas de su jornada en curso. La anulación es un comando que referencia a la venta por su identificador, que el dispositivo genera al confirmarla. `VENTA_ANULAR` v1 admite el modo `OFFLINE` por el lote de sincronización (por REST sigue siendo solo `ONLINE`): la venta debe ser de la jornada del sobre (`JORNADA_AJENA` si es de otra o no tiene jornada) y una venta inexistente o de otra organización es una dependencia inexistente (`VENTA_INEXISTENTE`, SYN-06). La anulación lleva la jornada del sobre aunque después se haya liberado. Una anulación enviada en el mismo lote que su venta se procesa después de ella (SYN-03). En el teléfono, la anulación se guarda, se encola y cuenta en el stock y el saldo locales en una sola transacción (CRE-08, INV-01) (ADR-058, ADR-066). | 1 |

### SYN-06 (`VENTA_INEXISTENTE`)

**Texto actual**

> | SYN-06 | Solo se rechazan comandos malformados, inconsistentes (SYN-02), de otra organización, con dependencias inexistentes o de dispositivos revocados. Una jornada del sobre que no existe en la organización es una dependencia inexistente (`JORNADA_INEXISTENTE`): en el lote el ítem se rechaza sin fila de comando y el lote sigue; por REST responde 404. Los comandos de dispositivos revocados se guardan en cuarentena para revisión manual; no se pierden. | 1 |

**Texto propuesto** (se agrega antes de la última oración)

> … por REST responde 404. **La venta que referencia una anulación sin conexión y no existe en la organización (nunca llegó, fue rechazada o es de otra organización) es también una dependencia inexistente (`VENTA_INEXISTENTE`): el ítem se rechaza con su fila de comando, de modo que el reenvío devuelve el mismo rechazo, y el lote sigue (ADR-066).** Los comandos de dispositivos revocados …

### SYN-07 (la anulación y sus observaciones)

**Texto actual** (fragmentos que cambian)

> … `PERMISO_REVOCADO`, `JORNADA_LIBERADA` … `UBICACION_TOMADA_AL_SINCRONIZAR` se emite solo sin conexión, sobre la venta, cuando la ubicación de la que salió el stock estaba tomada por una jornada al sincronizar (la propia en `EN_RENDICION` o la de otro vendedor); la venta se acepta igual (SYN-05, INV-17) y puede convivir con `JORNADA_LIBERADA` (aprobado por el usuario el 2026-10-20). …

**Texto propuesto** (se agrega al final de ese fragmento)

> … y puede convivir con `JORNADA_LIBERADA` (aprobado por el usuario el 2026-10-20). **`VENTA_ANULAR` sin conexión emite las mismas tres, siempre sobre la venta anulada: `PERMISO_REVOCADO` (el usuario ya no tenía `ANULAR_VENTA`), `JORNADA_LIBERADA` y `UBICACION_TOMADA_AL_SINCRONIZAR` (la mercadería vuelve a la ubicación donde está físicamente, sin jornada y con la constancia en la auditoría). La anulación sigue aceptada aunque las tenga, como la venta; un motivo del ámbito dado de baja después del bootstrap se acepta sin observación (ADR-066).** …

### STK-09 (también la anulación)

**Texto actual** (fragmento)

> … Una venta recibida sin conexión (SYN-05, INV-17) cuyo stock sale de una ubicación tomada al sincronizar —por la propia jornada en `EN_RENDICION` o por la de otro vendedor— se acepta aunque el usuario no tenga `LIBERAR_UBICACION`: la mercadería ya se entregó. Se descuenta el stock sin `jornada_id`, la venta conserva la jornada del sobre, lleva `UBICACION_TOMADA_AL_SINCRONIZAR` y la auditoría deja la constancia de la jornada que tiene la ubicación. Con conexión rige la regla de arriba (ADR-054).

**Texto propuesto**

> … Una venta recibida sin conexión (SYN-05, INV-17) cuyo stock sale de una ubicación tomada al sincronizar —por la propia jornada en `EN_RENDICION` o por la de otro vendedor— se acepta aunque el usuario no tenga `LIBERAR_UBICACION`: la mercadería ya se entregó. Se descuenta el stock sin `jornada_id`, la venta conserva la jornada del sobre, lleva `UBICACION_TOMADA_AL_SINCRONIZAR` y la auditoría deja la constancia de la jornada que tiene la ubicación. **Lo mismo vale para la anulación de una venta recibida sin conexión: la mercadería ya volvió al vehículo, se acepta, el reingreso queda sin `jornada_id`, la anulación conserva la jornada del sobre y lleva `UBICACION_TOMADA_AL_SINCRONIZAR` sobre la venta (ADR-066).** Con conexión rige la regla de arriba (ADR-054).

### RUT-09 (el teléfono corta la venta)

**Texto actual**

> | RUT-09 | Un usuario con `LIBERAR_UBICACION` puede liberar una jornada `ABIERTA` o `EN_RENDICION`, de cualquier usuario, con un motivo activo del ámbito `LIBERACION_JORNADA` y una observación opcional de hasta 500 caracteres; el stock del vehículo no se toca. Los comandos posteriores de esa jornada se aceptan al sincronizar con observación JORNADA_LIBERADA (a partir del primer comando de ruta, change 17). | 1 |

**Texto propuesto**

> | RUT-09 | Un usuario con `LIBERAR_UBICACION` puede liberar una jornada `ABIERTA` o `EN_RENDICION`, de cualquier usuario, con un motivo activo del ámbito `LIBERACION_JORNADA` y una observación opcional de hasta 500 caracteres; el stock del vehículo no se toca. Los comandos posteriores de esa jornada se aceptan al sincronizar con observación JORNADA_LIBERADA (a partir del primer comando de ruta, change 17), también la anulación de una venta. **El teléfono, cuando con conexión se entera de que su jornada ya no está `ABIERTA` (la consulta de cada ciclo de sincronización, `JORNADA_REQUERIDA` de «Actualizar datos», la consulta al entrar sin jornada o una `JORNADA_LIBERADA` en los resultados), lo guarda, deja de ofrecer «Vender» y «Anular venta» y avisa según el estado («Tu jornada fue liberada.», «Tu jornada está en rendición.», «Tu jornada fue cerrada.» o «Tu jornada ya no está abierta.», seguido de «Lo que ya vendiste se sigue enviando.»). El aviso vale sin señal y después de recargar; lo ya vendido y anulado se sigue enviando; sin conexión no cambia nada; al abrir otra jornada se borra (ADR-066).** | 1 |

### CRE-08 (la anulación y su rechazo)

**Texto actual**

> | CRE-08 | Sin conexión, el saldo actual es el del bootstrap más los movimientos registrados por el dispositivo durante la jornada que el bootstrap todavía no incluye (débito de la venta menos lo cobrado). Lo mismo rige para el stock del vehículo (RUT-04). Un movimiento local ya está incluido cuando la secuencia de su operación en la cola es menor o igual que la **secuencia procesada** del bootstrap (SYN-11); una operación fuera de la cola o un bootstrap sin esa marca cuentan siempre. Una venta **rechazada** sigue contando completa (stock, débito y su cobro en el momento, con el mismo `operation_id`) hasta que termine la jornada: la mercadería ya se entregó. Enviar una operación no la deja de contar: solo la deja de contar un bootstrap posterior que la incluya (ADR-063, ADR-065). | 1 |

**Texto propuesto** (se agrega antes de «Enviar una operación…»)

> … hasta que termine la jornada: la mercadería ya se entregó. **Una anulación local cuenta desde que se confirma, con la misma regla de la secuencia: devuelve el stock de la venta, acredita el total en la cuenta y, con devolución, descuenta lo cobrado en el momento (sin devolución, lo cobrado queda a favor del cliente). Una anulación rechazada deja de contar —la venta sigue vigente—, salvo que su venta también esté rechazada: entonces cuentan las dos y se compensan (ADR-066).** Enviar una operación no la deja de contar: solo la deja de contar un bootstrap posterior que la incluya (ADR-063, ADR-065, ADR-066). | 1 |

---

## `02-arquitectura.md`

### §6.5 — Fila de `VENTA_ANULAR` en la tabla de tipos

**Texto actual**

> | `VENTA_ANULAR` | ✓ | (change 22d, VTA-24) |

**Texto propuesto**

> | `VENTA_ANULAR` | ✓ | ✓ (solo por el lote; VTA-24, ADR-066) |

### §6.5 — Párrafo de `VENTA_ANULAR`

**Texto actual**

> `VENTA_ANULAR` (`ANULAR_VENTA`; solo `ONLINE` hasta el change 22d) lleva la venta (`venta_id`, el identificador que generó el dispositivo), un motivo del ámbito `ANULACION_VENTA`, una observación opcional de hasta 500 caracteres y `devuelve_dinero` (booleano estricto: obligatorio si la venta tiene su cobranza confirmada y omitido si no). Errores propios: `VENTA_YA_ANULADA` y `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409) y `DEVOLUCION_INVALIDA` (422); además `MOTIVO_INVALIDO`, `OBSERVACION_INVALIDA`, `UBICACION_TOMADA` y `UBICACION_INACTIVA`. Ruta `POST /api/v1/ventas/{venta_id}/anulacion`. No emite observaciones de SYN-07: el reingreso nunca deja stock negativo. Una fila de auditoría por comando, con el motivo y, en su observación, la cobranza anulada y la constancia de la ubicación tomada (AUD-01, AUD-02, ADR-058).

**Texto propuesto**

> `VENTA_ANULAR` (`ANULAR_VENTA`; v1 en los dos modos: por REST `POST /api/v1/ventas/{venta_id}/anulacion` solo `ONLINE`, por el lote de sincronización también `OFFLINE`) lleva la venta (`venta_id`, el identificador que generó el dispositivo), un motivo del ámbito `ANULACION_VENTA`, una observación opcional de hasta 500 caracteres y `devuelve_dinero` (booleano estricto: obligatorio si la venta tiene su cobranza confirmada y omitido si no). Errores propios: `VENTA_YA_ANULADA` y `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409) y `DEVOLUCION_INVALIDA` (422); además `MOTIVO_INVALIDO`, `OBSERVACION_INVALIDA`, `UBICACION_TOMADA` y `UBICACION_INACTIVA`. **Sin conexión, la venta debe ser de la jornada del sobre (`JORNADA_AJENA`) y una venta inexistente o de otra organización es `VENTA_INEXISTENTE`; se rechazan `VENTA_YA_ANULADA`, `DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`, `OBSERVACION_INVALIDA`, `MOTIVO_INVALIDO` (de otra organización o de otro ámbito) y `UBICACION_INACTIVA`; se aceptan un motivo dado de baja después del bootstrap (sin observación), el permiso revocado (`PERMISO_REVOCADO`), la jornada liberada (`JORNADA_LIBERADA`) y la ubicación tomada al sincronizar (`UBICACION_TOMADA_AL_SINCRONIZAR`), todas sobre la venta. `venta_anulacion.jornada_id` es la jornada del sobre; el reingreso la lleva solo si la ubicación es de esa jornada y está `ABIERTA`. El orden de bloqueo no cambia.** Con conexión no emite observaciones de SYN-07: el reingreso nunca deja stock negativo. Una fila de auditoría por comando, con el motivo y, en su observación, la cobranza anulada y la constancia de la ubicación tomada (AUD-01, AUD-02, ADR-058, ADR-066).

### §13.2 — Base local (Dexie)

**Texto actual** (filas `movimientos_locales` y siguientes, y el párrafo posterior)

> | `movimientos_locales` | Efectos locales sobre stock y saldos (`VENTA_STOCK`, `VENTA_DEBITO`, `COBRANZA_CREDITO`), para calcular disponibles. Su `estado_operacion` queda sin uso: qué movimientos cuentan lo decide la secuencia procesada y la secuencia de la operación en `cola` (CRE-08) |
>
> Las tablas de operaciones (versión 3 de Dexie) no las toca el bootstrap. El change 22c no suma versión de Dexie: la marca y las observaciones son campos de filas existentes (ADR-065). Confirmar una venta local escribe venta, cobranza, movimientos, comando y los dos contadores en **una sola transacción**: todo o nada. Reconfirmar con el mismo `operation_id` no encola otra venta (ADR-063).

**Texto propuesto**

> | `anulaciones` | Una por venta anulada en el dispositivo (`venta_id` clave, `operation_id` único, `jornada_id`, `estado_envio`): motivo, observación, `devuelve_dinero`, momento y nombre del motivo (para la nota). Su estado de envío cambia solo con el resultado del servidor y es independiente del de la venta |
> | `movimientos_locales` | Efectos locales sobre stock y saldos (`VENTA_STOCK`, `VENTA_DEBITO`, `COBRANZA_CREDITO` y, de la anulación, `ANULACION_STOCK`, `ANULACION_CREDITO`, `ANULACION_COBRANZA_DEBITO`, con el `operation_id` de la anulación), para calcular disponibles. Su `estado_operacion` queda sin uso: qué movimientos cuentan lo decide la secuencia procesada y la secuencia de la operación en `cola` (CRE-08) |
>
> Las tablas de operaciones (versión 4 de Dexie, change 22d) no las toca el bootstrap; la versión 4 solo agrega `anulaciones` y no modifica las demás (ADR-066). Confirmar una venta local escribe venta, cobranza, movimientos, comando y los dos contadores en **una sola transacción**: todo o nada; **anular una venta local escribe la anulación, sus movimientos, el comando `VENTA_ANULAR` `OFFLINE` y la última secuencia en una sola transacción, y reconfirmar la anulación de la misma venta devuelve la existente**. Reconfirmar con el mismo `operation_id` no encola otra venta (ADR-063). `meta` guarda además `jornada_no_abierta` (jornada, estado —`LIBERADA`, `EN_RENDICION`, `CERRADA` o «desconocido»— y momento en que el teléfono se enteró), que se ignora si la jornada de la sesión es otra y se borra al aplicar el bootstrap de otra jornada (RUT-09).

### §13.3 — Motor de sincronización

**Texto actual** (dos viñetas)

> - Usa una cola propia: envía en lotes de hasta 50, en orden de secuencia, solo los `PENDIENTE` del usuario y del dispositivo de la sesión (de cualquier jornada); un `RECHAZADO` no se reenvía solo. Aplica los resultados por `operation_id` en una sola transacción Dexie por lote (INV-01).
>
> - Muestra en todo momento, en la cabecera de `/ruta`, el estado de conexión y «N sin enviar» (o «Todo enviado»), con un aviso si hay ventas rechazadas; el inicio y la pantalla «Sincronización» muestran además la última sincronización exitosa, el último error con su texto y código, el botón «Sincronizar» y las ventas «Con observaciones» y «Rechazadas» (ADR-064). …

**Texto propuesto**

> - Usa una cola propia: envía en lotes de hasta 50, en orden de secuencia, solo los `PENDIENTE` del usuario y del dispositivo de la sesión (de cualquier jornada); un `RECHAZADO` no se reenvía solo. Aplica los resultados por `operation_id` en una sola transacción Dexie por lote (INV-01); **el resultado de una anulación cambia el estado de la fila de `anulaciones` y de su comando, no el de la venta**.
> - **Al empezar cada ciclo de sincronización (todos los disparadores, también con la cola vacía), junto a la versión mínima, consulta `GET /api/v1/stock/jornadas/{id}` de la jornada de la sesión; si no está `ABIERTA`, lo guarda en `meta.jornada_no_abierta` (RUT-09). Sin conexión, con 403 (el usuario no tiene `ABRIR_JORNADA`), 404 o cualquier error, no cambia nada y la sincronización sigue. Además lo aprenden `JORNADA_REQUERIDA` de «Actualizar datos» o del bootstrap, la consulta al entrar sin jornada abierta y una `JORNADA_LIBERADA` en los resultados del lote. La cola se sigue enviando con la jornada no abierta (ADR-066).**
> - Muestra en todo momento, en la cabecera de `/ruta`, el estado de conexión y «N sin enviar» (o «Todo enviado»), con un aviso si hay ventas rechazadas; el inicio y la pantalla «Sincronización» muestran además la última sincronización exitosa, el último error con su texto y código, el botón «Sincronizar» y las ventas «Con observaciones» y «Rechazadas» **y las anulaciones con problemas («Anulación de {número}»)** (ADR-064). **Lo pendiente se dice «N ventas y M anulaciones sin enviar» (solo ventas: «N ventas sin enviar»; solo anulaciones: «M anulaciones sin enviar»), también en los avisos de cierre de sesión y de pendientes de otro usuario.** …

---

## `03-modelo-de-datos.md`

### `venta_anulacion` — `jornada_id` sin conexión

**Texto actual**

> `id`, `organizacion_id`, `venta_id`, `motivo_id`, `observacion` (opcional, hasta 500), `devuelve_dinero` `boolean` (VTA-22; nulo si y solo si la venta no tenía cobranza confirmada), `jornada_id` (nulable: la jornada `ABIERTA` del usuario y el dispositivo sobre la ubicación de la venta, STK-09), columnas de operación. …

**Texto propuesto**

> … `jornada_id` (nulable: **con conexión**, la jornada `ABIERTA` del usuario y el dispositivo sobre la ubicación de la venta, STK-09; **sin conexión, la jornada del sobre —que es la de la venta—, aunque después se haya liberado, de modo que la rendición del change 24 cuenta la anulación por esa jornada, RUT-07; ADR-066**), columnas de operación. … *(Sin migración: la columna ya era nulable.)*

---

## `04-roadmap-changes.md`

### §11 — Fila del change 22d

**Texto actual**

> | 22d | `anulacion-sin-conexion` | `VENTA_ANULAR` sin conexión (VTA-24): modo `OFFLINE`, anulación local de una venta de la jornada en curso, su efecto en los disponibles locales y su resultado en «Sincronización» (deuda de ADR-058); el teléfono deja de vender cuando, con conexión, se entera de que su jornada ya no está abierta (deuda del 22c) | — |

**Texto propuesto**

> | 22d | `anulacion-sin-conexion` | `VENTA_ANULAR` sin conexión (VTA-24): modo `OFFLINE`, anulación local de una venta de la jornada en curso, su efecto en los disponibles locales y su resultado en «Sincronización» (deuda de ADR-058); el teléfono deja de vender cuando, con conexión, se entera de que su jornada ya no está abierta (deuda del 22c) — **terminado (ADR-066)** | — |

### §11 — Párrafo de cierre del 22d (nuevo, después del párrafo del 22c)

**Texto propuesto**

> **Change 22d (`anulacion-sin-conexion`) archivado (fecha de archivo) — terminado (ADR-066).** Entrega: `VENTA_ANULAR` v1 por el lote en modo `OFFLINE` (jornada del sobre, `JORNADA_AJENA`, `VENTA_INEXISTENTE`, rechazos y observaciones de D2, `venta_anulacion.jornada_id` del sobre); la anulación local atómica en el teléfono (Dexie v4 con `anulaciones`, movimientos inversos, comando encolado detrás de su venta), su efecto en los disponibles locales (CRE-08) y su resultado en «Sincronización» y en el detalle; la pantalla `/ruta/ventas/:id/anular`, la etiqueta «Anulada», la nota local con «ANULADA» y los pendientes «N ventas y M anulaciones sin enviar»; el estado de la jornada en el teléfono (consulta de cada ciclo, `JORNADA_REQUERIDA`, `JORNADA_LIBERADA`) con el corte de «Vender» y «Anular venta» y el aviso por estado; tres claves de ayuda nuevas y cuatro revisadas; el fixture `venta-anular-offline.json` y los códigos de la anulación en `codigos-de-sincronizacion.json`; la spec principal `ventas/anulacion-de-venta`, que faltaba, restituida. Sin migración ni permisos nuevos (el Vendedor no recibe `ANULAR_VENTA` por defecto). **Deudas saldadas:** la de ADR-058 «al 22c» (reasignada al 22d por ADR-065) y la del 22c «al 22d» (el corte de «Vender» con la jornada liberada). **Deudas nuevas:** al **24** (rendición), contar las anulaciones por `venta_anulacion.jornada_id` aunque la jornada se haya liberado; al **25**, la anulación de una venta «Rechazada» y la resolución de las rechazadas (D5). **Prueba manual:** pendiente (tarea 21.1).

### §11 — Deudas de ADR-058 y del 22c que se saldan

**Texto actual** (change 19, deudas nuevas)

> … al **22c**, habilitar `VENTA_ANULAR` sin conexión sin una v2 del comando (VTA-24: la regla de la jornada en curso, con la venta y la anulación con la misma jornada del sobre, `JORNADA_AJENA` si no, y la venta inexistente como dependencia inexistente); …
>
> **Deudas reasignadas** (22c): la anulación sin conexión (VTA-24, ADR-058 «al 22c») pasa al **22d**. **Deudas nuevas:** al **22d**, `VENTA_ANULAR` sin conexión y el corte de la venta con la jornada liberada; …
>
> **Deuda nominada por el change 22c para el change 22d …** (párrafo completo).

**Texto propuesto**

> En el párrafo del change 19, «al **22c**, habilitar …» pasa a «al **22c/22d** (saldada en el 22d, ADR-066), habilitar …». En el del 22c, «**Deudas reasignadas** … pasa al **22d**» y «**Deudas nuevas:** al **22d** …» se marcan «(saldadas en el 22d, ADR-066)». En el párrafo «Deuda nominada por el change 22c para el change 22d» se agrega al final: «**Saldada en el 22d (ADR-066):** el teléfono guarda el estado de su jornada y corta «Vender» y «Anular venta» con un aviso por estado.»
