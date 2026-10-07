# Diseño técnico — 13-listas-de-precios

> **Estado: D0 a D15 APROBADAS con la opción A por el usuario el 2026-10-06 (tarea 0.1).** Las specs y las tareas están escritas con la **opción A (recomendada)** de cada decisión. Cada decisión indica si es **de negocio** o **técnica**. Las que fijan reglas se documentan en **ADR-047** (listas de precios; salda las deudas de los changes 05, 06, 07 y 11b y matiza ADR-010 y ADR-016), que se redacta durante el apply en estado *Propuesto*. Dominio de gobernanza medio (lógica de negocio): se implementa por lotes con revisión,.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **usa sin duplicar**:

- **Costos informados** (change 06): `proveedores/service.py::obtener_costo_informado_vigente(organizacion_id, producto_id, fecha, sesion)` (CST-03, con desempate por `creado_en`), `listar_ultimo_costo_por_presentacion` y la columna `costo_informado.computa_credito_fiscal` (CST-06, ADR-045). Son por producto: no hay lectura por lote.
- **Catálogo** (change 05): `catalogo/service.py::obtener_referencia_de_producto`, `cambiar_referencia` (`PRESENTACION_REFERENCIA_CAMBIAR`), el puerto de verificadores de uso (ADR-023) y `GET /catalogo/productos` (abierto a `GESTIONAR_CATALOGO` y `REGISTRAR_COMPRA`).
- **Clientes** (change 07): `cliente.lista_precio_id` existe como `uuid` nulable **sin clave foránea** y los comandos de la ficha no la aceptan (D2 del change 07).
- **Organización** (change 02): `configuracion_organizacion.lista_precio_default_id`, `redondeo_multiplo` y `redondeo_direccion` existen, nulos y sin comando que los escriba; `motivo_obligatorio_lista = true`.
- **Permisos** `GESTIONAR_LISTAS`, `PUBLICAR_LISTAS` y `USAR_LISTA_ANTERIOR` ya están en el catálogo y en las plantillas (`identidad/domain/permisos.py`, `01` §19).
- **Dinero:** `core/money.py` (`redondear_importe`, `redondear_costo`) y `lib/money.ts`; arnés de fixtures compartidos con discriminador `"motor"` (`cst02`, `cmp02`, `cst11`).
- **Bus** con auditoría automática por comando (ADR-022), `requiere_algun_permiso`, ratchets de rutas, permisos y aislamiento.

No existe el módulo `precios`, ni `ventas`, ni ninguna tabla de `03` §8.

Lo que `docs/` **no** resuelve o resuelve de forma contradictoria:

- **Deuda del change 05 (`04` §7):** `precio_item` no congela las unidades de referencia; cambiar la referencia cambia el significado del precio. → D1.
- **Deuda del change 06 (`04` §7):** CST-03 toma el último costo informado sin importar la presentación; el precio depende del orden de carga. Además, precios no proporcionales. → D2.
- **Deuda del change 11b (ADR-045 punto 10):** costos vigentes calculados con la regla de IVA anterior. → D3.
- **Deuda del change 10 (`04` §7):** importador `PRECIOS`. La deuda pide resolver "presentación por nombre", pero PRC-10 y ADR-010 fijan un único precio por producto sobre la referencia; y nada dice si una planilla de precios crea un borrador, precios manuales o una versión publicada. → D0.
- **PRC-17** no define "productos afectados", ni qué pasa con la primera versión, con un producto sin costo, sin regla o nuevo, ni si un cambio de regla recalcula. `02` §6.5 tiene el comando `LISTA_GENERAR_BORRADOR` (explícito), pero PRC-17 dice "el sistema genera". → D4.
- **`01` §18** (BORRADOR → PUBLICADA → ANULADA) no dice cuántos borradores admite una lista ni cómo se abandona uno; PRC-05 solo anula publicadas. → D5.
- **PRC-02 y PRC-03:** no dicen cuándo se fija la vigencia, si puede ser pasada, ni qué pasa cuando vence la versión de mayor vigencia desde. Tampoco quién escribe `vigencia_hasta` sin romper INV-11. → D6.
- **PRC-16** pide guardar costo y regla en cada precio, pero no dice qué guarda un precio manual ni si se admite sin costo. → D7.
- **PRC-13** da la precedencia, no la unicidad: dos reglas activas del mismo alcance no tienen orden. → D8.
- **PRC-01** dice que la lista tiene regla de redondeo y `01` §4 un "redondeo por defecto" de la organización "a definir"; `03` §8 no tipa las columnas ni dice si son obligatorias. → D9.
- **ADR-016 y `02` §10.4** ubican el bruto de línea en `ventas/domain/calculo.py`, módulo que nace en el 18a; `04` §7 pide los fixtures PRC-22 en el 13. El formato de caso de `02` §10.4 es el del motor completo de venta (descuentos, totales). → D10.
- **`02` §5.3** no lista `clientes ──► precios`; `01` §4 dice que la organización inicial tiene la lista por defecto "General", pero no hay comando para definirla. → D11.
- **`01` §19** no dice quién lee listas y precios, ni si ver el costo de un precio exige `VER_COSTOS`. → D12.
- **`03` §8** no tiene columnas de anulación en `lista_version`, ni `actualizado_en` en los maestros, ni integridad para `regla_margen.alcance_id` (polimórfica, ADR-035). → D13.
- **`02` §7.3** no ubica las filas de `precios` en el orden de bloqueo. → D14.

