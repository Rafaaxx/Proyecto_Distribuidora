# Propuesta de cambios a `docs/` — change 13 `listas-de-precios` (tarea 16.2)

> **APLICADA a `docs/` el 2026-10-07 (aprobada por el usuario).** Cada cambio sale de `ADR-047` (estado Vigente) y de las decisiones D0 a D15 de `design.md` ya aprobadas el 2026-10-06. Prioridad de fuentes: `docs/adr/` > `docs/00` a `docs/04`; por eso, si el usuario aprueba el ADR, estos textos son su reflejo en los documentos de referencia. Cada punto indica el documento, la sección y el texto propuesto (lo que no se menciona no cambia).

## `docs/01-dominio.md`

### §4 Configuración por organización

| Fila | Hoy | Propuesto |
| --- | --- | --- |
| Lista de precios por defecto | `Lista` / `General` | `Lista` / **Sin definir**: no se siembra ninguna lista; un usuario con `ADMIN_CONFIGURACION` la elige entre las activas con `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (ADR-047) |
| Redondeo por defecto | `A definir` | Sin cambio (queda como deuda en `04`, ver abajo). Agregar la nota: *solo precarga el formulario de una lista nueva cuando esté definido; la lista siempre tiene su propio redondeo (PRC-01)* |

### §7.1 Listas y versiones (PRC-01 a PRC-06)

| ID | Texto propuesto |
| --- | --- |
| PRC-01 | Una lista tiene nombre (único por organización, sin distinguir mayúsculas) y una regla de redondeo **obligatoria**: múltiplo mayor que cero con hasta dos decimales y dirección. Sus precios viven en versiones. |
| PRC-02 | Una versión tiene estado almacenado (BORRADOR, PUBLICADA, ANULADA), vigencia desde y vigencia hasta opcional. **La vigencia se fija al publicar** (un borrador no tiene): la vigencia desde es opcional, por defecto el momento de la publicación, y nunca anterior a él; la vigencia hasta, si existe, es posterior a la desde. Dos versiones publicadas de una lista no tienen la misma vigencia desde. |
| PRC-03 | (sin cambio) + *Publicar no modifica la versión anterior: deja de ser vigente porque la nueva tiene mayor vigencia desde. Cuando vence una versión con vigencia hasta, vuelve a regir la anterior.* |
| PRC-04 | (sin cambio) + *El cambio de la presentación de referencia de un producto no altera el precio ni las unidades de referencia guardados en una versión publicada.* |
| PRC-05 | Solo puede anularse una versión publicada cuya vigencia aún no comenzó (la vigencia desde es posterior al momento de la anulación). **No pide motivo.** Sus precios no se borran ni cambian. |
| PRC-06 | (sin cambio) |

### §7.2 Cálculo del precio de referencia (PRC-10 a PRC-19)

| ID | Texto propuesto |
| --- | --- |
| PRC-10 | Cada versión tiene, por producto, un único precio de referencia sobre la presentación de referencia, **y guarda las unidades de esa presentación vigentes al calcularlo o fijarlo**. Las demás presentaciones se venden a precio proporcional. |
| PRC-11 | El costo de referencia es `costo base del costo informado vigente (CST-03) × unidades de la presentación de referencia`. Si los costos vigentes del producto por presentación difieren por unidad base, el precio lleva la señal "costos distintos por presentación" y la presentación de la que salió el costo. Si el costo se calculó con otra regla de IVA que la actual (CST-06), lleva la señal "costo con otra regla de IVA". |
| PRC-13 | Las reglas de margen pertenecen a una lista y se resuelven por precedencia, de más específica a más general: producto, marca, categoría, proveedor, lista. **Hay a lo sumo una regla activa por lista y alcance** (misma entidad). Las reglas no se borran: se modifican o se desactivan, y el cambio rige desde el próximo borrador. El valor es una fracción de hasta seis decimales; el margen bruto es menor que 1. |
| PRC-14 | (sin cambio) + *La sobrescritura activa de la categoría del producto manda sobre el redondeo de la lista. Si el redondeo deja el precio en cero, el producto no recibe precio.* |
| PRC-15 | (sin cambio) + *En modo C la generación del borrador se rechaza hasta la etapa 4.* |
| PRC-16 | Cada precio de versión guarda las unidades de referencia, el costo informado y el costo de referencia usados, la regla de margen aplicada (tipo y valor), el precio calculado sin redondear, el precio final y si fue fijado manualmente. **Un precio manual guarda lo mismo que pueda calcularse y nulos si el producto no tiene costo o regla: se admite un precio manual sin costo.** |
| PRC-17 | Ante nuevos costos informados, **el usuario genera** una versión BORRADOR con `LISTA_GENERAR_BORRADOR`: informar un costo no genera nada. El borrador parte de la versión base (la publicada y no anulada de mayor vigencia desde) y recalcula **todos los productos activos**; los precios manuales se conservan y se señalan si son menores que el calculado sin redondear ("margen menor que el de la regla"). Cada precio indica si es nuevo, cambia o queda igual respecto de la base. |
| **PRC-18** (nueva) | Una lista tiene a lo sumo **un borrador**. Generar crea el borrador (con el número siguiente) o lo reemplaza conservando los precios manuales; no se descarta. Publicar no recalcula: la pantalla muestra cuándo se generó. |
| **PRC-19** (nueva) | Un producto activo que el borrador no puede calcular queda **sin precio** y se informa con su causa: `SIN_COSTO`, `SIN_REGLA`, `PRECIO_NO_POSITIVO`, `SIN_PRESENTACION_DE_REFERENCIA` o `SIN_CALCULAR` (hoy se calcularía: hay que regenerar). Solo puede fijársele un precio manual si tiene presentación de referencia. |

### §7.3 Precio en la venta (PRC-20 a PRC-23)

| ID | Texto propuesto |
| --- | --- |
| PRC-20 | La lista de una venta es la asignada al cliente o, si no tiene, la lista por defecto de la organización; ambas deben estar activas (`LISTA_INACTIVA`, `SIN_LISTA_APLICABLE`). Se usa la versión vigente al `occurred_at` de la venta (`LISTA_SIN_VERSION_VIGENTE` si no hay). La lista por defecto, o la asignada a un cliente no inactivo, no se desactiva (`LISTA_EN_USO`). |
| PRC-21 | (sin cambio; lo implementa el change 18a) |
| PRC-22 | El importe bruto de una línea es `precio de referencia × cantidad base / unidades de referencia` (**las unidades guardadas en el precio**), redondeado a 2 decimales una sola vez. El precio unitario por presentación se muestra redondeado pero nunca se usa para calcular totales. Las presentaciones que se muestran las entrega `precios` junto con cada precio (activas y de venta, de menos unidades a más; ADR-047 punto 30). Se calcula en `precios/domain` y en `frontend/src/domain/precios`, con casos compartidos. |
| PRC-23 | (sin cambio; lo implementa el change 18a) |

### §18 Máquinas de estado

Agregar bajo la tabla un párrafo **"Versión de lista"**: *Una lista tiene a lo sumo un borrador (PRC-18). `PUBLICADA` y `ANULADA` no cambian sus precios (INV-11). Los estados derivados son `PROGRAMADA`, `VIGENTE` e `HISTÓRICA` (en la API, `HISTORICA`). Solo se anula una versión `PROGRAMADA`.*

### §19 Permisos y roles

| Fila | Texto propuesto |
| --- | --- |
| GESTIONAR_LISTAS | Listas, reglas de margen, redondeo y borradores (generar y fijar precios manuales); **leer listas, reglas, versiones y precios** |
| PUBLICAR_LISTAS | Publicar y anular versiones; **leer listas, reglas, versiones y precios** |

Párrafo nuevo bajo la tabla: *Las lecturas de listas, reglas, versiones y precios las puede hacer quien tenga `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`. El costo de referencia, el margen y el precio calculado de un precio solo se devuelven con `VER_COSTOS`; las señales siempre. Cada precio trae, sin costos, el nombre y las unidades de las presentaciones activas de venta de su producto, para mostrar el precio por presentación (PRC-22) sin una lectura por producto (ADR-047 punto 30). La lista de listas activas para elegir también se lee con `GESTIONAR_CLIENTES` y `ADMIN_CONFIGURACION`, y la lista predeterminada con `ADMIN_CONFIGURACION`, `GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`. Las lecturas de productos, categorías, marcas y proveedores para elegir el alcance de una regla se abren, solo en lectura, a `GESTIONAR_LISTAS` (ADR-047).*

## `docs/02-arquitectura.md`

### §5.3 Dependencias permitidas entre módulos

Reemplazar las líneas `clientes ──► cuentas_corrientes` y `precios ──► catalogo, proveedores (costos informados)` por:

```
clientes ──► cuentas_corrientes, precios (lista asignada, solo por service.py, ADR-047)
precios ──► catalogo, proveedores (costos informados), identidad (configuración y permisos)
```

Nota: `precios` no depende de `clientes`: este registra en `precios` un verificador de uso de listas (patrón de ADR-023) y no hay ciclo.

### §6.5 Tipos de comando de la etapa 1

Reemplazar la fila `LISTA_GENERAR_BORRADOR`, `LISTA_PUBLICAR`, `LISTA_ANULAR_VERSION` por:

| Tipo | Online | Offline |
| --- | :-: | :-: |
| `LISTA_PRECIO_CREAR`, `LISTA_PRECIO_MODIFICAR`, `REGLA_MARGEN_CREAR`, `REGLA_MARGEN_MODIFICAR`, `REDONDEO_CATEGORIA_DEFINIR` (con `GESTIONAR_LISTAS`) | ✓ | |
| `LISTA_GENERAR_BORRADOR`, `LISTA_BORRADOR_PRECIO_FIJAR` (con `GESTIONAR_LISTAS`) | ✓ | |
| `LISTA_PUBLICAR`, `LISTA_ANULAR_VERSION` (con `PUBLICAR_LISTAS`) | ✓ | |
| `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (con `ADMIN_CONFIGURACION`) | ✓ | |

