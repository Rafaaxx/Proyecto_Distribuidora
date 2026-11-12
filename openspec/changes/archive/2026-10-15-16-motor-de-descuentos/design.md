# Diseño técnico — 16-motor-de-descuentos

> **Estado: D0 a D20 APROBADAS por el usuario el 2026-10-13.** D0 a D10 y D12 a D20: **opción A**, sin cambios. D11: **A+B combinadas** (un porcentaje general por venta y, opcionalmente, uno propio por línea, que lo reemplaza en esa línea), con el tope de D12 comparado contra el mayor porcentaje manual entre las líneas. Proposal, specs y tareas están escritos con lo aprobado. Cada decisión conserva su contexto, las opciones descartadas y un ejemplo.
>
> **Los dos subpuntos que nacieron de propagar D11 también están APROBADOS por el usuario (2026-10-13), los dos con la opción A: D11.1** (el porcentaje propio de una línea no puede ser 0: mismo dominio que el general) **y D11.2** (un motivo por venta, que el 18b copia a cada descuento `MANUAL`). El usuario confirmó además la lectura literal del máximo: un general reemplazado en todas las líneas no cuenta. **No queda ninguna decisión abierta;** la tarea 0.1 está cerrada. **Confirmado además por el usuario el 2026-10-15 (D12, evaluación del tope):** un motivo en blanco cuenta como ausente; un usuario inactivo se evalúa sin permisos; el permiso propio `AUTORIZAR_DESCUENTO` se resuelve primero aunque se indique autorizador (`PERMISO_PROPIO`).
>
> Todo se documenta en **ADR-050** (estado *Propuesto* durante el apply, último lote). Precisaría ADR-004 (dónde vive la gemela de TypeScript, desempates, importe fijo, forma del manual) y ADR-016 (el motor de descuentos no vive en `ventas/domain/calculo.py`), y enmendaría `02` §5.3 y §10.4 y `03` §11.
>
> **Gobernanza por dominio.** **CRÍTICO** (análisis y aprobación explícita antes de escribir; lote propio): **D12** (quién autoriza un descuento sobre el tope) y **D13** (tope por rol: roles y permisos de `identidad`). **ALTO** (se propone y se espera revisión): **D18** (qué permiso abre cada lectura). El resto es **MEDIO** (lógica de negocio: D1, D2, D5 a D11, D14 a D16) o **BAJO** (técnicas sin regla de negocio: D0, D3, D4, D17, D19, D20).

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Permisos** (change 03): `GESTIONAR_DESCUENTOS` (solo Administrador), `DESCUENTO_MANUAL` (Administrador, Supervisor, Vendedor) y `AUTORIZAR_DESCUENTO` (Administrador, Supervisor) están en el catálogo y en las plantillas.
- **Topes** (change 03): `rol.tope_descuento numeric(9,6)` y `usuario.tope_descuento_override`, con sus `CHECK` de 0 a 1; el dominio de `identidad` ya tiene `resolver_tope_descuento_aplicable` y `validar_tope_descuento` (error `IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO`). Las plantillas nacen con tope `1.000000` para el Administrador y **`0` para las demás**, incluidas Supervisor y Vendedor. **Ningún comando cambia el tope de un rol ni el de un usuario**, y no hay lectura de roles (las rutas de roles son solo `PUT /roles/{id}/permisos`). `GET /yo` y el token no exponen el tope, a propósito.
- **Configuración** (change 02): `configuracion_organizacion.descuento_manual_habilitado` (sembrado en verdadero) y `motivo_obligatorio_descuento` (nulo: "a definir"). Ningún comando los cambia. El ámbito de motivo `DESCUENTO_MANUAL` está en el `CHECK` y **no tiene motivos sembrados**.
- **PIN de autorización** (change 03, ADR-011, ADR-019): se define y se rota; **no existe** una función que verifique un PIN en una operación.
- **Observación `DESCUENTO_DIFIERE`**: está en el catálogo de `sync` y nada la emite.
- **Cálculo compartido** (changes 01b y 13): arnés `shared/fixtures/calculo/*.json` con casos `{id, reglas, entrada, salida_esperada}`, donde `entrada.motor` elige la función (`"prc22"`, `"cst02"`, …); una prueba por motor en `backend/tests/fixtures_compartidos/` y otra en `frontend/tests/unit/calculo/`. PRC-22 vive en `precios/domain/bruto_de_linea.py` y `frontend/src/domain/precios/brutoDeLinea.ts`.
- **Listas** (change 13): cada precio guarda `unidades_referencia`; `precios/service.py` ya entrega precio y unidades. La regla de margen guarda su alcance como `alcance_tipo` + `alcance_id` con columnas generadas y claves foráneas compuestas (ADR-035, ADR-047).
- **No existen:** el módulo `descuentos`, las tablas `regla_descuento` y `regla_descuento_alcance`, el módulo `ventas`, ni `venta_linea_descuento`.

Lo que `docs/` **no** resuelve, y las contradicciones entre documentos (cada punto es una decisión abierta):