Para la distribuidora (monotributista, modo A, ADR-045) el precio de lista es el precio final y el costo informado ya incluye el IVA: los ejemplos de este documento lo señalan cuando importa.

## Goals / Non-Goals

**Goals:** un cálculo de precio puro, determinista y probado con los ejemplos de `01` §7; versiones publicadas que no cambian por ningún camino (INV-11); una interfaz de `precios/service.py` que el 18a use sin tocar `precios`; PRC-22 con una sola definición por lenguaje.

**Non-Goals:** motor de cálculo de la venta (descuentos, totales, crédito); que el dispositivo calcule márgenes o redondeos de lista; recálculo automático de precios al informar un costo; importes en `number` en ningún punto.

## Decisions

### D0 — Tamaño del change y el importador de precios · técnica

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** El alcance son cinco tablas, diez comandos, un cálculo puro, el bruto de línea en dos lenguajes y seis pantallas. La deuda del change 10 agrega el importador `PRECIOS`, cuyo contenido no está definido (ver Context). `04` §2 pide changes de hasta tres días.

- **A (recomendada).** Este change en cuatro lotes de apply, **sin** el importador, que pasa a un `13b-importacion-de-precios` posterior: (1) migración, listas, reglas y cálculo puro; (2) borrador, precio manual, publicación y anulación; (3) resolución, PRC-22, lista del cliente y por defecto; (4) pantallas, concurrencia, cobertura, docs y verificación manual. `PRECIOS` sigue rechazado con `TIPO_IMPORTACION_INVALIDO`.
- **B.** Todo en el 13, con un quinto lote para el importador. Obliga a decidir ahora qué crea una planilla de precios.
- **C.** Dividir también el núcleo: `13a` (listas, reglas, borrador, publicación) y `13b` (resolución, PRC-22, clientes).

**Ejemplo.** Con A, al cerrar el lote 2 se informa por API un costo de $6.600 para la caja de Vino A y el borrador muestra $9.500; los precios en papel de la distribuidora se cargan como precios manuales desde la pantalla (unos 100 productos) o esperan al 13b. Con B, el change supera los tres días y no se puede mostrar al cliente hasta resolver la planilla.

### D1 — Cambio de presentación de referencia con precios publicados · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.** Deuda del change 05 (`04` §7): el ADR debe optar entre bloquear o congelar.

**Qué hay que decidir.** `precio_item` guarda un precio "por la referencia" sin decir cuántas unidades tenía. Si la referencia cambia, el mismo precio pasa a leerse sobre otra cantidad.

- **A (recomendada). Congelar `unidades_referencia` en `precio_item`.** Cada precio guarda las unidades de la referencia vigentes al calcularlo. La resolución de precio devuelve precio y unidades juntos, y PRC-22 usa esas unidades. Cambiar la referencia sigue permitido y no altera ninguna versión; el próximo borrador calcula sobre la referencia nueva. Tampoco hace falta registrar un verificador de uso (ADR-023) para precios: las unidades ya quedaron en el precio.
- **B. Bloquear el cambio de referencia** mientras el producto tenga precio en una versión publicada vigente o programada (`REFERENCIA_CON_PRECIOS`), por un puerto que `precios` registra en `catalogo`. También habría que congelar las unidades de la presentación de referencia con un verificador, porque puede no tener costos ni compras.

**Ejemplo.** Vino A, referencia Caja x6, precio publicado $8.600; una botella vale $1.433,33. Se cambia la referencia a Caja x12. A: la versión publicada sigue diciendo "$8.600 por 6 unidades" y la botella sigue a $1.433,33; el próximo borrador calcula la caja x12. B: el cambio se rechaza hasta que deje de haber precios publicados, que en la práctica es nunca. Sin decidir nada: los $8.600 pasarían a leerse por 12 unidades y la botella a $716,67.

### D2 — Costo de referencia con varias presentaciones de compra y precios no proporcionales · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.** Deuda del change 06 (`04` §7). El usuario indicó que se revisa "si es necesario".

