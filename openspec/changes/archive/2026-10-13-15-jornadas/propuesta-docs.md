# Propuesta de cambios a `docs/` — change 15 `jornadas`

> **Aprobada por el usuario el 2026-10-13 con dos correcciones (§2 de `04`: el change 15 no tuvo revisión entre lotes; §6.3 de `02`: el paso nuevo es `1b` y no se renumeran los siguientes) y aplicada a `docs/01` a `docs/04`.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como estaba antes de aplicarla) y el **texto propuesto** (lo que dejan las decisiones D0 a D22 aprobadas el 2026-10-09, registradas en `docs/adr/ADR-049-jornadas-y-toma-de-ubicacion.md`).
>
> Orden: `01` §8.1, §8.2, §13, §15, §18, §19, §20; `02` §6.3, §6.5, §7.3, §7.4, §7.5, §12.1; `03` §4, §9, §13, §15; `04` §2, §4, §6, §8.

---

## `01-dominio.md`

### §8.1 Stock — STK-09 precisada

**Texto actual**

> | STK-09 | Mientras una ubicación está tomada, solo la jornada que la tomó puede generar movimientos sobre ella, salvo la rendición y usuarios con `LIBERAR_UBICACION`, con auditoría. | 1 |

**Texto propuesto**

> | STK-09 | Una ubicación está **tomada** mientras tiene una jornada `ABIERTA` o `EN_RENDICION`; una ubicación que requiere toma y no tiene jornada no cerrada se mueve libremente. Mientras está tomada, solo la jornada que la tomó puede generar movimientos sobre ella: un movimiento es **de la jornada** si la jornada está `ABIERTA` y el usuario y el dispositivo del comando son los de la jornada. Excepciones: la rendición (change 24) y los usuarios con `LIBERAR_UBICACION`, que mueven la ubicación en cualquier estado de la jornada; ese movimiento queda sin jornada y con una observación en la auditoría que nombra la regla y la jornada. En `EN_RENDICION` la propia jornada ya no mueve stock. Cualquier otro caso se rechaza con `UBICACION_TOMADA` y no escribe nada. La regla se aplica en la única puerta del libro, a todo camino que mueve stock (ADR-049). | 1 |

### §8.2 Jornada y rendición — RUT-01, RUT-02, RUT-03, RUT-08, RUT-09

**Texto actual**

> | RUT-01 | Una jornada tiene usuario, dispositivo, ubicación, apertura y cierre. Una ubicación que requiere toma admite como máximo una jornada no cerrada. | 1 |
> | RUT-02 | La carga del vehículo es una transferencia desde depósito, con conexión, antes o durante la apertura. | 1 |
> | RUT-03 | La apertura requiere conexión y `ABRIR_JORNADA`. Toma la ubicación y ejecuta el bootstrap. | 1 |
> | RUT-08 | Tras la rendición puede transferirse el remanente a depósito. El cierre libera la ubicación. | 1 |
> | RUT-09 | Un usuario con `LIBERAR_UBICACION` puede liberar una jornada abierta con motivo. Los comandos posteriores de esa jornada se aceptan al sincronizar con observación JORNADA_LIBERADA. | 1 |

**Texto propuesto**

> | RUT-01 | Una jornada tiene usuario, dispositivo, ubicación, apertura y cierre. Una ubicación que requiere toma admite como máximo una jornada no cerrada, y un usuario y un dispositivo, a lo sumo una cada uno. Solo se abre sobre una ubicación activa que requiere toma (`UBICACION_SIN_TOMA`, `UBICACION_INACTIVA`, `UBICACION_TOMADA`, `USUARIO_CON_JORNADA`, `DISPOSITIVO_CON_JORNADA`). | 1 |
> | RUT-02 | La carga del vehículo es una transferencia desde depósito (`STOCK_TRANSFERIR`), con conexión, antes o durante la apertura; la apertura no lleva líneas. Antes de abrir la hace cualquiera con `TRANSFERIR_STOCK`; con la jornada abierta, el vendedor de la jornada desde su dispositivo o quien tenga `LIBERAR_UBICACION`. | 1 |
> | RUT-03 | La apertura requiere conexión y `ABRIR_JORNADA`. Toma la ubicación para el usuario y el dispositivo de la sesión. El bootstrap lo ejecuta el cliente después de abrir (change 21). | 1 |
> | RUT-08 | Tras la rendición puede transferirse el remanente a depósito. El cierre (`EN_RENDICION → CERRADA`) libera la ubicación, que vuelve a moverse libremente. | 1 |
> | RUT-09 | Un usuario con `LIBERAR_UBICACION` puede liberar una jornada `ABIERTA` o `EN_RENDICION`, de cualquier usuario, con un motivo activo del ámbito `LIBERACION_JORNADA` y una observación opcional de hasta 500 caracteres; el stock del vehículo no se toca. Los comandos posteriores de esa jornada se aceptan al sincronizar con observación JORNADA_LIBERADA (a partir del primer comando de ruta, change 17). | 1 |