- **Contradicción de alcance.** `00` §6.1 pone en la etapa 1 "una o dos reglas de descuento por volumen" y §6.2 deja para la etapa 2 "reglas por categoría, marca, cliente, promociones temporales, acumulabilidad completa". `01` DSC-01 a DSC-05 (todas etapa 1), `03` §11, la fila 16 de `04` §8 y ADR-004 incluyen alcance por producto, categoría o marca, vigencia y acumulables. → D1.
- **Contradicción de ubicación.** ADR-004 pone el motor en `modules/descuentos/domain/` y `domain/calculo.ts`; ADR-016, en `ventas/domain/calculo.py`; `02` §10.4 (enmendado por ADR-047), en `ventas/domain/calculo.py` "desde el change 18a"; `02` §5.1 dice que `descuentos` tiene "reglas y motor". → D3.
- La fila 16 de `04` dice "descuento manual con tope y autorización" y la del 18b, "descuentos automáticos y manuales en la venta … PIN de supervisor". No dice dónde se corta. → D2.
- El ejemplo de caso de `02` §10.4 es una venta completa (con IVA y total); el arnés real separa por motor. → D4.
- DSC-03 no dice con qué unidades se calculan las cajas equivalentes de una línea ni si la medida se redondea. → D5. Tampoco si la condición de una acumulable mira el bruto o lo ya descontado. → D6.
- DSC-05 dice "la de mayor beneficio total, con desempate por prioridad": no dice si el ganador es uno por venta o uno por línea, qué número de prioridad gana, ni qué pasa si también empata la prioridad. → D7, D8.
- DSC-04 reparte el importe fijo "en proporción a su bruto" y DSC-05 aplica las acumulables "sobre el resultado anterior": no dicen cuál manda cuando el importe fijo es acumulable, ni qué pasa si supera lo que queda, ni cómo se desempata "la línea de mayor importe". → D9, D10.
- DSC-06 no dice si el descuento manual es por venta o por línea, ni si puede ser un importe; tampoco contra qué se compara el tope ni hasta cuánto puede autorizar quien tiene `AUTORIZAR_DESCUENTO`. → D11, D12. DSC-08 guarda "motivo y autorizador" en cada línea y no dice si el motivo se elige una vez por venta o línea por línea. → D11.2.
- `01` §19 dice que la organización puede modificar los topes; no hay comando. → D13. `01` §4 deja "a definir" el motivo obligatorio. → D14.
- `01` §18 da la máquina `BORRADOR → ACTIVA ↔ PAUSADA` y no dice si una regla activada se edita. → D15. `03` §11 lista `vigencia_desde` y `vigencia_hasta` sin tipo ni extremos. → D16.
- `03` §11 lista `accion_valor` sin tipo; `CLAUDE.md` §4 exige `numeric(9,6)` para porcentajes y `numeric(14,2)` para importes. → D17.
- `01` §19 no dice quién lee las reglas. → D18. `02` §5.3 no lista dependencias de `descuentos`. → D19.

## Goals / Non-Goals

**Goals:** un motor de descuentos puro, determinista e idéntico en Python y TypeScript, probado con casos compartidos y con propiedades; reglas administrables con su máquina de estados; la decisión de tope y autorización lista para que la venta la use; un servicio (`descuentos/service.py`) que el 18b y el 21 consumen sin tocar el módulo.

**Non-Goals:** nada de la venta (persistir descuentos por línea, recalcular y comparar, `DESCUENTO_DIFIERE`, verificar el PIN, auditar el descuento manual); totales e IVA; bootstrap; condiciones, medidas o acciones fuera de DSC-02 a DSC-04; simulador de reglas (D20); estadísticas de uso de reglas.

## Decisions

### D0 — Tamaño del change y lotes · técnica · BAJO · **APROBADA 2026-10-13: opción A**

**Contexto.** `04` §2 pide entre medio día y tres días. El alcance suma dos motores gemelos con sus casos compartidos y propiedades, dos tablas, cuatro comandos, lecturas, la evaluación del manual, un comando en `identidad` y pantallas. No entra en tres días. Los changes 14 y 15 fueron excepciones aceptadas con cuatro lotes.

- **A (recomendada). Un change en cuatro lotes**, sin frenar entre lotes (el usuario revisa con todo implementado), salvo las confirmaciones de alcance de las piezas críticas y altas:
  1. **Lote 1:** casos compartidos y motor puro en Python y TypeScript (condición, porcentaje, importe fijo, orden de resolución, aplicación del manual) con propiedades. No toca la base.
  2. **Lote 2:** migración, modelos, dominio de reglas, los cuatro comandos, consultas (D18, ALTO), servicio para el 18b y el 21, ratchets.
  3. **Lote 3 (CRÍTICO):** evaluación del descuento manual con tope y autorización (D12) y tope por rol (D13). Es autocontenido: si se alarga, se corta a un `16b` sin rehacer nada.
  4. **Lote 4:** pantallas, concurrencia, cobertura, ADR-050, propuesta de docs y verificación manual.
  Consecuencia: vuelve a superar `04` §2 y se anota la excepción.
- **B. Dividir en `16a-motor-de-descuentos` (lotes 1, 2 y 4) y `16b-descuento-manual` (lote 3 y su pantalla).** El 16a queda cerca del tope y la pieza crítica se revisa sola. Consecuencia: dos proposals, `04` §4 suma una fila y el 18b pasa a depender de los dos.
- **C. Dividir en `16a` (motor puro y casos compartidos) y `16b` (reglas, manual y pantallas).** Consecuencia: el 16a se archiva sin nada que probar en el navegador (`04` §2.1 punto 5).

**Ejemplo.** Al cerrar el lote 1, los casos compartidos corren en verde en pytest y en Vitest sin que exista ninguna tabla. Al cerrar el lote 2, un Administrador crea y activa por API la regla "cajas equivalentes ≥ 20 → 5%".

### D1 — Qué reglas entran, frente a `00` §6 · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** Es la contradicción de alcance de arriba, y `04` §14 nombra el riesgo: "el motor de descuentos crece más de lo necesario … volver a las reglas reales; lo demás es etapa 2". Las reglas reales del cliente no están escritas en `docs/`: ADR-004 solo dice que "ya negocia descuentos por volumen (cajas, unidades o importe)". **El usuario tiene que confirmar qué usa el cliente.**

- **A (recomendada). Exactamente lo que `01` DSC-01 a DSC-04 marca como etapa 1, y nada más:** dos tipos (`VOLUMEN_OPERACION`, `VOLUMEN_ALCANCE`), alcance por producto, categoría o marca, tres medidas, dos operadores, dos acciones, prioridad, acumulable y vigencia. Queda fuera todo lo de DSC-10 y de `00` §6.2 que `01` no trae: reglas por cliente o segmento, fidelización, precio especial, bonificación en unidades, margen mínimo, tramos escalonados, combinaciones de condiciones. Consecuencia: `00` §6.1 y §6.2 se precisan en `propuesta-docs.md` para que no contradigan a `01`. Se recomienda porque `CLAUDE.md` §8 prohíbe simplificar una regla por cuenta propia, porque `01`, `03`, `04` y ADR-004 coinciden, y porque el costo extra frente a B es chico: el motor solo compara tres identificadores por línea.
- **B. Recortar a la lectura de `00` §6:** solo `VOLUMEN_OPERACION` y `VOLUMEN_ALCANCE` por producto, sin categoría ni marca, y sin reglas acumulables (el indicador existe y se rechaza en verdadero). Consecuencia: menos pantalla y menos casos; se enmiendan DSC-02 y DSC-05 (pasan a "etapa 2" en parte) y `03` §11 conserva las columnas.
- **C. Mínimo:** solo `VOLUMEN_OPERACION` con porcentaje. Consecuencia: cubre "una o dos reglas por volumen" del criterio 5 de `00` §9; deja sin implementar DSC-02 y DSC-04 (importe fijo), que `01` marca etapa 1.