**Qué hay que decidir.** Si un proveedor vende dos presentaciones con distinto costo por unidad, CST-03 toma el último costo informado, sin importar la presentación.

- **A (recomendada). Mantener CST-03 y PRC-11 como están**, y hacerlo visible: cada precio del borrador guarda de qué costo informado salió, la pantalla muestra su presentación y avisa cuando los costos vigentes por presentación difieren por unidad. Los precios siguen siendo proporcionales (ADR-010, PRC-10).
- **B. Presentación de compra habitual por producto:** el costo de referencia sale siempre de esa presentación. Agrega un dato al catálogo y un comando.
- **C. El mayor de los costos vigentes por presentación.** Protege el margen, pero encarece el precio cuando la compra habitual es la presentación barata.

**Ejemplo.** Vino A: se informa Caja x6 a $6.000 ($1.000 por botella) y después, con la misma vigencia, Caja x12 a $11.400 ($950 por botella). Markup 30%, redondeo a $100 más cercano. A: costo de referencia 950 × 6 = $5.700, precio $7.410 → **$7.400**, con el aviso "costo tomado de Caja x12; Caja x6 difiere". B con Caja x6 habitual y C: $6.000 → **$7.800**.

### D3 — Costos vigentes calculados con otra regla de IVA · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.** Deuda del change 11b (ADR-045 punto 10).

**Qué hay que decidir.** Tras un cambio de condición frente al IVA quedan costos vigentes calculados con la regla anterior (`computa_credito_fiscal` distinto del actual).

- **A (recomendada). Se usan y se señalan.** El borrador los calcula igual (CST-03 no se altera) y marca cada precio con "costo calculado con otra regla de IVA"; el resultado de `LISTA_GENERAR_BORRADOR` informa cuántos son. Publicar no se bloquea.
- **B. Bloquear la generación** mientras exista alguno (`COSTOS_CON_OTRA_REGLA_IVA`).
- **C. Excluirlos:** esos productos conservan el precio de la versión anterior.

**Ejemplo.** La distribuidora pasa de monotributo a inscripta. Cerveza B tiene vigente Caja x12 a $21.780 (IVA como costo, $1.815 por unidad). Markup 30%, redondeo a $100. A: precio 21.780 × 1,3 = $28.314 → $28.300, con la señal; al informar el costo neto de $18.000 y regenerar, $23.400. B: no se puede generar ninguna lista hasta reinformar todos los costos. Hoy la organización no cambió de condición: la señal no aparece.

### D4 — Qué calcula el borrador · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** PRC-17: "copia la versión vigente y recalcula los productos afectados".

- **A (recomendada). El borrador recalcula todos los productos activos, con una sola regla determinista.** `LISTA_GENERAR_BORRADOR` es un comando explícito (`02` §6.5); informar un costo no genera nada por sí solo. La **versión base** es la `PUBLICADA` no anulada de mayor vigencia desde de la lista (vigente o programada); si no hay, el borrador nace sin base. Para cada producto activo: si en la base (o en el borrador que se regenera, D5) tiene precio manual, se conserva y se evalúa su señal (D7); si no, se calcula con el costo informado vigente a la fecha de negocio de la generación, la regla de margen aplicable (PRC-13) y el redondeo (D9). Un producto sin costo vigente, sin regla aplicable o cuyo redondeo da cero **no recibe precio** y se informa en el resultado con su causa. Cada precio indica si es nuevo, cambia o queda igual respecto de la base. Con las mismas reglas y los mismos costos el resultado es idéntico a copiar la base, que es lo que PRC-17 pide.

> **Adición aprobada por el usuario el 2026-10-06.** Un producto activo sin presentación de referencia tampoco recibe precio (sin ella no hay costo de referencia, PRC-10 y PRC-11) y se informa en el resultado y en la lectura del borrador con la causa `SIN_PRESENTACION_DE_REFERENCIA`, igual que los otros casos sin precio; no queda fuera de la lista en silencio. Un precio manual no puede fijarse sobre ese producto (`LISTA_BORRADOR_PRECIO_FIJAR` responde 404): si eso debe cambiar, es una pregunta abierta.
- **B. Recalcular solo los productos con costo distinto** al `costo_referencia` guardado en la base; el resto se copia tal cual. Un cambio de regla de margen o de redondeo no llega a ningún precio hasta que cambie el costo.
- **C. Generación automática** del borrador en cada `COSTO_INFORMAR`. Invierte la dependencia (`proveedores` → `precios`) y genera borradores que nadie pidió.

