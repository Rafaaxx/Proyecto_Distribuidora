# Propuesta de cambios a `docs/` — change 18a `venta-online-core`

> **Estado: APLICADA a `docs/01` a `docs/04` el 2026-10-21 con el visto bueno del usuario** (el punto de `ADR-049` quedó como sección de enmienda al final del ADR, sin editar su cuerpo). Divergencias menores al aplicar: la tabla de `venta` ya tenía `lista_version_id` y las columnas `credito_*` (se marcaron como del 18b); la fila nueva de `01` §4 va tras el motivo de lista anterior; el párrafo de deudas de `04` va tras el de la presentación (change 05) en §9.
>
> **Completado en la tarea 18.1 con lo aprobado por el usuario (D0 a D22 el 2026-10-17 con la opción A, y las precisiones del apply del 2026-10-19 al 2026-10-21, ver `design.md` y ADR-054). No se aplica a `docs/` sin el visto bueno del usuario.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto**. Las decisiones quedan en `docs/adr/ADR-054-venta-con-conexion-y-confirmacion-atomica.md` (estado *Propuesto*) y las enmiendas a los ADR anteriores, al final de cada uno.
>
> Orden: `01` §4, §7.3 (CAT-08, PRC-03, PRC-04, PRC-06, PRC-21, PRC-23), §9 (STK-09), §11.1, §11.2, §13, §19; `02` §5.3, §6.5, §7.3, §7.7, §9, §10.4; `03` §4, §12, §13, §15; `04` §2, §9, §11; `docs/adr/ADR-049` punto 9.
>
> Dudas del propose resueltas aquí: el texto perdido de PRC-23, PRC-03, PRC-04 y PRC-06 se restituye (de `git show 73e0291:docs/01-dominio.md`); la versión de lista va por línea y también en la cabecera de la venta (D16); el desvío de reloj es de 300 s por defecto (aprobado el 2026-10-17); los tres motivos de `LISTA_ANTERIOR` están aprobados.

---

## `01-dominio.md`

### §7.3 CAT-08 como fila de la tabla de reglas (propuesta del 2026-10-20)

**Texto actual:** CAT-08 ("Visualización de cantidades") es un párrafo debajo de la tabla de reglas de catálogo, sin fila propia; por eso la prueba de trazabilidad de la ayuda no puede citarlo.
**Texto propuesto:** convertir CAT-08 en una fila de la tabla, como CAT-01 a CAT-07, con el mismo contenido (`floor(|q| / u)` cajas y `|q| mod u` unidades, con signo negativo si `q < 0`), y dejar la tabla de ejemplos como está. **Una vez aplicado**, CAT-08 se agrega de nuevo a `reglas` de `ventas.cajasYUnidades` en `frontend/src/ayuda/textos.ts` (y a su prueba).

### §4 Configuración por organización (desvío de reloj, D9)

**Texto actual:** no hay fila en `01` §4; `03` §4 tiene `desvio_reloj_max_segundos` ("`02` §9") y `02` §9 dice "un umbral configurable" (ver la sección `02` §9 más abajo).

**Texto propuesto (fila nueva)**

> | Desvío máximo del reloj del dispositivo en operaciones con conexión | Segundos | 300 si la organización no lo define (aprobado el 2026-10-17, ADR-054) | 1 |

### §7.3 PRC-21 y PRC-23

**Texto actual**

> | PRC-21 | Usar otra lista o una versión anterior requiere `USAR_LISTA_ANTERIOR` y motivo según configuración. | 1 |
> | PRC-23 | (sin cambio; lo implementa el change 18a) | 1 |

**Texto propuesto**

> | PRC-21 | Usar otra lista activa o una versión anterior requiere `USAR_LISTA_ANTERIOR` y, si la organización lo exige, un motivo activo del ámbito `LISTA_ANTERIOR`. Una versión anterior es una versión publicada, no anulada, de la lista elegida cuya vigencia desde no es posterior al momento de la venta; las programadas no (`VERSION_NO_PERMITIDA`). La venta guarda la lista, la versión y el motivo, y la auditoría lo registra (ADR-054). | 1 |
> | PRC-23 | La venta congela, por línea, versión de lista, precio de referencia y unidades de referencia. | 1 |

