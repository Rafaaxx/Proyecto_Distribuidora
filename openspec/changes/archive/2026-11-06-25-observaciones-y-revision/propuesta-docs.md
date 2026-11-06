# Propuesta de cambios a `docs/` — change 25 `observaciones-y-revision`

> **Completa: decisiones aprobadas de `design.md` (tarea 0.1, 2026-11-05: todas A salvo D9 = B) más las precisiones del apply (tarea 22.1, sección final «Precisiones del apply»).** Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia. Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**; en las filas largas se indica el fragmento exacto que cambia. Las decisiones van en `docs/adr/ADR-069-revision-de-observaciones-y-rechazos.md` (pasa de *Propuesto* a *Vigente* al archivar). Ya incluye D9 = B (RUT-05, `01` §18, `02` §6.5).
>
> **Cuidado al aplicar:** toda fila de las tablas de `01-dominio.md` debe conservar la columna `| ID |` al principio y `| etapa |` al final (el archivo de un change anterior truncó filas). Después de aplicar, correr `frontend/tests/unit/ayuda/trazabilidad.test.ts`.
>
> Orden: `01` RUT-05, CRE-08, CRE-09, SYN-06, SYN-07, SYN-08, SYN-09, SYN-11, §18, §19; `02` §6.3, §6.4, §6.5 (dos filas), §11, §13.2; `03` §3, §13 (`comando_cuarentena`, `comando_rechazado`, `observacion`); `04` §11.

---

## `01-dominio.md`

### RUT-05 (la rendición espera a los rechazos) — D9 = B

**Fragmento actual (final de la fila)**

> La rendición exige la entrega (`JORNADA_SIN_ENTREGA`); sin teléfono no hay rendición y la jornada se libera (RUT-09) (ADR-068).** | 1 |

**Fragmento propuesto (final de la fila)**

> La rendición exige la entrega (`JORNADA_SIN_ENTREGA`); sin teléfono no hay rendición y la jornada se libera (RUT-09) (ADR-068).** **La entrega asegura que todo se envió, no que todo se aceptó: la rendición exige además que la jornada no tenga comandos sin conexión rechazados sin resolver en el registro de rechazos (`RECHAZOS_PENDIENTES`, 409, con la cantidad), para que la venta rechazada que se carga con conexión entre en el esperado y no se descuente dos veces. La cuarentena no la bloquea (su teléfono dado de baja no entrega el día). No se bloquean la entrega, el cierre ni la liberación; la condición se comprueba después de validar el estado de la jornada y la entrega (ADR-069).** | 1 |

**RUT-06 no cambia:** el conteo, el esperado y `DIFERENCIA_RENDICION` siguen igual; la condición nueva es de la rendición (RUT-05).

### CRE-08 (la venta rechazada resuelta) — D8

**Fragmento actual**

> Una venta **rechazada** sigue contando completa (stock, débito y su cobro en el momento, con el mismo `operation_id`) hasta que termine la jornada: la mercadería ya se entregó.

**Fragmento propuesto**

> Una venta **rechazada** sigue contando completa (stock, débito y su cobro en el momento, con el mismo `operation_id`) hasta que termine la jornada **o hasta que un bootstrap posterior la informe resuelta por administración (SYN-11): desde entonces deja de contar, porque la corrección, si la hubo, ya está en los datos del bootstrap (ADR-069)**: la mercadería ya se entregó.

### CRE-09 (la notificación a administración) — D5

**Fragmento actual**

> Si detecta un exceso que el dispositivo no detectó, agrega la observación EXCESO_CREDITO_DETECTADO_SYNC y notifica a administración. | 1 |

**Fragmento propuesto**

> Si detecta un exceso que el dispositivo no detectó, agrega la observación EXCESO_CREDITO_DETECTADO_SYNC y notifica a administración. **La notificación es el aviso de `/admin` a quien tiene `REVISAR_OBSERVACIONES`: el contador de «Revisión» y, en el inicio, la cantidad de excesos detectados al sincronizar pendientes, aparte de los demás avisos, que se actualiza sola (ADR-069).** | 1 |

### SYN-06 (rechazos y cuarentena) — D6, D7

**Fragmento actual**

> Los comandos de dispositivos revocados se guardan en cuarentena para revisión manual; no se pierden. | 1 |

**Fragmento propuesto**