**Ejemplo.** Lista General, margen bruto 30%, redondeo a $100 hacia arriba. Versión vigente: Vino A $8.600 (costo de referencia $6.000) y Cerveza B $31.200 (costo de referencia $21.780). Se informa Vino A a $1.100 por botella. A y B: Vino A pasa a 6.600 / 0,7 = $9.428,57 → **$9.500** ("cambia"); Cerveza B queda en $31.200 ("igual"). Si además se subió el margen de la lista a 35%: A recalcula las dos (Vino A 6.600 / 0,65 = $10.153,85 → $10.200); y Cerveza B, 21.780 / 0,65 = $33.507,69 → $33.600; B deja Cerveza B en $31.200, con el margen viejo y sin avisar.

### D5 — Ciclo de vida del borrador · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Cuántos borradores hay y cómo se abandona uno.

- **A (recomendada). Un solo borrador por lista, que se regenera.** `LISTA_GENERAR_BORRADOR` crea el borrador si no existe (con el número siguiente de la lista) o reemplaza los precios del existente, conservando los manuales fijados en él. No hay "descartar": un borrador que no se quiere queda sin publicar y se regenera cuando haga falta. La máquina de `01` §18 no cambia y nada de `lista_version` se borra.
- **B. Descartar con borrado físico** (`LISTA_BORRADOR_DESCARTAR`): el borrador no es una operación confirmada (TR-06), pero exige `DELETE` sobre `lista_version` y deja huecos en la numeración.
- **C. Estado nuevo `DESCARTADA`** y varios borradores por lista. Cambia `01` §18 y PRC-02.

**Ejemplo.** Se genera el borrador n.º 4 de General y se fija a mano Vino A en $9.000. Llega otro costo y se regenera: A conserva el n.º 4, mantiene los $9.000 manuales y recalcula el resto. Con B, si se descarta el n.º 4, el siguiente borrador es el n.º 5 y los $9.000 se pierden.

### D6 — Vigencias · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Cuándo se fija la vigencia y cómo se resuelve PRC-03 sin tocar versiones publicadas.

- **A (recomendada).** (1) La vigencia se fija **al publicar**: `vigencia_desde` es opcional (por defecto, el momento de la publicación) y no puede ser anterior a ese momento (`VIGENCIA_INVALIDA`): nunca se publica hacia atrás. `vigencia_hasta` es opcional y posterior a `vigencia_desde`. Un borrador no tiene vigencia. (2) Dos versiones publicadas de la misma lista no pueden tener la misma `vigencia_desde` (`VIGENCIA_DUPLICADA`). (3) Publicar **no modifica** la versión anterior: deja de ser vigente porque la nueva tiene mayor vigencia desde (PRC-03). (4) PRC-03 se lee filtrando primero: entre las publicadas que ya empezaron y no vencieron, la de mayor vigencia desde. Cuando una versión con `vigencia_hasta` vence, vuelve a regir la anterior. (5) Anular (PRC-05) solo si `vigencia_desde` es posterior al momento de la anulación (`VERSION_YA_VIGENTE` si no), sin motivo de catálogo: PRC-05 y PRC-06 no lo piden.
- **B.** Igual, pero una versión vencida no devuelve la vigencia a la anterior: la lista queda sin versión vigente y no se puede vender con ella hasta publicar otra.
- **C.** Admitir vigencia desde pasada. Cambia hacia atrás qué versión regía para ventas ya registradas con `occurred_at` anterior (PRC-20) y para las offline que aún no sincronizaron.

**Ejemplo.** General: versión 2 desde el 01/09, sin fin. El 28/09 se publica la versión 3 "precios de octubre" desde el 01/10 hasta el 01/11. El 30/09 la 3 está programada y se puede anular; el 02/10 ya no. El 05/11: con A vuelve a regir la versión 2; con B la lista General no tiene precio y ninguna venta resuelve PRC-20.

### D7 — Precio manual · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Cómo se fija, qué guarda y cuándo se señala (PRC-16, PRC-17).

- **A (recomendada).** `LISTA_BORRADOR_PRECIO_FIJAR` (con `GESTIONAR_LISTAS`), solo sobre un borrador: fija el precio final de un producto activo (mayor que cero, dos decimales, **sin** aplicarle el redondeo de la lista) o quita la marca manual, y entonces el precio vuelve a calcularse. El precio manual guarda igual el costo de referencia, la regla aplicable y el precio calculado sin redondear de ese momento, o nulos si el producto no tiene costo o regla: **se admite un precio manual sin costo**, para cargar los precios actuales de un producto antes de tener su costo. La señal "margen menor que el de la regla" (PRC-17) vale cuando el precio manual es menor que el precio calculado sin redondear; sin costo o sin regla no hay señal, sino el aviso "sin costo".
- **B.** Igual, pero un precio manual exige costo vigente y regla aplicable (`PRODUCTO_SIN_COSTO`).
- **C.** El precio manual también pasa por el redondeo de la lista.