Y agregar el párrafo: *Los comandos de listas son solo online. Los errores propios son `MARGEN_INVALIDO`, `ALCANCE_INVALIDO`, `REDONDEO_INVALIDO`, `IMPORTE_INVALIDO`, `PRECIO_NO_POSITIVO`, `VIGENCIA_INVALIDA`, `VERSION_SIN_PRECIOS` (422) y `NOMBRE_DUPLICADO`, `REGLA_DUPLICADA`, `LISTA_INACTIVA`, `LISTA_EN_USO`, `VERSION_NO_ES_BORRADOR`, `VERSION_NO_PUBLICADA`, `VERSION_YA_VIGENTE`, `VIGENCIA_DUPLICADA`, `SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE` (409). Las lecturas cuelgan de `/api/v1/precios/…` (listas, reglas, borrador, versiones, precios de una versión paginados por cursor, `vigente?momento=` y `lista-predeterminada`); `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` aceptan `lista_precio_id` (ADR-047).*

### §7.3 Orden global de bloqueo

Agregar un párrafo: *La fila de `lista_precio` es el candado de la lista y no entra en el orden de arriba: todo comando que escribe versiones o precios de una lista la toma `FOR UPDATE` primero, revalida el estado de la versión y recién escribe; quien asigna una lista a un cliente la lee `FOR SHARE`, de modo que desactivarla y asignarla no se cruzan. Ningún comando de `precios` toca `saldo_cuenta`, `costo_producto` ni `stock_saldo` (ADR-047 punto 19).*

