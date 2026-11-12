# Propuesta de cambios a `docs/` — change 17 `cobranzas`

> **Borrador con lo aprobado el 2026-10-15 (D0 a D20: opción A en todas salvo D13 = C). No se aplica a `docs/` sin el visto bueno del usuario.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. La tarea 19.1 lo completa con lo que se apruebe y lo que precise el apply; las decisiones quedan en `docs/adr/ADR-052-cobranzas-y-comandos-offline-en-el-lote.md` (estado *Propuesto*).
>
> Orden: `01` §12.2, §13 (SYN-05, SYN-07, SYN-10), §19; `02` §5.3, §6.3, §6.5, §7.3; `03` §4, §12, §13, §15; `04` §2, §8.

---

## `01-dominio.md`

### §12.2 COB-01

**Texto actual**

> | COB-01 | Una cobranza tiene `operation_id`, cliente, `occurred_at`, importe mayor que cero, usuario, dispositivo, origen (VENTA o INDEPENDIENTE) y uno o más medios. | 1 |

**Texto propuesto**

> | COB-01 | Una cobranza tiene identificador generado por quien la origina, `operation_id`, cliente, `occurred_at` (su momento, D3), importe mayor que cero, usuario, dispositivo, jornada si la registró un vendedor en jornada, origen (VENTA o INDEPENDIENTE), de 1 a 20 medios activos (el mismo medio puede repetirse; sin conexión, un medio inactivo o una referencia faltante se aceptan con observación, SYN-07) y una observación opcional de hasta 500 caracteres. Se cobra a clientes activos, suspendidos e inactivos; al consumidor final no se le registra una cobranza independiente (`CONSUMIDOR_FINAL_SIN_CUENTA`). Puede superar la deuda: el saldo queda a favor del cliente (ADR-052). | 1 |

### §12.2 COB-05

**Texto actual**

> | COB-05 | Una cobranza solo se corrige por anulación con `ANULAR_COBRANZA` y motivo. | 1 |

**Texto propuesto**

> | COB-05 | Una cobranza solo se corrige por anulación total, con conexión, con `ANULAR_COBRANZA`, un motivo del ámbito `ANULACION_COBRANZA` y una observación opcional. La anulación deja la cobranza `ANULADA` y registra un movimiento `ANULACION_COBRANZA` que devuelve el saldo. Se anula una sola vez, también si el cliente está inactivo o su jornada cerrada; la de origen VENTA se anula con su venta (VTA-22) (ADR-052). | 1 |

### §13 SYN-05

**Texto actual**

> | SYN-05 | Una venta o cobranza registrada sin conexión nunca se rechaza por reglas de negocio (stock, crédito, lista, descuentos, estado del cliente o permisos). Se acepta con las observaciones que correspondan. | 1 |

**Texto propuesto**

> | SYN-05 | Una venta o cobranza registrada sin conexión nunca se rechaza por reglas de negocio (stock, crédito, lista, descuentos, estado del cliente, permisos, un medio de pago desactivado o una referencia faltante). Se acepta con las observaciones que correspondan. La suma de los medios igual al importe (INV-08) no es una regla de negocio: si no se cumple, el comando está malformado (SYN-06) (ADR-052). | 1 |

### §13 SYN-07

**Texto actual**

> | SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, EXCESO_CREDITO_ADVERTIDO, EXCESO_CREDITO_AUTORIZADO_OFFLINE, EXCESO_CREDITO_DETECTADO_SYNC, LISTA_NO_VIGENTE, DESCUENTO_DIFIERE, CLIENTE_NO_HABILITADO, PERMISO_REVOCADO, JORNADA_LIBERADA, ANULACION_COMPRA_SIN_RECALCULO. | 1 |

**Texto propuesto**

> | SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, EXCESO_CREDITO_ADVERTIDO, EXCESO_CREDITO_AUTORIZADO_OFFLINE, EXCESO_CREDITO_DETECTADO_SYNC, LISTA_NO_VIGENTE, DESCUENTO_DIFIERE, CLIENTE_NO_HABILITADO, PERMISO_REVOCADO, JORNADA_LIBERADA, ANULACION_COMPRA_SIN_RECALCULO, MEDIO_INACTIVO, REFERENCIA_FALTANTE. `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` se emiten solo sin conexión, una por cada línea de medio afectada: el medio de pago está inactivo al sincronizar, o exige referencia y la línea llegó sin ella; su detalle indica la línea, el medio y el importe. Con conexión, esos casos se rechazan (`MEDIO_PAGO_INACTIVO`, `REFERENCIA_OBLIGATORIA`) (ADR-052). | 1 |

Catálogo de los códigos que emite este change (para la tabla de SYN-07 y la bandeja del change 25):

| Código | Cuándo (solo `OFFLINE`) | Detalle | Origen |
| --- | --- | --- | --- |
| `CLIENTE_NO_HABILITADO` | Cobranza independiente al consumidor final | cliente | existente (SYN-07) |
| `PERMISO_REVOCADO` | Al sincronizar, el usuario no tiene el permiso del tipo, o él o su rol están inactivos | permiso; motivo `PERMISO_QUITADO`, `USUARIO_INACTIVO` o `ROL_INACTIVO` | existente (SYN-10) |
| `JORNADA_LIBERADA` | La jornada del sobre está `LIBERADA` | jornada; momento de la liberación | existente (RUT-09) |
| `MEDIO_INACTIVO` | Una línea con un medio de pago inactivo al sincronizar | `medio` (posición desde 0), `medio_pago_id`, `nombre`, `importe` | **nuevo** (D13) |
| `REFERENCIA_FALTANTE` | Una línea cuyo medio exige referencia (configuración al sincronizar) llega sin ella o con solo espacios; se guarda nula | `medio`, `medio_pago_id`, `nombre`, `importe` | **nuevo** (D13) |

### §13 SYN-10

**Texto actual**

> | SYN-10 | Sin conexión, los permisos vigentes son los descargados al abrir la jornada. Si al sincronizar el usuario ya no tiene el permiso, la operación se acepta con PERMISO_REVOCADO. | 1 |

**Texto propuesto**

> | SYN-10 | Sin conexión, los permisos vigentes son los descargados al abrir la jornada (en el dispositivo). Si al sincronizar el usuario ya no tiene el permiso que declara el tipo de comando, o el usuario o su rol están inactivos, la operación se acepta con PERMISO_REVOCADO. El servidor compara con los permisos actuales; no guarda una foto (ADR-052). Un comando offline sin jornada (`JORNADA_REQUERIDA`) o con la jornada de otro usuario o dispositivo (`JORNADA_AJENA`) se rechaza (SYN-06). | 1 |

### §19 Permisos — nota de lecturas (párrafo nuevo, después del de pagos)

**Texto actual:** no existe.

**Texto propuesto**

> El listado y el detalle de cobranzas exigen `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA` y alcanzan a todas las cobranzas de la organización; el saldo de un cliente y la lista de clientes para elegir se leen con `GESTIONAR_CLIENTES` o `REGISTRAR_COBRANZA`; la ficha y el estado de cuenta, solo con `GESTIONAR_CLIENTES`. "Sus clientes" son todos los de la organización mientras no exista una asignación de clientes a vendedores (ADR-052).

---

## `02-arquitectura.md`

### §5.3 Dependencias

**Texto actual**

> cobranzas ──► cuentas_corrientes

**Texto propuesto**

> cobranzas ──► cuentas_corrientes, clientes, configuracion (medios y motivos; la validación de medios es compartida con proveedores), stock (jornada), identidad (permisos) — solo por service.py, ADR-052

### §6.3 Paso 4

**Texto actual**

> 4. **Permisos.** En `ONLINE`, un permiso faltante rechaza. En `OFFLINE`, se valida contra los permisos vigentes al abrir la jornada y, si fueron revocados después, se acepta con observación (SYN-10).

**Texto propuesto**

