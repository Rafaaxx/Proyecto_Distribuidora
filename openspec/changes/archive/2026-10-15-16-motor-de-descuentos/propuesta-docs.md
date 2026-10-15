# Propuesta de cambios a `docs/` — change 16 `motor-de-descuentos`

> **Pendiente de revisión del usuario. No se aplica a `docs/` sin su visto bueno.** Cada sección tiene el **texto actual** (copiado de `docs/` tal como está hoy) y el **texto propuesto** (lo que dejan las decisiones D0 a D20 aprobadas el 2026-10-13, más las precisiones aprobadas durante el apply, registradas en `docs/adr/ADR-050-motor-de-descuentos.md`, hoy en estado *Propuesto*).
>
> Orden: `00` §6.1, §6.2; `01` §4, §10, §18, §19 (y §15 AUD-01); `02` §5.3, §6.5, §10.4, §11; `03` §11, §15; `04` §2, §8, §9.
>
> Dos puntos para decidir al revisar: (1) la fila de `AUD-01` (§15 de `01`) y la de `INV-05`/DSC en `03` §15 no estaban en la lista de la tarea 18.2: se agregan porque el tope por rol queda auditado y la tabla `regla_descuento` tiene privilegios acotados; se pueden quitar sin afectar al resto. (2) El aviso de "tope 0 %" de la pantalla "Topes por rol" se muestra solo en los roles con `DESCUENTO_MANUAL`, porque `GET /identidad/roles` devuelve los permisos de cada rol (ajuste aprobado el 2026-10-15, ADR-050 punto 13).

---

## `00-vision-y-alcance.md`

### §6.1 Etapa 1 — fila Venta

**Texto actual**

> | Venta | Pedido en cajas y unidades, precio desde lista, descuento manual controlado por permiso y tope, una o dos reglas de descuento por volumen, control de crédito, pago total/parcial/cuenta corriente con varios medios, confirmación atómica, costo congelado, anulación por reversión | Fidelización por historial, devoluciones parciales, bonificación en unidades |

**Texto propuesto**

> | Venta | Pedido en cajas y unidades, precio desde lista, descuento manual controlado por permiso y tope (un porcentaje general de la venta y, opcionalmente, uno propio por línea), reglas de descuento por volumen (cajas equivalentes, unidades base o importe bruto) sobre toda la venta o sobre productos, categorías o marcas, con prioridad, acumulables y vigencia, control de crédito, pago total/parcial/cuenta corriente con varios medios, confirmación atómica, costo congelado, anulación por reversión | Fidelización por historial, promociones por cliente o segmento, precio especial, bonificación en unidades, devoluciones parciales |

### §6.2 Etapa 2 — viñeta del motor de descuentos

**Texto actual**

> - Fidelización por historial de compras y ampliación del motor de descuentos (reglas por categoría, marca, cliente, promociones temporales, acumulabilidad completa).

**Texto propuesto**

> - Fidelización por historial de compras y ampliación del motor de descuentos (reglas por cliente o segmento, promociones por cliente, precio especial, bonificación en unidades, margen mínimo, tramos escalonados y combinaciones de condiciones). Las reglas por categoría y marca, la vigencia y la acumulabilidad ya son de la etapa 1 (`01` DSC-02 a DSC-05).

---

## `01-dominio.md`

### §4 Configuración por organización — motivo obligatorio

**Texto actual**

> | Motivo obligatorio en descuento manual | Sí / no | A definir | 1 |

**Texto propuesto**

> | Motivo obligatorio en descuento manual | Sí / no | A definir; mientras esté sin definir, el motivo no es obligatorio (el comando que lo define llega con el change 18b) | 1 |

### §10 Descuentos — DSC-03, DSC-04, DSC-05, DSC-06, DSC-07, DSC-08

**Texto actual**