*(Nota: el texto de PRC-23 se perdió al aplicar la propuesta del change 13; se restituye el original.)*

**PRC-03, PRC-04 y PRC-06: restituir el texto perdido.** Las tres filas dicen hoy "(sin cambio)" (PRC-03 y PRC-04 con un agregado) porque la propuesta del change 13 copió la etiqueta en lugar del texto. Texto original, tomado de `git show 73e0291:docs/01-dominio.md`.

**Texto actual**

> | PRC-03 | (sin cambio) + *Publicar no modifica la versión anterior: deja de ser vigente porque la nueva tiene mayor vigencia desde. Cuando vence una versión con vigencia hasta, vuelve a regir la anterior.* | 1 |
> | PRC-04 | (sin cambio) + *El cambio de la presentación de referencia de un producto no altera el precio ni las unidades de referencia guardados en una versión publicada.* | 1 |
> | PRC-06 | (sin cambio) | 1 |

**Texto propuesto**

> | PRC-03 | La versión vigente de una lista en un momento es la PUBLICADA con mayor vigencia desde que no supere ese momento y cuya vigencia hasta, si existe, sea posterior. Los estados PROGRAMADA, VIGENTE e HISTÓRICA se derivan de las fechas y no se almacenan. Publicar no modifica la versión anterior: deja de ser vigente porque la nueva tiene mayor vigencia desde. Cuando vence una versión con vigencia hasta, vuelve a regir la anterior. | 1 |
> | PRC-04 | Una versión publicada es inmutable. Las correcciones generan una versión nueva. El cambio de la presentación de referencia de un producto no altera el precio ni las unidades de referencia guardados en una versión publicada. | 1 |
> | PRC-06 | Publicar requiere `PUBLICAR_LISTAS` y queda auditado. | 1 |

*(PRC-05 no se toca: su texto actual está completo.)*

### §11.1 VTA-06

**Texto actual**

> | VTA-06 | El número de nota de venta es el prefijo del dispositivo seguido de un correlativo del dispositivo (`V03-000142`). Es único por organización. | 1 |

**Texto propuesto**

> | VTA-06 | El número de nota de venta es el prefijo del dispositivo seguido de un correlativo de seis dígitos del dispositivo (`V03-000142`). Lo propone el dispositivo, también con conexión; el servidor exige el prefijo del dispositivo de la sesión (`NUMERO_INVALIDO`) y rechaza uno ya usado (`NUMERO_DUPLICADO`). Es único por organización. El último correlativo del dispositivo pasa al mayor entre el actual y el de la venta y nunca retrocede (ADR-054). | 1 |

### §11.2 VTA-10 y VTA-11

**Texto actual**

> | VTA-10 | Confirmar requiere `VENDER`, cliente habilitado (CLI-02) y precio resoluble (PRC-20). | 1 |
> | VTA-11 | La cobranza registrada con la venta puede ser nula, parcial, total o superior al total. El excedente reduce el saldo previo del cliente. | 1 |

**Texto propuesto**

> | VTA-10 | Confirmar requiere `VENDER`, cliente habilitado (CLI-02) y precio resoluble (PRC-20): con conexión, sin lista aplicable, sin versión vigente o con algún producto sin precio en la versión, la venta entera se rechaza (`SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE`, `PRODUCTO_SIN_PRECIO`). Con conexión se confirma el precio que vio el usuario: si difiere del que resuelve el servidor, `PRECIO_DIFIERE`. Un producto sin costo promedio no se vende con conexión (`PRODUCTO_SIN_COSTO`) (ADR-054). | 1 |
> | VTA-11 | La cobranza registrada con la venta puede ser nula, parcial, total o superior al total, con de 1 a 20 medios que suman su importe; es a lo sumo una por venta, de origen VENTA. El excedente reduce el saldo previo del cliente. Al consumidor final se le vende solo de contado: la cobranza es igual al total (`CONSUMIDOR_FINAL_CONTADO`) (ADR-054). | 1 |

### §13 SYN-05 y SYN-07, y §9 STK-09

**Texto actual (SYN-07)**