**Ejemplo.** Con A, el Administrador puede cargar "10 cajas o más de la marca Bodega Norte → 8%". Con B solo podría cargarla producto por producto. Con C no existe.

### D2 — Frontera con el change 18b · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** No existe la venta. La fila 16 de `04` nombra el "descuento manual con tope y autorización"; la del 18b, "descuentos automáticos y manuales en la venta … PIN de supervisor".

- **A (recomendada). El 16 entrega el cálculo y la decisión; el 18b, el efecto.** En el 16: aplicación del manual como paso 5 del motor; evaluación pura de tope y autorización, que recibe al autorizador **ya identificado** (no verifica PIN); servicio que resuelve configuración, permisos y tope. En el 18b: verificar el PIN (con conexión y sin ella), persistir `venta_linea_descuento` (DSC-08), recalcular y rechazar o marcar `DESCUENTO_DIFIERE` (DSC-09), auditar el descuento manual y su autorización (AUD-01), validar el motivo y decidir qué pasa sin conexión (SYN-05, SYN-10). Consecuencia: nada del 16 escribe una autorización; el tope se puede definir, pero se ejerce recién en el 18b.
- **B. El 16 solo trae descuentos automáticos; todo lo manual pasa al 18b.** Consecuencia: contradice la fila 16 y carga más al 18b, que ya suma crédito y PIN.
- **C. El 16 trae también la verificación del PIN con conexión y un comando "autorizar descuento".** Consecuencia: una autorización que no cuelga de ninguna venta, sin entidad que auditar; habría que rehacerla en el 18b.

**Ejemplo.** Con A, el 18b llama `evaluar_descuento_manual` con el vendedor, el 10% (el mayor porcentaje manual de la venta, D11) y la Supervisora cuyo PIN ya verificó, y recibe "aceptado, `AUTORIZADO_POR_SUPERVISOR`, tope aplicado 5%" para guardar y auditar.

### D3 — Dónde vive el motor · técnica · BAJO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** Es la contradicción de ubicación de arriba. ADR-047 punto 11 ya matizó ADR-016 al dejar PRC-22 en `precios`.

- **A (recomendada). Cada regla de cálculo vive en el módulo dueño de la regla.** Python en `descuentos/domain/` (ADR-004, `02` §5.1), expuesto por `descuentos/service.py`; TypeScript en `frontend/src/domain/descuentos/` (mismo criterio que `domain/precios/brutoDeLinea.ts`). `ventas/domain/calculo.py` y `domain/calculo.ts` nacen en el 18a como orquestadores: bruto (por `precios`), descuentos (por `descuentos`), totales. Consecuencia: precisa ADR-016 y `02` §10.4; `ventas ──► descuentos` ya está en `02` §5.3.
- **B. Literal de ADR-016: `ventas/domain/calculo.py`.** Consecuencia: crea el módulo `ventas` dos changes antes de tiempo y deja a `descuentos` sin su motor, contra ADR-004 y `02` §5.1.
- **C. Python en `descuentos/domain/` y TypeScript en un único `domain/calculo.ts`** (literal de ADR-004). Consecuencia: el archivo crece con crédito y totales en el 18a y 18b, y rompe la simetría de carpetas que hoy tiene `precios`.

### D4 — Formato de los casos compartidos · técnica · BAJO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** `02` §10.4 muestra un caso de venta completa; el arnés real elige la función con `entrada.motor`.

- **A (recomendada). Dos archivos por motor.** `shared/fixtures/calculo/dsc-05-descuentos.json` (`"motor": "dsc05"`): la entrada trae las líneas con su `bruto` ya calculado, `cantidad_base`, `unidades_referencia`, `producto_id`, `categoria_id`, `marca_id`, las `reglas_descuento` aplicables y el descuento manual en dos lugares (D11): `descuento_manual_general` a nivel de la venta (porcentaje o nulo) y, en cada línea, `descuento_manual` (porcentaje propio o nulo); la salida, por línea, `descuentos` (origen, regla, porcentaje, importe), `descuento_total` y `neto`, y a nivel de la venta `porcentaje_manual_maximo` (el mayor porcentaje manual que quedó aplicado en alguna línea, o nulo si ninguna lleva manual). `dsc-06-descuento-manual.json` (`"motor": "dsc06"`): la entrada trae habilitado, permisos, tope, `porcentaje_maximo` (ese mismo máximo, que es lo que se compara contra el tope: D12), motivo y autorizador; la salida, la resolución o el código de error. Sin IVA ni total: son VTA-04 y los agrega el 18a sobre este mismo formato (deuda ya nominada por el 13). Consecuencia: el caso de `02` §10.4 queda como el formato del 18a.
- **B. Formato completo de `02` §10.4** (precio de referencia, IVA, total). Consecuencia: el motor de descuentos tendría que calcular el bruto (duplicando PRC-22) y el total (VTA-04, del 18a).
- **C. Un solo archivo para todo.** Consecuencia: mezcla dos funciones con entradas distintas bajo un mismo `motor`.

### D5 — Cajas equivalentes y comparación exacta · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** El glosario define cajas equivalentes como cantidad base dividida por las unidades de la presentación de referencia. Desde ADR-047 el precio guarda las unidades de referencia con que se calculó, que pueden diferir de las del catálogo de hoy.

