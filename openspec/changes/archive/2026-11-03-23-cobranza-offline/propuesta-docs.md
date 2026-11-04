# Propuesta de cambios a `docs/` — change 23 `cobranza-offline`

> **Propuesta completa (tarea 15.1) con lo aprobado en 0.1 (D0 a D12 en A) y las precisiones del apply. Se aplica a `docs/` al archivar el change, con el visto bueno del usuario; hasta entonces `docs/` no cambia.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones van en `docs/adr/ADR-067-cobranza-sin-conexion-en-el-telefono.md` (pasa de *Propuesto* a *Vigente* al archivar).
>
> **Nota previa:** las filas `CRE-08` y `SYN-06` de `01-dominio.md` habían quedado truncadas (sin el comienzo de la fila) por el archivo del change 22d y rompían `frontend/tests/unit/ayuda/trazabilidad.test.ts`. Ya se restauraron en el árbol de trabajo (el texto actual de abajo es el restaurado); la restauración forma parte de este change.
>
> Orden: `01` COB-04, CRE-08, RUT-09; `02` §6.6, §13.2, §13.3; `04` §11 (fila del 23 y deudas saldadas y nuevas). `03` no cambia: no hay migración.

---

## `01-dominio.md`

### COB-04 (la cobranza del teléfono)

**Texto actual**

> | COB-04 | Las cobranzas pueden registrarse sin conexión y se consideran en el saldo local (CRE-08). | 1 |

**Texto propuesto**

> | COB-04 | Las cobranzas pueden registrarse sin conexión y se consideran en el saldo local (CRE-08). **En `/ruta` la cobranza va siempre por la cola, con o sin señal: el teléfono la valida, la guarda y encola `COBRANZA_REGISTRAR` `OFFLINE` con la jornada de la sesión en una sola transacción (INV-01); con señal la sincronización se dispara enseguida. Se cobra a los clientes que el teléfono tiene (activos y suspendidos, de la cartera o no) y nunca al consumidor final (COB-01); requiere `REGISTRAR_COBRANZA` en los permisos del bootstrap. El teléfono exige un importe mayor que cero con dos decimales como máximo, de 1 a 20 medios activos con importe positivo que sumen el importe (INV-08), la referencia donde el medio la exige y una observación de hasta 500 caracteres; muestra el saldo local actual y el resultante, y si el resultante queda a favor del cliente pide confirmarlo (CC-04). No hay comprobante de cobranza en la etapa 1 (COB-06) (ADR-067).** | 1 |

### CRE-08 (la cobranza rechazada)

**Texto actual** (fragmento que cambia)

> … Una venta **rechazada** sigue contando completa (stock, débito y su cobro en el momento, con el mismo `operation_id`) hasta que termine la jornada: la mercadería ya se entregó. **Una anulación local cuenta desde que se confirma, … (ADR-066).** Enviar una operación no la deja de contar: solo la deja de contar un bootstrap posterior que la incluya (ADR-063, ADR-065, ADR-066). | 1 |

**Texto propuesto** (se agrega después de la oración de la anulación)

> … (ADR-066).** **Una cobranza local independiente (no el cobro de una venta) cuenta desde que se confirma, con la misma regla de la secuencia: baja el saldo del cliente y le libera crédito (el saldo puede quedar negativo, a favor del cliente). Una cobranza independiente rechazada deja de contar: el servidor solo la rechaza por datos (cliente o medio inexistente, contenido inválido, duplicada, jornada), nunca por reglas de negocio, así que no está en la cuenta del cliente y contarla liberaría crédito que el sistema no reconoce; el dinero queda en poder del vendedor y administración lo resuelve. El cobro de una venta sigue la regla de su venta, también cuando la venta está rechazada (ADR-067).** Enviar una operación no la deja de contar: solo la deja de contar un bootstrap posterior que la incluya (ADR-063, ADR-065, ADR-066, ADR-067). | 1 |

### RUT-09 («Cobrar» también se corta)

**Texto actual** (fragmento que cambia)

> … **El teléfono, cuando con conexión se entera de que su jornada ya no está `ABIERTA` (…), lo guarda, deja de ofrecer «Vender» y «Anular venta» y avisa según el estado («Tu jornada fue liberada.», «Tu jornada está en rendición.», «Tu jornada fue cerrada.» o «Tu jornada ya no está abierta.», seguido de «Lo que ya vendiste se sigue enviando.»). El aviso vale sin señal y después de recargar; lo ya vendido y anulado se sigue enviando; sin conexión no cambia nada; al abrir otra jornada se borra (ADR-066).** | 1 |

**Texto propuesto**