> 4. **Permisos.** En `ONLINE`, un permiso faltante rechaza (lo valida el handler, por REST y por el lote). En `OFFLINE`, el bus valida el permiso que el tipo declara en el catálogo contra los permisos actuales del usuario (inactivo = sin permisos) y, si falta, acepta con `PERMISO_REVOCADO` (SYN-10). Antes de reservar, un comando `OFFLINE` sin jornada se rechaza con `JORNADA_REQUERIDA` y uno con la jornada de otro usuario o dispositivo con `JORNADA_AJENA`; una jornada `LIBERADA` se acepta con `JORNADA_LIBERADA` (RUT-09) (ADR-052).

### §6.5 Párrafo de cobranzas (nuevo, después del de pagos)

**Texto propuesto**

> `COBRANZA_REGISTRAR` (`REGISTRAR_COBRANZA`; `ONLINE` y `OFFLINE`) lleva el identificador de la cobranza, cliente, importe, de 1 a 20 medios y una observación opcional; `COBRANZA_ANULAR` (`ANULAR_COBRANZA`, solo `ONLINE`) lleva la cobranza (en la ruta), un motivo del ámbito `ANULACION_COBRANZA` y una observación opcional, y deja el motivo en su fila de auditoría. Con conexión, un medio inactivo o una referencia faltante se rechazan (`MEDIO_PAGO_INACTIVO`, `REFERENCIA_OBLIGATORIA`), igual que en los pagos; sin conexión, `COBRANZA_REGISTRAR` los acepta con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` por línea, y con `CLIENTE_NO_HABILITADO` la cobranza al consumidor final (SYN-05, SYN-07). Los errores propios son `COBRANZA_DUPLICADA`, `COBRANZA_YA_ANULADA`, `COBRANZA_DE_VENTA`, `CONSUMIDOR_FINAL_SIN_CUENTA` y `JORNADA_AJENA` (409) y `JORNADA_REQUERIDA` (422). Las rutas son `POST /api/v1/cobranzas` y `POST /api/v1/cobranzas/{id}/anulacion`; las lecturas, `GET /api/v1/cobranzas` (filtros de cliente, estado, usuario, jornada y fechas, con cursor), `GET /api/v1/cobranzas/{id}`, `GET /api/v1/clientes/opciones` y `GET /api/v1/clientes/{id}/saldo` (ADR-052).

**Texto propuesto (agregar al final del párrafo de cobranzas)**

> Un tipo de comando con handler registrado pero sin declarar en el catálogo de tipos no tiene modo permitido: el lote lo rechaza en `ONLINE` y en `OFFLINE` (aprobado 2026-10-16, ADR-052). Un handler que intenta `commit`, `rollback` o `close` sobre la sesión del bus es un error de programación: aborta el lote y no se informa como `RECHAZADO` de ese ítem (ADR-052).

### §7.3 Orden de bloqueo

**Texto propuesto (agregar al párrafo de las filas de la operación)**

> `COBRANZA_ANULAR` toma la cobranza `FOR UPDATE` antes de `saldo_cuenta`; `COBRANZA_REGISTRAR` parte del nivel 1 y lee la jornada `FOR SHARE` en el nivel 5 (ADR-052).

---

## `03-modelo-de-datos.md`

### §4 Motivos (agregar al párrafo de siembra)

**Texto propuesto**

> Las organizaciones nuevas nacen también con tres motivos del ámbito `ANULACION_COBRANZA` ("Error de carga", "Pago rechazado o no acreditado" y "Otro"); la migración del change 17 los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-052).

### §12 `cobranza`, `cobranza_medio`, `cobranza_anulacion`

**Texto actual**

> | `cobranza` | `id`, `organizacion_id`, `cliente_id`, `venta_id` (nulo si independiente), `origen` (`VENTA`, `INDEPENDIENTE`), `importe` `CHECK (> 0)`, `estado`, `jornada_id`, columnas de operación |
> | `cobranza_medio` | `id`, `organizacion_id`, `cobranza_id`, `medio_pago_id`, `importe`, `referencia` |
> | `cobranza_anulacion` | `id`, `organizacion_id`, `cobranza_id` (único), `motivo_id`, columnas de operación |

**Texto propuesto**

> | `cobranza` | `id` (generado por quien origina), `organizacion_id`, `cliente_id`, `venta_id` (nulo si independiente; sin FK hasta el change 18a), `origen` (`VENTA`, `INDEPENDIENTE`, coherente con `venta_id`), `importe` `numeric(14,2)` `CHECK (> 0)`, `estado` (`CONFIRMADA`, `ANULADA`), `jornada_id`, `observacion` (opcional, hasta 500), columnas de operación |
> | `cobranza_medio` | `id`, `organizacion_id`, `cobranza_id`, `orden` `CHECK (>= 0)` (posición de la línea en el pedido, única por cobranza; D16), `medio_pago_id`, `importe` `CHECK (> 0)`, `referencia` |
> | `cobranza_anulacion` | `id`, `organizacion_id`, `cobranza_id` (único), `motivo_id`, `observacion` (opcional, hasta 500), columnas de operación |
>
> FK compuestas a `cliente`, `jornada`, `usuario`, `dispositivo`, `medio_pago` y `motivo`. Índices `(organizacion_id, occurred_at DESC, id DESC)`, `(organizacion_id, cliente_id, occurred_at DESC, id DESC)` y `(organizacion_id, jornada_id)`. `app_runtime` tiene `SELECT, INSERT` en las tres, `UPDATE` solo de `cobranza.estado` y nunca `DELETE` (INV-05). INV-08 se valida en el servicio y se cubre con una propiedad que suma con SQL (ADR-052).

### §13 `observacion` (agregar después de la lista de columnas)

**Texto actual**

> `id`, `organizacion_id`, `comando_id`, `operacion_tipo`, `operacion_id`, `codigo` (SYN-07), `detalle` `jsonb`, `estado` (`PENDIENTE`, `RESUELTA`), `resuelto_por_id`, `resuelto_en`, `comentario`.

**Texto propuesto**

> `id`, `organizacion_id`, `comando_id`, `operacion_tipo`, `operacion_id`, `codigo` (SYN-07; `CHECK` `ck_observacion__codigo` con el catálogo, que el change 17 amplía con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`), `detalle` `jsonb`, `estado` (`PENDIENTE`, `RESUELTA`), `resuelto_por_id`, `resuelto_en`, `comentario`. En las observaciones de un medio de cobranza, `detalle` lleva `medio` (posición de la línea), `medio_pago_id`, `nombre` e `importe` (ADR-052).

