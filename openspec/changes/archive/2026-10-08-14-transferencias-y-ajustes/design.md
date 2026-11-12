# Diseño técnico — 14-transferencias-y-ajustes

> **Estado: D0 a D11 APROBADAS por el usuario el 2026-10-07.** Opción A tal como estaba escrita en D0 (ampliada a cuatro lotes), D2, D3, D6, D7, D8, D9 y D11; **D1 = B**; **D4 = opción D** (propuesta por el usuario: no se desactiva un producto con stock); **D5 = B** (anulación, con las reglas aprobadas); **D10 = B** acotada a este change. Las opciones descartadas quedan como alternativas consideradas.
>
> **Las ocho subdecisiones** que aparecieron al incorporar D4, D5 y D10 quedaron **APROBADAS (A) por el usuario el 2026-10-07** (tarea 0.2): técnicas **D4.1, D4.2, D5.1, D5.2, D10.1**; de negocio **D4.3, D5.3, D5.4**.
>
> Todo se documenta en **ADR-048** (estado *Propuesto* durante el apply, último lote), que enmienda ADR-039 (consecuencias: "un ingreso de otro tipo se rechaza"), ADR-044 punto 4 (stock negativo solo en la anulación de compra), ADR-022 (la fila de auditoría del bus lleva el motivo en tres comandos) y `02` §7.3 (el producto entra en el orden de bloqueo, si D4.2 = A). **ADR-038 punto 5 queda sin enmendar** (D4). Dominio de gobernanza **medio-alto** (stock y costos), con dos piezas de gobernanza **crítica** aprobadas explícitamente y solo con este alcance: la auditoría (D10) y el permiso nuevo `ANULAR_TRANSFERENCIA` (D5). No se escribe código hasta la tarea 0.2.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Libro de stock** (change 09, ADR-039): `stock_movimiento` ya acepta en su `CHECK` los nueve tipos de STK-03, incluidos `TRANSFERENCIA_SALIDA`, `TRANSFERENCIA_ENTRADA` y `AJUSTE`; tiene `motivo_id` con FK compuesta a `motivo` (de cualquier ámbito) y `costo_unitario numeric(18,6)` nulable. `origen_tipo` es texto sin `CHECK`. `app_runtime` solo tiene `SELECT, INSERT` (INV-05). No hace falta migrar el libro.
- **Única puerta** `stock/service.py::registrar_movimientos`: valida las líneas en `domain/movimientos.py`, toma las ubicaciones `FOR SHARE` (y exige que estén activas), valida productos activos por `catalogo/service.py::obtener_producto` (**lectura sin bloqueo**), bloquea `costo_producto` vía `costeo.bloquear_costos` y después `stock_saldo` por `(producto_id, ubicacion_id)` ascendentes, y recién entonces aplica cada línea en el orden recibido. Hoy **rechaza** con `TIPO_MOVIMIENTO_INVALIDO` cualquier ingreso que no sea `STOCK_INICIAL`, `COMPRA` o `ANULACION_VENTA` y exige costo en todo ingreso. `permitir_negativo` solo alcanza a `ANULACION_COMPRA` (`puede_quedar_negativo`, ADR-044 punto 4), y solo ese tipo admite un producto inactivo (`productos_que_exigen_estar_activos`, ADR-044 punto 5).
- **Costeo** (`costeo/service.py`): `aplicar_ingreso` (CST-11 con historia), `revertir_ingreso` (CMP-06), `aplicar_egreso` (baja `stock_total`, devuelve el promedio vigente para valorizar, sin historia; el promedio puede ser nulo, ADR-039 punto 6). **No existe** un ingreso que sume `stock_total` sin recalcular.
- **Catálogo** (changes 05 y 06): `PRODUCTO_MODIFICAR` (`PUT /api/v1/catalogo/productos/{id}`, estado completo, permiso `GESTIONAR_CATALOGO`) cambia `activo` sin ninguna comprobación de stock y **sin bloquear** la fila (`repository.obtener_producto_por_id`; existen `…_para_actualizar` y `…_para_compartir`, que usan presentaciones y `COSTO_INFORMAR`). `catalogo` no depende de ningún módulo de operaciones (`02` §5.3) y ya resolvió dos veces la consulta inversa con **puertos de registro** en `catalogo/service.py`: `registrar_verificador_uso` (ADR-023, tolera la lista vacía) y `registrar_consulta_proveedor` (ADR-025, falla cerrado). `stock/service.py` **importa** `catalogo/service.py`.
- **Motivos:** `motivo.ambito` es una lista cerrada (`ck_motivo__ambito`, `configuracion/domain/valores.py::AMBITOS_MOTIVO`) que admite `AJUSTE_STOCK`; `app/seed.py` siembra "Rotura", "Vencimiento", "Muestra", "Consumo interno", "Diferencia de inventario" y "Otro". El change 12 agregó el ámbito `ANULACION_PAGO` con una migración que rehace el `CHECK` y siembra tres motivos en las organizaciones existentes que no tengan ninguno (precedente de D5). `GET /configuracion/motivos?ambito=` responde con cualquier sesión (ADR-043). El patrón de validación de motivo (de la organización, activo, del ámbito; si no `MOTIVO_INVALIDO`) existe en `proveedores/service.py`.
- **Anulaciones existentes** (changes 11 y 12): `compra` y `pago_proveedor` llevan `estado` (`CONFIRMADA`/`ANULADA`), `anulacion_motivo_id`, `anulada_en` y `anulada_por_id` con un `CHECK` que las ata; `app_runtime` tiene `GRANT UPDATE` **solo sobre esas columnas**; la anulación toma la cabecera `FOR UPDATE` antes del nivel 1 del orden de bloqueo (`02` §7.3), se expone como `POST …/{id}/anulacion` y rechaza la segunda vez con `COMPRA_YA_ANULADA` / `PAGO_YA_ANULADO` (409).
- **Permisos** `TRANSFERIR_STOCK` (ADM, GES, SUP, VEN) y `AJUSTAR_STOCK` (ADM, GES) ya están en el catálogo y en las plantillas (`01` §19). `PERMITIR_STOCK_NEGATIVO` solo ADM. El catálogo tiene 39 permisos (`identidad/domain/permisos.py`, tabla `permiso`, `rol_permiso`).
- **Bus:** una fila de auditoría por comando (ADR-022) escrita por `sync/service.py` con `identidad_service.registrar_auditoria(...)`, que **ya acepta** `motivo_id` y `observacion`; la tabla `auditoria` **ya tiene** esas dos columnas y el bus hoy no las llena. Los handlers devuelven una tupla (`ResultadoHandler`, o `ResultadoHandlerConObservaciones` con `ObservacionProducida`, SYN-04, SYN-07).
- **Lecturas:** `GET /stock/ubicaciones`, `GET /stock/ubicaciones/{id}/saldos` y `GET /stock/kardex` (con `TRANSFERIR_STOCK`; costos solo con `VER_COSTOS`, ADR-036). El kardex devuelve `origen_tipo` y `origen_id` pero no el motivo.
- **Frontend** `areas/admin/stock/`, `features/stock/`, `domain/stock/cantidades.ts` (cajas + unidades, CAT-08) y el patrón `useOperationIdPorContenido` de compras.
- **Modelo** `03` §9 define `transferencia` (con `estado`), `transferencia_linea`, `ajuste_stock` (sin `estado`) y `ajuste_stock_linea`. **Ninguna de las cuatro tablas existe todavía.**

Lo que `docs/` **no** resolvía y resolvieron las decisiones del 2026-10-07:

- **Deuda del change 11 (`04` §7):** cómo se regulariza el stock negativo, y si los egresos del 14 lo admiten (ADR-044, alternativa B). → D1, D2.
- **CST-12** no dice nada del **ingreso** por ajuste ni de un producto sin promedio. → D3.
- **ADR-038 punto 5** prohíbe movimientos de productos inactivos, pero el catálogo dejaba desactivar un producto con stock. → D4.
- **`03` §9** pone `estado` en `transferencia` pero `01` §18 no tiene máquina de estados para transferencias ni ajustes. → D5.
- **STK-07/STK-08** no fijan la forma de los comandos. → D6. **ADR-036** no dice quién lee transferencias y ajustes. → D7. **`03` §9** no fija detalles del modelo. → D8.
- **AUD-01/AUD-02** piden auditar los ajustes con su motivo; la auditoría del bus no lo guardaba. → D10.

Reglas heredadas que se vuelven visibles (no son decisión):

- Desde la primera transferencia o el primer ajuste de un producto, ese producto ya no admite `STOCK_INICIAL` (`PRODUCTO_CON_OPERACIONES`, STK-10). Anular esa transferencia o ese ajuste **no** lo reabre: los movimientos siguen en el libro.
- STK-09 (toma de ubicación) no se aplica: nace con `jornada` en el change 15 (ADR-038, consecuencias). Hasta entonces se puede transferir a un vehículo sin jornada, y anular esa transferencia.
- Una ubicación inactiva rechaza todo movimiento (`UBICACION_INACTIVA`), como origen o como destino (ADR-038 punto 5).

## Goals / Non-Goals

**Goals:** transferencia y ajuste como operaciones atómicas e idempotentes que pasan por la única puerta del libro; su anulación total con movimientos inversos; INV-15 cerrado con prueba de propiedades contra PostgreSQL real; un camino documentado para regularizar el stock negativo; ningún producto se desactiva con stock; el motivo en la fila de auditoría de los tres comandos que lo llevan; cero regresiones en stock inicial, compras, importación y catálogo.

**Non-Goals:** jornadas y toma (15); rendición (24); recuento (etapa 2); transferencias en tránsito o con confirmación del destino; anulación parcial; alta de motivos; valuación de inventario en pantalla; cambios en `costo_producto_mov` (el promedio no cambia, CST-13 no pide historia); llevar el motivo a la auditoría de las anulaciones de compra y de pago (deuda nominada, D10); migrar productos que hoy ya están inactivos con stock (D4).

## Decisions

### D0 — Tamaño del change y lotes · técnica

> **APROBADA (A, ampliada a cuatro lotes) — 2026-10-07.**

**Qué se decidió.** Un solo change. Con D4, D5 y D10 el alcance creció a cuatro comandos, una regla nueva en el catálogo, un cambio en el bus, cuatro lecturas, una migración y dos pantallas, así que los tres lotes pasan a **cuatro**:

1. **Lote 1:** migración completa (tablas, estado y columnas de anulación, ámbitos, permiso), modelos y catálogos, dominio, libro y costeo, y `STOCK_TRANSFERIR` de punta a punta por API.
2. **Lote 2:** `STOCK_AJUSTAR`, el motivo en la auditoría del bus (D10) y la regla "un producto con stock no se desactiva" (D4).
3. **Lote 3:** las dos anulaciones (D5), lecturas, kardex y ratchets.
4. **Lote 4:** pantallas, concurrencia, propiedades, cobertura, ADR, docs y verificación manual.

Las anulaciones van en el lote 3 y no en el último porque las lecturas y el kardex (estado, movimientos inversos) y las pantallas dependen de ellas.

**Supera lo previsto en `04` §2** ("entre medio día y tres días de trabajo; un change más grande se divide"): el usuario aceptó el 2026-10-07 que el change crezca en lugar de dividirlo. Se anota la excepción en la propuesta de docs (`04` §8).

**Alternativa considerada — B. Dividir en `14a-transferencias` y `14b-ajustes`:** descartada: la rotura de 6 botellas en la camioneta no se podría registrar hasta archivar el 14a, y las anulaciones y la regla del catálogo quedarían partidas entre dos changes.

**Ejemplo.** Al cerrar el lote 1 ya se pueden pasar por API 48 unidades de Vino A del depósito a "Camioneta 1"; al cerrar el lote 3, esa transferencia se puede anular por API y el kardex muestra las cuatro líneas.

### D1 — ¿Una transferencia o un ajuste pueden dejar stock negativo? · de negocio · ADR-048

> **APROBADA (B) — 2026-10-07.** Salda la deuda del change 11 y enmienda ADR-044 punto 4.

**Qué se decidió. Solo la transferencia.** Sin permiso, una salida de transferencia que no alcanza es `STOCK_INSUFICIENTE` (409) y no se escribe nada. Con `PERMITIR_STOCK_NEGATIVO` se aplica y el comando queda `ACEPTADO_CON_OBSERVACIONES` con una observación `STOCK_NEGATIVO` por cada producto y ubicación que quedó bajo cero. Un **ajuste nunca deja stock negativo**: un ajuste refleja un conteo físico, y lo físico no es negativo; un ajuste negativo que no alcanza se rechaza con `STOCK_INSUFICIENTE` **tenga o no** el usuario `PERMITIR_STOCK_NEGATIVO`. No se toca el criterio de los demás tipos (STK-10 sigue sin excepción).

**Consecuencias.**

- D2: la acción "Ajustar" que lleva a cero un saldo negativo es un ajuste **positivo**; sigue valiendo.
- D9: `permitir_negativo` se extiende a `TRANSFERENCIA_SALIDA` y **no** a `AJUSTE`.
- D5: la **anulación** de un ajuste positivo sí puede dejar negativo con permiso; no contradice esta decisión porque es una anulación, no un ajuste (mismo criterio que la anulación de compra, ADR-044).
- STK-05 en `01` se precisa: "salvo los ajustes y las correcciones de stock inicial, que nunca dejan negativo".

**Alternativas consideradas.**

- **A. STK-05 al pie de la letra para los dos** (el ajuste negativo también admite negativo con permiso): descartada por el usuario.
- **C. Ninguno:** más estricto que STK-05; nadie podría cargar la camioneta antes de registrar la compra.

**Ejemplo.** Depósito con 48 unidades de Vino A; el Administrador transfiere 60 a "Camioneta 1" porque la compra de hoy todavía no se cargó: queda depósito −12 y camioneta +60, con la observación `STOCK_NEGATIVO`; un Supervisor recibe `STOCK_INSUFICIENTE`. El mismo Administrador ajusta −11 sobre un saldo de 10: `STOCK_INSUFICIENTE`, aunque tenga el permiso.

### D2 — ¿Cómo se regulariza el stock negativo? · de negocio · ADR-048

> **APROBADA (A) — 2026-10-07.** Salda la deuda del change 11 (`04` §7).

**Qué se decidió. Sin mecanismo especial.** Cualquier ingreso regulariza: una compra (que, con stock total ≤ 0, fija el promedio en su costo, CST-11), una transferencia entrante o un ajuste positivo con el motivo que corresponda (por ejemplo "Diferencia de inventario"). El stock por ubicación marca los saldos negativos y ofrece la acción "Ajustar" sobre esa línea con la cantidad que lo lleva a cero precargada (editable). Las observaciones `STOCK_NEGATIVO` quedan pendientes hasta que las resuelva el change 25.

**Alternativas consideradas.**