> | SYN-07 | Observaciones de la etapa 1: STOCK_NEGATIVO, EXCESO_CREDITO_ADVERTIDO, EXCESO_CREDITO_AUTORIZADO_OFFLINE, EXCESO_CREDITO_DETECTADO_SYNC, LISTA_NO_VIGENTE, DESCUENTO_DIFIERE, CLIENTE_NO_HABILITADO, PERMISO_REVOCADO, JORNADA_LIBERADA, ANULACION_COMPRA_SIN_RECALCULO, MEDIO_INACTIVO, REFERENCIA_FALTANTE. `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE` se emiten solo sin conexión, una por cada línea de medio afectada: … (ADR-052). | 1 |

**Texto propuesto:** la lista de códigos suma `VENTA_SIN_COSTO`, `CONSUMIDOR_FINAL_CON_DEUDA` y `UBICACION_TOMADA_AL_SINCRONIZAR` después de `REFERENCIA_FALTANTE`, y se agrega al final:

> … `CONSUMIDOR_FINAL_CON_DEUDA` se emite solo sin conexión, una vez por venta al consumidor final cuya cobranza no es igual al total (si el cliente además no está habilitado, solo `CLIENTE_NO_HABILITADO`). `VENTA_SIN_COSTO` se emite solo sin conexión, una por línea de un producto sin costo promedio; la línea queda con costo nulo. `LISTA_NO_VIGENTE` se emite una vez por venta sin conexión cuando la versión que usó el dispositivo no es la vigente al `occurred_at` para la lista aplicable (ADR-054). `UBICACION_TOMADA_AL_SINCRONIZAR` se emite solo sin conexión, sobre la venta, cuando la ubicación de la que salió el stock estaba tomada por una jornada al sincronizar (la propia en `EN_RENDICION` o la de otro vendedor); la venta se acepta igual (SYN-05, INV-17) y puede convivir con `JORNADA_LIBERADA` (aprobado por el usuario el 2026-10-20).

**STK-09, texto actual:** "… ese movimiento queda sin jornada y con una observación en la auditoría que nombra la regla y la jornada. En `EN_RENDICION` … Cualquier otro caso se rechaza con `UBICACION_TOMADA` y no escribe nada. La regla se aplica en la única puerta del libro, a todo camino que mueve stock (ADR-049)."

**STK-09, texto propuesto ("nombra la regla y la jornada" pasa a "nombra la jornada", y se agrega al final; aprobado por el usuario el 2026-10-20):** "Una venta recibida sin conexión (SYN-05, INV-17) cuyo stock sale de una ubicación tomada al sincronizar —por la propia jornada en `EN_RENDICION` o por la de otro vendedor— se acepta aunque el usuario no tenga `LIBERAR_UBICACION`: la mercadería ya se entregó. Se descuenta el stock sin `jornada_id`, la venta conserva la jornada del sobre, lleva `UBICACION_TOMADA_AL_SINCRONIZAR` y la auditoría deja la constancia de la jornada que tiene la ubicación. Con conexión rige la regla de arriba (ADR-054)."

**SYN-05, texto propuesto (se agrega al final):** "Una venta sin conexión de un producto o presentación desactivados después del bootstrap se acepta (ADR-054); unos totales que no coinciden con el cálculo sobre los valores enviados son un comando malformado (`TOTALES_INCONSISTENTES`)."

### §19 Permisos (párrafo nuevo después del de cobranzas)

> El listado y el detalle de ventas exigen `VENDER` o `ANULAR_VENTA` y alcanzan a todas las ventas de la organización; los costos de cada línea, además `VER_COSTOS`. Con `VENDER` se leen, solo para vender, los precios de la versión aplicable con las presentaciones de venta y el stock de la ubicación (sin costos), la numeración del dispositivo, la lista de clientes para elegir y su saldo, las listas activas y las ubicaciones activas; las versiones elegibles, con `USAR_LISTA_ANTERIOR` (ADR-054). Sin `USAR_LISTA_ANTERIOR`, los precios para vender son solo los de la versión vigente de la lista que corresponde al cliente. Quien llega a las ubicaciones solo por `VENDER` recibe únicamente las activas y ve quién tiene cada una. El detalle de la venta no trae utilidad (REP-04 exige `VER_UTILIDAD`; es de los reportes). La matriz de permisos de este documento no cambia: `VENDER` y `USAR_LISTA_ANTERIOR` ya existen.