> | DSC-03 | La condición de volumen compara, con operador explícito (≥ o >), una medida contra un umbral. Medidas: cajas equivalentes, unidades base o importe bruto de las líneas elegibles. | 1 |
> | DSC-04 | Acciones de la etapa 1: porcentaje sobre las líneas elegibles o importe fijo distribuido entre ellas en proporción a su bruto; el remanente de redondeo se asigna a la línea de mayor importe. | 1 |
> | DSC-05 | Orden de resolución: (1) bruto por línea desde la lista; (2) se evalúan las reglas activas y vigentes cuyo alcance aplica; (3) entre las no acumulables se aplica solo la de mayor beneficio total, con desempate por prioridad; (4) las acumulables se aplican en orden de prioridad, cada una sobre el resultado anterior; (5) se aplica el descuento manual sobre el resultado. | 1 |
> | DSC-06 | El descuento manual requiere que la organización lo tenga habilitado y el permiso `DESCUENTO_MANUAL`, cuyo tope porcentual depende del rol. Superar el tope requiere `AUTORIZAR_DESCUENTO` o PIN de supervisor. | 1 |
> | DSC-07 | Cada descuento se calcula y redondea a 2 decimales por línea. | 1 |
> | DSC-08 | Cada línea guarda cada descuento aplicado con origen (AUTOMATICO o MANUAL), regla, porcentaje o importe, motivo y autorizador. | 1 |

**Texto propuesto**

> | DSC-03 | La condición de volumen compara, con operador explícito (≥ o >), una medida contra un umbral. Medidas: cajas equivalentes, unidades base o importe bruto de las líneas elegibles. Las cajas equivalentes de una línea usan las **unidades de referencia guardadas con su precio** (PRC-22) y la medida es la suma exacta de `cantidad base / unidades de referencia`, **sin redondear**, comparada con aritmética entera. El umbral es mayor que 0: hasta 4 decimales en cajas, entero en unidades base, hasta 2 decimales en importe. La condición de toda regla, también de las acumulables, se evalúa una sola vez sobre cantidades y brutos de las líneas, no sobre importes ya descontados. | 1 |
> | DSC-04 | Acciones de la etapa 1: porcentaje sobre las líneas elegibles (mayor que 0 y hasta 100 %, con hasta 6 decimales de fracción) o importe fijo (mayor que 0, hasta 2 decimales) distribuido entre ellas en proporción a su **importe al momento de aplicar la regla** (el bruto si es la primera en aplicarse; el resultado anterior si es acumulable). Cada parte se redondea a 2 decimales y el remanente de redondeo, positivo o negativo, se asigna a la línea de mayor importe y, en empate, a la primera en el orden de la venta. Si el importe fijo supera la suma de las líneas elegibles, se aplica esa suma: ninguna línea queda con neto negativo. | 1 |
> | DSC-05 | Orden de resolución: (1) bruto por línea desde la lista; (2) se evalúan las reglas activas y vigentes cuyo alcance aplica; (3) entre las no acumulables gana **una sola en toda la venta**: la de mayor beneficio total (la suma de los descuentos que daría sobre sus líneas elegibles), con desempate por prioridad —el número más bajo es la mayor prioridad— y, si también empata, por la regla creada primero; las demás no acumulables no se aplican a ninguna línea; (4) las acumulables se aplican en orden de prioridad (y, a igual prioridad, por antigüedad), cada una sobre el resultado anterior; (5) se aplica el descuento manual sobre el resultado: cada línea lleva el porcentaje manual **propio** si lo tiene y, si no, el **general** de la venta (el propio reemplaza al general; no se suman ni se encadenan). El resultado no depende del orden en que se entregan las reglas. | 1 |
> | DSC-06 | El descuento manual requiere que la organización lo tenga habilitado y el permiso `DESCUENTO_MANUAL`, cuyo tope porcentual depende del rol (o del propio usuario, si lo tiene). Es siempre un **porcentaje** (mayor que 0 y hasta 100 %, hasta 6 decimales), nunca un importe; puede ser **general** para la venta y/o **propio** de líneas individuales, y el propio tiene el mismo dominio que el general. El tope se compara contra el **mayor porcentaje manual que quedó aplicado en alguna línea** de la venta (un general reemplazado en todas las líneas no cuenta). Superar el tope requiere `AUTORIZAR_DESCUENTO` del propio usuario o la autorización de otro usuario que lo tenga (PIN de supervisor, change 18b); **una sola autorización cubre toda la venta** y quien autoriza no queda limitado por su propio tope. Si la organización exige motivo, hay un motivo por venta. | 1 |
> | DSC-07 | Cada descuento se calcula y redondea a 2 decimales por línea (mitad hacia arriba). Un descuento cuyo importe redondea a $0,00 no se informa. | 1 |
> | DSC-08 | Cada línea guarda cada descuento aplicado con origen (AUTOMATICO o MANUAL), regla, porcentaje o importe, motivo y autorizador. Una línea lleva **a lo sumo un descuento `MANUAL`**, y el motivo y el autorizador de la venta se copian en cada uno. | 1 |