- **B. Comando propio `STOCK_REGULARIZAR`** que lleva a cero todos los saldos negativos de una ubicación con un motivo fijo: descartada, es un ajuste masivo sin conteo.
- **C. Bloquear los egresos** de un producto mientras tenga algún saldo negativo: descartada, paraliza la venta (18a) de ese producto.

**Ejemplo.** Depósito con −12 de Vino A tras anular una compra de 60 (quedaban 48, ya se habían vendido 12). Se cuenta el depósito, hay 0 botellas; ajuste +12 con "Diferencia de inventario" valorizado a $1.050,000000 y el saldo queda en 0. Si en cambio llega una compra de 24, el saldo queda en 12 y el promedio pasa a ser el costo de esa compra (stock total previo ≤ 0, CST-11).

### D3 — Valorización de transferencias y ajustes, y ajuste positivo sin promedio · de negocio · ADR-048

> **APROBADA (A) — 2026-10-07.** Precisa CST-12.

**Qué se decidió.** Todo movimiento de transferencia y de ajuste, de ingreso o de egreso, guarda en `costo_unitario` el **promedio vigente** al momento de aplicarse, sin recalcularlo y sin historia en `costo_producto_mov` (CST-12, CST-13). `stock_total` sube o baja con cada movimiento; la transferencia lo deja igual (INV-15). `ajuste_stock_linea.costo_unitario` repite ese valor. Un **ajuste positivo** de un producto **sin promedio** se rechaza con `PRODUCTO_SIN_COSTO` (409): ese stock se carga con stock inicial o compra, que sí fijan costo. Una transferencia de un producto sin promedio (solo posible con stock negativo, D1) guarda `costo_unitario` nulo. Los movimientos **inversos** de una anulación no se valorizan al promedio del momento: repiten el costo del movimiento original (D5).

**Alternativas consideradas.**

- **B. El ajuste positivo pide costo** y recalcula el promedio como un ingreso (CST-11): descartada, contradice CST-12.
- **C. Ajuste positivo sin promedio admitido con costo nulo:** descartada, deja stock sin valor que después vendería el 18a sin costo.

**Ejemplo.** Vino A con 120 en la organización y promedio $1.050,000000. Ajuste −6 por "Rotura" en el depósito: el movimiento guarda −6 a $1.050,000000 (pérdida $6.300 que verá el reporte), promedio igual, stock total 114. Ajuste +2 por "Diferencia de inventario": +2 a $1.050,000000, stock total 116, promedio igual. Producto nuevo "Agua 500" sin compras: ajuste +24 → `PRODUCTO_SIN_COSTO`.

### D4 — Productos inactivos: no se desactiva un producto con stock · de negocio · ADR-048

> **APROBADA (opción D, propuesta por el usuario) — 2026-10-07.** No es ninguna de las tres opciones originales. **ADR-038 punto 5 queda sin enmendar.**

**Qué se decidió.** `PRODUCTO_MODIFICAR` que pasa un producto de activo a inactivo se rechaza con **`PRODUCTO_CON_STOCK` (409)** si el producto tiene algún `stock_saldo` **distinto de cero** en cualquier ubicación de la organización, **incluidos los saldos negativos**. Es el mismo criterio que ADR-038 punto 4 para las ubicaciones (`UBICACION_CON_STOCK`) y que ADR-024 y ADR-026 para categorías y proveedores. Reactivar, o guardar un producto que ya estaba inactivo sin cambiar su estado, no dispara la comprobación.

**Consecuencias.**

- Sobre un producto inactivo **no se registra ningún movimiento** de este change: ni transferencia, ni ajuste (de ningún signo), ni sus anulaciones. Todos responden `PRODUCTO_INACTIVO` (ADR-038 punto 5, literal). `productos_que_exigen_estar_activos` no cambia: la única excepción sigue siendo `ANULACION_COMPRA` (ADR-044 punto 5; ver D4.3).
- Se mira cada saldo, no el stock total: +5 en el depósito y −5 en la camioneta suman cero pero **bloquean** la desactivación.
- Toca el comando `PRODUCTO_MODIFICAR` del módulo `catalogo` (change 05) y necesita que `catalogo` consulte a `stock` sin importarlo (D4.1) y que la desactivación se serialice con un ingreso simultáneo (D4.2).
- **Productos que hoy ya están inactivos con stock** (se desactivaron antes de este change): **no se migra nada** y no se reactivan solos. Siguen inactivos y su stock no se puede mover; para vaciarlos hay que **reactivar el producto, vaciarlo (transferencia o ajuste) y volver a desactivarlo**. La regla nueva solo actúa en la transición de activo a inactivo. La verificación manual incluye una consulta de solo lectura que los lista, para que el usuario sepa cuáles son.
- No aplica a la importación de maestros: solo crea productos (no tiene columna `activo` ni llama a `PRODUCTO_MODIFICAR`). Si en el futuro la importación modifica productos, la regla la alcanza siempre que pase por `catalogo.modificar_producto`.

**Alternativas consideradas.**

- **A. Admitir la transferencia y el ajuste negativo de un producto inactivo** (enmendando ADR-038 punto 5): descartada por el usuario: prefiere que el problema no nazca.
- **B. Rechazar todo sin tocar la desactivación** (ADR-038 literal): descartada: deja stock inmovilizado e invisible.
- **C. Admitir todo, también el ajuste positivo:** descartada: contradice CAT-05.

**Ejemplo.** "Vino Rosado" se discontinúa con 18 botellas en "Camioneta 1". Al desactivarlo, el catálogo responde `PRODUCTO_CON_STOCK`. El usuario transfiere las 18 al depósito (sigue con stock: 18 en el depósito), las ajusta −18 por "Vencimiento" y recién entonces lo desactiva. Si lo hubieran desactivado el mes pasado con esas 18 botellas, hoy tiene que reactivarlo, vaciarlo y desactivarlo de nuevo.

#### D4.1 — Cómo consulta `catalogo` el stock sin depender de `stock` · técnica · ADR-048

> **APROBADA (A) — 2026-10-07.**

**Qué hay que decidir.** `stock/service.py` ya importa `catalogo/service.py`; si `catalogo` importara `stock/service.py` habría un ciclo entre módulos, y `02` §5.3 fija `catalogo ──► (sin dependencias de negocio)`. El contrato de import-linter `catalogo-solo-por-service-ajeno` hoy prohíbe a `catalogo` importar `proveedores` y `sync` completos, pero **no** nombra a `stock`.

- **A (recomendada). Puerto de registro en `catalogo/service.py`**, tercer uso del patrón de ADR-023 y ADR-025: `registrar_verificador_de_stock(funcion: Callable[[UUID, UUID, Session], bool])`. `stock/service.py` registra `producto_tiene_stock(organizacion_id, producto_id, sesion)` (lee sus propias filas de `stock_saldo`) en ese puerto al importarse, igual que `proveedores/service.py` y `clientes/service.py` con los puertos de ADR-023 y ADR-025; `app.main` lo deja registrado al arrancar porque importa `stock.commands`. `catalogo` nunca importa `stock`; `stock` sigue usando a `catalogo` solo por su `service.py`. **Falla cerrado** (semántica de ADR-025, no la de ADR-023): sin verificador registrado, desactivar un producto falla con un error de configuración; nunca se desactiva sin comprobar. Se agrega `app.modules.stock` entero a `forbidden_modules` de `catalogo-solo-por-service-ajeno`; de `costeo` se prohíben solo sus internas (`app.modules.costeo.models`, `.repository` y `.domain`), porque `catalogo/api.py` ya importa `costeo.service` desde antes (permitido por ADR-035 punto 5) y prohibir `costeo` entero rompería `lint-imports`: catálogo alcanza a `costeo` solo por su `service.py`. Una prueba de arranque verifica que, tras importar `app.main`, el verificador está registrado.
- **B. `catalogo/service.py` importa `stock/service.py`** (y `stock` deja de validar el producto por `catalogo`): invierte la dirección de `02` §5.3 y obliga a reescribir la única puerta del libro.
- **C. Mecanismo común de registro** para los tres puertos (ADR-025 lo sugiere "si aparece un tercero"): más prolijo, pero refactoriza dos puertos en uso dentro de un change que ya es grande. Se deja como deuda nominada.
- **D. `catalogo` consulta `stock_saldo` por SQL directo:** viola `02` §5.2.