**Ejemplo.** Vino A, costo de referencia $6.000, margen bruto 30%: calculado $8.571,43. Se fija a mano $9.000: no hay señal (9.000 ≥ 8.571,43). El costo sube a $6.600 y se regenera: calculado $9.428,57, el manual sigue en $9.000 y aparece la señal "margen menor que el de la regla". Con C, un precio manual de $8.990 en una lista que redondea a $100 quedaría en $9.000.

### D8 — Unicidad y validación de las reglas de margen · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** PRC-13 ordena los alcances, no dos reglas del mismo alcance.

- **A (recomendada). Una sola regla activa por lista y alcance** (`REGLA_DUPLICADA` si ya existe una activa para la misma lista, tipo de alcance y entidad). Las reglas se crean, se modifican (tipo, valor, actividad) y se desactivan; nunca se borran. Modificarlas no toca ninguna versión: rige desde el próximo borrador, y cada precio conserva el tipo y el valor que usó (PRC-16). El valor es una fracción de hasta seis decimales: markup ≥ 0, margen bruto ≥ 0 y < 1 (`MARGEN_INVALIDO`). La entidad del alcance debe existir en la organización (404 si no); puede estar inactiva. Una regla de alcance `LISTA` no es obligatoria: sin regla aplicable el producto no recibe precio (D4).
- **B.** Varias reglas activas por alcance; gana la última creada. El resultado depende del orden de carga.

**Ejemplo.** General tiene "categoría Vinos: margen bruto 30%" y se carga otra "categoría Vinos: markup 40%". A: se rechaza; hay que modificar la existente. B: rigen las dos y la segunda pisa a la primera sin que la pantalla lo diga.

### D9 — Redondeo · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Obligatoriedad, cascada y valores (PRC-01, PRC-14, PRC-15, `01` §4).

- **A (recomendada).** (1) La lista **siempre** tiene redondeo (PRC-01): múltiplo mayor que cero con hasta dos decimales y dirección `ARRIBA`, `CERCANO` o `ABAJO`. Un múltiplo de $0,01 equivale a no redondear más que a centavos. (2) Cascada: sobrescritura de la categoría del producto si está activa, si no la de la lista. El redondeo por defecto de la organización solo precarga el formulario de una lista nueva cuando está definido; este change no agrega un comando para definirlo (sigue "a definir", `01` §4). (3) El redondeo se aplica al precio calculado **sin redondear** (TR-03); en `CERCANO` el punto medio sube (PRC-14). (4) Si el resultado es cero (dirección `ABAJO` con un precio menor que el múltiplo), el producto no recibe precio y se informa (D4). (5) En modos A y B se redondea el precio neto; con modo C la generación se rechaza (`MODO_IMPOSITIVO_NO_SOPORTADO`, PRC-15: etapa 4).
- **B.** Redondeo de la lista opcional, con cascada categoría → lista → organización; sin ninguno, el precio final es el calculado a dos decimales.

**Ejemplo.** Vino A, calculado $8.571,43, múltiplo $100: arriba $8.600, más cercano $8.600, abajo $8.500 (`01` §7.2). Un calculado de $8.550,00 con "más cercano" da $8.600. Con B y sin ningún redondeo definido, el precio sería $8.571,43.

### D10 — Dónde vive PRC-22 y qué fixtures se comparten · técnica · ADR-047 (matiza ADR-016)

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** `04` §7 pide los fixtures PRC-22 en este change; ADR-016 ubica el cálculo en `ventas`, que no existe.

- **A (recomendada).** El bruto de línea es una función pura de `precios/domain/`, expuesta por `precios/service.py` (el motor de `ventas` la usará en el 18a, `ventas ──► precios`), y su gemela en `frontend/src/domain/precios/`. Casos en `shared/fixtures/calculo/prc-22-bruto-de-linea.json` con `"motor": "prc22"` (mismo patrón que `cst02` y `cmp02`), ejecutados por pytest y Vitest. El formato de `02` §10.4 con descuentos y totales lo completan el 16 y el 18a. El cálculo de costo de referencia, margen y redondeo (PRC-11, PRC-12, PRC-14) corre **solo en el servidor** y se prueba con unitarias y propiedades en Python: el dispositivo no genera listas (ADR-016 cubre lo que se calcula sin conexión).
- **B.** Además, casos compartidos de PRC-11, PRC-12 y PRC-14 y una segunda implementación en TypeScript, para previsualizar el efecto de una regla en la pantalla.
- **C.** Crear ya `ventas/domain/calculo.py` con solo PRC-22. `precios` tendría que depender de `ventas`, al revés de `02` §5.3.

**Ejemplo.** Caso `PRC22-una-unidad`: precio de referencia `"8600.00"`, unidades de referencia 6, cantidad base 1 → `"1433.33"`. Con A, ese caso lo corren las dos suites y es lo único que el teléfono necesita. Con B se duplican además unas quince reglas de margen y redondeo que el teléfono nunca ejecuta.