- **A (recomendada). Las unidades de referencia de la línea**, es decir, las guardadas en el precio con el que se calculó su bruto (PRC-10, PRC-22). La medida es la suma exacta, línea por línea, de `cantidad base / unidades de referencia`, **sin redondear**, comparada con aritmética entera (multiplicando en cruz), nunca con decimales truncados. El umbral admite hasta 4 decimales en cajas (`numeric(14,4)`), es entero en unidades base y tiene hasta 2 decimales en importe. Consecuencia: el dispositivo y el servidor usan el mismo dato que ya viaja con el precio; no depende del catálogo actual.
- **B. Las unidades de la presentación de referencia vigente en el catálogo.** Consecuencia: si la referencia cambió después de publicar la lista, el bruto se calcula con unas unidades y el descuento con otras; el dispositivo necesita un dato más.
- **C. Redondear la medida a 2 decimales antes de comparar.** Consecuencia: 19,996 cajas pasarían a 20,00 y la regla aplicaría sin haber llegado al umbral.

**Ejemplo.** Tres líneas de 2 unidades de tres vinos x6: con A, 1/3 + 1/3 + 1/3 es exactamente 1 y "≥ 1" aplica; con decimales truncados daría 0,9999 y no aplicaría. 19 cajas y 5 unidades (19,83) no alcanzan "≥ 20", como en `01` §10.

### D6 — Líneas elegibles y sobre qué se evalúa la condición · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada).** `VOLUMEN_OPERACION`: todas las líneas. `VOLUMEN_ALCANCE`: las líneas cuyo producto, categoría **o** marca figura en alguno de los alcances (unión). La condición de toda regla, también de las acumulables, se evalúa una sola vez sobre cantidades y brutos de las líneas (paso 2 de DSC-05), no sobre importes ya descontados. Consecuencia: que una regla aplique no depende del orden en que se aplican las demás.
- **B. La condición de importe de una acumulable mira el resultado anterior.** Consecuencia: una regla puede dejar de aplicar porque otra descontó antes; el resultado depende del orden y es más difícil de explicar al cliente.
- **C. Varios alcances se combinan como intersección** (el producto debe cumplir todos). Consecuencia: "categoría Vinos y marca Bodega Norte" sería posible, pero dos productos en una regla nunca coincidirían; `01` no describe combinaciones.

**Ejemplo.** Venta de bruto $236.000 (líneas de $150.000 y $86.000) cuya regla ganadora fija $38.000 y la deja en $198.000 ($125.847,46 y $72.152,54): con A, la acumulable "importe bruto ≥ 200.000 → 2%" aplica (descuenta $2.516,95 y $1.443,05); con B, no. (Con la ganadora R2 del ejemplo de D7, que deja la venta en $224.000, el bruto de $236.000 también alcanza el umbral y se aplica el 2% sobre $138.000 y $86.000.)

### D7 — Un ganador no acumulable por venta y último desempate · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). Literal de DSC-05 y ADR-004: un solo ganador en toda la venta.** El beneficio total de cada regla no acumulable es la suma de los descuentos que daría sobre el bruto de sus líneas elegibles; gana la mayor; empate → prioridad (D8); si también empata la prioridad, la regla creada primero (su identificador, que es un UUIDv7 ordenable). Las demás no acumulables no se aplican a ninguna línea. Consecuencia: una línea puede quedar sin descuento aunque una regla perdedora la cubría.
- **B. La mejor regla no acumulable por línea.** Consecuencia: más descuento total para el cliente y otro significado de "beneficio total"; contradice el texto de DSC-05 y ADR-004 y habría que enmendarlos.
- **C. Como A, pero sin último desempate: dos reglas activas no pueden tener la misma prioridad** (lo impide un índice único). Consecuencia: el resultado nunca depende de la fecha de alta; obliga a renumerar prioridades y a decidir qué pasa con las pausadas.

**Ejemplo.** 12 cajas de Vino A ($150.000) y 10 de Vino B ($86.000). R1 "≥ 20 cajas → 5%" (toda la venta) daría $11.800; R2 "≥ 10 cajas de Vino A → 8%" daría $12.000. Con A gana R2 y **Vino B queda sin descuento** (total descontado $12.000). Con B, Vino A lleva 8% y Vino B 5% (total $16.300).

### D8 — Sentido de la prioridad · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). El número más bajo es la mayor prioridad** (1 va primero): gana los empates y se aplica antes entre las acumulables. Entero mayor o igual que 1. Consecuencia: se lee como una lista ordenada.
- **B. El número más alto es la mayor prioridad.** Consecuencia: agregar una regla "más importante" no obliga a renumerar; es menos intuitivo en un listado.

**Ejemplo.** Dos reglas empatadas en beneficio, con prioridades 1 y 2: con A gana la 1.

### D9 — Reglas acumulables: orden y base · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada).** Primero la no acumulable ganadora, si hay; después todas las acumulables que aplican, por prioridad (D8) y, a igual prioridad, por antigüedad. Cada una calcula sobre el importe que dejó la anterior en cada línea elegible (DSC-05 paso 4). Un descuento que redondea a cero no se informa. El neto de una línea nunca baja de cero. Consecuencia: 8% y después 2% dan 9,84%, no 10%.
- **B. Todas las acumulables calculan sobre el bruto y se suman.** Consecuencia: 8% + 2% = 10%; contradice "cada una sobre el resultado anterior".
- **C. Las acumulables van antes que la no acumulable ganadora.** Consecuencia: contradice el orden de DSC-05.

**Ejemplo.** Vino A queda en $138.000 tras R2; la acumulable del 2% descuenta $2.760 (no $3.000) y lo deja en $135.240.

### D10 — Importe fijo: base del reparto, remanente y tope · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada).** El importe se reparte en proporción al importe de cada línea elegible **al momento de aplicar la regla**: el bruto si es la primera en aplicarse (que es lo que dice DSC-04), el resultado anterior si es acumulable (DSC-05 paso 4). Cada parte se redondea (DSC-07) y el remanente, positivo o negativo, va a la línea elegible de mayor importe; en empate, a la primera en el orden de la venta. Si el importe fijo supera la suma de las líneas elegibles, se aplica esa suma: ninguna línea queda negativa. Consecuencia: precisa DSC-04 para el caso acumulable.
- **B. Siempre en proporción al bruto original, recortando cada línea a lo que le queda.** Consecuencia: el total descontado puede ser menor que el importe de la regla sin que nadie lo vea, porque lo recortado se pierde.
- **C. Una regla de importe fijo que supera lo que queda no se aplica.** Consecuencia: resultado "todo o nada", difícil de anticipar para el vendedor.