**Texto actual** (párrafo posterior a la tabla)

> Ejemplo de DSC-03 con regla "cajas equivalentes ≥ 20 → 5%": 19 cajas + 5 unidades de un vino x6 son 19,83 cajas equivalentes y no aplica; 20 cajas aplica.

**Texto propuesto**

> Ejemplo de DSC-03 con regla "cajas equivalentes ≥ 20 → 5%": 19 cajas + 5 unidades de un vino x6 son 19,83 cajas equivalentes y no aplica; 20 cajas aplica. Tres líneas de 2 unidades de tres vinos x6 suman exactamente 1 caja equivalente (1/3 + 1/3 + 1/3) y "≥ 1" aplica.

### §15 Auditoría — AUD-01 (fragmento; el resto de la fila no cambia)

**Texto actual** (fragmento)

> … uso de lista no asignada o versión anterior; descuentos manuales y autorizaciones; autorizaciones de crédito; …

**Texto propuesto** (fragmento)

> … uso de lista no asignada o versión anterior; descuentos manuales y autorizaciones; cambios del tope de descuento de un rol (una fila con el valor anterior y el nuevo); autorizaciones de crédito; …

### §18 Máquinas de estado — regla de descuento

**Texto actual**

> | Regla de descuento | Almacenada | BORRADOR → ACTIVA ↔ PAUSADA | 1 |
> | Regla de descuento | Derivada | VENCIDA | 1 |

**Texto propuesto**

> | Regla de descuento | Almacenada | BORRADOR → ACTIVA ↔ PAUSADA. Solo un borrador se edita completo; activada o pausada solo admite fijar su vigencia hasta. Ninguna regla vuelve a BORRADOR ni se borra. | 1 |
> | Regla de descuento | Derivada | VENCIDA (activa o pausada con la vigencia hasta ya pasada) | 1 |

### §19 Permisos y roles

**Texto actual**

> | ADMIN_USUARIOS | Usuarios, roles y permisos | ✓ | | | | |
> | GESTIONAR_DESCUENTOS | Reglas de descuento | ✓ | | | | |
> | AUTORIZAR_DESCUENTO | Superar tope de descuento | ✓ | | ✓ | | |

**Texto propuesto**

> | ADMIN_USUARIOS | Usuarios, roles y permisos (incluye definir el tope de descuento manual de cada rol y consultar los roles con su tope) | ✓ | | | | |
> | GESTIONAR_DESCUENTOS | Reglas de descuento: alta, edición del borrador, activación, pausa y consulta. Abre, solo en lectura, las categorías, marcas y productos para elegir alcances | ✓ | | | | |
> | AUTORIZAR_DESCUENTO | Superar tope de descuento, el propio o el de otro usuario; quien autoriza no queda limitado por su propio tope | ✓ | | ✓ | | |

(`DESCUENTO_MANUAL` y el párrafo de roles no cambian.)