### §15 Restricciones

**Texto propuesto (fila INV-05)**: agregar "y de cobranzas (`UPDATE` solo del estado; anulación única por `cobranza_anulacion.cobranza_id`)".

---

## `04-roadmap-changes.md`

### §2 Tamaño (excepciones)

**Texto propuesto**: agregar "y el change 17 (`cobranzas`) en cinco lotes sin revisión entre ellos (ADR-052, punto 1)".

### §8 Hito 4 (párrafo nuevo al archivar)

**Texto propuesto**

> **Change 17 (`cobranzas`) — deudas saldadas (ADR-052):** la firma tipada de los handlers y el despacho por lote (deudas de los changes 05, 14 y 15); el paso 4 de `02` §6.3 en el lote y `PERMISO_REVOCADO` (deuda del 06b repartida por el 15); la foto de permisos (no se guarda); la validación de la jornada del sobre y `JORNADA_LIBERADA` (RUT-09). INV-08 queda cerrado también para cobranzas. SYN-07 suma `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`. **Deudas nuevas:** al **18a**, la FK de `cobranza.venta_id` y la cobranza de origen `VENTA` por `cobranzas/service.py::registrar_cobranza`, y declarar el permiso offline de `VENTA_CONFIRMAR`; al **19**, la anulación de la cobranza de una venta (VTA-22); al **21**, el bootstrap con los permisos (SYN-10) y los medios activos; al **23**, la cola y la pantalla de `/ruta`; al **25**, la bandeja para resolver también `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`; al **24**, si una cobranza tardía sobre una jornada cerrada necesita observación (RUT-05); a la asignación de clientes a vendedores (sin change), "sus clientes" de `01` §19.