> Los comandos de dispositivos revocados se guardan en cuarentena para revisión manual; no se pierden. **Todo comando sin conexión de un dispositivo activo que el lote rechaza se guarda, en una transacción aparte, en el registro de rechazos, con su contenido y su código (salvo los que traen credenciales y un lote rechazado entero por cola ajena); el reenvío no lo duplica. Rechazos y cuarentena los revisa quien tiene `REVISAR_OBSERVACIONES`: los resuelve con un comentario y, si la operación ocurrió, con el vínculo a la venta o la cobranza cargada con conexión que la corrige (la anulación rechazada se resuelve solo con comentario) (`RECHAZO_RESOLVER`). Ningún comando rechazado o en cuarentena se reenvía ni se reprocesa (ADR-069).** | 1 |

### SYN-07 (`PRODUCTO_DESACTIVADO`) — D10

**Fragmento actual (lista)**

> UBICACION_TOMADA_AL_SINCRONIZAR, AUTORIZACION_OFFLINE, **JORNADA_RENDIDA**.

**Fragmento propuesto (lista)**

> UBICACION_TOMADA_AL_SINCRONIZAR, AUTORIZACION_OFFLINE, JORNADA_RENDIDA, **PRODUCTO_DESACTIVADO**.

**Fragmento actual (final de la fila)**

> su detalle indica la jornada y el momento de la rendición; la operación no entra en el conteo (ADR-068).** | 1 |

**Fragmento propuesto (final de la fila)**

> su detalle indica la jornada y el momento de la rendición; la operación no entra en el conteo (ADR-068).** **`PRODUCTO_DESACTIVADO` se emite solo sin conexión, una por línea de una venta cuyo producto o presentación está inactivo al sincronizar; su detalle indica la línea, el producto, la presentación y cuál está inactivo (`PRODUCTO` si lo están los dos); la venta se acepta igual (ADR-069).** | 1 |

### SYN-08 (la resolución) — D1, D2

**Texto actual**

> | SYN-08 | Una observación queda PENDIENTE hasta que un usuario con `REVISAR_OBSERVACIONES` la resuelve con un comentario. Resolverla no modifica la operación; las correcciones se hacen con operaciones nuevas. | 1 |

**Texto propuesto**

> | SYN-08 | Una observación queda PENDIENTE hasta que un usuario con `REVISAR_OBSERVACIONES` la resuelve con un comentario. Resolverla no modifica la operación; las correcciones se hacen con operaciones nuevas. **`OBSERVACION_RESOLVER` (solo con conexión) resuelve de 1 a 100 observaciones con un mismo comentario de 1 a 500 caracteres, todas o ninguna (`OBSERVACIONES_INVALIDAS`, `COMENTARIO_INVALIDO`, `OBSERVACION_YA_RESUELTA`); guarda quién, cuándo y el comentario. Una observación resuelta no vuelve a pendiente ni cambia, y la base solo admite actualizar las columnas de la resolución (ADR-069).** | 1 |

### SYN-09 (la rechazada resuelta en el teléfono) — D8

**Fragmento actual**

> Un RECHAZADO queda visible en el dispositivo, no se reenvía solo y se avisa.

**Fragmento propuesto**

> Un RECHAZADO queda visible en el dispositivo, no se reenvía solo y se avisa; **cuando el bootstrap lo informa resuelto, muestra además «Resuelta por administración» (ADR-069)**.

### SYN-11 (rechazos resueltos en el bootstrap) — D8

**Fragmento actual**

> **la secuencia procesada de la jornada** (la mayor `secuencia` de los comandos registrados de la jornada del bootstrap, del usuario y del dispositivo de la sesión; nula si no hay) y configuración de la organización y de la nota.

**Fragmento propuesto**

> **la secuencia procesada de la jornada** (la mayor `secuencia` de los comandos registrados de la jornada del bootstrap, del usuario y del dispositivo de la sesión; nula si no hay), **los `operation_id` de los rechazos ya resueltos de esa jornada, usuario y dispositivo, en el nivel superior de la respuesta (`rechazos_resueltos`, fuera de `sesion`) (ADR-069)** y configuración de la organización y de la nota.

### §18 Máquinas de estado, jornada — D9 = B

**Fragmento actual**

> `ABIERTA → EN_RENDICION` es la rendición **(exige la entrega del día y registra el conteo, RUT-05, RUT-06)**;

**Fragmento propuesto**

> `ABIERTA → EN_RENDICION` es la rendición **(exige la entrega del día y que la jornada no tenga rechazos pendientes, y registra el conteo, RUT-05, RUT-06, ADR-069)**;