**Ejemplo.** Con A, `PRODUCTO_MODIFICAR` de "Vino Rosado" con `activo = false` llama al verificador registrado; `stock` responde `True` (18 en "Camioneta 1") y el catálogo lanza `PRODUCTO_CON_STOCK`. En una prueba unitaria de catálogo se registra un verificador de prueba, como en INV-18.

#### D4.2 — Serialización de la desactivación con un movimiento simultáneo · técnica · ADR-048 (enmienda `02` §7.3)

> **APROBADA (A) — 2026-10-07.**

**Qué hay que decidir.** Hoy la desactivación no bloquea el producto y la única puerta lo lee sin bloqueo, así que un ingreso y una desactivación simultáneos pueden cruzarse: el ingreso ve el producto activo, la desactivación no ve stock, y queda stock en un producto recién desactivado. Leer las filas de saldo `FOR SHARE` no alcanza: el primer ingreso de un producto **crea** su fila de saldo y la desactivación no la vería.

- **A (recomendada). Mismo esquema que ADR-038 puntos 4 y 5 para las ubicaciones.** La desactivación toma el producto `FOR UPDATE` (`obtener_producto_por_id_para_actualizar`, ya existe) y el verificador de D4.1 lee los saldos de ese producto `FOR SHARE`. `registrar_movimientos` toma cada producto `FOR SHARE` (`catalogo_service.obtener_producto_para_compartir`, ya existe) por id ascendente, **después** de las ubicaciones y **antes** de `costo_producto` y `stock_saldo`. Así un movimiento y una desactivación del mismo producto se esperan: o el movimiento ve el producto inactivo (`PRODUCTO_INACTIVO`) o la desactivación ve el saldo (`PRODUCTO_CON_STOCK`). Enmienda `02` §7.3: el producto pasa a ser un nivel previo a `costo_producto` en todo camino que mueve stock (también stock inicial, compras e importación, que ganan ese bloqueo compartido). No hay interbloqueo: la desactivación solo toma el producto y después lee saldos; el movimiento toma el producto antes que cualquier saldo.
- **B. La desactivación bloquea `costo_producto`** del producto por el puerto (todo movimiento ya lo bloquea) y la única puerta vuelve a leer el producto **después** de bloquear costos: no agrega un nivel al orden, pero deja la validez de la regla en una relectura fácil de romper y hace que `catalogo` dispare, por el puerto, un bloqueo de `costeo`.
- **C. Sin serializar** (comprobación sin bloqueos): admite la carrera; contradice el criterio de ADR-038.

**Ejemplo.** A las 10:00:00 un Vendedor transfiere 6 de "Vino Rosado" a "Camioneta 1" y, a la vez, Administración lo desactiva (saldo cero en todos lados). Con A, si gana la transferencia, la desactivación espera y responde `PRODUCTO_CON_STOCK`; si gana la desactivación, la transferencia espera y responde `PRODUCTO_INACTIVO`. Nunca quedan 6 botellas de un producto inactivo.

#### D4.3 — La anulación de compra de un producto inactivo · de negocio · ADR-048

> **APROBADA (A) — 2026-10-07.** Tensión encontrada al incorporar D4; `docs/` no la resuelve.

**Qué hay que decidir.** ADR-044 punto 5 (change 11, D11) deja anular una compra aunque el producto esté inactivo. Con D4, un producto desactivado tiene saldo cero, así que esa anulación, si la hace alguien con `PERMITIR_STOCK_NEGATIVO`, deja un **saldo negativo en un producto inactivo**, que según D4 no se puede regularizar sin reactivarlo.

- **A (recomendada). No tocar ADR-044 punto 5.** Queda como caso residual y deuda nominada: la regla de D4 garantiza saldo cero **al desactivar**, no para siempre. Para regularizar ese negativo se reactiva el producto y se ajusta. No se toca el módulo de compras en este change.
- **B. La anulación de compra rechaza un producto inactivo** (`PRODUCTO_INACTIVO`): cierra el caso, pero enmienda ADR-044 punto 5 y obliga a reactivar el producto para anular una compra vieja.

**Ejemplo.** Compra de 60 de "Vino Rosado" en septiembre; se vendieron, el producto quedó en cero y se desactivó. En octubre el Administrador anula la compra: con A el depósito queda en −60 con la observación `STOCK_NEGATIVO` sobre un producto inactivo; con B recibe `PRODUCTO_INACTIVO` y debe reactivarlo antes.

### D5 — Corrección de una transferencia o un ajuste mal cargado: anulación · de negocio · ADR-048

> **APROBADA (B, con las reglas de abajo) — 2026-10-07.**

**Qué se decidió.** TR-06 prohíbe editar o borrar; la corrección es una **anulación**.