---

## `02-arquitectura.md`

### §5.3 Dependencias permitidas entre módulos

**Texto actual** (después de la línea de `stock`)

> `stock ──► catalogo, costeo, configuracion (motivos, solo por service.py, ADR-048)`
> `catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)`

**Texto propuesto**

> `stock ──► catalogo, costeo, configuracion (motivos, solo por service.py, ADR-048)`
> `descuentos ──► catalogo, identidad (alcances, configuración del descuento manual, permisos y tope; solo por service.py, ADR-050)`
> `catalogo ──► costeo (solo lectura del costo promedio de un producto, ADR-036)`

Y una nota a continuación de las existentes:

> Nota: `catalogo` e `identidad` no importan `descuentos`; `ventas` consume el motor y la evaluación del descuento manual solo por `descuentos/service.py`.

### §6.5 Tipos de comando de la etapa 1

**Texto actual** (filas)

> | `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (con `ADMIN_CONFIGURACION`) | ✓ | |
> | `SALDO_INICIAL_REGISTRAR` | ✓ | |

**Texto propuesto**

> | `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (con `ADMIN_CONFIGURACION`) | ✓ | |
> | `REGLA_DESCUENTO_CREAR`, `REGLA_DESCUENTO_MODIFICAR`, `REGLA_DESCUENTO_ACTIVAR`, `REGLA_DESCUENTO_PAUSAR` (con `GESTIONAR_DESCUENTOS`) | ✓ | |
> | `ROL_TOPE_DESCUENTO_DEFINIR` (con `ADMIN_USUARIOS`) | ✓ | |
> | `SALDO_INICIAL_REGISTRAR` | ✓ | |

**Texto actual** (párrafo nuevo; hoy no existe)

> (ninguno)

**Texto propuesto** (a continuación del párrafo de los comandos de listas)

> `REGLA_DESCUENTO_CREAR` lleva nombre, tipo, medida, operador, umbral, acción (tipo y valor, el valor como cadena: fracción de seis decimales para el porcentaje o importe de dos decimales), prioridad entera desde 1, acumulable, los alcances (identificadores de productos, categorías o marcas) y, opcionalmente, la vigencia desde y hasta; la regla nace en `BORRADOR`. `REGLA_DESCUENTO_MODIFICAR` reemplaza un borrador con los mismos campos; en una regla activada o pausada solo admite la vigencia hasta (`REGLA_NO_ES_BORRADOR`, 409, en cualquier otro caso). `REGLA_DESCUENTO_ACTIVAR` (desde `BORRADOR` o `PAUSADA`) y `REGLA_DESCUENTO_PAUSAR` (desde `ACTIVA`) llevan solo la regla; una transición que no corresponde responde `REGLA_ESTADO_INVALIDO` (409). Los errores propios son `UMBRAL_INVALIDO`, `ACCION_INVALIDA`, `PRIORIDAD_INVALIDA`, `NOMBRE_INVALIDO`, `ALCANCE_INVALIDO`, `VIGENCIA_INVALIDA`, `REGLA_DESCUENTO_INVALIDA` (422) y `REGLA_ESTADO_INVALIDO`, `REGLA_NO_ES_BORRADOR` (409). Las rutas cuelgan de `/api/v1/descuentos/reglas` (alta, edición, `/{id}/activacion`, `/{id}/pausa`) y las lecturas, `GET /api/v1/descuentos/reglas` (filtro de estado, que admite `VENCIDA`, y cursor) y `GET /api/v1/descuentos/reglas/{id}`, todas con `GESTIONAR_DESCUENTOS`. `ROL_TOPE_DESCUENTO_DEFINIR` lleva el rol y el tope como cadena (fracción de hasta seis decimales entre 0 y 1; `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`, 422), cambia solo `rol.tope_descuento`, deja una fila de auditoría con el valor anterior y el nuevo y se expone en `PUT /api/v1/identidad/roles/{rol_id}/tope-descuento`; `GET /api/v1/identidad/roles` devuelve los roles con su tope y sus permisos (`ADMIN_USUARIOS`); la pantalla "Topes por rol" exige `GESTIONAR_DESCUENTOS` y `ADMIN_USUARIOS`, y el tope no se expone en `GET /yo` ni en el token (el usuario ve el suyo recién en el 18b, con el bootstrap, SYN-11). La evaluación del descuento manual no es un comando: la consulta la venta por `descuentos/service.py` y devuelve `DESCUENTO_MANUAL_DESHABILITADO` (409), `MOTIVO_REQUERIDO` (422), `AUTORIZACION_REQUERIDA` y `AUTORIZADOR_SIN_PERMISO` (403) cuando corresponde.