### D11 — Lista del cliente, lista por defecto y alcance de la resolución · de negocio y técnica · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.** Incluye la deuda del change 07 (D2).

**Qué hay que decidir.** Cómo se asignan las listas y qué entrega este change de PRC-20.

- **A (recomendada).**
  1. **Lista asignada (CLI-01):** clave foránea compuesta `cliente (organizacion_id, lista_precio_id) → lista_precio`. `CLIENTE_CREAR` y `CLIENTE_MODIFICAR` aceptan `lista_precio_id` (nulo = la de la organización); una lista inexistente o ajena responde 404 y una inactiva `LISTA_INACTIVA`. Dependencia nueva `clientes ──► precios`, solo por `service.py` (no hay ciclo: `precios` no depende de `clientes`).
  2. **Lista por defecto (`01` §4):** `LISTA_PRECIO_PREDETERMINADA_DEFINIR`, con `ADMIN_CONFIGURACION` (mismo criterio que `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR`), escribe `configuracion_organizacion.lista_precio_default_id` por `identidad/service.py`, con clave foránea compuesta. Solo admite una lista activa. **No se siembra la lista "General":** crearla exige un redondeo que `01` §4 deja "a definir"; se crea desde la pantalla.
  3. **Lista en uso:** una lista que es la predeterminada, o que está asignada a algún cliente no inactivo, no se desactiva (`LISTA_EN_USO`; mismo criterio que ADR-024 y ADR-026). `clientes` registra en `precios` un verificador de uso, como en ADR-023.
  4. **Resolución (PRC-20):** `precios/service.py` entrega la lista aplicable (la asignada o la predeterminada; `SIN_LISTA_APLICABLE` si no hay ninguna activa), la versión vigente a un momento (`LISTA_SIN_VERSION_VIGENTE`) y los precios de una versión con sus unidades de referencia. Lectura `GET /api/v1/precios/listas/{id}/vigente?momento=`. **Quedan para el 18a:** usar otra lista o una versión anterior con `USAR_LISTA_ANTERIOR` y motivo (PRC-21), congelar por línea (PRC-23) y la observación `LISTA_NO_VIGENTE`.
- **B.** Igual, sembrando "General" con múltiplo $0,01 como predeterminada en la organización inicial. Inventa un redondeo.
- **C.** Sin dependencia `clientes ──► precios`: la clave foránea garantiza la existencia y no se valida que la lista esté activa.

**Ejemplo.** "Kiosco La Esquina" no tiene lista: compra con General. "Kiosco El Faro" tiene "Mayorista". Si se intenta desactivar Mayorista: A lo rechaza con `LISTA_EN_USO` hasta reasignar a El Faro; con C se desactiva y El Faro queda apuntando a una lista inactiva, que el 18a tendría que resolver en la venta.

### D12 — Permisos de lectura y visibilidad de costos · de negocio · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** `01` §19 solo cubre gestionar y publicar.

- **A (recomendada). Sin permisos nuevos.** Con `GESTIONAR_LISTAS`: listas, reglas, redondeos, generar borrador y fijar precios manuales. Con `PUBLICAR_LISTAS`: publicar y anular. Lecturas de listas, reglas, versiones y precios: cualquiera de los dos. Los campos de costo de un precio (costo de referencia, margen, precio calculado) solo se devuelven con `VER_COSTOS`; sin él van en nulo (mismo criterio que el kardex, ADR-036); las señales sí se ven. `GET /precios/listas/opciones` (id y nombre de las activas) también con `GESTIONAR_CLIENTES` y `ADMIN_CONFIGURACION`. Las lecturas que alimentan los selectores de alcance (productos, categorías, marcas, opciones de proveedor) se abren, solo en lectura, a `GESTIONAR_LISTAS` (como ADR-043 con `REGISTRAR_COMPRA`).
- **B.** Todo lo anterior exige además `VER_COSTOS`: quien no ve costos no entra a listas.

**Ejemplo.** Un rol "Comercial" con `GESTIONAR_LISTAS` y sin `VER_COSTOS` abre el borrador de General. A: ve Vino A a $9.500 con la señal de margen, sin el costo de $6.600 ni el 30%. B: no puede abrir la pantalla.

### D13 — Modelo de datos, INV-11 y migración · técnica · ADR-047

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Qué se agrega a `03` §8 y en qué capa se garantiza INV-11.