### §10.4 Motor de cálculo compartido

Reemplazar la primera viñeta de implementaciones por: *`backend/app/modules/precios/domain/bruto_de_linea.py` (PRC-22; el motor completo de venta —descuentos, totales, crédito— vivirá en `ventas/domain/calculo.py` desde el change 18a y consumirá esta función por `precios/service.py`) y `frontend/src/domain/precios/brutoDeLinea.ts`; el resto del motor, en `frontend/src/domain/calculo.ts`.* Agregar: *Los casos de PRC-22 están en `shared/fixtures/calculo/prc-22-bruto-de-linea.json` (`"motor": "prc22"`). El cálculo de costo de referencia, margen y redondeo (PRC-11, PRC-12, PRC-14) corre solo en el servidor y no tiene gemela (ADR-047 punto 11, matiza ADR-016).*

## `docs/03-modelo-de-datos.md`

### §8 Precios (reemplazo de la tabla y de las restricciones)

| Tabla | Columnas | Reglas |
| --- | --- | --- |
| `lista_precio` | `id`, `organizacion_id`, `nombre`, `redondeo_multiplo` `numeric(14,2)`, `redondeo_direccion`, `activo`, `creado_en`, `actualizado_en`, `actualizado_por_id` | PRC-01, PRC-14 |
| `regla_margen` | `id`, `organizacion_id`, `lista_id`, `alcance_tipo`, `alcance_id` (nulo si `LISTA`), `tipo`, `valor` `numeric(9,6)`, `activo`, `creado_en`, `actualizado_en`; columnas generadas `producto_id`, `marca_id`, `categoria_id`, `proveedor_id` | PRC-12, PRC-13 |
| `redondeo_categoria` | `id`, `organizacion_id`, `lista_id`, `categoria_id`, `multiplo`, `direccion`, `activo` | PRC-14 |
| `lista_version` | `id`, `organizacion_id`, `lista_id`, `numero`, `estado`, `vigencia_desde` (nulo solo en `BORRADOR`), `vigencia_hasta`, `generado_en`, `version_base_id`, `creado_por_id`, `publicado_por_id`, `publicado_en`, `anulado_por_id`, `anulado_en`, `operation_id` | PRC-02 a PRC-06, PRC-18 |
| `precio_item` | `id`, `organizacion_id`, `version_id`, `producto_id`, `unidades_referencia` `integer`, `costo_informado_id` (nulo), `costo_referencia`, `regla_margen_id`, `tipo_margen`, `valor_margen`, `precio_calculado` (todos nulos en un precio manual sin costo o regla), `precio_final` `numeric(14,2)`, `manual` | PRC-10, PRC-16 |