### §10.4 Motor de cálculo compartido

**Texto actual**

> - `backend/app/modules/precios/domain/bruto_de_linea.py` (PRC-22; el motor completo de venta —descuentos, totales, crédito— vivirá en `ventas/domain/calculo.py` desde el change 18a y consumirá esta función por `precios/service.py`) y `frontend/src/domain/precios/brutoDeLinea.ts`; el resto del motor, en `frontend/src/domain/calculo.ts`.

> Los casos de PRC-22 están en `shared/fixtures/calculo/prc-22-bruto-de-linea.json` (`"motor": "prc22"`). El cálculo de costo de referencia, margen y redondeo (PRC-11, PRC-12, PRC-14) corre solo en el servidor y no tiene gemela (ADR-047 punto 11, matiza ADR-016).

Formato de un caso:

> ```json
> { "id": "PRC-22-caja-y-sueltas", "reglas": ["PRC-22"], "entrada": { "modo_impositivo": "A", "lineas": [ { "producto_id": "p1", "precio_referencia": "12500.00", "unidades_referencia": 6, "cantidad_base": 15, "alicuota": "0.210000" } ], "reglas_descuento": [], "descuento_manual": null }, "salida_esperada": { "lineas": [ { "bruto": "31250.00", "descuentos": "0.00", "neto": "31250.00", "iva": "0.00" } ], "total": "31250.00" } }
> ```

**Texto propuesto**

> - `backend/app/modules/precios/domain/bruto_de_linea.py` (PRC-22) y `frontend/src/domain/precios/brutoDeLinea.ts`; el motor de descuentos (DSC-03 a DSC-07), en `backend/app/modules/descuentos/domain/` y `frontend/src/domain/descuentos/`, expuesto por `descuentos/service.py`; el motor completo de venta —bruto, descuentos, totales, crédito— vivirá en `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts` desde el change 18a, como orquestadores que consumen las funciones de `precios` y `descuentos` por sus `service.py` (ADR-050).

> Los casos de PRC-22 están en `shared/fixtures/calculo/prc-22-bruto-de-linea.json` (`"motor": "prc22"`). Los del motor de descuentos están en `shared/fixtures/calculo/dsc-05-descuentos.json` (`"motor": "dsc05"`: condición, acciones, orden de resolución y descuento manual general y propio, con `porcentaje_manual_maximo`) y los de la evaluación del tope y la autorización, en `shared/fixtures/calculo/dsc-06-descuento-manual.json` (`"motor": "dsc06"`). Los casos de totales (VTA-04) y de crédito se agregan, con el mismo formato, en los changes 18a y 18b. El cálculo de costo de referencia, margen y redondeo (PRC-11, PRC-12, PRC-14) corre solo en el servidor y no tiene gemela (ADR-047 punto 11, matiza ADR-016).

Formato de un caso (el de descuentos, con el descuento manual en dos niveles):