1. **Dos comandos nuevos**, solo `ONLINE`: `STOCK_TRANSFERENCIA_ANULAR` (`POST /api/v1/stock/transferencias/{id}/anulacion`) y `STOCK_AJUSTE_ANULAR` (`POST /api/v1/stock/ajustes/{id}/anulacion`), con `motivo_id` obligatorio. Anulación **total** (todas las líneas) y **una sola vez**: la segunda responde `TRANSFERENCIA_YA_ANULADA` / `AJUSTE_YA_ANULADO` (409), como `COMPRA_YA_ANULADA`.
2. **Ámbitos de motivo nuevos** `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE`, sobre el precedente de `ANULACION_PAGO` (change 12): la migración rehace `ck_motivo__ambito`, `AMBITOS_MOTIVO` los suma y se siembran motivos en la siembra y, de forma idempotente, en las organizaciones existentes que no tengan ninguno de ese ámbito (cuáles: D5.3). Un motivo inactivo o de otro ámbito es `MOTIVO_INVALIDO` (422); uno ajeno, 404.
3. **Estado en ambas cabeceras.** `transferencia.estado` y `ajuste_stock.estado` (este último no estaba en `03` §9) con `CONFIRMADA → ANULADA`, más `anulacion_motivo_id`, `anulada_en`/`anulado_en` y `anulada_por_id`/`anulado_por_id` atados por un `CHECK`, como `compra`. `app_runtime` recibe `UPDATE` **solo sobre esas cuatro columnas** de cada cabecera; las líneas y las tablas de libro siguen sin `UPDATE` ni `DELETE` (INV-05). `01` §18 suma dos filas: "Transferencia · Operativa · CONFIRMADA → ANULADA" y "Ajuste de stock · Operativa · CONFIRMADA → ANULADA".
4. **Movimientos inversos con el costo original.** Cada movimiento inverso lleva el mismo `costo_unitario` que su original (nulo si el original era nulo). El promedio no cambia y no hay historia de costo. La anulación de una transferencia deja el stock total igual (INV-15); la de un ajuste lo mueve en sentido contrario al ajuste. Cómo se representan en el libro: D5.1; cómo entra el costo por la única puerta: D5.2.
5. **Permisos.** Con `TRANSFERIR_STOCK` un usuario anula **solo las transferencias que él mismo creó** (`transferencia.usuario_id` = usuario del comando). Para anular la de otro hace falta el permiso nuevo **`ANULAR_TRANSFERENCIA`**, que entra al catálogo (40 permisos) y a las plantillas **Administrador y Administración (Gestor)**; la migración lo inserta y lo asigna a esos roles en las organizaciones existentes. Una transferencia **de otro usuario de la misma organización** sin `ANULAR_TRANSFERENCIA` responde **403 `PERMISO_REQUERIDO`** (el recurso existe y el usuario puede leerlo; 404 queda para lo de otra organización, INV-21). Los **ajustes** los anula cualquiera con `AJUSTAR_STOCK`, propios o ajenos, sin permiso nuevo. La combinación `ANULAR_TRANSFERENCIA` sin `TRANSFERIR_STOCK`: D5.4.
6. **Stock negativo al anular.** Si la anulación dejaría un saldo negativo (la camioneta ya vendió parte de lo transferido; el stock de un ajuste positivo ya salió), se rechaza con `STOCK_INSUFICIENTE` y nada se escribe, **salvo** que el usuario tenga `PERMITIR_STOCK_NEGATIVO`: entonces se acepta y el comando queda `ACEPTADO_CON_OBSERVACIONES` con `STOCK_NEGATIVO` por cada producto y ubicación bajo cero (mismo criterio que la anulación de compra, ADR-044). Vale para la anulación de transferencia y para la de un ajuste con líneas positivas. No contradice D1 = B: es una anulación, no un ajuste.
7. **Inactivos.** Si algún producto o alguna ubicación de la operación está inactivo, la anulación se rechaza (`PRODUCTO_INACTIVO` / `UBICACION_INACTIVA`), coherente con D4 y ADR-038 punto 5: un inactivo no puede recibir stock. Se reactiva, se anula y se vuelve a desactivar.
8. **Bloqueo y atomicidad.** La anulación toma la cabecera `FOR UPDATE` **antes** de todo lo demás (regla de `02` §7.3 para "las filas de la propia operación que el comando anula"), revalida el estado y recién entonces llama **una vez** a `registrar_movimientos` con todas las líneas inversas. Dos anulaciones simultáneas de la misma operación dejan un solo efecto. Todo o nada (INV-01).
9. **Auditoría.** Una fila por comando con el motivo de la anulación (D10).
10. **Pantallas** (D11): botón "Anular" en el detalle; estado visible en listados y kardex.

**Deuda nominada para el change 15:** anular una transferencia hacia o desde un vehículo con jornada abierta debe validar la toma (STK-09) cuando exista `jornada`.

**Alternativas consideradas.**

- **A. Sin anulación** (se corrige con la operación inversa a mano; `CHECK (estado = 'CONFIRMADA')`): descartada por el usuario: menos trazable, y el ajuste inverso pediría un motivo de `AJUSTE_STOCK` que no describe un error de carga.
- **C. Sin anulación y sin columna `estado`:** descartada: se aparta de `03` §9.
- **Anulación parcial** (por línea) o repetible: descartada: se anula todo y se carga de nuevo lo correcto.

**Ejemplo.** Marta (Vendedora) transfirió 60 de Vino A a "Camioneta 1" en lugar de 6. La anula ella misma con el motivo "Error de carga": el libro suma −60 en la camioneta y +60 en el depósito al mismo costo $1.050,000000 que los originales, la transferencia queda `ANULADA` y carga una nueva de 6. Si otro Vendedor, Pedro, intenta anularla, recibe 403; un Gestor (con `ANULAR_TRANSFERENCIA`) sí puede. Si la camioneta ya vendió 10 (quedan 50), la anulación de Marta da `STOCK_INSUFICIENTE`; la del Administrador se acepta y deja la camioneta en −10 con `STOCK_NEGATIVO`.

#### D5.1 — Cómo se representan los movimientos inversos en el libro · técnica · ADR-048

> **APROBADA (A) — 2026-10-07.**

**Qué hay que decidir.** STK-03 lista nueve tipos de movimiento y el `CHECK` de `stock_movimiento.tipo` los fija; no hay `ANULACION_TRANSFERENCIA` ni `ANULACION_AJUSTE`. `origen_tipo` no tiene `CHECK`.

- **A (recomendada). Se reutilizan los tipos existentes y cambia el origen.** La anulación de una transferencia escribe, por línea, `TRANSFERENCIA_SALIDA` (−q) en el **destino** y `TRANSFERENCIA_ENTRADA` (+q) en el **origen**, con `origen_tipo = 'ANULACION_TRANSFERENCIA'`. La de un ajuste escribe un `AJUSTE` de signo contrario por línea con `origen_tipo = 'ANULACION_AJUSTE_STOCK'` y, en `motivo_id`, el **motivo de la anulación**. En los dos casos `origen_id` es el id de la cabecera anulada (la misma de los movimientos originales). **No se migra `stock_movimiento`** y STK-03 queda igual; el kardex distingue un inverso por su `origen_tipo`. Se suma al final de STK-03 la aclaración de que los inversos de transferencias y ajustes reutilizan sus tipos.
- **B. Dos tipos nuevos** `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE`: simétrico con `ANULACION_COMPRA`, pero migra el `CHECK` del libro, cambia STK-03 y un solo tipo tendría los dos signos en la transferencia.
- **C. Sin distinguir el origen** (mismo `origen_tipo` que el original): el kardex no podría decir cuál es el inverso.

**Ejemplo.** Kardex de Vino A en "Camioneta 1" con A: "+60 · Entrada de transferencia · Transferencia (anulada)" y "−60 · Salida de transferencia · Anulación de transferencia"; las dos líneas enlazan al mismo detalle.

#### D5.2 — Cómo entra el costo original por la única puerta · técnica · ADR-048

> **APROBADA (A) — 2026-10-07.**

**Qué hay que decidir.** D9 dice que los ingresos de transferencia y de ajuste entran **sin** costo y se valorizan al promedio vigente; los inversos deben guardar el costo del **original** (D5 punto 4), que puede diferir del promedio de hoy.

- **A (recomendada). Costo explícito solo con origen de anulación.** `stock/service.py::anular_transferencia` y `::anular_ajuste` leen los movimientos originales del propio libro (por `origen_tipo` y `origen_id`) y arman cada línea inversa con su `costo_unitario`. En `domain/movimientos.py`, una línea de tipo `TRANSFERENCIA_SALIDA`, `TRANSFERENCIA_ENTRADA` o `AJUSTE` con `origen_tipo` de anulación **lleva** su costo (que puede ser nulo) y la puerta lo guarda tal cual; con cualquier otro origen, un costo en esos tipos sigue siendo `COSTO_INVALIDO`. `costeo` solo mueve `stock_total` (`aplicar_egreso` / `aplicar_ingreso_sin_recalculo`) y el valor que devuelve se descarta. `PRODUCTO_SIN_COSTO` no se aplica a un inverso (no es un ajuste nuevo). `puede_quedar_negativo` admite, con permiso, el `AJUSTE` negativo **solo** con origen `ANULACION_AJUSTE_STOCK` (D1, D5 punto 6).
- **B. Valorizar los inversos al promedio vigente** (sin costo, como cualquier ajuste): más simple, pero contradice la regla aprobada "mismo costo que los originales" y deja una diferencia de valor entre el ajuste y su anulación.
- **C. Una función aparte `stock.revertir_origen`** que escriba los inversos sin pasar por la puerta: abre una segunda puerta al libro (descartada también en ADR-044).