**Texto actual (último párrafo de §19 sobre cobranzas):** "El listado y el detalle de cobranzas exigen `REGISTRAR_COBRANZA` o `ANULAR_COBRANZA` … el saldo de un cliente y la lista de clientes para elegir se …"; el párrafo nuevo va a continuación.

---

## `02-arquitectura.md`

### §5.3 Dependencias

**Texto actual:** `ventas ──► precios, descuentos, clientes, stock, costeo, cuentas_corrientes, cobranzas, catalogo`

**Texto propuesto:** `ventas ──► precios, descuentos, clientes, stock, costeo, cuentas_corrientes, cobranzas, catalogo, configuracion (motivos), identidad (configuración, dispositivo y permisos) — solo por service.py; ventas/domain alcanza precios.domain (bruto de línea) y descuentos.domain (motor) como código puro con dos ignore_imports (ADR-054)`.

### §6.5 Tipos de comando (párrafo nuevo)

**Texto actual:** la tabla de tipos de §6.5 tiene la fila `VENTA_CONFIRMAR | ✓ | ✓` y no hay un párrafo propio; el párrafo siguiente va después del de jornadas.

> `VENTA_CONFIRMAR` (`VENDER`; `ONLINE` y `OFFLINE`, `permiso_offline = VENDER`) lleva el identificador de la venta, su número, cliente, ubicación (con conexión, si no hay jornada abierta), lista o versión elegidas con su motivo, de 1 a 200 líneas (identificador, producto, presentación, cantidad y los valores esperados: versión, precio y unidades de referencia, bruto), el total esperado y la cobranza opcional (identificador, de 1 a 20 medios, observación). Los errores propios son `VENTA_SIN_LINEAS`, `LINEAS_INVALIDAS`, `LINEA_DUPLICADA`, `NUMERO_INVALIDO`, `MOMENTO_FUERA_DE_RANGO`, `CONSUMIDOR_FINAL_CONTADO` y `MOTIVO_INVALIDO` y `UBICACION_REQUERIDA` (422) y `VENTA_DUPLICADA`, `NUMERO_DUPLICADO`, `PRECIO_DIFIERE`, `PRODUCTO_SIN_PRECIO`, `PRODUCTO_SIN_COSTO`, `PRESENTACION_NO_VENDIBLE`, `VERSION_NO_PERMITIDA`, `CLIENTE_SUSPENDIDO`, `CLIENTE_INACTIVO`, `MODO_IMPOSITIVO_NO_SOPORTADO`, `JORNADA_AJENA`, `STOCK_INSUFICIENTE`, `UBICACION_INACTIVA` y `UBICACION_TOMADA` (409); sin conexión, `TOTALES_INCONSISTENTES` (SYN-06). Emite, solo sin conexión, `STOCK_NEGATIVO`, `CLIENTE_NO_HABILITADO`, `CONSUMIDOR_FINAL_CON_DEUDA`, `LISTA_NO_VIGENTE`, `VENTA_SIN_COSTO`, `UBICACION_TOMADA_AL_SINCRONIZAR`, y sobre la cobranza `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`; `STOCK_NEGATIVO` también con conexión si el usuario tiene `PERMITIR_STOCK_NEGATIVO`. La fila de auditoría del bus lleva el motivo de la lista y la constancia de ubicación tomada cuando corresponden. Ruta `POST /api/v1/ventas`; lecturas `GET /api/v1/ventas`, `/{id}`, `/precios`, `/versiones` y `/numeracion` (ADR-054).

### §7.3 Orden global de bloqueo (agregado)

> La venta lee la lista `FOR SHARE` (candado propio de la lista, fuera del orden) antes del nivel 1; toma `saldo_cuenta` del cliente (nivel 1) y los productos `FOR SHARE` (nivel 2) **antes** de leer las presentaciones (`FOR KEY SHARE`), así una `PRESENTACION_MODIFICAR` simultánea, que toma el producto `FOR UPDATE`, espera o se ve (INV-18). **Nivel 6:** la fila del `dispositivo` que actualiza el último correlativo, al final de la transacción; solo la toman la venta y la revocación del dispositivo, que no toma otras filas (ADR-054).