> ```json
> {
>   "id": "DSC05-res-manual-sin-automaticos",
>   "reglas": ["DSC-05", "PRC-22"],
>   "comentario": "Sin reglas: 5% de 31250.00 = 1562.50; neto 29687.50. Maximo 0.050000.",
>   "entrada": {
>     "motor": "dsc05",
>     "lineas": [
>       { "id": "l-vino", "bruto": "31250.00", "cantidad_base": 15, "unidades_referencia": 6,
>         "producto_id": "prod-vino", "categoria_id": "cat-vinos", "marca_id": "marca-bodega-norte",
>         "descuento_manual": null }
>     ],
>     "reglas_descuento": [],
>     "descuento_manual_general": "0.050000"
>   },
>   "salida_esperada": {
>     "lineas": [
>       { "id": "l-vino",
>         "descuentos": [ { "origen": "MANUAL", "regla_id": null, "porcentaje": "0.050000", "importe": "1562.50" } ],
>         "descuento_total": "1562.50", "neto": "29687.50" }
>     ],
>     "porcentaje_manual_maximo": "0.050000"
>   }
> }
> ```
>
> El caso completo de venta con IVA y total (`modo_impositivo`, `alicuota`, `iva`, `total`) lo introduce el change 18a sobre este mismo formato; el `descuento_manual` único de nivel venta que traía el ejemplo anterior pasa a `descuento_manual_general` más el `descuento_manual` propio de cada línea.

### §11 API — agrupación de endpoints

**Texto actual**

> | Identidad | usuarios, roles, dispositivos, PIN |
> | Descuentos | reglas |

**Texto propuesto**

> | Identidad | usuarios, roles (con su tope de descuento), dispositivos, PIN |
> | Descuentos | reglas (alta, edición del borrador, activación, pausa, consulta) |

---

## `03-modelo-de-datos.md`

### §11 Descuentos

**Texto actual**

> | `regla_descuento` | `id`, `organizacion_id`, `nombre`, `tipo` (`VOLUMEN_OPERACION`, `VOLUMEN_ALCANCE`), `medida` (`CAJAS_EQUIVALENTES`, `UNIDADES_BASE`, `IMPORTE_BRUTO`), `operador` (`GTE`, `GT`), `umbral` `numeric(14,4)`, `accion_tipo` (`PORCENTAJE`, `IMPORTE_FIJO`), `accion_valor`, `prioridad` `integer`, `acumulable` `boolean`, `vigencia_desde`, `vigencia_hasta`, `estado` (`BORRADOR`, `ACTIVA`, `PAUSADA`) | DSC-01 a DSC-04 |
> | `regla_descuento_alcance` | `id`, `organizacion_id`, `regla_id`, `alcance_tipo` (`PRODUCTO`, `CATEGORIA`, `MARCA`), `alcance_id` | DSC-02 |
>
> Una regla `VOLUMEN_OPERACION` no tiene filas de alcance. Una `VOLUMEN_ALCANCE` tiene al menos una.

**Texto propuesto**