**Ejemplo.** Ajuste −6 de Vino A a $1.050,000000 el lunes; el martes una compra lleva el promedio a $1.100,000000; el miércoles se anula el ajuste: con A el inverso es +6 a $1.050,000000 (el ajuste y su anulación se compensan en valor: $6.300 y −$6.300) y el promedio sigue en $1.100,000000; con B sería +6 a $1.100,000000.

#### D5.3 — Motivos sembrados en los ámbitos nuevos · de negocio · ADR-048

> **APROBADA (A) — 2026-10-07.** Los nombres de motivos son catálogo de la organización (TR-09); `docs/` no los fija.

- **A (recomendada).** Dos motivos por ámbito, como el mínimo común de compras y pagos: `ANULACION_TRANSFERENCIA` → "Error de carga" y "Otro"; `ANULACION_AJUSTE` → "Error de carga" y "Otro".
- **B. Un solo motivo "Error de carga"** por ámbito.
- **C. Sin sembrar:** la organización no podría anular hasta que exista el alta de motivos (no está en este change).

**Ejemplo.** Con A, el diálogo "Anular transferencia" ofrece "Error de carga" y "Otro".

#### D5.4 — `ANULAR_TRANSFERENCIA` sin `TRANSFERIR_STOCK` · de negocio · ADR-048

> **APROBADA (A) — 2026-10-07.** No ocurre en las plantillas (ADM y GES tienen los dos), pero los roles son editables (`01` §19).

- **A (recomendada). `TRANSFERIR_STOCK` es siempre necesario** para `STOCK_TRANSFERENCIA_ANULAR`; `ANULAR_TRANSFERENCIA` solo **agrega** el alcance sobre las transferencias ajenas. No se abre ninguna lectura nueva (D7 queda igual: transferencias se leen con `TRANSFERIR_STOCK`).
- **B. Cualquiera de los dos alcanza** (`requiere_algun_permiso`), y las lecturas de transferencias se abren también a `ANULAR_TRANSFERENCIA`, como `ANULAR_PAGO_PROVEEDOR` con los pagos (ADR-046).

**Ejemplo.** Un rol a medida "Auditor de stock" con solo `ANULAR_TRANSFERENCIA`: con A no ve ni anula transferencias (403); con B las ve y anula cualquiera.

### D6 — Contenido de los comandos · de negocio · ADR-048

> **APROBADA (A) — 2026-10-07.**

**Qué se decidió.** `STOCK_TRANSFERIR` y `STOCK_AJUSTAR` llevan de 1 a 200 líneas (`LINEAS_INVALIDAS`), sin producto repetido (`PRODUCTO_REPETIDO`), con `cantidad_base` entera en unidad base (INV-04). Transferencia: `ubicacion_origen_id`, `ubicacion_destino_id` distintas (`UBICACIONES_IGUALES`, 422), cantidades mayores que cero (`CANTIDAD_INVALIDA`) y `observacion` opcional. Ajuste: `ubicacion_id`, `motivo_id` activo del ámbito `AJUSTE_STOCK` de la organización (`MOTIVO_INVALIDO`, 422; ajeno, 404), cantidades distintas de cero y **signos mezclados admitidos** (un conteo puede dar sobrantes y faltantes), `observacion` opcional. Observación recortada, vacía como nula, hasta 500 caracteres. Sin campo de fecha: rige el `occurred_at` del sobre (TR-05). Un motivo por ajuste, no por línea (`03` §9). Las dos anulaciones (D5) llevan solo el id de la operación (en la ruta) y `motivo_id`, como `COMPRA_ANULAR`.

**Alternativas consideradas.**

- **B. Observación obligatoria con el motivo "Otro":** descartada: requiere distinguir "Otro" por nombre o agregar un indicador al motivo.
- **C. Un ajuste de un solo producto por comando:** descartada: un conteo de 30 productos serían 30 comandos.

**Ejemplo.** Conteo en "Camioneta 1": Vino A −2 y Agua 500 +1, motivo "Diferencia de inventario": un solo ajuste con dos líneas.

### D7 — Permisos de lectura y selector de productos · de negocio · ADR-048

> **APROBADA (A, sin agregados) — 2026-10-07.** Precisa ADR-036.

**Qué se decidió.** `GET /stock/transferencias` y `GET /stock/transferencias/{id}` con `TRANSFERIR_STOCK`; `GET /stock/ajustes` y `GET /stock/ajustes/{id}` con `AJUSTAR_STOCK`. Los campos de costo de un ajuste se omiten sin `VER_COSTOS` (ADR-036 punto 4). El kardex (`TRANSFERIR_STOCK`) agrega el nombre del motivo de un movimiento `AJUSTE`. **Selector:** la transferencia elige productos del stock de la ubicación de origen (`GET /stock/ubicaciones/{id}/saldos`, ya con `TRANSFERIR_STOCK`); el ajuste usa `GET /catalogo/productos`, que exige `GESTIONAR_CATALOGO` y que en las plantillas tiene todo rol con `AJUSTAR_STOCK` (ADM, GES). No se abre ninguna lectura nueva.

**Consecuencia anotada.** Desde la pantalla **no se puede elegir** un producto con saldo cero o sin fila de saldo en el origen, **aunque el usuario tenga `PERMITIR_STOCK_NEGATIVO`**: el permiso sirve para transferir más de lo que hay de un producto que ya figura en el origen (48 en el depósito, se transfieren 60), no para transferir uno que no figura. La API sí lo admite; la limitación es solo del selector.

**Alternativas consideradas.**

- **B. Abrir `GET /catalogo/productos` en lectura a `TRANSFERIR_STOCK` y `AJUSTAR_STOCK`:** descartada: el Vendedor vería los 100 productos del catálogo, incluidos los que no hay.
- **C. Lecturas de ajustes también con `TRANSFERIR_STOCK`:** descartada: el Vendedor vería las roturas de toda la organización.

**Ejemplo.** Un Vendedor carga su camioneta: ve solo los productos con stock en el depósito; no ve el listado de ajustes, pero sí en el kardex "Ajuste −2 · Rotura". El Administrador quiere transferir 24 de "Agua 500", que no tiene saldo en el depósito porque la compra no se cargó: no aparece en el selector; carga primero la compra.

### D8 — Modelo de datos y migración · técnica · ADR-048

> **APROBADA (A) — 2026-10-07, ajustada por D5 = B** (estado, columnas de anulación y `UPDATE` acotado; ámbitos y permiso). Precisa `03` §9.

**Qué se decidió.** **Una sola** revisión de Alembic (lote 1) que:

- Crea las cuatro tablas con `UNIQUE (organizacion_id, id)`, FK compuestas a `ubicacion`, `producto`, `motivo`, `usuario` y `dispositivo`, columnas de operación completas (`operation_id`, `usuario_id`, `dispositivo_id`, `occurred_at`, `registered_at`, como `compra`; sin `UNIQUE` sobre `operation_id`, porque INV-06 ya lo garantiza la reserva en `comando`). Agrega `transferencia.observacion` (no está en `03`), `orden integer` en las líneas con `UNIQUE (cabecera, orden)`, `CHECK (origen <> destino)`, `CHECK (cantidad_base > 0)` en `transferencia_linea` y `CHECK (cantidad_base <> 0)` en `ajuste_stock_linea`; `ajuste_stock_linea.costo_unitario` nulable (D3). Índices `(organizacion_id, occurred_at DESC, id DESC)` en ambas cabeceras para el listado y por ubicación.
- **Estado y anulación (D5):** `estado` en `transferencia` **y en `ajuste_stock`** con `CHECK (estado IN ('CONFIRMADA','ANULADA'))`, y `anulacion_motivo_id` (FK compuesta a `motivo`), `anulada_en`/`anulado_en` (`timestamptz`) y `anulada_por_id`/`anulado_por_id` (FK compuesta a `usuario`), con el `CHECK` de coherencia de `compra` (las tres son no nulas si y solo si el estado es `ANULADA`).
- **Privilegios de `app_runtime`:** `SELECT, INSERT` en las cuatro; `UPDATE` **solo** sobre `estado` y las tres columnas de anulación de cada cabecera; sin `UPDATE` sobre las líneas y sin `DELETE` en ninguna (INV-05).
- **Catálogos:** rehace `ck_motivo__ambito` con `ANULACION_TRANSFERENCIA` y `ANULACION_AJUSTE` y siembra sus motivos (D5.3) en las organizaciones existentes; inserta el permiso `ANULAR_TRANSFERENCIA` y lo asigna a los roles de plantilla Administrador y Administración de las organizaciones existentes (D5 punto 5).
- **Libro:** los movimientos usan `origen_tipo = 'TRANSFERENCIA'` u `'AJUSTE_STOCK'` (y los de anulación, D5.1) y `origen_id` = id de la cabecera; los de ajuste llevan `motivo_id`. **No se migra `stock_movimiento`, `costo_producto_mov` ni `auditoria`** (D10).

**Alternativa considerada — B. Sin tablas de cabecera ni líneas** (la operación se reconstruye del libro por `operation_id`): descartada: se aparta de `03` §9 y deja la observación, el motivo y el estado sin lugar propio.

**Ejemplo.** La transferencia de 48 de Vino A deja una fila en `transferencia` (`CONFIRMADA`), una en `transferencia_linea` y dos en `stock_movimiento` (−48 depósito, +48 camioneta) con `origen_tipo = 'TRANSFERENCIA'` y el mismo `origen_id`. Al anularla, la cabecera pasa a `ANULADA` con su motivo, momento y usuario, y el libro suma dos filas más; `app_runtime` no puede cambiar `ubicacion_destino_id` ni la cantidad de la línea.

### D9 — Cómo se aplica en el libro y en costeo · técnica · ADR-048

> **APROBADA (A) — 2026-10-07, ajustada por D1 = B, D4 y D5.** Enmienda las consecuencias de ADR-039 y el punto 4 de ADR-044.

**Qué se decidió.** `registrar_movimientos` sigue siendo la **única puerta**. En `stock/domain/movimientos.py`:

- Los ingresos `TRANSFERENCIA_ENTRADA` y `AJUSTE` se admiten **sin costo** (con costo es `COSTO_INVALIDO`, salvo origen de anulación, D5.2) y no recalculan.
- `permitir_negativo` se extiende **solo a `TRANSFERENCIA_SALIDA`** (D1 = B). Un `AJUSTE` negativo nunca queda bajo cero, salvo el inverso de una anulación de ajuste con permiso (D5 punto 6, D5.2).
- **Todos los tipos de este change exigen el producto activo** (D4): `productos_que_exigen_estar_activos` no cambia.

En `costeo/service.py` se agrega `aplicar_ingreso_sin_recalculo(producto, cantidad)` → sube `stock_total` y devuelve el promedio vigente (función pura en `costeo/domain`). La transferencia llama **una sola vez** a `registrar_movimientos` con las líneas `[salida_1, entrada_1, salida_2, ...]`: los bloqueos se toman una vez en el orden global (ubicaciones `FOR SHARE` por id, productos `FOR SHARE` por id si D4.2 = A, `costo_producto` por producto, `stock_saldo` por `(producto, ubicacion)`), y cada salida se aplica antes que su entrada. Los servicios nuevos `stock/service.py::transferir`, `::ajustar`, `::anular_transferencia` y `::anular_ajuste` validan la cabecera (D6), resuelven el motivo por `configuracion/service.py`, comprueban `PRODUCTO_SIN_COSTO` con la fila de costo ya bloqueada, insertan o actualizan cabecera y líneas y llaman a la puerta. Ninguno bloquea filas de saldo o de costo por su cuenta (ADR-015); las anulaciones toman antes solo su propia cabecera (D5 punto 8).

**Alternativa considerada — B. Una función `stock.transferir` que solo mueve `stock_saldo`** sin pasar por `costeo`: descartada: abre una segunda puerta al libro y la transferencia de un producto sin fila de costo no la crearía.

**Ejemplo.** Transferencia A→B y otra B→A de Vino A y Agua 500 al mismo tiempo: las dos bloquean `costo_producto` (Agua, Vino por id) y luego los cuatro saldos en el mismo orden, así que una espera a la otra sin interbloqueo.

### D10 — Auditoría y observaciones: el bus copia el motivo · técnica (gobernanza crítica) · ADR-048 (enmienda ADR-022)

> **APROBADA (B, acotada a este change) — 2026-10-07.** Aprobación explícita del usuario para este alcance **y nada más**.

**Qué se decidió.** El handler devuelve el motivo y el bus lo copia a **su** fila de auditoría (sigue siendo una sola fila por comando, ADR-022). **No hay migración:** la tabla `auditoria` ya tiene la columna `motivo_id` y `identidad_service.registrar_auditoria` ya la acepta; hoy el bus no la llena.

- **Alcance: tres comandos.** `STOCK_AJUSTAR` (el motivo del ajuste, AUD-01, AUD-02), `STOCK_TRANSFERENCIA_ANULAR` y `STOCK_AJUSTE_ANULAR` (el motivo de la anulación). `STOCK_TRANSFERIR` no lleva motivo y su fila queda con `motivo_id` nulo.
- **Fuera del alcance, deuda nominada:** `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` siguen dejando `motivo_id` nulo en la auditoría (su motivo está en la cabecera, alcanzable por `operation_id`); se llevan al change que las toque o al 26/28. La columna `auditoria.observacion` **sigue sin llenarse**: lo aprobado es el motivo.
- **Nada más cambia en la auditoría:** misma acción (tipo de comando), misma entidad, mismo `operation_id`; un reenvío idempotente no ejecuta el handler y no escribe otra fila; un comando rechazado no deja fila con motivo.
- **Observaciones:** `STOCK_NEGATIVO` (D1, D5) se emite con `operacion_tipo` `TRANSFERENCIA` o `AJUSTE_STOCK`, el id de la cabecera y en `detalle` el producto, la ubicación y el saldo resultante.

**Alternativas consideradas.**

- **A. Solo la auditoría del bus sin motivo** (el motivo se lee de la operación por `operation_id`): descartada: no cumple AUD-02 al pie de la letra.
- **C. El servicio escribe una segunda fila de auditoría** con el motivo: descartada: duplica la auditoría del comando (contradice ADR-022).
- **B sin acotar** (también compras y pagos): descartada por alcance: toca dos comandos de otro módulo ya archivados.

**Ejemplo.** Ajuste −6 por "Rotura": la consulta de auditoría (change 26/28) muestra `STOCK_AJUSTAR`, el usuario, el `operation_id` y el motivo "Rotura" en la misma fila. La anulación de la transferencia de Marta muestra `STOCK_TRANSFERENCIA_ANULAR` con "Error de carga".