**Ejemplo.** $1.000 fijos sobre $31.250,00, $4.300,00 y $1.433,33: partes $844,98, $116,27 y $38,76 (suman $1.000,01); el centavo se quita de la primera, que queda en $844,97.

### D11 — Forma del descuento manual · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: A+B combinadas**

**Contexto.** DSC-05 dice "se aplica el descuento manual sobre el resultado" y DSC-06 habla de "tope porcentual"; el caso de `02` §10.4 lo trae a nivel de venta. Ninguno dice si puede haber un descuento manual distinto en una línea.

**Decisión (usuario, 2026-10-13): A y B combinadas.**

1. **Dos niveles.** Una venta puede llevar un porcentaje manual **general** (para toda la venta) y, opcionalmente, un porcentaje manual **propio** en líneas individuales. Los dos son opcionales.
2. **El de la línea reemplaza al general en esa línea; no se suman ni se encadenan.** Cada línea lleva exactamente un descuento manual: el propio si lo tiene; si no, el general; si no hay ninguno, ninguno. El reemplazo vale en los dos sentidos: un porcentaje propio menor que el general también lo reemplaza.
3. **Solo porcentajes.** No hay descuento manual en pesos. Cada porcentaje, general o propio, es una fracción de hasta 6 decimales, mayor que 0 y hasta 1; fuera de ese dominio → `DESCUENTO_MANUAL_INVALIDO`.
4. **Cálculo.** El porcentaje que le toca a cada línea se aplica sobre el resultado de esa línea después de los descuentos automáticos (DSC-05 paso 5), se redondea por línea (DSC-07) y se informa por línea con origen `MANUAL` y su porcentaje (DSC-08).
5. **Tope (D12).** Se compara contra el **mayor porcentaje manual que quedó aplicado en alguna línea de la venta**, sea el general o uno propio. Si supera el tope, **una sola autorización cubre toda la venta**. El motor entrega ese máximo junto con el resultado (`porcentaje_manual_maximo`, D4, D20) para que el servidor y el dispositivo comparen el mismo número. Un general que quedó reemplazado en todas las líneas no se aplica en ninguna y, por lo tanto, no entra en el máximo. **Lectura confirmada por el usuario (2026-10-13):** general 10%, todas las líneas con propio 3% y tope 5% → el máximo es 3% y no hace falta autorización.

**Nota (usuario, 2026-10-14): un descuento manual cuyo importe redondea a $0,00 no se informa y no cuenta para `porcentaje_manual_maximo`.** Es el mismo criterio de D9 para los automáticos; el porcentaje que "queda aplicado" es el de los descuentos `MANUAL` efectivamente informados en alguna línea.

Consecuencia: precisa DSC-05, DSC-06 y DSC-08 y el caso de `02` §10.4 (`descuento_manual` a nivel de venta) en `propuesta-docs.md`; la pantalla de venta del 18b tiene que permitir un porcentaje por línea además del general.

**Ejemplos.** General 5% y Vino A con propio 10%: Vino A lleva 10% y las demás líneas, 5%. Con líneas que quedaron en $135.240 (Vino A) y $84.280 (Vino B) tras los automáticos: Vino A descuenta $13.524,00 y Vino B $4.214,00. Con tope 5%, el máximo es 10% y hace falta **una** autorización para la venta. Sin general y Vino A con propio 10%: solo Vino A lleva descuento manual.

**Alternativas descartadas.**

- **A sola. Un porcentaje único por venta.** El tope se compara directo contra ese porcentaje. Descartada: el vendedor no puede mejorarle el precio a un solo producto.
- **B sola. Un porcentaje por línea, sin general.** Descartada: descontar toda la venta obliga a cargarlo línea por línea; y con el tope comparado línea por línea, la autorización podía hacer falta en unas líneas y no en otras.
- **C. Porcentaje o importe por venta.** Descartada: el importe hay que convertirlo a porcentaje efectivo para compararlo con el tope y repartirlo como en D10; más casos y más pantalla.
- **Sumar o encadenar el general y el propio en la misma línea.** Descartada por el usuario: el de la línea reemplaza.

#### D11.1 — ¿El porcentaje propio de una línea puede ser 0, para excluirla del general? · negocio · MEDIO · **APROBADA 2026-10-13: opción A**

**Contexto.** Con el reemplazo, "general 5% y esta línea sin descuento manual" solo se puede expresar si la línea admite un propio de 0. El usuario mantuvo el dominio "mayor que 0 y hasta 1" de D11-A y no habló de este caso; `docs/` no lo resuelve.

- **A (recomendada). No.** El porcentaje propio tiene el mismo dominio que el general (mayor que 0); un 0 se rechaza con `DESCUENTO_MANUAL_INVALIDO`. Si hay general, todas las líneas llevan descuento manual. Para dejar una línea afuera se quita el general y se cargan propios en las demás. Consecuencia: es lo literal de lo aprobado; una sola regla de dominio; nunca hay una línea "con manual 0%" que registrar.
- **B. Sí: un propio de 0 excluye la línea.** La línea no lleva descuento de origen `MANUAL` y no cuenta para el máximo. Consecuencia: más cómodo en ventas largas; el dominio del propio (0 a 1) pasa a ser distinto del general (mayor que 0) y hay que decidir si la exclusión se guarda en la venta (18b).

**Ejemplo.** General 5% en una venta de 12 líneas donde una no debe llevar descuento: con A se quita el general y se carga 5% en las otras 11; con B se pone 0% en esa línea.

#### D11.2 — ¿El motivo es uno por venta o uno por línea? · negocio · MEDIO · **APROBADA 2026-10-13: opción A**

**Contexto.** DSC-08 guarda el motivo en cada descuento de cada línea; no dice si se elige una vez o línea por línea. El usuario decidió "una sola autorización por venta" y no habló del motivo. En el 16 el motivo es solo "presente o ausente" (D14); quien lo guarda es el 18b.