> | `regla_descuento` | `id`, `organizacion_id`, `nombre`, `tipo` (`VOLUMEN_OPERACION`, `VOLUMEN_ALCANCE`), `medida` (`CAJAS_EQUIVALENTES`, `UNIDADES_BASE`, `IMPORTE_BRUTO`), `operador` (`GTE`, `GT`), `umbral` `numeric(14,4)` (mayor que 0), `accion_tipo` (`PORCENTAJE`, `IMPORTE_FIJO`), `accion_porcentaje` `numeric(9,6)` (mayor que 0 y hasta 1), `accion_importe` `numeric(14,2)` (mayor que 0) —exactamente una de las dos, la que corresponde a `accion_tipo`—, `prioridad` `integer` (desde 1; el número más bajo es la mayor prioridad), `acumulable` `boolean`, `vigencia_desde` `timestamptz`, `vigencia_hasta` `timestamptz` (posterior a la desde), `estado` (`BORRADOR`, `ACTIVA`, `PAUSADA`; `VENCIDA` es derivado y no se almacena), `creado_en`, `actualizado_en`, `actualizado_por_id` | DSC-01 a DSC-04 |
> | `regla_descuento_alcance` | `id`, `organizacion_id`, `regla_id`, `alcance_tipo` (`PRODUCTO`, `CATEGORIA`, `MARCA`), `alcance_id`, y las columnas generadas `producto_id`, `categoria_id`, `marca_id` (cada una toma `alcance_id` solo si `alcance_tipo` es el suyo), `creado_en` | DSC-02 |
>
> Una regla `VOLUMEN_OPERACION` no tiene filas de alcance. Una `VOLUMEN_ALCANCE` tiene al menos una (lo garantiza el servicio; no es expresable como `CHECK` de fila). Restricciones: `UNIQUE (organizacion_id, id)` en las dos tablas; `CHECK` de catálogo en `tipo`, `medida`, `operador`, `accion_tipo`, `estado` y `alcance_tipo`; `CHECK` que exige la columna de acción que corresponde y fija el dominio de cada una; `vigencia_hasta > vigencia_desde`; `estado = 'BORRADOR' OR vigencia_desde IS NOT NULL`; claves foráneas compuestas (incluyen `organizacion_id`) de cada alcance a la regla y, por las columnas generadas, a `producto`, `categoria` y `marca`; único por regla, tipo y entidad; índice de listado `(organizacion_id, estado, id DESC)`. El usuario de aplicación tiene `SELECT`, `INSERT` y `UPDATE` sobre `regla_descuento` y ningún `DELETE` (TR-06); sobre `regla_descuento_alcance`, `SELECT`, `INSERT` y `DELETE` y ningún `UPDATE` (el `DELETE` solo lo usa el servicio al reemplazar los alcances de un borrador).

### §15 Restricciones que la base garantiza

**Texto actual** (filas)

> | INV-05 | Permisos del usuario de aplicación sobre tablas de libro y sobre las líneas y cabeceras de transferencias y ajustes (`UPDATE` acotado por columna en las cabeceras) y de jornadas (`UPDATE` acotado por columna) |
> | INV-06 | `UNIQUE (organizacion_id, operation_id)` en `comando` |

**Texto propuesto**

> | INV-05 | Permisos del usuario de aplicación sobre tablas de libro y sobre las líneas y cabeceras de transferencias y ajustes (`UPDATE` acotado por columna en las cabeceras), de jornadas (`UPDATE` acotado por columna) y de reglas de descuento (sin `DELETE` en `regla_descuento`; sin `UPDATE` en `regla_descuento_alcance`) |
> | INV-06 | `UNIQUE (organizacion_id, operation_id)` en `comando` |
> | DSC-01 a DSC-04 | `CHECK` de catálogo, de dominio y de coherencia en `regla_descuento` (una sola columna de acción, la que corresponde al tipo; vigencia ordenada; vigencia desde obligatoria si la regla no es borrador) |

---

## `04-roadmap-changes.md`

### §2 Convenciones de change — tamaño

**Texto actual**

> - **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide. Excepciones aceptadas por el usuario: el change 14 (`transferencias-y-ajustes`) se implementó en cuatro lotes con revisión entre cada uno, y el change 15 (`jornadas`) en cuatro lotes, en lugar de dividirse (ADR-048, punto 1; ADR-049, punto 1).

**Texto propuesto**

> - **Tamaño:** entre medio día y tres días de trabajo. Un change más grande se divide. Excepciones aceptadas por el usuario: el change 14 (`transferencias-y-ajustes`) se implementó en cuatro lotes con revisión entre cada uno, el change 15 (`jornadas`) en cuatro lotes, y el change 16 (`motor-de-descuentos`) en cuatro lotes sin revisión entre ellos, con la confirmación de alcance de sus piezas críticas, en lugar de dividirse (ADR-048, punto 1; ADR-049, punto 1; ADR-050, punto 1).

### §8 Hito 4 — fila del change 16 y deudas

**Texto actual**