#### D10.1 — Cómo le llega el motivo al bus · técnica · ADR-048

> **APROBADA (A) — 2026-10-07.**

**Qué hay que decidir.** El resultado de un handler es una tupla (`ResultadoHandler`; con observaciones, un cuarto elemento). `app/commands` no puede importar módulos de negocio (`commands-no-modulos`).

- **A (recomendada). El resultado del handler gana un dato opcional de auditoría**, declarado en `app/commands` (por ejemplo `DatosDeAuditoria(motivo_id: UUID | None)`) y devuelto junto con las observaciones; `sync/service.py` lo pasa a `registrar_auditoria(motivo_id=...)`. Los handlers existentes no cambian (ausente = nulo). Un ratchet exige que los tres comandos del alcance lo devuelvan.
- **B. El bus lee `motivo_id` del contenido del comando por nombre de campo:** sin tocar los handlers, pero acopla el bus a la forma de cada contenido y alcanzaría, sin quererlo, a `COMPRA_ANULAR` y `PAGO_PROVEEDOR_ANULAR` (fuera del alcance aprobado).
- **C. Una variable de contexto** que el servicio de stock escribe y el bus lee: efecto lateral invisible en la firma.

**Ejemplo.** Con A, `manejar_stock_ajustar` devuelve el resultado, las observaciones y `DatosDeAuditoria(motivo_id=<Rotura>)`; `manejar_compra_anular` sigue devolviendo lo de siempre y su fila queda con `motivo_id` nulo.

### D11 — Pantallas `/admin` · de negocio

> **APROBADA (A) — 2026-10-07, con lo que suma D5.**

**Qué se decidió.** Dos pantallas nuevas en la sección Stock, cada una con su permiso: **Transferencias** (listado con filtros de ubicación y fechas, alta, detalle) y **Ajustes** (listado con filtros de ubicación, motivo y fechas, alta, detalle). En las altas, cada línea muestra en cajas + unidades (CAT-08) el saldo actual y el resultante en origen y destino (o en la ubicación del ajuste) y marca en rojo un resultado negativo; el botón avisa que requiere conexión y reutiliza el `operation_id` en el reintento. Desde el stock por ubicación: "Transferir desde acá" y "Ajustar" (esta última precargada con la cantidad que lleva a cero un saldo negativo, D2). En el kardex, el motivo del ajuste y un enlace al detalle de la operación (solo si el usuario tiene el permiso de lectura). Sin importes calculados en el frontend.

**Por D5:** el **estado** (`Confirmada` / `Anulada`) se ve en los dos listados, en los detalles y en el kardex (la operación de origen anulada y sus movimientos inversos). El detalle ofrece **"Anular"** solo si la operación está confirmada y el usuario puede anularla (transferencia: propia con `TRANSFERIR_STOCK` o cualquiera con `ANULAR_TRANSFERENCIA`; ajuste: `AJUSTAR_STOCK`); abre un diálogo con el motivo obligatorio del ámbito que corresponde, avisa que requiere conexión y muestra el mensaje del servidor ante `STOCK_INSUFICIENTE`, `PRODUCTO_INACTIVO`, `UBICACION_INACTIVA` o "ya anulada". El detalle de una operación anulada muestra motivo, usuario y momento de la anulación. **Por D4:** el formulario de producto del catálogo muestra el mensaje de `PRODUCTO_CON_STOCK` al desactivar.

**Alternativa considerada — B. Una sola pantalla "Movimientos de stock"** con pestañas: descartada: cada operación tiene su permiso.

**Ejemplo.** El Vendedor abre "Stock → Transferencias → Nueva", elige depósito → "Camioneta 1", ve Vino A "20 cajas" en el depósito, carga "8 cajas" y ve "Depósito: 12 cajas · Camioneta: 8 cajas" antes de confirmar. Después abre el detalle, toca "Anular", elige "Error de carga" y la transferencia pasa a "Anulada".

## Risks / Trade-offs

- [El change supera el tamaño de `04` §2] → aceptado por el usuario; cuatro lotes con revisión entre cada uno (D0).
- [El stock inicial queda cerrado para un producto en cuanto se transfiere o se ajusta, y anular no lo reabre (STK-10)] → la pantalla de stock inicial ya muestra `PRODUCTO_CON_OPERACIONES`; se avisa en la verificación manual y en la propuesta de docs. Cargar todo el stock inicial antes de empezar a transferir.
- [Un Administrador puede dejar stock negativo con una transferencia o con una anulación (D1, D5)] → solo ADM tiene `PERMITIR_STOCK_NEGATIVO`; la observación queda pendiente para el change 25 y el stock por ubicación marca el saldo.
- [Productos ya inactivos con stock, o con saldo negativo por una anulación de compra (D4, D4.3)] → no se migran; se listan en la verificación manual; se vacían reactivando.
- [Cambio en la única puerta del libro (tipos nuevos y, si D4.2 = A, bloqueo compartido del producto en todo movimiento): regresiones en stock inicial, compras e importación] → red de seguridad con sus suites antes de tocar `movimientos.py`, `service.py` y `costeo`; prueba de concurrencia de desactivación contra ingreso.
- [Tercer puerto de registro en `catalogo/service.py` (D4.1): un arranque que no importe `stock.commands` (que importa `stock/service.py`, donde se registra el verificador) deja el puerto vacío] → falla cerrado y prueba de arranque, como ADR-025.
- [Cambio en el bus y en la auditoría (D10), dominio crítico] → alcance cerrado a tres comandos, ratchet que lo fija y prueba de que los demás comandos siguen dejando `motivo_id` nulo.
- [Permiso nuevo en el catálogo y en plantillas (D5)] → las pruebas que cuentan 39 permisos pasan a 40; la migración solo agrega filas a `permiso` y `rol_permiso`.
- [`UPDATE` sobre las cabeceras] → acotado por columna, como `compra`; una prueba confirma que `app_runtime` no puede cambiar ninguna otra columna ni las líneas.
- [Transferir a un vehículo sin jornada, o anular esa transferencia (STK-09 llega en el 15)] → deuda nominada para el change 15.
- [Dos transferencias opuestas, una transferencia y una desactivación de ubicación, o dos anulaciones concurrentes] → pruebas de concurrencia con commits reales (D9, D5 punto 8, ADR-038 punto 4).

## Migration Plan

Una revisión de Alembic sobre la cabeza actual (`e2f3a4b5c6d7`, listas de precios) que **crea** las cuatro tablas con sus restricciones, índices y privilegios, **rehace** `ck_motivo__ambito` con los dos ámbitos nuevos y **agrega** filas de catálogo (motivos de anulación, permiso `ANULAR_TRANSFERENCIA` y su asignación a las plantillas). No modifica filas existentes ni toca `stock_movimiento`, `costo_producto_mov` ni `auditoria`. `downgrade` elimina las tablas, los motivos de los dos ámbitos, el permiso y sus asignaciones, y restaura el `CHECK` (pérdida explícita de transferencias, ajustes, sus anulaciones, esos motivos y ese permiso; sus movimientos quedan en el libro; aserción en la prueba de ciclo). Sin dependencias nuevas: no hace falta reconstruir imágenes. Los productos ya inactivos con stock no se tocan (D4).

## Open Questions

Las ocho subdecisiones pendientes: **D4.1, D4.2, D5.1, D5.2, D10.1** (técnicas) y **D4.3, D5.3, D5.4** (de negocio). Ninguna otra.