- **A (recomendada). Una revisión de Alembic con las cinco tablas de `03` §8 y estos agregados:**
  1. `lista_precio`: `redondeo_multiplo numeric(14,2) NOT NULL CHECK (> 0)`, `redondeo_direccion` con `CHECK` de catálogo, `actualizado_en`, `actualizado_por_id`, único `(organizacion_id, lower(nombre))`.
  2. `regla_margen`: `valor numeric(9,6)` con el `CHECK` de `03` §8; `CHECK` "sin `alcance_id` ⇔ alcance `LISTA`"; columnas generadas `producto_id`, `marca_id`, `categoria_id` y `proveedor_id` con clave foránea compuesta cada una (ADR-035); único parcial por lista y alcance entre las activas (D8); `actualizado_en`.
  3. `redondeo_categoria`: `multiplo` y `direccion` como en la lista, `activo`, único `(organizacion_id, lista_id, categoria_id)`.
  4. `lista_version`: `vigencia_desde` nulable solo en `BORRADOR`; `CHECK` de coherencia de publicación y de anulación; `anulado_en`, `anulado_por_id`, `generado_en`, `version_base_id`; único parcial "un borrador por lista" (D5) y único parcial `(organizacion_id, lista_id, vigencia_desde)` entre las publicadas (D6); índice de resolución `(organizacion_id, lista_id, vigencia_desde DESC)`.
  5. `precio_item`: `unidades_referencia integer NOT NULL CHECK (>= 1)` (D1); `costo_informado_id` nulable con clave foránea compuesta (D2, D3); `costo_referencia`, `regla_margen_id`, `tipo_margen`, `valor_margen` y `precio_calculado` nulables (D7); `precio_final numeric(14,2) CHECK (> 0)`; el único de `03` §8.
  6. Claves foráneas compuestas de `cliente.lista_precio_id` y de `configuracion_organizacion.lista_precio_default_id`; la migración aborta con mensaje claro si encuentra un valor que no apunta a ninguna lista.
  7. Privilegios de `app_runtime`: `SELECT, INSERT, UPDATE` en los tres maestros; en `lista_version`, `SELECT, INSERT` y `UPDATE` solo de estado, vigencias, publicación, anulación y generación, sin `DELETE`; en `precio_item`, `SELECT, INSERT, UPDATE, DELETE` (el borrador se regenera).
  **INV-11 se garantiza en el servicio**, como dice `03` §8: toda escritura sobre precios pasa por una única función que exige versión `BORRADOR` con la lista bloqueada (D14), más pruebas de integración y de concurrencia que citan INV-11.
- **B.** Lo mismo, más un disparador en la base que rechaza `UPDATE` y `DELETE` sobre `precio_item` de una versión no `BORRADOR` y cualquier cambio de una versión publicada que no sea su anulación. Sería el primer disparador del proyecto y contradice la letra de `03` §8.
- **C.** Solo las columnas literales de `03` §8. Deja sin resolver D1, D5, D6 y D7.

**Ejemplo.** Un defecto futuro en el servicio intenta cambiar Vino A de $8.600 a $9.000 en la versión 3, ya publicada. A: lo detienen la función única de escritura y sus pruebas; un `UPDATE` directo con el usuario de aplicación pasaría. B: la base lo rechaza también en ese caso.

`downgrade`: quita las dos claves foráneas y borra las cinco tablas; pierde listas, reglas y versiones por diseño, y una prueba lo deja escrito. `cliente.lista_precio_id` y `lista_precio_default_id` vuelven a nulo.

### D14 — Bloqueos y concurrencia · técnica · ADR-047 (precisa `02` §7.3)

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Cómo se serializan generar, fijar, publicar y anular.

- **A (recomendada). La fila de `lista_precio` es el candado de la lista.** Todo comando que escribe versiones o precios de una lista toma primero `lista_precio FOR UPDATE`, revalida el estado de la versión y recién entonces escribe; el número de versión se asigna bajo ese candado, con el índice único como garantía final. Ningún comando de `precios` toca `saldo_cuenta`, `costo_producto` ni `stock_saldo`, así que no entra en el orden de `02` §7.3. Costos y catálogo se leen sin bloquear: el borrador es una foto recalculable. `LISTA_PRECIO_PREDETERMINADA_DEFINIR` y la desactivación de una lista toman el mismo candado.
- **B.** Sin candado explícito: solo los índices únicos. Dos regeneraciones simultáneas del mismo borrador pueden mezclar precios de dos fotos distintas.

**Ejemplo.** Un usuario publica el borrador n.º 4 mientras otro le fija Vino A en $9.000. A: uno espera al otro; o el precio manual entra antes y se publica con $9.000, o llega después y se rechaza con `VERSION_NO_ES_BORRADOR`. Nunca cambia un precio ya publicado (INV-11).

Idempotencia: la reserva del bus (INV-06) cubre los diez comandos.

### D15 — Alcance de las pantallas · de negocio

> **APROBADA (opción A) por el usuario el 2026-10-06.**