(RUT-04 a RUT-07 y RUT-10 no cambian.)

### §13 Sincronización y comandos — SYN-06

**Texto actual**

> | SYN-06 | Solo se rechazan comandos malformados, inconsistentes (SYN-02), de otra organización, con dependencias inexistentes o de dispositivos revocados. Los comandos de dispositivos revocados se guardan en cuarentena para revisión manual; no se pierden. | 1 |

**Texto propuesto**

> | SYN-06 | Solo se rechazan comandos malformados, inconsistentes (SYN-02), de otra organización, con dependencias inexistentes o de dispositivos revocados. Una jornada del sobre que no existe en la organización es una dependencia inexistente (`JORNADA_INEXISTENTE`): en el lote el ítem se rechaza sin fila de comando y el lote sigue; por REST responde 404. Los comandos de dispositivos revocados se guardan en cuarentena para revisión manual; no se pierden. | 1 |

### §15 Auditoría — AUD-01

**Texto actual** (fragmento; el resto de la fila no cambia)

> … transferencias y ajustes de stock y sus anulaciones (la fila de `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` lleva el motivo, AUD-02); diferencias de rendición; liberación forzada de ubicaciones; cambios de límite y política de crédito; …

**Texto propuesto** (fragmento)

> … transferencias y ajustes de stock y sus anulaciones (la fila de `STOCK_AJUSTAR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` lleva el motivo, AUD-02); apertura, rendición, cierre y liberación forzada de jornadas (la fila de `JORNADA_LIBERAR` lleva el motivo, AUD-02); todo movimiento hecho sobre una ubicación tomada por quien tiene `LIBERAR_UBICACION` (la fila del comando lleva una observación que nombra STK-09 y la jornada); renovaciones de sesión de un usuario o rol inactivo con jornada no cerrada; diferencias de rendición; cambios de límite y política de crédito; …

### §18 Máquinas de estado — la rendición sin conteo hasta el change 24

**Texto actual**

> | Jornada | Almacenada | ABIERTA → EN_RENDICION → CERRADA; ABIERTA/EN_RENDICION → LIBERADA | 1 |

**Texto propuesto** (la fila no cambia; se agrega un párrafo después de la tabla, junto a **Cliente** y **Versión de lista**)

> **Jornada.** "No cerrada" es `ABIERTA` o `EN_RENDICION`: en esos dos estados la ubicación está tomada. `ABIERTA → EN_RENDICION` es la rendición; `EN_RENDICION → CERRADA` es el cierre y libera la ubicación; `LIBERADA` es la liberación forzada con motivo. Cualquier otra transición se rechaza con `JORNADA_ESTADO_INVALIDO` y deja la jornada como estaba; una `CERRADA` o `LIBERADA` no admite ninguna. Hasta el change 24 la rendición no registra conteo ni diferencias (RUT-05 a RUT-07 son de ese change): la jornada pasa a `EN_RENDICION` y se cierra. Las jornadas cerradas antes del 24 no tienen conteo.

### §19 Permisos y roles — `ABRIR_JORNADA`, `RENDIR_JORNADA`, `LIBERAR_UBICACION` y sus lecturas

**Texto actual**

> | ABRIR_JORNADA | Abrir jornada y tomar ubicación | ✓ | | ✓ | ✓ | |
> | RENDIR_JORNADA | Rendir y cerrar jornada | ✓ | ✓ | ✓ | | |
> | LIBERAR_UBICACION | Liberación forzada | ✓ | | ✓ | | |