> … **El teléfono, cuando con conexión se entera de que su jornada ya no está `ABIERTA` (…), lo guarda, deja de ofrecer «Vender», «Anular venta» y «Cobrar» y avisa según el estado («Tu jornada fue liberada.», «Tu jornada está en rendición.», «Tu jornada fue cerrada.» o «Tu jornada ya no está abierta.», seguido de «Lo que ya vendiste y cobraste se sigue enviando.»). Con el formulario de cobro abierto, «Confirmar cobranza» no confirma y los datos siguen. El aviso vale sin señal y después de recargar; lo ya vendido, anulado y cobrado se sigue enviando; sin conexión no cambia nada; al abrir otra jornada se borra (ADR-066, ADR-067).** | 1 |

---

## `02-arquitectura.md`

### §6.6 Compatibilidad de versiones («Cobrar» y la versión mínima)

**Texto actual** (viñeta de la compilación)

> - La compilación del frontend lleva su versión (`APP_VERSION`, formato `X.Y.Z`; por omisión `dev`). El teléfono guarda en `meta` la última mínima conocida cada vez que sincroniza y compara por números, no por texto. Por debajo de la mínima, «Vender» queda deshabilitado en el inicio y en la ficha del cliente, y «Confirmar venta» no confirma (con un carrito abierto, el carrito sigue y se muestra el aviso); la cola se sigue enviando. Sin señal vale la última mínima conocida. Si la versión de la compilación o la mínima no tienen formato `X.Y.Z`, no se restringe nada. La compilación de producción debe definir `APP_VERSION` (ADR-064).

**Texto propuesto**

> - La compilación del frontend lleva su versión (`APP_VERSION`, formato `X.Y.Z`; por omisión `dev`). El teléfono guarda en `meta` la última mínima conocida cada vez que sincroniza y compara por números, no por texto. Por debajo de la mínima, «Vender» y **«Cobrar»** quedan deshabilitados en el inicio y en la ficha del cliente, y «Confirmar venta» **y «Confirmar cobranza»** no confirman (con un carrito o un formulario de cobro abierto, los datos siguen y se muestra el aviso); la cola se sigue enviando. Sin señal vale la última mínima conocida. Si la versión de la compilación o la mínima no tienen formato `X.Y.Z`, no se restringe nada. La compilación de producción debe definir `APP_VERSION` (ADR-064, ADR-067).

### §13.2 Base local (Dexie)

**Texto actual**

> | `ventas`, `cobranzas` | Operaciones locales con estado de envío (`PENDIENTE`, `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA`; solo cambia con el resultado del servidor) y los datos congelados de la nota |
>
> Las tablas de operaciones (versión 4 de Dexie, change 22d) no las toca el bootstrap; la versión 4 solo agrega `anulaciones` y no modifica las demás (ADR-066). Confirmar una venta local escribe venta, cobranza, movimientos, comando y los dos contadores en **una sola transacción**: todo o nada; **anular una venta local escribe la anulación, … en una sola transacción, y reconfirmar la anulación de la misma venta devuelve la existente**. Reconfirmar con el mismo `operation_id` no encola otra venta (ADR-063).

**Texto propuesto**

> | `ventas`, `cobranzas` | Operaciones locales con estado de envío (`PENDIENTE`, `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA`; solo cambia con el resultado del servidor) y los datos congelados de la nota. **`cobranzas` guarda dos orígenes: `VENTA` (el cobro en el momento de una venta, con `venta_id`; sigue la suerte de su venta y no tiene estado de envío propio) e `INDEPENDIENTE` (la cobranza suelta del vendedor, con `venta_id` nulo, `cliente_id`, `jornada_id`, `operation_id`, observación, los nombres congelados del cliente, de los medios y del vendedor y su propio `estado_envio`, que cambia solo con el resultado del servidor). Una fila sin `origen` es de una venta** |
>
> Las tablas de operaciones (**versión 5 de Dexie, change 23**) no las toca el bootstrap; **la versión 5 solo agrega a `cobranzas` los índices `operation_id`, `cliente_id`, `jornada_id` y `estado_envio` (la 4 agregó `anulaciones`) y no modifica filas ni otras tablas (ADR-066, ADR-067)**. Confirmar una venta local escribe venta, cobranza, movimientos, comando y los dos contadores en **una sola transacción**: todo o nada; anular una venta local … **y registrar una cobranza local escribe la cobranza, su movimiento `COBRANZA_CREDITO` (con el `operation_id` de la cobranza), el comando `COBRANZA_REGISTRAR` `OFFLINE` y la última secuencia en una sola transacción; reconfirmar el mismo `cobranza_id` devuelve la existente**. Reconfirmar con el mismo `operation_id` no encola otra venta (ADR-063).