> | 16 | `motor-de-descuentos` | Reglas de volumen, alcance, prioridad, acumulabilidad; motor en Python y TypeScript; descuento manual con tope y autorización; fixtures compartidos DSC-05 | — |

**Texto propuesto**

> | 16 | `motor-de-descuentos` | Reglas de volumen, alcance, prioridad, acumulabilidad y vigencia; motor en Python y TypeScript; descuento manual (general por venta y propio por línea) con tope y autorización; tope de descuento por rol; fixtures compartidos DSC-05 y DSC-06; pantallas de reglas y de topes. El efecto en la venta es del 18b | — |

**Texto actual** (párrafo; hoy no existe)

> (ninguno)

**Texto propuesto** (a continuación de las deudas del change 15)

> **Change 16 (`motor-de-descuentos`) — deudas saldadas (ADR-050):** la parte de descuentos de la deuda nominada por el change 13 al 18a ("completar los casos compartidos de §10.4 con descuentos") queda saldada con `dsc-05-descuentos.json` y `dsc-06-descuento-manual.json`; la parte de totales (VTA-04) sigue en el 18a. La migración `b5c6d7e8f9a0` baja borrando las dos tablas nuevas: pierde las reglas, sin pérdida de historia mientras ninguna venta las referencie.

### §9 Hito 5 — deudas nuevas

**Texto actual** (párrafo; hoy no existe)

> (ninguno)

**Texto propuesto** (a continuación de la tabla del hito 5)

> **Deudas nuevas del change 16 (`motor-de-descuentos`):** **al change 18a (`venta-online-core`):** `ventas/domain/calculo.py` y `frontend/src/domain/calculo.ts` como orquestadores del bruto, los descuentos y los totales; casos compartidos de totales (VTA-04) sobre el formato de `dsc-05`. **Al change 18b (`venta-online-descuentos-credito`):** llamar al motor y a la evaluación del descuento manual (una evaluación por venta, con el `porcentaje_manual_maximo` que entrega el motor); la **pantalla de venta con un porcentaje manual general y uno propio por línea**, que muestra cuál lleva cada línea; una sola autorización y un solo motivo por venta, copiados a cada descuento `MANUAL`; verificar el PIN; persistir `venta_linea_descuento` con clave foránea compuesta a `regla_descuento`; DSC-09 y `DESCUENTO_DIFIERE`; la auditoría del descuento manual y de su autorización (AUD-01); el comando que define los parámetros del descuento manual, los motivos sembrados del ámbito `DESCUENTO_MANUAL` y la validación del motivo; que la pantalla de venta del vendedor le muestre **su propio tope aplicable** (p. ej. "Podés descontar hasta 5 %; más pide autorización"), recibido con el bootstrap (SYN-11) y no por `GET /yo` ni por el token (decisión del usuario, 2026-10-15: cada usuario no ve su tope hasta el 18b; "Topes por rol" queda solo para administración); y el comportamiento sin conexión (SYN-05, SYN-10). **Al change 21 (`pwa-y-bootstrap`):** el bootstrap incluye las reglas activas con sus alcances y los topes del usuario (SYN-11), y las líneas locales necesitan `categoria_id` y `marca_id` del producto. **Al change de usuarios y roles:** el tope propio por usuario. (La lectura de roles que incluye sus permisos se resolvió dentro del change 16, decisión del 2026-10-15, para que "Topes por rol" avise el tope 0 % solo en los roles con `DESCUENTO_MANUAL`.)


### Nota para la fila del 18b de `docs/04-roadmap-changes.md` (§8, decisión del usuario 2026-10-15)

**Texto propuesto** (agregar a la fila `18b`)

> La pantalla de venta del vendedor le muestra su propio tope de descuento aplicable (p. ej. "Podés descontar hasta 5 %; más pide autorización"), recibido con el bootstrap (SYN-11). Hasta el 18b ningún usuario ve su tope; la pantalla "Topes por rol" es solo de administración (`ADMIN_USUARIOS` y `GESTIONAR_DESCUENTOS`).