(Lo nuevo: «y que la jornada no tenga rechazos pendientes» y «, ADR-069».)

### §19 (lecturas de la revisión) — D3, D7, D11

**Texto actual (fila)**

> | REVISAR_OBSERVACIONES | Resolver observaciones | ✓ | ✓ | ✓ | | |

**Texto propuesto (fila)**

> | REVISAR_OBSERVACIONES | Resolver observaciones; **leer la bandeja de observaciones, el resumen de pendientes, y revisar y resolver los rechazos sin conexión y la cuarentena (ADR-069)** | ✓ | ✓ | ✓ | | |

---

## `02-arquitectura.md`

### §6.3 paso 1 y rechazos — D6

**Texto actual**

> 1. **Dispositivo.** Si está revocado, el comando se guarda en cuarentena en una transacción aparte y se responde RECHAZADO (SYN-06).

**Texto propuesto**

> 1. **Dispositivo.** Si está revocado, el comando se guarda en cuarentena en una transacción aparte y se responde RECHAZADO (SYN-06). **En el lote, todo comando `OFFLINE` de un dispositivo activo que termina RECHAZADO se guarda después, también en una transacción aparte, en `comando_rechazado` (contenido y código; nunca credenciales); si eso falla por un error transitorio, el ítem es un error transitorio y corta el lote (ADR-069).**

### §6.4 — D6

**Texto actual**

> - Un resultado ACEPTADO, ACEPTADO_CON_OBSERVACIONES o RECHAZADO no detiene el lote.

**Texto propuesto**

> - Un resultado ACEPTADO, ACEPTADO_CON_OBSERVACIONES o RECHAZADO no detiene el lote. **Un RECHAZADO sin conexión queda en el registro de rechazos para que administración lo revise (SYN-06, ADR-069).**

### §6.5 — D1, D7

**Texto actual (fila)**

> | `OBSERVACION_RESOLVER` | ✓ | |

**Texto propuesto (fila)**

> | `OBSERVACION_RESOLVER`, `RECHAZO_RESOLVER` (con `REVISAR_OBSERVACIONES`; `OBSERVACIONES_INVALIDAS`, `COMENTARIO_INVALIDO` y `VINCULO_INVALIDO` 422, `OBSERVACION_YA_RESUELTA` y `RECHAZO_YA_RESUELTO` 409, ADR-069) | ✓ | |

### §6.5 párrafo de jornadas — D9 = B

**Fragmento actual**

> **errores nuevos: `JORNADA_SIN_ENTREGA`, `JORNADA_YA_ENTREGADA`, `ESPERADO_DIFIERE` y `UBICACION_CON_TOMA` (409), `CONTEO_INCOMPLETO` (422);

**Fragmento propuesto**

> **errores nuevos: `JORNADA_SIN_ENTREGA`, `JORNADA_YA_ENTREGADA`, `ESPERADO_DIFIERE` y `UBICACION_CON_TOMA` (409), `CONTEO_INCOMPLETO` (422); `RECHAZOS_PENDIENTES` (409, con la cantidad) en la rendición, comprobado con la jornada tomada por un puerto que `stock/service.py` declara y `sync/service.py` registra (ADR-069);

(El fragmento está dentro de un tramo en negrita de `02`: lo nuevo va sin marcas propias, desde «`RECHAZOS_PENDIENTES`» hasta «(ADR-069)».)

**Fragmento actual**

> `GET /api/v1/stock/jornadas/{id}` devuelve además `entregada_en`;

**Fragmento propuesto**

> `GET /api/v1/stock/jornadas/{id}` devuelve además `entregada_en` y `rechazos_pendientes` (solo la cantidad, ADR-069);

(También dentro del tramo en negrita: lo nuevo es «y `rechazos_pendientes` (solo la cantidad, ADR-069)».)

### §11 — D3, D5, D7

**Texto actual (fila)**

> | Observaciones | listado, resolución |

**Texto propuesto (fila)**

> | Observaciones | `GET /observaciones` (por operación, con filtros y cursor), `GET /observaciones/resumen`, `POST /observaciones/resolucion`, `GET /observaciones/rechazos`, `GET /observaciones/rechazos/{id}`, `POST /observaciones/rechazos/{id}/resolucion`, todas con `REVISAR_OBSERVACIONES`; los detalles de venta, cobranza, compra, transferencia y ajuste informan la resolución de sus observaciones (ADR-069) |

### §13.2 `meta` — D8

**Texto actual (fila)**