**Texto propuesto** (las columnas de roles no cambian)

> | ABRIR_JORNADA | Abrir jornada y tomar ubicación; leer las jornadas y la propia jornada actual | ✓ | | ✓ | ✓ | |
> | RENDIR_JORNADA | Rendir y cerrar jornada; leer las jornadas | ✓ | ✓ | ✓ | | |
> | LIBERAR_UBICACION | Liberación forzada de una jornada con motivo; mover una ubicación tomada (STK-09); leer las jornadas | ✓ | | ✓ | | |

Párrafo nuevo, después del que cierra con "…(ADR-048)." al final de la sección:

> El listado y el detalle de jornadas se leen con cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, y alcanzan a todas las jornadas de la organización; la jornada actual del usuario y del dispositivo de la sesión se lee con `ABRIR_JORNADA`. El listado de ubicaciones y el stock por ubicación (`TRANSFERIR_STOCK`) indican qué ubicaciones están tomadas, por quién y desde cuándo. Quien tiene `LIBERAR_UBICACION` puede además mover una ubicación tomada (STK-09); los permisos propios de cada operación se exigen igual (ADR-049).

### §20 Invariantes — INV-16

**Texto actual**

> | INV-16 | Una ubicación que requiere toma tiene como máximo una jornada no cerrada. | Nuevo |

**Texto propuesto**

> | INV-16 | Una ubicación que requiere toma tiene como máximo una jornada no cerrada (`ABIERTA` o `EN_RENDICION`); lo mismo vale para cada usuario y cada dispositivo. | Nuevo |

---

## `02-arquitectura.md`

### §6.3 Procesamiento — validación de la jornada del sobre

**Texto actual**

> 1. **Dispositivo.** Si está revocado, el comando se guarda en cuarentena en una transacción aparte y se responde RECHAZADO (SYN-06).
> 2. **Reserva de idempotencia.** `INSERT INTO comando (organizacion_id, operation_id, tipo, huella, estado) VALUES (…, 'PROCESANDO') ON CONFLICT DO NOTHING`.

**Texto propuesto** (un paso nuevo entre 1 y 2, numerado `1b`; los siguientes no se renumeran; en el documento va como párrafo sangrado bajo el paso 1)

> 1. **Dispositivo.** (sin cambios)
> 1b. **Jornada del sobre.** Si el sobre trae `jornada_id`, se comprueba, antes de reservar, que existe en la organización (por `stock/service.py`). Si no existe o es de otra organización, se responde RECHAZADO con `JORNADA_INEXISTENTE` (SYN-06): en el lote el ítem queda rechazado sin fila de `comando` y el lote sigue; por REST la respuesta es 404. El bus no valida que la jornada sea del usuario ni su estado: es regla de cada comando. La clave foránea compuesta de `comando.jornada_id` queda como respaldo.
> 2. **Reserva de idempotencia.** (sin cambios)

### §6.5 Tipos de comando de la etapa 1 — los cuatro comandos de jornada

**Texto actual** (la fila de la tabla)

> | `JORNADA_ABRIR`, `JORNADA_RENDIR`, `JORNADA_CERRAR`, `JORNADA_LIBERAR` | ✓ | |

**Texto propuesto** (la fila no cambia; se agrega un párrafo junto a los de `STOCK_*`)

> `JORNADA_ABRIR` (`ABRIR_JORNADA`) lleva solo la ubicación: el usuario y el dispositivo salen de la sesión, nunca del contenido. `JORNADA_RENDIR` y `JORNADA_CERRAR` (`RENDIR_JORNADA`) llevan la jornada (en la ruta); `JORNADA_LIBERAR` (`LIBERAR_UBICACION`) lleva la jornada, un motivo del ámbito `LIBERACION_JORNADA` y una observación opcional de hasta 500 caracteres. Los cuatro son solo online, con `Operation-Id`; la fila de auditoría del bus de `JORNADA_LIBERAR` lleva el motivo (ADR-049). Los errores propios son `UBICACION_TOMADA`, `USUARIO_CON_JORNADA`, `DISPOSITIVO_CON_JORNADA`, `UBICACION_SIN_TOMA` y `JORNADA_ESTADO_INVALIDO` (409), `MOTIVO_INVALIDO` y `OBSERVACION_INVALIDA` (422) y `JORNADA_INEXISTENTE` (404); una jornada ajena o inexistente es 404. Las rutas son `POST /api/v1/stock/jornadas` y `POST /api/v1/stock/jornadas/{id}/rendicion`, `/cierre` y `/liberacion`. Las lecturas son `GET /api/v1/stock/jornadas` (filtros de ubicación, usuario, estado y fechas de negocio, con cursor), `GET /api/v1/stock/jornadas/{id}` y `GET /api/v1/stock/jornadas/actual`, con cualquiera de `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION` (la última, con `ABRIR_JORNADA`). Todo comando que mueve stock sobre una ubicación tomada responde `UBICACION_TOMADA` salvo que sea de la jornada o de quien tiene `LIBERAR_UBICACION` (STK-09).