**Qué hay que decidir.** Qué se ve en `/admin/precios`.

- **A (recomendada).** Área "Listas de precios": (1) listado de listas con su versión vigente y si tienen borrador; (2) alta y edición de lista con redondeo; (3) detalle de lista con reglas de margen (alta, edición, fórmula visible, PRC-12), redondeos por categoría y versiones con su estado derivado (PRC-03); (4) borrador: tabla de precios con precio de la versión base, precio nuevo, costo y regla (según `VER_COSTOS`), señales, productos sin precio con su causa, precio manual, "Regenerar" y "Publicar" con vigencia; (5) versión publicada de solo lectura, con "Anular" si está programada; (6) precio por presentación mostrado con PRC-22. Además, selector de lista en la ficha del cliente y de lista predeterminada en Configuración.
- **B.** Igual, sin la comparación con la versión base ni el precio por presentación.

**Ejemplo.** Punto de validación de `04` §7: con A el cliente ve "Vino A: $8.600 → $9.500 (caja x6), botella $1.583,33" al lado del costo nuevo. Con B ve solo $9.500.

## Enfoque técnico (con la opción A de cada decisión)

- **Dominio** (`precios/domain/`, puro): `resolver_regla` (PRC-13), `calcular_precio` (PRC-11, PRC-12, PRC-14, con `Decimal` exacto y un solo redondeo final por `core/money.py`), `aplicar_redondeo`, `estado_derivado` y `version_vigente` (PRC-03), reglas de transición (PRC-04, PRC-05), señales (D3, D7) y `calcular_bruto_de_linea` (PRC-22). Errores como `DomainError` con código estable.
- **Servicio** `precios/service.py`: interfaz pública para `clientes`, `ventas` (18a) e `importacion` (13b).
- **Lecturas nuevas en otros módulos, solo en `service.py`:** `catalogo` entrega los productos activos con referencia, categoría, marca y proveedor en una consulta; `proveedores` entrega los costos informados vigentes de varios productos a una fecha en una consulta (misma regla que `obtener_costo_informado_vigente`). Evitan una consulta por producto.
- **Comandos** (`ONLINE`, v1): `LISTA_PRECIO_CREAR`, `LISTA_PRECIO_MODIFICAR`, `REGLA_MARGEN_CREAR`, `REGLA_MARGEN_MODIFICAR`, `REDONDEO_CATEGORIA_DEFINIR`, `LISTA_GENERAR_BORRADOR`, `LISTA_BORRADOR_PRECIO_FIJAR`, `LISTA_PUBLICAR`, `LISTA_ANULAR_VERSION`, `LISTA_PRECIO_PREDETERMINADA_DEFINIR`.
- **API** bajo `/api/v1/precios/`; importes, costos y porcentajes como string; cursor en los listados de precios.
- **Dependencias** (`02` §5.3): `precios ──► catalogo, proveedores, identidad` (ya previstas) y la nueva `clientes ──► precios`; contratos de import-linter para `precios`.
- **Frontend:** `domain/precios/` (bruto de línea, esquemas Zod, texto de la fórmula), `features/precios/` (hooks y `Operation-Id` por contenido), `areas/admin/precios/` (pantallas sin lógica de negocio).

## Risks / Trade-offs

- [INV-11 queda solo en el servicio y `app_runtime` puede modificar `precio_item`] → función única de escritura, pruebas que la citan y D13-B disponible si el usuario prefiere la garantía en la base.
- [El cálculo de precio diverge de los ejemplos de `01` §7.2] → los ejemplos son las primeras pruebas, antes del código; propiedad Hypothesis sobre el redondeo.
- [PRC-22 queda en `precios` y ADR-016 lo nombra en `ventas`] → ADR-047 lo matiza; el 18a lo consume por `precios/service.py`.
- [Generar el borrador con muchos productos hace muchas consultas] → lecturas por lote en `catalogo` y `proveedores`.
- [Un borrador viejo se publica con costos desactualizados] → la pantalla muestra cuándo se generó y ofrece "Regenerar"; publicar no recalcula.
- [La migración encuentra un `lista_precio_id` colgado] → aborta con mensaje; prueba de migración con ese dato sembrado.
- [`downgrade` pierde listas y versiones] → aceptado y probado como aserción explícita.
- [Sin importador, cargar los precios actuales es manual] → D0; unos 100 productos.

## Migration Plan

Una revisión de Alembic (D13), aplicable con datos. Despliegue: `alembic upgrade head`; sin dependencias nuevas previstas, así que no hace falta reconstruir imágenes salvo que el apply agregue alguna. Después del despliegue: crear la lista "General", sus reglas y definirla como predeterminada (D11). Rollback: `alembic downgrade -1`, con la pérdida descripta en D13.