- **A (recomendada). Uno por venta.** La evaluación recibe un único motivo, que cubre el general y todos los propios; el 18b lo copia en cada descuento `MANUAL` de cada línea (DSC-08). Consecuencia: simétrico con la autorización única; el vendedor elige el motivo una vez.
- **B. Uno por línea con porcentaje propio**, más uno para el general. Consecuencia: permite "rotura" en una línea y "cliente frecuente" en la venta; `MOTIVO_REQUERIDO` pasa a evaluarse línea por línea, cambian la entrada de `dsc06` y la firma de `evaluar_descuento_manual`, y la pantalla del 18b suma un selector por línea.

**Ejemplo.** General 5% y Vino A con 10%, con motivo obligatorio: con A el vendedor elige "Cliente frecuente" una vez; con B elige uno para la venta y otro para Vino A.

### D12 — Tope y autorización · negocio · **CRÍTICO** · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** DSC-06: el descuento manual requiere que la organización lo habilite y el permiso `DESCUENTO_MANUAL`, "cuyo tope porcentual depende del rol. Superar el tope requiere `AUTORIZAR_DESCUENTO` o PIN de supervisor". `01` §19 describe `AUTORIZAR_DESCUENTO` como "Superar tope de descuento".

- **A (recomendada). Literal.** Orden de la evaluación: (1) organización deshabilitada → `DESCUENTO_MANUAL_DESHABILITADO`; (2) sin `DESCUENTO_MANUAL` → `PERMISO_REQUERIDO`; (3) motivo obligatorio y ausente → `MOTIVO_REQUERIDO` (D14); (4) porcentaje a evaluar ≤ tope aplicable (el propio del usuario o el de su rol) → aceptado, `DENTRO_DEL_TOPE`; (5) porcentaje mayor: aceptado si el propio usuario tiene `AUTORIZAR_DESCUENTO` (`PERMISO_PROPIO`) o si lo autoriza otro usuario con `AUTORIZAR_DESCUENTO` (`AUTORIZADO_POR_SUPERVISOR`); con un autorizador sin el permiso → `AUTORIZADOR_SIN_PERMISO`; sin nada → `AUTORIZACION_REQUERIDA`. **El porcentaje a evaluar es el mayor porcentaje manual que quedó aplicado en alguna línea de la venta** (el general o uno propio, D11); la evaluación es **una por venta** y, si hace falta autorización, una sola cubre todas las líneas. El tope se compara contra el descuento manual, no contra los automáticos ni contra el descuento total. El motivo del paso (3) es uno por venta (D11.2). **Quien autoriza no queda limitado por su propio tope**: puede autorizar hasta el 100%. Consecuencia: un Supervisor con tope 10% autoriza un 40%; queda registrado en la venta y auditado (18b).
- **B. El autorizador autoriza hasta su propio tope.** Consecuencia: por encima del tope del Supervisor solo autoriza quien tenga un tope mayor; con el Supervisor sembrado en 0% nadie salvo el Administrador podría autorizar hasta que se definan topes.
- **C. Como A, pero el tope se compara contra el descuento total de la venta** (automáticos más manual). Consecuencia: una regla de volumen generosa dejaría al vendedor sin margen para el manual; DSC-06 habla del tope del descuento manual.

**Ejemplo.** Vendedor con tope 5% pide 10%. Con A, la Supervisora (`AUTORIZAR_DESCUENTO`, tope 8%) lo autoriza. Con B no puede: el 10% supera su 8%. Con D11: general 5% y una línea con 10%, tope 5% → el máximo es 10% y hace falta una autorización, que cubre la venta entera; general 5% y una línea con 3%, tope 5% → el máximo es 5% y no hace falta.

### D13 — Cómo se define el tope de un rol · negocio · **CRÍTICO** · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** Las plantillas Supervisor y Vendedor nacen con tope 0 y ningún comando lo cambia: hoy todo descuento manual de un vendedor pediría autorización. Es dominio de `identidad` (roles).

- **A (recomendada). Un comando mínimo `ROL_TOPE_DESCUENTO_DEFINIR`** (`ADMIN_USUARIOS`, solo `ONLINE`) en `identidad`, que reutiliza la validación existente y deja una única fila de auditoría con el valor anterior y el nuevo (mismo patrón que `cambiar_condicion_iva` y `definir_lista_precio_default`, que ya escriben `antes` y `despues` con el `operation_id` del comando), más una lectura de roles con su tope y la pantalla "Topes por rol". No toca permisos, ni el tope propio de usuarios, ni `GET /yo`. Consecuencia: `identidad` suma un comando y una lectura; se hace en el lote crítico, con el alcance confirmado antes de escribir.
- **B. Nominarlo al change de usuarios y roles** (sin número; ver la nota del 06b en `04` §6). Consecuencia: el 18b se probaría con todos los vendedores en 0% o tocando la base a mano.
- **C. Como A, y además el tope propio por usuario.** Consecuencia: hace falta edición de usuarios, que hoy no existe (solo alta); es el change de usuarios y roles.

**Ejemplo.** Con A, el Administrador abre "Topes por rol", pone 5% al Vendedor y 15% al Supervisor; queda una fila de auditoría por cambio.

### D14 — Motivo obligatorio sin definir y motivos del descuento manual · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** `motivo_obligatorio_descuento` es nulo y no hay comando que lo defina; el ámbito `DESCUENTO_MANUAL` no tiene motivos.

- **A (recomendada). El 16 solo lee.** La evaluación exige motivo cuando el parámetro es verdadero; nulo se trata como "no obligatorio". El comando que define los dos parámetros del descuento manual, los motivos sembrados y la validación del motivo (activo y del ámbito) se nominan al 18b, que es quien guarda el motivo (DSC-08). Consecuencia: en el 16 el motivo es solo "presente o ausente".
- **B. El 16 agrega `DESCUENTO_MANUAL_CONFIGURAR`** (`ADMIN_CONFIGURACION`), su pantalla en Configuración y tres motivos sembrados. Consecuencia: un comando de configuración y una siembra más en un change que ya supera el tamaño; gobernanza alta.
- **C. Nulo se trata como "obligatorio".** Consecuencia: más estricto; sin motivos sembrados, ningún descuento manual podría darse hasta que alguien cargue motivos.