### §7.3 Orden global de bloqueo — la ubicación en la apertura y la jornada como nivel 5

**Texto actual** (el nivel 5 y el párrafo de las ubicaciones)

> 5. `jornada` (si la operación la valida)
>
> … Las ubicaciones se toman `FOR SHARE` al comienzo del movimiento, como hasta ahora (ADR-038). …

**Texto propuesto**

> 5. `jornada` (`FOR SHARE`, por `ubicacion_id` ascendente: todo movimiento lee la jornada no cerrada de cada una de sus ubicaciones antes de decidir; `FOR UPDATE` en las transiciones de la propia jornada)
>
> … Las ubicaciones se toman `FOR SHARE` al comienzo del movimiento, como hasta ahora (ADR-038); `JORNADA_ABRIR` toma la ubicación `FOR UPDATE` en ese mismo paso, así que una apertura y un movimiento sobre la misma ubicación se esperan: o el movimiento termina antes de la toma, o ve la ubicación tomada. `JORNADA_RENDIR`, `JORNADA_CERRAR` y `JORNADA_LIBERAR` toman su jornada `FOR UPDATE`, revalidan el estado y no tocan stock ni saldos, por lo que no pueden cerrar un ciclo; una liberación espera a los movimientos en curso de esa jornada y al revés (ADR-049). La rendición del change 24, que necesitará la jornada antes que el stock, debe resolver cómo convive con este nivel.

### §7.4 Stock — la toma

**Texto actual**

> - Una ubicación con toma se valida contra la jornada abierta dentro de la misma transacción (STK-09).

**Texto propuesto**

> - Una ubicación tomada se valida dentro de la misma transacción: después de bloquear los saldos, `registrar_movimientos` lee la jornada no cerrada de cada ubicación (`FOR SHARE`, nivel 5) y decide por ubicación con STK-09 (libre, de la jornada o por excepción de `LIBERAR_UBICACION`; cualquier otro caso es `UBICACION_TOMADA` y no escribe nada). El permiso de excepción llega como dato, como `permitir_negativo`, y falla cerrado (ADR-049).

### §7.5 Jornadas — los tres índices

**Texto actual**

> Índice único parcial: una sola jornada no cerrada por ubicación (INV-16). El intento de abrir una segunda falla por la restricción, no por una verificación previa en código.

**Texto propuesto**

> Tres índices únicos parciales sobre las jornadas no cerradas (`ABIERTA` o `EN_RENDICION`): una por ubicación (INV-16), una por dispositivo y una por usuario. El intento de abrir una segunda falla por la restricción, no por una verificación previa en código; la violación se traduce a `UBICACION_TOMADA`, `DISPOSITIVO_CON_JORNADA` o `USUARIO_CON_JORNADA`. La apertura toma la ubicación `FOR UPDATE` (§7.3).

### §12.1 Tokens — la excepción de renovación ya efectiva

**Texto actual** (final de la viñeta "Sesión habilitada")

> … La renovación (`refresh`) revoca las familias de refresh del usuario y deja auditoría antes de rechazar, para que la sesión revocada no pueda revivir con una reactivación.

**Texto propuesto** (se agrega al final de esa viñeta)