> | `meta` | Versión de esquema local, dispositivo, último correlativo y última secuencia, fecha de bootstrap |

**Texto propuesto (fila)**

> | `meta` | Versión de esquema local, dispositivo, último correlativo y última secuencia, fecha de bootstrap, **los rechazos resueltos del último bootstrap (sin versión nueva de la base local, ADR-069)** |

---

## `03-modelo-de-datos.md`

### §3 — D6

**Texto actual**

> sync             comando · comando_cuarentena · observacion

**Texto propuesto**

> sync             comando · comando_cuarentena · comando_rechazado · observacion

### §13 `comando_cuarentena` — D2, D7

**Texto actual**

> `id`, `organizacion_id`, `dispositivo_id`, `usuario_id`, `operation_id`, `tipo`, `contenido` `jsonb`, `motivo`, `recibido_en`, `revisado_en`, `revisado_por_id` (SYN-06).

**Texto propuesto**

> `id`, `organizacion_id`, `dispositivo_id`, `usuario_id`, `operation_id`, `tipo`, `contenido` `jsonb`, `motivo`, `recibido_en`, `revisado_en`, `revisado_por_id`, **`comentario` (de 1 a 500), `vinculo_tipo`, `vinculo_id`** (SYN-06). **El usuario de aplicación solo actualiza las columnas de la revisión; `CHECK` de coherencia (revisada con las tres primeras no nulas). Migración del change 25 (ADR-069).**

### §13 `comando_rechazado` (nueva) — D6

**Texto propuesto (sección nueva, después de `comando_cuarentena`)**

> ### `comando_rechazado`
>
> `id`, `organizacion_id`, `operation_id` (`UNIQUE (organizacion_id, operation_id)`), `tipo`, `version`, `modo`, `usuario_id`, `dispositivo_id`, `jornada_id` (nulable; nula si la jornada del sobre no existía), `secuencia`, `occurred_at`, `app_version`, `contenido` `jsonb`, `error_codigo`, `recibido_en`, `estado` (`PENDIENTE`, `RESUELTO`), `resuelto_por_id`, `resuelto_en`, `comentario` (de 1 a 500), `vinculo_tipo`, `vinculo_id` (SYN-06). FK compuestas a `usuario`, `dispositivo` y `jornada`. El lote la escribe en transacción aparte por cada comando sin conexión rechazado; el usuario de aplicación tiene `SELECT`, `INSERT` y `UPDATE` solo de las columnas de la resolución, nunca `DELETE` (INV-05). Índice parcial `(organizacion_id, jornada_id) WHERE estado = 'PENDIENTE'` (ADR-069).

### §13 `observacion` — D2, D10

**Fragmento actual**

> el change 18b con `AUTORIZACION_OFFLINE` y el change 24 con `JORNADA_RENDIDA`), `detalle` `jsonb`, `estado` (`PENDIENTE`, `RESUELTA`), `resuelto_por_id`, `resuelto_en`, `comentario`.

**Fragmento propuesto**

> el change 18b con `AUTORIZACION_OFFLINE`, el change 24 con `JORNADA_RENDIDA` **y el change 25 con `PRODUCTO_DESACTIVADO`**), `detalle` `jsonb`, `estado` (`PENDIENTE`, `RESUELTA`), `resuelto_por_id`, `resuelto_en`, `comentario`. **El usuario de aplicación solo actualiza `estado`, `resuelto_por_id`, `resuelto_en` y `comentario`; `CHECK` `ck_observacion__resolucion_coherente` (pendiente con las tres nulas, resuelta con las tres no nulas) y `ck_observacion__comentario` (de 1 a 500) (ADR-069).**

---

## `04-roadmap-changes.md`

### §11 fila 25 y párrafo de cierre — al archivar

**Texto actual (fila)**

> | 25 | `observaciones-y-revision` | Bandeja de observaciones pendientes, resolución con comentario, notificación de excesos detectados al sincronizar | SYN-08 (resolver no altera operación) |

**Texto propuesto (fila)**

> | 25 | `observaciones-y-revision` | Bandeja de observaciones pendientes, resolución con comentario, notificación de excesos detectados al sincronizar; registro y resolución de los rechazos sin conexión y de la cuarentena — **terminado (ADR-069)** | SYN-08 (resolver no altera operación) |

**Párrafo nuevo (después del del change 24), a completar al archivar con la fecha, la entrega real y la prueba manual:**