### D15 — Qué se puede editar de una regla · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

**Contexto.** Las líneas de venta van a referenciar la regla (`venta_linea_descuento.regla_id`, DSC-08).

- **A (recomendada). Una regla se edita completa solo en `BORRADOR`.** Activada (o pausada), solo cambia de estado y admite fijar o mover su vigencia hasta; para cambiar condición, acción, alcance, prioridad o acumulabilidad se pausa y se crea otra. Ninguna regla se borra ni vuelve a `BORRADOR`. Consecuencia: una regla referenciada por una venta dice siempre lo mismo; pueden acumularse reglas pausadas.
- **B. Editable también en `PAUSADA`.** Consecuencia: cómodo para corregir; una venta vieja apuntaría a una regla que ya no dice lo que descontó (el importe queda congelado, la descripción no).
- **C. Editable siempre, con auditoría.** Consecuencia: un cambio en caliente haría diferir a los dispositivos sin conexión (`DESCUENTO_DIFIERE`) sin que nadie lo decida.

### D16 — Vigencia · negocio · MEDIO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). Como las versiones de lista (PRC-02, PRC-20).** `vigencia_desde` y `vigencia_hasta` son momentos (`timestamptz`); la regla aplica si `desde ≤ momento de la operación < hasta`. La desde es opcional en el borrador y obligatoria desde la activación (por defecto, el momento de activar; puede ser futura). La hasta es opcional y posterior a la desde. `VENCIDA` es derivado: activa o pausada con la hasta ya pasada. Activar una regla ya vencida se rechaza (`VIGENCIA_INVALIDA`). Consecuencia: una misma semántica de vigencia en precios y descuentos.
- **B. Fechas de negocio** (`date`, en la zona de la organización), con los dos extremos incluidos. Consecuencia: más natural para "todo marzo"; distinta de las listas y obliga a convertir zona en el dispositivo.
- **C. Sin vigencia en la etapa 1** (lectura de `00` §6.2, "promociones temporales"). Consecuencia: contradice DSC-01; las columnas quedarían sin uso.

### D17 — Modelo de datos · técnica · BAJO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). Una revisión de Alembic sobre `a4b5c6d7e8f9`** con las dos tablas de `03` §11 y estos agregados: en `regla_descuento`, en lugar de `accion_valor`, dos columnas `accion_porcentaje numeric(9,6)` y `accion_importe numeric(14,2)` con un `CHECK` que exige exactamente la que corresponde a `accion_tipo` (así cada una respeta el tipo de `CLAUDE.md` §4 y la prueba de INV-03); `CHECK` de catálogo en `tipo`, `medida`, `operador`, `accion_tipo` y `estado`; `umbral > 0`; `prioridad >= 1`; `vigencia_hasta > vigencia_desde`; `estado = 'BORRADOR' OR vigencia_desde IS NOT NULL`; `UNIQUE (organizacion_id, id)`; `actualizado_en` y `actualizado_por_id`; índice por organización y estado. En `regla_descuento_alcance`: `alcance_tipo` + `alcance_id` con columnas generadas `producto_id`, `categoria_id`, `marca_id` y sus claves foráneas compuestas (precedente de `regla_margen`), y único por regla, tipo y entidad. "Una regla de operación no tiene alcances y una de alcance tiene al menos uno" lo garantiza el servicio y lo comprueba una prueba (no es expresable como `CHECK` de fila). El usuario de aplicación no tiene `DELETE` sobre `regla_descuento`; sobre `regla_descuento_alcance` sí, y el servicio solo lo usa al reemplazar los alcances de un borrador. Sin datos que migrar.
- **B. `accion_valor numeric(14,6)` única**, literal de `03` §11. Consecuencia: una columna de importe con 6 decimales, contra `CLAUDE.md` §4.
- **C. Tres tablas de alcance, una por tipo.** Consecuencia: claves foráneas simples; se aparta de `03` §11 y del precedente.

**Ajuste a D13 (aprobado por el usuario, 2026-10-15).** `GET /identidad/roles` (mismo permiso `ADMIN_USUARIOS`) devuelve además `permisos` de cada rol (códigos ordenados, una sola consulta, filtrada por organización). La pantalla "Topes por rol" muestra el aviso de tope 0 % solo en los roles con `DESCUENTO_MANUAL` y tope 0. El tope sigue sin exponerse en `GET /yo` ni en el token; cada usuario verá el suyo recién en el 18b, con el bootstrap (SYN-11).

### D18 — Comandos, permisos y lecturas · permisos · **ALTO** · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). Sin permisos nuevos.** Cuatro comandos `ONLINE` v1 con `GESTIONAR_DESCUENTOS`: `REGLA_DESCUENTO_CREAR`, `REGLA_DESCUENTO_MODIFICAR`, `REGLA_DESCUENTO_ACTIVAR`, `REGLA_DESCUENTO_PAUSAR`. Rutas bajo `/api/v1/descuentos/reglas` (alta, edición, `/{id}/activacion`, `/{id}/pausa`). Lecturas `GET /api/v1/descuentos/reglas` (filtro de estado, cursor) y `/{id}`, solo con `GESTIONAR_DESCUENTOS`. Las lecturas de productos, categorías y marcas para elegir alcance se abren, solo en lectura, a `GESTIONAR_DESCUENTOS` (mismo criterio que `GESTIONAR_LISTAS` en ADR-047 punto 16). La venta y el bootstrap no leen por HTTP: usan `descuentos/service.py`. Consecuencia: un vendedor no ve el listado de reglas en `/admin`; ve el descuento calculado en su venta (18b).
- **B. Las lecturas de reglas también con `VENDER`.** Consecuencia: el vendedor consulta las reglas vigentes desde ya; abre una lectura que hoy nadie necesita.
- **C. Sin abrir el catálogo.** Consecuencia: un rol a medida con `GESTIONAR_DESCUENTOS` y sin `GESTIONAR_CATALOGO` no podría elegir alcances.