> … La renovación (`refresh`) revoca las familias de refresh del usuario y deja auditoría antes de rechazar, para que la sesión revocada no pueda revivir con una reactivación. **Excepción (ADR-028 D9.3-B, ADR-049):** si el usuario o su rol están inactivos pero el dispositivo que renueva tiene una jornada `ABIERTA` o `EN_RENDICION` de ese usuario, la renovación se acepta, rota el refresh, no revoca las familias y deja una fila de auditoría `RENOVAR_SESION_CON_JORNADA_PENDIENTE` por cada renovación; el token resultante solo abre el lote de sincronización. Cuando la jornada se cierra o se libera, la renovación siguiente se rechaza. Si el mismo usuario intenta renovar desde otro dispositivo sin jornada, se rechaza y se revocan sus familias menos la del dispositivo con jornada no cerrada. El inicio de sesión sigue rechazando al inactivo. `identidad` consulta la jornada por un puerto que registra `stock` al importarse; sin puerto registrado, la excepción no existe.

---

## `03-modelo-de-datos.md`

### §4 `motivo` — motivos sembrados de `LIBERACION_JORNADA`

**Texto actual** (final del párrafo bajo la tabla de `motivo`)

> … El catálogo de `permiso` (§4, `rol_permiso`) suma `ANULAR_TRANSFERENCIA`, que la misma migración asigna a las plantillas Administrador y Administración.

**Texto propuesto** (se agrega al final del mismo párrafo)

> … El catálogo de `permiso` (§4, `rol_permiso`) suma `ANULAR_TRANSFERENCIA`, que la misma migración asigna a las plantillas Administrador y Administración. Las organizaciones nuevas nacen también con tres motivos del ámbito `LIBERACION_JORNADA` ("Dispositivo perdido o averiado", "Vendedor ausente" y "Otro"); la migración del change 15 (`a4b5c6d7e8f9`) los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-049).

### §9 `jornada`

**Texto actual**

> | Columna | Tipo | Notas |
> | --- | --- | --- |
> | `id`, `organizacion_id` | `uuid` | |
> | `usuario_id`, `dispositivo_id`, `ubicacion_id` | `uuid` | RUT-01 |
> | `estado` | `text` | `ABIERTA`, `EN_RENDICION`, `CERRADA`, `LIBERADA` |
> | `abierta_en`, `rendida_en`, `cerrada_en`, `liberada_en` | `timestamptz` | |
> | `liberada_por_id`, `motivo_liberacion_id` | `uuid` | RUT-09 |
>
> ```sql
> CREATE UNIQUE INDEX ux_jornada__ubicacion_abierta
>     ON jornada (organizacion_id, ubicacion_id)
>     WHERE estado IN ('ABIERTA', 'EN_RENDICION');   -- INV-16
> ```

**Texto propuesto**

> | Columna | Tipo | Notas |
> | --- | --- | --- |
> | `id`, `organizacion_id` | `uuid` | `UNIQUE (organizacion_id, id)` |
> | `usuario_id`, `dispositivo_id`, `ubicacion_id` | `uuid` | RUT-01. FK compuestas a `usuario`, `dispositivo` y `ubicacion` |
> | `estado` | `text` | `ABIERTA`, `EN_RENDICION`, `CERRADA`, `LIBERADA`; `CHECK` de catálogo |
> | `operation_id`, `occurred_at`, `registered_at`, `creado_en` | | Columnas de operación (§2.3) de la apertura, todas `NOT NULL` |
> | `abierta_en`, `rendida_en`, `cerrada_en`, `liberada_en` | `timestamptz` | `abierta_en` `NOT NULL`; los demás, nulos hasta que ocurre la transición |
> | `rendida_por_id`, `cerrada_por_id`, `liberada_por_id` | `uuid` | Quién rindió, cerró y liberó; FK compuestas a `usuario`; nulos si y solo si su momento es nulo |
> | `motivo_liberacion_id` | `uuid` | RUT-09. FK compuesta a `motivo` (ámbito `LIBERACION_JORNADA`); no nulo si y solo si `liberada_en` no es nulo |
> | `observacion_liberacion` | `text` | Opcional, de 1 a 500 caracteres; solo en una `LIBERADA` |
>
> `CHECK` de coherencia por estado: `CERRADA` tiene cierre y rendición; `LIBERADA` tiene liberación y motivo y no cierre; `EN_RENDICION` tiene rendición; `ABIERTA` no tiene rendición. El usuario de aplicación tiene `SELECT` e `INSERT`, y `UPDATE` **solo** de `estado` y de las columnas de transición (nunca de `ubicacion_id`, `usuario_id`, `dispositivo_id` ni `abierta_en`); no tiene `DELETE` (INV-05, TR-06). No hay tabla de toma: la toma es la fila en `ABIERTA` o `EN_RENDICION` más sus índices.
>
> ```sql
> CREATE UNIQUE INDEX ux_jornada__ubicacion_abierta
>     ON jornada (organizacion_id, ubicacion_id)
>     WHERE estado IN ('ABIERTA', 'EN_RENDICION');   -- INV-16
> CREATE UNIQUE INDEX ux_jornada__usuario_abierta
>     ON jornada (organizacion_id, usuario_id)
>     WHERE estado IN ('ABIERTA', 'EN_RENDICION');
> CREATE UNIQUE INDEX ux_jornada__dispositivo_abierta
>     ON jornada (organizacion_id, dispositivo_id)
>     WHERE estado IN ('ABIERTA', 'EN_RENDICION');
> CREATE INDEX ix_jornada__abierta_en
>     ON jornada (organizacion_id, abierta_en DESC, id DESC);   -- listado
> ```