### §7.7 Numeración (agregado)

> Hasta el bootstrap (change 21), el último correlativo se lee con `GET /api/v1/ventas/numeracion`; el cliente usa el mayor entre ese y el guardado localmente. El servidor no exige que el correlativo supere al último: solo que el número sea del dispositivo y no esté usado; el último pasa al mayor de los dos (ADR-054).

### §9 Desvío del reloj del dispositivo (D9)

**Texto actual:** "`occurred_at` proviene del dispositivo y puede ser inexacto. El servidor guarda también `registered_at` y registra una advertencia si la diferencia es mayor que un umbral configurable hacia el futuro."

**Texto propuesto (se agrega al final):** "El umbral es `desvio_reloj_max_segundos` (300 por defecto si es nulo). Con conexión, una venta cuyo `occurred_at` se aleja del reloj del servidor más que ese margen, en cualquier sentido, se rechaza con `MOMENTO_FUERA_DE_RANGO` (422); sin conexión no se valida, porque el momento es el de la entrega (ADR-054)."

### §10.4 Motor de cálculo compartido

**Texto actual:** "Los casos de totales (VTA-04) y de crédito se agregan, con el mismo formato, en los changes 18a y 18b."

**Texto propuesto:** "Los casos de totales (VTA-04) están en `shared/fixtures/calculo/vta-04-totales.json` (`"motor": "vta04"`: líneas con precio, unidades de referencia, cantidad base, alícuota y reglas; salida con descuentos, neto e IVA por línea y `total_neto`, `total_iva`, `total`; modos B y C rechazados con `MODO_IMPOSITIVO_NO_SOPORTADO`). Los de crédito se agregan en el 18b (ADR-054)."

---

## `03-modelo-de-datos.md`

### §4 `motivo` (agregado al párrafo de siembras)

> Las organizaciones nuevas nacen también con tres motivos del ámbito `LISTA_ANTERIOR` ("Precio acordado con el cliente", "Error en la lista vigente" y "Otro", aprobados el 2026-10-17); la migración del change 18a (`a2b3c4d5e6f7`) los agrega, de forma idempotente, a las organizaciones existentes que no tengan ninguno de ese ámbito (ADR-054).

### §12 `venta` y `venta_linea`

**Texto actual:** la tabla de `venta` (sin `lista_id`, `motivo_lista_id` ni `creado_en`) y la de `venta_linea` (sin `lista_version_id`), con `ck_venta__jornada` y los índices de la tabla.

**Cambios propuestos sobre las tablas actuales:** `venta` suma `lista_id` (FK compuesta a `lista_precio`) y conserva `lista_version_id` (ya está en `03`: es la versión común de todas las líneas, que el servidor exige igual, D16), `motivo_lista_id` (nulable, FK compuesta a `motivo`) y `creado_en`; **no** tiene todavía las columnas `credito_*` (las agrega el 18b, ADR-054 D15); `CHECK (total = total_neto + total_iva)`; índice `(organizacion_id, jornada_id)`. `venta_linea` suma `lista_version_id` por línea (PRC-23), `costo_unitario` y `costo_total` **nulables** juntos (D10), `UNIQUE (organizacion_id, venta_id, orden)`, `CHECK (cantidad > 0)` y `CHECK (cantidad_base = cantidad * unidades_presentacion)`. `app_runtime`: `SELECT, INSERT` en ambas, sin `UPDATE` ni `DELETE` (el 19 agrega `UPDATE` de `venta.estado`). `venta_linea_descuento` llega con el 18b y `venta_anulacion` con el 19.

### §12 `cobranza`

**Texto actual:** "`venta_id` (nulo si independiente; sin FK hasta el change 18a)"

**Texto propuesto:** "`venta_id` (nulo si independiente; FK compuesta `(organizacion_id, venta_id)` a `venta`, change 18a)".

### §13 `observacion`

**Texto actual:** "`codigo` (SYN-07; `CHECK` `ck_observacion__codigo` con el catálogo, que el change 17 amplía con `MEDIO_INACTIVO` y `REFERENCIA_FALTANTE`)".

**Texto propuesto (agregado):** "… que el change 18a amplía con `VENTA_SIN_COSTO`, `CONSUMIDOR_FINAL_CON_DEUDA` y `UBICACION_TOMADA_AL_SINCRONIZAR`."