Restricciones nuevas (además de las existentes): `lista_precio`: `redondeo_multiplo > 0`, catálogo de `redondeo_direccion` y único `(organizacion_id, lower(nombre))`; `regla_margen`: "sin `alcance_id` ⇔ alcance `LISTA`", clave foránea compuesta de cada columna generada (ADR-035) y único parcial por lista y alcance entre las activas; `redondeo_categoria`: único `(organizacion_id, lista_id, categoria_id)`; `lista_version`: `CHECK` de coherencia de publicación y de anulación, único parcial "un borrador por lista", único parcial `(organizacion_id, lista_id, vigencia_desde)` entre las publicadas e índice `(organizacion_id, lista_id, vigencia_desde DESC)`; `precio_item`: `unidades_referencia >= 1`, `precio_final > 0` y clave foránea compuesta de `costo_informado_id`.

Privilegios de `app_runtime`: `SELECT, INSERT, UPDATE` en los maestros; en `lista_version`, `SELECT, INSERT` y `UPDATE` solo de estado, vigencias, publicación, anulación y generación, sin `DELETE`; en `precio_item`, `SELECT, INSERT, UPDATE, DELETE` (el borrador se regenera). La inmutabilidad de una versión publicada (INV-11) se aplica en el servicio, con una única función de escritura de precios y pruebas de integración, concurrencia y propiedades (ADR-047 punto 18).

### §4 `configuracion_organizacion`

`lista_precio_default_id`: *`uuid`, nulo hasta que se define; clave foránea compuesta `(organizacion_id, lista_precio_default_id)` a `lista_precio`. Lo escribe `LISTA_PRECIO_PREDETERMINADA_DEFINIR` (solo una lista activa).*

### §10 `cliente`

`lista_precio_id`: reemplazar la nota "Columna sin FK hasta que el change 13…" por *"Nulo = la lista por defecto de la organización (PRC-20). Clave foránea compuesta `(organizacion_id, lista_precio_id)` a `lista_precio`. Se ofrece en la ficha con las listas activas (ADR-047 punto 12). En `PUT /clientes/{id}` y `CLIENTE_MODIFICAR`, ausente conserva la lista, nulo explícito la quita y un identificador la asigna (ADR-047 punto 29)."*

### §15 Restricciones que la base garantiza

Agregar filas: `PRC-13 | Índice único parcial en regla_margen`; `PRC-18 | Índice único parcial de borrador en lista_version`; `PRC-02 | Índice único parcial de vigencia desde entre las publicadas`. INV-11 sigue en "el resto (se garantiza en los servicios)".