En `stock_movimiento` (misma sección), fila de `jornada_id`:

**Texto actual**

> | `jornada_id`, `motivo_id` | `uuid` | Opcionales. `motivo_id` con FK compuesta a `motivo`; **`jornada_id` sin FK** hasta que exista `jornada` (change 15, mismo trato que `comando.jornada_id`) |

**Texto propuesto**

> | `jornada_id`, `motivo_id` | `uuid` | Opcionales. `motivo_id` con FK compuesta a `motivo`; `jornada_id` con FK compuesta `(organizacion_id, jornada_id)` a `jornada` (change 15, ADR-049). Lo fija la puerta del libro, nunca el sobre: la jornada de la ubicación tomada si el movimiento es de la jornada, y nulo si la ubicación estaba libre o se movió por excepción |

### §13 `comando` — FK de `jornada_id`

**Texto actual**

> | `usuario_id`, `dispositivo_id`, `jornada_id` | `uuid` | |

**Texto propuesto**

> | `usuario_id`, `dispositivo_id`, `jornada_id` | `uuid` | `jornada_id` opcional, con FK compuesta `(organizacion_id, jornada_id)` a `jornada` (change 15, ADR-049); el bus comprueba antes de reservar que la jornada existe (`02` §6.3, paso 1b) |

### §15 Restricciones que la base garantiza — INV-16

**Texto actual**

> | INV-16 | Índice único parcial en `jornada` |

**Texto propuesto**

> | INV-16 | Índices únicos parciales en `jornada` (por ubicación, por usuario y por dispositivo, sobre `ABIERTA` y `EN_RENDICION`) |

Además, la fila de INV-05 suma `jornada` a las tablas con `UPDATE` acotado por columna: "Permisos del usuario de aplicación sobre tablas de libro y sobre las líneas y cabeceras de transferencias y ajustes (`UPDATE` acotado por columna en las cabeceras)" → "… y de jornadas (`UPDATE` acotado por columna)".

---

## `04-roadmap-changes.md`

### §2 Convenciones — tamaño

**Texto actual**

> - **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide. Excepción aceptada por el usuario: el change 14 (`transferencias-y-ajustes`) se implementó en cuatro lotes con revisión entre cada uno, en lugar de dividirse (ADR-048, punto 1).

**Texto propuesto**

> - **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide. Excepciones aceptadas por el usuario: el change 14 (`transferencias-y-ajustes`) se implementó en cuatro lotes con revisión entre cada uno, y el change 15 (`jornadas`) en cuatro lotes, en lugar de dividirse (ADR-048, punto 1; ADR-049, punto 1).

### §4 Tabla de dependencias — el 17 depende del 15

**Texto actual**

> | 17 cobranzas | 07, 08 |

**Texto propuesto**

> | 17 cobranzas | 07, 08, 15 |

(`cobranza.jornada_id` necesita la tabla `jornada`, y el 17 hereda la deuda del paso 4 de `02` §6.3 y de `PERMISO_REVOCADO`; ver §8.)