### §13.3 Motor de sincronización (cobranzas en «Sincronización», en lo pendiente y el resultado)

**Texto actual** (dos fragmentos)

> - … Aplica los resultados por `operation_id` en una sola transacción Dexie por lote (INV-01); **el resultado de una anulación cambia el estado de la fila de `anulaciones` y de su comando, no el de la venta**.
>
> - … las ventas «Con observaciones» y «Rechazadas» **y las anulaciones con problemas («Anulación de {número}»)** (ADR-064). **Lo pendiente se dice «N ventas y M anulaciones sin enviar» (solo ventas: «N ventas sin enviar»; solo anulaciones: «M anulaciones sin enviar»), también en los avisos de cierre de sesión y de pendientes de otro usuario.**

**Texto propuesto**

> - … Aplica los resultados por `operation_id` en una sola transacción Dexie por lote (INV-01); el resultado de una anulación cambia el estado de la fila de `anulaciones` y de su comando, no el de la venta; **el resultado de una cobranza cambia el estado de la fila de `cobranzas` (origen `INDEPENDIENTE`) y de su comando, no el de ninguna venta; sus observaciones se guardan en el comando y una `JORNADA_LIBERADA` marca la jornada como no abierta (ADR-067)**.
>
> - … las ventas «Con observaciones» y «Rechazadas», las anulaciones con problemas («Anulación de {número}») **y las cobranzas con problemas («Cobranza a {cliente}», con su texto y acceso al detalle)** (ADR-064). **Lo pendiente se dice uniendo las partes que no son cero: «N ventas, M anulaciones y K cobranzas sin enviar» («2 ventas, 1 anulación y 1 cobranza sin enviar»; solo cobranzas: «3 cobranzas sin enviar»), también en los avisos de cierre de sesión y de pendientes de otro usuario («Hay 3 cobranzas sin enviar de {vendedor}.») (ADR-067).** Los textos de los rechazos y las observaciones de la cobranza salen de `rechazos_de_cobranza` y `observaciones_de_cobranza` del fixture `codigos-de-sincronizacion.json`, elegidos por el tipo de operación.

---

## `04-roadmap-changes.md`

### §11 (fila del 23 y registro del change)

**Texto actual**

> | 23 | `cobranza-offline` | Cobranza sin conexión y su efecto en el crédito disponible local | — |

**Texto propuesto**

> | 23 | `cobranza-offline` | Cobranza sin conexión y su efecto en el crédito disponible local: pantalla de cobro en `/ruta`, cobranza local atómica por la cola (Dexie v5), su efecto en el saldo local (CRE-08) con la regla de la cobranza rechazada, «Cobrar» cortado con la jornada no abierta y la versión mínima — **terminado (ADR-067)** | — |

Más un párrafo nuevo después del 22d (se completa con la fecha y la prueba manual al archivar):

> **Change 23 (`cobranza-offline`) archivado 2026-11-03 — terminado (ADR-067).** Entrega: la cobranza del teléfono siempre por la cola (`COBRANZA_REGISTRAR` v1 `OFFLINE`, contrato fijado por `cobranza-registrar-offline.json` y pruebas de caracterización del lote, **sin cambios de código en el servidor**); la base local v5 con la cobranza independiente en `cobranzas`; la cobranza local atómica y su efecto en el saldo y el crédito disponible locales, con la cobranza independiente rechazada sin contar; las pantallas «Cobrar», «Cobranza guardada» y «Cobranzas de hoy»; las cobranzas en «Sincronización» y en lo pendiente («N ventas, M anulaciones y K cobranzas sin enviar»); los rechazos y las observaciones de la cobranza traducidos; el corte de «Cobrar» con la jornada no abierta y la versión mínima; cuatro claves de ayuda nuevas y cinco revisadas. Sin migración ni permisos nuevos. **Deudas saldadas:** del 17 «al 23» (ADR-052, deuda 3: la pantalla de cobranza del vendedor y su cola local) y del 22c «al 23» (ADR-065, D2: la regla de la cobranza suelta rechazada). **Deudas nuevas:** al **24** (rendición), contar las cobranzas de la jornada en el resumen y decidir qué pasa con la cobranza que llega con la jornada `EN_RENDICION` o `CERRADA` (RUT-05; ya nominada por ADR-052, deuda 4); al **25** (observaciones y revisión), la resolución de las cobranzas rechazadas; a la **etapa 2**, COB-06 (comprobante de cobranza). **Prueba manual:** 2026-11-03.