## `docs/04-roadmap-changes.md`

### §7 Hito 3

- **Fila del change 13:** *Listas, reglas de margen con precedencia y unicidad, redondeo, generación de borrador único, precio manual, publicación con vigencia, anulación de versiones programadas, versiones anteriores de solo lectura, lista asignada al cliente y por defecto, resolución de precio (PRC-20). **No incluye el importador `PRECIOS`** (pasa al `13b`).* Invariantes: `INV-11 (versión inmutable), fixtures compartidos PRC-22`.
- **Deuda del change 05 (referencia y precios publicados):** agregar *"**Saldada por el change 13 (ADR-047 punto 2):** `precio_item` congela `unidades_referencia`; cambiar la referencia no altera ninguna versión."*
- **Deuda del change 06 (costo de referencia con varias presentaciones):** agregar *"**Saldada por el change 13 (ADR-047 punto 3):** se mantiene CST-03 y los precios proporcionales; cada precio muestra de qué presentación salió el costo y avisa cuando los costos por presentación difieren."*
- **Deuda del change 10 (importador `PRECIOS`):** reemplazar el texto por *"**Reasignada al change `13b-importacion-de-precios` (D0, ADR-047 punto 1):** el 13 deja el tipo `PRECIOS` rechazado con `TIPO_IMPORTACION_INVALIDO`. El `13b` debe decidir qué crea una planilla de precios (borrador, precios manuales o versión publicada) y resolver las referencias por clave natural (lista por nombre, producto por código); la presentación no se resuelve por nombre porque hay un único precio por producto sobre la referencia (PRC-10)."*
- **Deuda del change 07 (lista asignada del cliente):** agregar *"**Saldada por el change 13 (ADR-047 punto 12):** `cliente.lista_precio_id` tiene su clave foránea compuesta y la ficha la ofrece."*
- **Impacto del change 11b en el 13 (inciso a):** agregar *"**Saldada por el change 13 (ADR-047 punto 4):** los costos calculados con otra regla de IVA se usan y se señalan; no se bloquea la generación ni la publicación."*
- **INV-11:** agregar *"**INV-11 cerrado por el change 13:** una única función de escritura de precios (solo sobre un borrador y con la lista bloqueada) y pruebas que lo citan: integración (`test_inv11_version_publicada_inmutable.py`), concurrencia (`test_precios_concurrencia.py`) y propiedad contra PostgreSQL (`test_precios_inv11.py`)."*

### Deudas nuevas

- **Deuda nominada por el change 13 para el change `13b-importacion-de-precios`:** el importador `PRECIOS` (ver arriba). Va con la misma política de todo o nada (ADR-040) y los mismos códigos de error que la pantalla.
- **Deuda nominada por el change 13 para el change 18a (`venta-online-core`):** consumir `precios/service.py` (`resolver_lista_aplicable`, `resolver_precios`, `calcular_bruto_de_linea`); implementar PRC-21 (`USAR_LISTA_ANTERIOR`, con motivo según configuración), PRC-23 (congelar por línea versión, precio y unidades de referencia) y la observación `LISTA_NO_VIGENTE`; decidir qué hace la venta con `SIN_LISTA_APLICABLE`, `LISTA_SIN_VERSION_VIGENTE` y un producto sin precio en la versión (VTA-10); completar los casos compartidos de §10.4 con descuentos y totales junto con el change 16.
- **Deuda nominada por el change 13 para el change 21 (`pwa-y-bootstrap`):** el bootstrap (SYN-11) debe incluir, de las listas, las versiones vigentes y las anteriores permitidas con sus `unidades_referencia`, sin campos de costo salvo `VER_COSTOS`; leerlas por `precios/service.py`. La lista predeterminada y la asignada de cada cliente ya están en `configuracion_organizacion` y `cliente`.
- **Deuda: redondeo por defecto de la organización (`01` §4, "a definir"):** no hay comando que lo defina; solo precargaría el formulario de una lista nueva. Sin change asignado; se hace si molesta (decisión del usuario, 2026-10-07).
- **Decidido (usuario, Lote 3, 2026-10-06):** un precio manual sobre un producto sin presentación de referencia se rechaza (404); no hay pregunta abierta.