### D19 — Dependencias del módulo `descuentos` · técnica · BAJO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). `descuentos ──► catalogo` (validar que el producto, la categoría o la marca de un alcance existen en la organización y obtener sus nombres) e `identidad` (configuración del descuento manual, permisos y tope), solo por `service.py`.** El motor no consulta nada: recibe las líneas con sus identificadores. Contratos de import-linter: `descuentos/domain` sin infraestructura ni bus; `descuentos` alcanza a los demás solo por `service.py`; los demás alcanzan a `descuentos` solo por `service.py`; `catalogo` e `identidad` no importan `descuentos`. Consecuencia: `02` §5.3 suma una línea; sin ciclos.
- **B. Sin dependencia de `catalogo`: el alcance se valida solo por la clave foránea.** Consecuencia: un alcance ajeno aparece como error de base y hay que traducirlo a 404 a mano; el detalle no puede mostrar nombres.
- **C. El motor lee categoría y marca del catálogo al calcular.** Consecuencia: deja de ser puro y no puede tener gemela en el dispositivo.

### D20 — Qué expone `descuentos/service.py` y qué no · técnica · BAJO · ADR-050 · **APROBADA 2026-10-13: opción A**

- **A (recomendada). Tres funciones para el 18b y el 21, sin HTTP de cálculo:** `reglas_aplicables(organizacion, momento)` (activas y vigentes, con alcances), `calcular_descuentos(lineas, reglas, descuento_manual_general)` (el motor; cada línea trae su `descuento_manual` propio o nulo, y el resultado trae además `porcentaje_manual_maximo`, D11) y `evaluar_descuento_manual(organizacion, usuario, porcentaje_maximo, motivo, autorizador)`, que se llama una vez por venta con ese máximo y solo si no es nulo (D12). No hay endpoint que calcule ni simulador en pantalla. Consecuencia: el motor se prueba con casos compartidos y propiedades; en el navegador se verifican las reglas, y el efecto en una venta recién en el 18b.
- **B. Además, `POST /descuentos/calculo`** para previsualizar. Consecuencia: una ruta que nadie usa hasta el 18b, con su permiso y sus ratchets.
- **C. Además, un simulador en la pantalla de reglas** (se arma una venta de prueba y se ve qué descuenta). Consecuencia: útil para el cliente, y es justo el crecimiento que advierte `04` §14.

## Risks / Trade-offs

- **[El motor crece más de lo necesario, `04` §14]** → D1 fija el techo en DSC-02 a DSC-04; los tipos, medidas y acciones son listas cerradas con `CHECK` y una prueba que rechaza cualquier otro valor; D20 deja fuera el simulador.
- **[Divergencia entre Python y TypeScript]** → casos compartidos antes del código (ADR-016), propiedades en Python sobre los mismos invariantes y comparación exacta con aritmética entera en las dos gemelas (D5).
- **[Los importes de los ejemplos se calcularon a mano]** → al escribir los casos compartidos, cada salida esperada se deriva paso a paso en el propio caso (campo de comentario) y la corren las dos suites; si un ejemplo de las specs resultara mal calculado, se corrige la spec antes de tocar el código.
- **[El change no deja un efecto visible del motor en el navegador]** → se verifica a mano la administración de reglas y de topes; el efecto en una venta se demuestra en el 18b. Se le avisa al usuario en la verificación manual.
- **[El porcentaje que se evalúa contra el tope no es el que se aplicó, D11 y D12]** → el máximo lo calcula el motor y lo entrega en su resultado; quien llama no lo recalcula. Una propiedad fija que es el mayor de los porcentajes `MANUAL` informados en las líneas, y un caso compartido cubre el general reemplazado en todas las líneas.
- **[Reglas pausadas que se acumulan, D15]** → el listado filtra por estado; no se borra nada (TR-06).
- **[Tope definido pero no ejercido hasta el 18b, D13]** → la evaluación ya queda probada con el tope real del rol; el 18b solo la invoca.
- **[`regla_descuento_alcance` admite `DELETE`]** → solo sobre borradores; una prueba recorre los comandos y verifica que ninguno borra alcances de una regla activada.

## Migration Plan

Una revisión de Alembic nueva sobre `a4b5c6d7e8f9`, solo aditiva (dos tablas, sin tocar datos ni tablas existentes). El `downgrade` borra las dos tablas; como ninguna venta las referencia todavía, no hay pérdida de historia. El comando de tope no necesita migración. Sin dependencias nuevas previstas en `requirements.txt` ni en `package.json`; si el apply agregara alguna, se reconstruyen las imágenes antes de la verificación manual.

## Deudas que se nominan

- **Al 18a:** `ventas/domain/calculo.py` y `domain/calculo.ts` como orquestadores; casos compartidos de totales (VTA-04) sobre el formato de D4.
- **Al 18b:** llamar al motor y a la evaluación (una evaluación por venta, con el `porcentaje_manual_maximo` que entrega el motor); la pantalla de venta permite cargar un porcentaje manual general y uno propio por línea, y muestra cuál lleva cada línea (D11); una sola autorización y un solo motivo por venta, copiados a cada descuento `MANUAL` de cada línea (DSC-08; D11.2); verificar el PIN; persistir `venta_linea_descuento` con clave foránea compuesta a `regla_descuento`; DSC-09 y `DESCUENTO_DIFIERE`; auditoría del descuento manual y de su autorización (AUD-01); comando de configuración del descuento manual, motivos sembrados y validación del motivo (D14); cómo conoce la pantalla de venta el tope del usuario (`GET /yo` no lo expone); el comportamiento sin conexión (SYN-05, SYN-10).
- **Al 21:** el bootstrap incluye las reglas activas con sus alcances y los topes del usuario (SYN-11), leídos por `descuentos/service.py` e `identidad/service.py`; las líneas locales necesitan `categoria_id` y `marca_id` del producto.
- **Al change de usuarios y roles:** el tope propio por usuario.
- **Deuda heredada que este change salda:** la parte de descuentos de la deuda del 13 al 18a ("completar los casos compartidos de §10.4 con descuentos … junto con el change 16"). La parte de totales sigue en el 18a.