> **Change 25 (`observaciones-y-revision`) archivado AAAA-MM-DD — terminado (ADR-069).** Entrega: `OBSERVACION_RESOLVER` en bloque con comentario y la resolución inmutable en la base; la bandeja de `/admin` por operación con el detalle legible de cada código; el aviso de pendientes con los excesos detectados al sincronizar (CRE-09); el registro de los rechazos sin conexión y `RECHAZO_RESOLVER` para rechazos y cuarentena, con vínculo opcional a la corrección y sin reenvío; los rechazos resueltos en el bootstrap y la venta rechazada resuelta que deja de contar en el teléfono; la rendición que espera a que se resuelvan las rechazadas de la jornada (`RECHAZOS_PENDIENTES`); `PRODUCTO_DESACTIVADO`; migración nueva; sin permisos nuevos ni versión nueva de Dexie. **Deudas saldadas:** del 04 (permiso y reenvío de la cuarentena, `OBSERVACION_RESOLVER`), del 17 (`MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`), del 18a (`CONSUMIDOR_FINAL_CON_DEUDA`, producto desactivado), del 18b (`AUTORIZACION_OFFLINE`, causas de `DESCUENTO_DIFIERE`, `EXCESO_CREDITO_DETECTADO_SYNC` y su notificación), del 22c (venta rechazada), del 22d (anulación de una «Rechazada» y resolución de las rechazadas), del 23 (cobranzas rechazadas) y del 24 (`JORNADA_RENDIDA`). **Deudas nuevas:** al **26**, observaciones y rechazos por vendedor; a la **etapa 2**, aviso por correo. **Prueba manual:** AAAA-MM-DD.

**Párrafos a marcar como saldados al archivar:** «Deuda heredada del change 04 para el change 25» y «Deuda nominada por el change 22c para el change 25» (se agrega al final de cada uno: «**Saldada en el change 25 (ADR-069).**»).

---

## Precisiones del apply (tarea 22.1)

Cambios respecto del borrador de la propuesta, ya incorporados en las secciones de arriba y en `ADR-069`:

1. **Dónde vive el resumen de las operaciones.** El registro de resumidores (de las operaciones y del contenido rechazado) y los lectores de vínculo `VENTA` y `COBRANZA` están en `app/core/resumen.py`, no en `sync`: `import-linter` prohíbe `sync` ↔ `ventas`/`cobranzas`/`proveedores`. `sync.service.resumir_operaciones` es solo una fachada. La sesión se tipa `Any` en `core` con justificación (el módulo no importa SQLAlchemy). **No cambia `02`**: es una decisión interna de implementación; el puerto del contador de rechazos pendientes sigue como en D9 (declarado en `stock/service.py`, registrado por `sync/service.py`; sin registro, `RuntimeError`).
2. **Orden de las comprobaciones de la rendición.** `RECHAZOS_PENDIENTES` se comprueba después de las de estado de la jornada y de la entrega (ya en RUT-05).
3. **Códigos y filtros.** Código nuevo `RECHAZO_YA_RESUELTO` (409; ya en `02` §6.5). `GET /observaciones/rechazos` filtra por `estado` `PENDIENTE` (por defecto), `RESUELTO` o `TODOS`. Los resúmenes de referencias que no existen dicen «(no existe)».
4. **`PRODUCTO_DESACTIVADO`.** Si el producto y la presentación están inactivos, el detalle indica `PRODUCTO` (ya en SYN-07). Una prueba del change 22 que afirmaba la aceptación sin observación se reemplazó (ADR-054 punto 27 enmendado).
5. **Bootstrap.** `rechazos_resueltos` va en el nivel superior de la respuesta, no dentro de `sesion` (ya en SYN-11), y se guarda en `meta` de Dexie (ya en `02` §13.2); la versión de Dexie no cambia (v5).
6. **Inicio de `/admin`.** Para quien tiene `REVISAR_OBSERVACIONES` el inicio es la tarjeta «Para revisar»; las cuarentenas se suman a «operaciones rechazadas» de la tarjeta. No cambia ninguna tabla de `docs/`.
7. **Detalles de operación.** Los endpoints de detalle de venta, cobranza, compra, transferencia y ajuste exponen la resolución de sus observaciones (`sync.service.listar_observaciones_con_resolucion`; ya en `02` §11).
8. **Verificación al aplicar.** Las filas de las tablas de `01` conservan `| ID |` al principio y `| etapa |` al final; correr `frontend/tests/unit/ayuda/trazabilidad.test.ts`.