### §15 Restricciones

**Texto actual:** las filas de INV-05, INV-09, INV-18 y VTA-06 de la tabla de §15 (INV-05 no nombra `venta` ni `venta_linea`; no hay fila de INV-14).

**Fila INV-14 nueva:** "`CHECK (total = total_neto + total_iva)` en `venta` y `CHECK (importe_neto = importe_bruto - importe_descuento)` en `venta_linea`; la suma por líneas se verifica en el servicio y con una propiedad que suma con SQL". **INV-05:** se agregan `venta` y `venta_linea` (sin `UPDATE` ni `DELETE`).

---

## `04-roadmap-changes.md`

### §2 Tamaño (agregado)

> El change 18a (`venta-online-core`) se implementa en cinco lotes y pasa de la estimación: se anota como excepción de tamaño, igual que el 17 (ADR-054).

### §9 Deudas (al archivar)

> **Change 18a (`venta-online-core`) — deudas saldadas (ADR-054):** costo de una venta sin promedio (09: rechazada con conexión, costo nulo con `VENTA_SIN_COSTO` sin conexión); venta sobre saldo negativo (14: promedio vigente, `STOCK_NEGATIVO` con permiso o sin conexión); modo y modalidad de IVA (11b: solo modo A, sin leer la modalidad); `precios/service.py`, PRC-21, PRC-23 y `LISTA_NO_VIGENTE` (13); orquestadores y casos de totales VTA-04 (16); FK de `cobranza.venta_id`, cobranza de origen `VENTA` y permiso offline de `VENTA_CONFIRMAR` (17); verificador `venta_linea` (05, INV-18). **Deudas nuevas:** al **22a** (confirmación local de la venta en `/ruta`), bloquear sin conexión la confirmación del consumidor final cuya cobranza no sea igual al total (decisión del usuario, 2026-10-19; el servidor la acepta con `CONSUMIDOR_FINAL_CON_DEUDA` solo como red de seguridad); al **25**, mostrar `CONSUMIDOR_FINAL_CON_DEUDA` en la bandeja; al **18b**, las columnas `credito_*`, `venta_linea_descuento`, el motor de descuentos en la venta y la regla del consumidor final frente al límite cero; al **19**, `UPDATE` de `venta.estado` y anular la cobranza de la venta (VTA-22, que ADR-052 punto 79 nombraba para el 18a); al **21**, el último correlativo en el bootstrap y las versiones elegibles (SYN-11); al **25**, revisar ventas con producto desactivado sin observación; al **26**, la utilidad de líneas sin costo.

---

### §9 Tabla del hito: fila 18a y deudas anteriores nominadas al 18a

**Texto actual:** los párrafos "Deudas nuevas del change 16", "Deuda nominada por el change 05" y los del 06b, 09, 11b, 14 y 17 que nombran al 18a quedan como están; al archivar el change se agrega el párrafo anterior, que los marca saldados.

### §11 Fila 22a (cola y confirmación local)

**Texto actual:** "Confirmación local atómica en Dexie (venta + movimientos + cola en una transacción), generación local del comprobante, estado de sincronización visible".

**Texto propuesto (se agrega al final):** "; bloquea la confirmación sin conexión de una venta al consumidor final cuya cobranza no sea igual al total (CLI-03; el servidor la acepta con `CONSUMIDOR_FINAL_CON_DEUDA`, ADR-054)".

---

## `docs/adr/ADR-049-jornadas-y-toma-de-ubicacion.md`

### Punto 9 (enmienda, al archivar; aprobada el 2026-10-20)

> **Texto actual:** "... con un texto fijo que nombra la regla y la jornada (`STK-09: ubicación tomada por la jornada <id>`) ..."
> **Texto propuesto:** "... con un texto fijo que nombra la jornada (`ubicación tomada por la jornada <id>`; con varias, `<id1>, <id2>`) ...". Las filas ya guardadas conservan el texto anterior (AUD-03). Con el change 18a, `VENTA_CONFIRMAR` también devuelve la constancia: el ratchet de la constancia pasa de ocho a nueve comandos. Los specs principales de stock no fijan el texto literal: no cambian.
