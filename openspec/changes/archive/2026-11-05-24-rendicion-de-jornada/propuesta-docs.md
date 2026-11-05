# Propuesta de cambios a `docs/` — change 24 `rendicion-de-jornada`

> **Completada el 2026-11-04 (tarea 20.1) con las opciones A de `design.md`, aprobadas en 0.1, y las precisiones del apply (ADR-068, «Precisiones del apply»). Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-068-rendicion-de-jornada.md` (pasa de *Propuesto* a *Vigente* al archivar). Las fechas del archivo van como AAAA-MM-DD hasta el archivo; la prueba manual y las decisiones llevan su fecha.
>
> **Cuidado al aplicar:** toda fila de las tablas de `01-dominio.md` debe conservar la columna `| ID |` al principio y `| etapa |` al final (el archivo de un change anterior truncó filas). Después de aplicar, correr `frontend/tests/unit/ayuda/trazabilidad.test.ts`.
>
> Orden: `01` RUT-05 a RUT-08, STK-09, CST-12, SYN-07, AUD-01, §18, §19, §21; `02` §6.5, §7.3, §13.3; `03` §9 (`jornada`, `rendicion`, `rendicion_linea`, `observacion`); `04` §2, §11.

---

## `01-dominio.md`

### RUT-05 (la entrega del día)

**Texto actual**

> | RUT-05 | La rendición requiere conexión, `RENDIR_JORNADA` y que el dispositivo no tenga comandos pendientes de esa jornada. | 1 |

**Texto propuesto**

> | RUT-05 | La rendición requiere conexión, `RENDIR_JORNADA` y que el dispositivo no tenga comandos pendientes de esa jornada. **Se cumple con la entrega del día: el vendedor toca «Terminar el día» en el teléfono (con `ABRIR_JORNADA`, con o sin señal), que encola `JORNADA_ENTREGAR` detrás de todo lo pendiente y deja de ofrecer «Vender», «Anular venta» y «Cobrar» en esa jornada. Como la cola se procesa en orden y un error transitorio corta el lote, cuando el servidor acepta la entrega todo lo anterior del dispositivo ya tiene resultado. La entrega exige la jornada propia `ABIERTA` y no entregada (`JORNADA_ESTADO_INVALIDO`, `JORNADA_YA_ENTREGADA`; el handler exige `ABRIR_JORNADA`, `PERMISO_REQUERIDO`), no cambia su estado y no se revierte; una jornada que ya se entregó y después se libera conserva su entrega (RUT-09). La rendición exige la entrega (`JORNADA_SIN_ENTREGA`); sin teléfono no hay rendición y la jornada se libera (RUT-09) (ADR-068).** | 1 |

### RUT-06 (el conteo y las diferencias)

**Texto actual**

> | RUT-06 | En la rendición se registra el conteo físico por producto. La diferencia entre contado y esperado genera un movimiento DIFERENCIA_RENDICION auditado. | 1 |

**Texto propuesto**

> | RUT-06 | En la rendición se registra el conteo físico por producto. La diferencia entre contado y esperado genera un movimiento DIFERENCIA_RENDICION auditado. **Se cuentan todos los productos con saldo distinto de cero en la ubicación o con movimientos en ella durante la jornada (`CONTEO_INCOMPLETO`), en unidades base enteras no negativas (un número con decimales se rechaza como contenido no serializable y uno negativo con `CANTIDAD_INVALIDA`); se puede agregar un sobrante de un producto activo (el faltante de un producto inactivo se acepta; su sobrante exige reactivarlo). Si el esperado cambió mientras se contaba, se rechaza (`ESPERADO_DIFIERE`, con los productos distintos y sus esperados) sin escribir nada. Cada diferencia distinta de cero es un `DIFERENCIA_RENDICION` con origen en la rendición y con la jornada, sin motivo, al promedio vigente sin recalcularlo (CST-12); un sobrante de un producto sin promedio entra con costo nulo; un producto inactivo con una diferencia distinta de cero se rechaza (`PRODUCTO_INACTIVO`). Después de la rendición el stock es lo contado. Una observación opcional de hasta 500 caracteres acompaña la rendición (ADR-068).** | 1 |

### RUT-07 (el resumen)

**Texto actual**

> | RUT-07 | El resumen de rendición muestra stock al abrir, ingresos, ventas, anulaciones, stock esperado, contado, diferencias y cobranzas por medio de pago. | 1 |

**Texto propuesto**

> | RUT-07 | El resumen de rendición muestra stock al abrir, ingresos, ventas, anulaciones, stock esperado, contado, diferencias y cobranzas por medio de pago. **El stock se toma por producto de los movimientos de la ubicación registrados entre la apertura y la rendición: al abrir, ingresos (`TRANSFERENCIA_ENTRADA`), ventas, anulaciones de venta y otros; esperado = al abrir + ingresos − ventas + anulaciones + otros, y se congela al rendir. El dinero se toma por la jornada de cada operación: ventas vigentes y anuladas (por la jornada de la anulación, aunque se haya liberado), cobranzas confirmadas por medio de pago y anuladas aparte; lo registrado después del momento de registro de la rendición («tardío») se muestra aparte. El valor de las diferencias requiere `VER_COSTOS`. Una jornada sin conteo muestra el stock calculado sin contado ni diferencias (ADR-068).** | 1 |

### RUT-08 (el remanente en el cierre)

**Texto actual**

> | RUT-08 | Tras la rendición puede transferirse el remanente a depósito. El cierre (`EN_RENDICION → CERRADA`) libera la ubicación, que vuelve a moverse libremente. | 1 |

**Texto propuesto**

> | RUT-08 | Tras la rendición puede transferirse el remanente a depósito. El cierre (`EN_RENDICION → CERRADA`) libera la ubicación, que vuelve a moverse libremente. **La devolución se hace en el cierre, opcional y con `TRANSFERIR_STOCK`: una transferencia común (anulable) a una ubicación activa sin toma (`UBICACION_CON_TOMA` si el destino requiere toma), que no puede dejar negativo, en la misma transacción que el cierre (ADR-068).** | 1 |

### STK-09 (la excepción de la rendición)

**Texto actual** (fragmento que cambia)

> … Excepciones: la rendición (change 24) y los usuarios con `LIBERAR_UBICACION`, que mueven la ubicación en cualquier estado de la jornada; ese movimiento queda sin jornada y con una observación en la auditoría que nombra la jornada. …

**Texto propuesto**

> … Excepciones: la rendición y los usuarios con `LIBERAR_UBICACION`, que mueven la ubicación en cualquier estado de la jornada; el movimiento de `LIBERAR_UBICACION` queda sin jornada y con una observación en la auditoría que nombra la jornada. **La rendición mueve solo la ubicación de la jornada que rinde o cierra (las diferencias y la salida de la devolución del remanente), y esos movimientos llevan la jornada (ADR-068).** …

### CST-12 (las rendiciones)

**Texto actual** (fragmento que cambia)

> | CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio ni dejan historia de costo. Todo movimiento de transferencia o de ajuste, de ingreso o de egreso, y los egresos de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. …

**Texto propuesto**

> | CST-12 | Las transferencias, los ajustes y las rendiciones no modifican el promedio ni dejan historia de costo. Todo movimiento de transferencia, de ajuste **o de diferencia de rendición**, de ingreso o de egreso, y los egresos de corrección de un stock inicial (STK-10), se valorizan al promedio vigente. **Un sobrante de rendición de un producto sin promedio entra con costo nulo (ADR-068).** …

### SYN-07 (`JORNADA_RENDIDA`)

**Texto actual** (fragmento que cambia)

> | SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, …, UBICACION_TOMADA_AL_SINCRONIZAR, AUTORIZACION_OFFLINE. …

**Texto propuesto** (se agrega el código a la lista y una oración al final de la fila, antes de `| 1 |`)

> | SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, …, UBICACION_TOMADA_AL_SINCRONIZAR, AUTORIZACION_OFFLINE, **JORNADA_RENDIDA**. … **`JORNADA_RENDIDA` se emite solo sin conexión, una por operación, sobre la venta, la anulación o la cobranza cuya jornada del sobre está `EN_RENDICION` o `CERRADA`; su detalle indica la jornada y el momento de la rendición; la operación no entra en el conteo (ADR-068).** | 1 |

### AUD-01 (la rendición)

**Texto actual** (fragmento que cambia)

> … apertura, rendición, cierre y liberación forzada de jornadas (la fila de `JORNADA_LIBERAR` lleva el motivo, AUD-02); …

**Texto propuesto**

> … apertura, **entrega del día**, rendición **con su conteo y sus diferencias**, cierre **con la devolución del remanente** y liberación forzada de jornadas (la fila de `JORNADA_LIBERAR` lleva el motivo, AUD-02; **la rendición no lleva motivo: su registro es la rendición y sus líneas, ADR-068**); …

### §18 Jornada (párrafo)

**Texto actual**

> **Jornada.** "No cerrada" es `ABIERTA` o `EN_RENDICION`: en esos dos estados la ubicación está tomada. `ABIERTA → EN_RENDICION` es la rendición; `EN_RENDICION → CERRADA` es el cierre y libera la ubicación; `LIBERADA` es la liberación forzada con motivo. Cualquier otra transición se rechaza con `JORNADA_ESTADO_INVALIDO` y deja la jornada como estaba; una `CERRADA` o `LIBERADA` no admite ninguna. Hasta el change 24 la rendición no registra conteo ni diferencias (RUT-05 a RUT-07 son de ese change): la jornada pasa a `EN_RENDICION` y se cierra. Las jornadas cerradas antes del 24 no tienen conteo.

**Texto propuesto**

> **Jornada.** "No cerrada" es `ABIERTA` o `EN_RENDICION`: en esos dos estados la ubicación está tomada. `ABIERTA → EN_RENDICION` es la rendición **(exige la entrega del día y registra el conteo, RUT-05, RUT-06)**; `EN_RENDICION → CERRADA` es el cierre y libera la ubicación **(puede devolver el remanente, RUT-08)**; `LIBERADA` es la liberación forzada con motivo. **La entrega del día no es un estado: la jornada entregada sigue `ABIERTA`.** Cualquier otra transición se rechaza con `JORNADA_ESTADO_INVALIDO` y deja la jornada como estaba; una `CERRADA` o `LIBERADA` no admite ninguna. **Las jornadas cerradas antes del change 24 y las liberadas no tienen conteo; su resumen muestra el stock calculado (ADR-068).**

### §19 (lecturas de jornadas)

**Texto actual** (fragmento que cambia)

> El listado y el detalle de jornadas se leen con cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, y alcanzan a todas las jornadas de la organización; …

**Texto propuesto**

> El listado, el detalle **y el resumen** de jornadas se leen con cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, y alcanzan a todas las jornadas de la organización **(el valor de las diferencias, además con `VER_COSTOS`); `RENDIR_JORNADA` lee también, solo en lectura, los productos activos para agregar un sobrante, y devolver el remanente en el cierre exige además `TRANSFERIR_STOCK`. La entrega del día se hace con `ABRIR_JORNADA` (ADR-068)**; …

### §21 (fila de la diferencia de rendición)

**Texto actual**

> | Diferencia de rendición | + / − | — | — | — | — | Sí |

**Texto propuesto**

> | Diferencia de rendición | + / − | No cambia (valoriza al promedio vigente) | — | — | — | Sí |

---

## `02-arquitectura.md`

### §6.5 (comandos de jornada)

**Texto actual** (fragmento que cambia)

> `JORNADA_RENDIR` y `JORNADA_CERRAR` (`RENDIR_JORNADA`) llevan la jornada (en la ruta); … Los cuatro son solo online, con `Operation-Id`; …

**Texto propuesto**

> `JORNADA_RENDIR` **v2** y `JORNADA_CERRAR` (`RENDIR_JORNADA`) llevan la jornada (en la ruta); **la rendición lleva además las líneas del conteo (producto, cantidad contada, esperado visto) y una observación opcional, y exige la entrega; el cierre v2, una devolución opcional (destino y líneas; con `TRANSFERIR_STOCK`). `JORNADA_RENDIR` v1 no se acepta más (`VERSION_DE_COMANDO_SIN_HANDLER`, tampoco al reenviar uno ya aceptado: el bus resuelve el handler antes de la idempotencia). `JORNADA_ENTREGAR` v1 (`ABRIR_JORNADA`) solo por el lote en modo `OFFLINE`, con el contenido vacío y la jornada del sobre; `JORNADA_CERRAR` v1 sigue registrada.** Los **cuatro de `/admin`** son solo online, con `Operation-Id`; … **Errores nuevos: `JORNADA_SIN_ENTREGA`, `JORNADA_YA_ENTREGADA`, `ESPERADO_DIFIERE` y `UBICACION_CON_TOMA` (409), `CONTEO_INCOMPLETO` (422); `CANTIDAD_INVALIDA`, `PRODUCTO_REPETIDO` y `OBSERVACION_INVALIDA` (422) en el conteo. Lecturas nuevas: `GET /api/v1/stock/jornadas/{id}/resumen`; `GET /api/v1/stock/jornadas/{id}` devuelve además `entregada_en`; `GET /api/v1/catalogo/productos` se abre, solo en lectura, a `RENDIR_JORNADA`. Los lectores de ventas y cobranzas del resumen se registran como puertos en `stock/service.py` (límite entre módulos, ADR-025) (ADR-068).**

### §7.3 (orden de bloqueo de la rendición)

**Texto actual** (fragmento que cambia)

> … `JORNADA_RENDIR`, `JORNADA_CERRAR` y `JORNADA_LIBERAR` toman su jornada `FOR UPDATE`, revalidan el estado y no tocan stock ni saldos, por lo que no pueden cerrar un ciclo; una liberación espera a los movimientos en curso de esa jornada y al revés (ADR-049). La rendición del change 24, que necesitará la jornada antes que el stock, debe resolver cómo convive con este nivel. …

**Texto propuesto**

> … `JORNADA_LIBERAR` **y `JORNADA_ENTREGAR` toman** su jornada `FOR UPDATE`, revalidan el estado y no tocan stock ni saldos, por lo que no pueden cerrar un ciclo; una liberación espera a los movimientos en curso de esa jornada y al revés (ADR-049). **`JORNADA_RENDIR` y `JORNADA_CERRAR` toman primero la ubicación de la jornada `FOR UPDATE` (en el mismo paso en que los movimientos la toman `FOR SHARE`, como `JORNADA_ABRIR`), después la jornada `FOR NO KEY UPDATE` (no choca con el bloqueo de clave que toma la fila de `comando` de una operación sin conexión al referenciar la jornada, y sí con el `FOR SHARE` de los movimientos), leen los saldos y llaman una sola vez a `registrar_movimientos` (niveles 2 a 5; el nivel 5 es la misma jornada, ya tomada). No toman `saldo_cuenta`: una venta o una cobranza que lo tiene y espera la ubicación o la jornada no cierra ciclo (ADR-068).** …

### §13.3 (la entrega en el teléfono)

**Texto propuesto** (viñeta nueva)

> - **«Terminar el día» encola `JORNADA_ENTREGAR` `OFFLINE` con la siguiente secuencia y guarda en `meta` la marca de la jornada con el estado local `ENTREGADA`, en una sola transacción; corta «Vender», «Anular venta» y «Cobrar» como la jornada no abierta (ADR-066), también sin señal y después de recargar, y «Sincronización» muestra «Entrega del día» y su resultado, y la excluye de los pendientes. Sin versión nueva de Dexie (ADR-068).**

---

## `03-modelo-de-datos.md`

### §9 `jornada` (columnas nuevas)

**Texto propuesto** (fila nueva de la tabla y precisión del `CHECK` y de los privilegios)

> | `entregada_en`, `entrega_occurred_at`, `entrega_secuencia` | `timestamptz`, `timestamptz`, `integer` | RUT-05. La entrega del día: nulas juntas; solo en `ABIERTA`, `EN_RENDICION`, `CERRADA` o `LIBERADA` (`ck_jornada__entrega_coherente`: una jornada entregada y luego liberada la conserva); toda `EN_RENDICION` o `CERRADA` posterior al change 24 la tiene (ADR-068) |
>
> … El usuario de aplicación tiene `SELECT` e `INSERT`, y `UPDATE` **solo** de `estado`, de las columnas de transición **y de las de la entrega** …

### §9 `rendicion` y `rendicion_linea`

**Texto actual**

> | `rendicion` | `id`, `organizacion_id`, `jornada_id` (único), columnas de operación |
> | `rendicion_linea` | `id`, `organizacion_id`, `rendicion_id`, `producto_id`, `cantidad_esperada`, `cantidad_contada`, `diferencia` `integer` |
>
> Las diferencias generan movimientos `DIFERENCIA_RENDICION` con origen en la rendición (RUT-06).

**Texto propuesto**

> | `rendicion` | `id`, `organizacion_id`, `jornada_id` (único), **`observacion` (opcional, de 1 a 500)**, columnas de operación |
> | `rendicion_linea` | `id`, `organizacion_id`, `rendicion_id`, `producto_id`, **`stock_al_abrir`, `ingresos`, `ventas`, `anulaciones`, `otros`**, `cantidad_esperada`, `cantidad_contada` (**`CHECK (>= 0)`**), `diferencia` `integer`; **`costo_unitario` `numeric(18,6)` nulable; `UNIQUE (organizacion_id, rendicion_id, producto_id)`; `CHECK (diferencia = cantidad_contada - cantidad_esperada)` y `CHECK (cantidad_esperada = stock_al_abrir + ingresos - ventas + anulaciones + otros)`** |
>
> Las diferencias generan movimientos `DIFERENCIA_RENDICION` con origen en la rendición (RUT-06). **FK compuestas a `jornada`, `producto`, `usuario` y `dispositivo`. El usuario de aplicación tiene `SELECT` e `INSERT` y nunca `UPDATE` ni `DELETE` (INV-05). Las columnas de la línea son el resumen de stock congelado al rendir (RUT-07, ADR-068).**

### Migración

**Texto propuesto:** revisión `d2f4a6c8e0b1_rendicion_de_jornada` (sobre el head anterior): crea `rendicion` y `rendicion_linea`, agrega las tres columnas de `jornada` y rehace el `CHECK` de `observacion.codigo`; sube y baja limpia sobre una base con datos y el `downgrade` aborta con un mensaje claro si hay rendiciones o entregas (ADR-068).

### `observacion` (catálogo)

**Texto propuesto:** el `CHECK` de `codigo` suma `JORNADA_RENDIDA` (SYN-07, ADR-068).

---

## `04-roadmap-changes.md`

### §2 (excepción de tamaño)

**Texto propuesto** (se agrega al final de la viñeta **Tamaño**)

> … **El change 24 (`rendicion-de-jornada`) se implementa en seis lotes y pasa de la estimación: se anota como excepción de tamaño (ADR-068).**

### §11 (fila del 24 y deudas)

**Texto actual**

> | 24 | `rendicion-de-jornada` | Conteo físico, diferencias auditadas, resumen de jornada, devolución de remanente, cierre | RUT-05 (cola vacía antes de rendir) |

**Texto propuesto**

> | 24 | `rendicion-de-jornada` | Conteo físico, diferencias auditadas, resumen de jornada, devolución de remanente, cierre: «Terminar el día» en el teléfono (`JORNADA_ENTREGAR` por la cola), `JORNADA_RENDIR` v2 con conteo y `DIFERENCIA_RENDICION`, resumen congelado, `JORNADA_CERRAR` v2 con devolución, `JORNADA_RENDIDA` para lo tardío — **terminado (ADR-068)** | RUT-05 (cola vacía antes de rendir) |

**Texto propuesto** (párrafo nuevo después del del change 23)

> **Change 24 (`rendicion-de-jornada`) archivado AAAA-MM-DD — terminado (ADR-068).** Entrega: la entrega del día por la cola (RUT-05), el conteo con sus diferencias por la única puerta al promedio vigente, el orden de bloqueo con la ubicación como candado, el resumen (stock congelado y dinero por jornada), el cierre con devolución del remanente, `JORNADA_RENDIDA`, las pantallas de `/admin` y «Terminar el día» en el teléfono; migración nueva; sin permisos nuevos ni Dexie nuevo. **Deudas saldadas:** del 15 (ADR-049 deuda 3: conteo como versión nueva de `JORNADA_RENDIR`, RUT-05, jornadas cerradas sin conteo, orden de bloqueo; archivos propios por área), del 14 (ADR-048 punto 9: diferencias y remanente), del 19 y del 22d (anulaciones por `venta_anulacion.jornada_id`), del 17 (ADR-052 deuda 4) y del 23 (ADR-067: cobranzas en el resumen y cobranza tardía). **Deudas nuevas:** al **25**, mostrar y resolver `JORNADA_RENDIDA`; al **26**, la rendición por vendedor y jornada sobre `rendicion_linea`; a la **etapa 2**, RUT-10 y la rendición sin el teléfono. **Prueba manual:** AAAA-MM-DD (la fecha en que el usuario la hace).