### §6 Hito 2 — deuda del 06b saldada en parte, repartida

**Texto actual** (el párrafo "Deuda nominada por el change 06b … para el change 15 (`jornadas`) o el 18a (`venta-online-core`)", que termina "… no la excepción a la renovación (`test_bus_lote_sincronizacion.py::TestUsuarioInactivoNoSeRechazaPorRuta`)")

> (el párrafo completo, sin cambios, queda como registro histórico)

**Texto propuesto** (párrafo nuevo a continuación)

> **Deuda del change 06b repartida por el change 15 (`jornadas`) (ADR-049, puntos 18 y 19):** (a) la **excepción de renovación con jornada no cerrada** (ADR-028 D9.3-B) queda **saldada** por el change 15: un usuario o rol inactivo con una jornada `ABIERTA` o `EN_RENDICION` en ese dispositivo renueva su sesión, con auditoría por cada renovación, y la revocación en bloque la respeta; no alcanza a las jornadas `LIBERADA`. (b) El **paso 4 de `02` §6.3** (permisos por comando en `POST /sync/comandos`) y **`PERMISO_REVOCADO`** (SYN-10) **pasan al change 17**, el primero con un tipo `OFFLINE`, y no al 18a. Hasta entonces la excepción de renovación no tiene efecto visible: el token no abre ninguna ruta de negocio.

### §8 Hito 4 — deudas saldadas y nuevas

**Texto actual** (tabla y deudas nominadas para el 15)

> | 15 | `jornadas` | Apertura con toma, bloqueo de ubicación, cierre, liberación auditada | INV-16 (dos aperturas simultáneas) |
>
> **Deuda heredada del change 04 para el change 15 (`jornadas`):** `comando.jornada_id` quedó como columna sin FK … Agregar la FK compuesta (`organizacion_id`, `jornada_id`) hacia `jornada` como parte de este change.
>
> **Deuda nominada por el change 14 (`transferencias-y-ajustes`) para el change 15 (`jornadas`):** (1) aplicar STK-09 también a `STOCK_TRANSFERIR`, `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` con vehículos tomados; hoy se puede transferir a un vehículo sin jornada y anular esa transferencia. (2) La carga del vehículo en la apertura (RUT-02) reutiliza `STOCK_TRANSFERIR`.

**Texto propuesto** (la tabla no cambia; a continuación de las deudas actuales)

> **Change 15 (`jornadas`) — deudas saldadas (ADR-049):** (1) `comando.jornada_id` y `stock_movimiento.jornada_id` tienen FK compuesta a `jornada` (deudas del 04 y del 09); la migración aborta si hay filas con `jornada_id`. (2) STK-09 se aplica en `registrar_movimientos` a todos los caminos que mueven stock: stock inicial (pantalla e importación), compra y su anulación, transferencia, ajuste y las dos anulaciones del 14 (deuda del 09 y deuda (1) del 14). (3) La carga del vehículo es un `STOCK_TRANSFERIR` aparte (deuda (2) del 14). (4) INV-16 queda cerrado: dos aperturas simultáneas con commits reales, tres índices únicos parciales y una máquina de estados de Hypothesis contra PostgreSQL. (5) La excepción de renovación de ADR-028 D9.3-B (deuda del 06b).
>
> **Deudas nuevas del change 15:** **al change 17 (`cobranzas`):** el paso 4 de `02` §6.3 en el lote y `PERMISO_REVOCADO` (SYN-10); la foto de permisos al abrir la jornada, si hace falta; la validación de la jornada del sobre y la observación `JORNADA_LIBERADA` (RUT-09); y la firma de los handlers y el despacho por lote, que hoy tampoco funciona para los cuatro comandos de jornada (solo online). **Al change 21:** el bootstrap al abrir (RUT-03, SYN-11) y la apertura desde `/ruta`. **Al change 24:** el conteo como versión nueva de `JORNADA_RENDIR`, RUT-05, el destino de las jornadas cerradas sin conteo y el orden de bloqueo de la rendición (necesita la jornada `FOR UPDATE` antes que el stock y debe convivir con el nivel 5 `FOR SHARE` de los movimientos); el código de rendición dentro de `stock` sigue la convención de archivos propios por área (ADR-049, punto 2).
