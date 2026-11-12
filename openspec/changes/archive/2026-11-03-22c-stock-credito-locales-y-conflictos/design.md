# Diseño técnico — 22c-stock-credito-locales-y-conflictos

> **Estado: DECISIONES APROBADAS (2026-11-02).** El usuario aprobó **D0 a D9 con la opción recomendada A** (D0 = A: el change se divide; la anulación sin conexión, VTA-24, pasa al change nuevo 22d `anulacion-sin-conexion`, antes del 23). Los textos de ayuda y de pantalla (tarea 0.2: D5, D9, D4 y D6) fueron aprobados **tal como están propuestos, sin cambios y sin ejemplos**. Cada decisión conserva sus opciones y consecuencias; la recomendada es **A**. Las decisiones se documentan en **ADR-065** (*Propuesto* hasta el archivo, `docs/adr/ADR-065-conciliacion-local-y-conflictos-en-el-telefono.md`).
>
> **Gobernanza.** Ninguna decisión es **CRÍTICA** (no se toca autenticación, permisos ni dinero del servidor). **MEDIA:** D1 a D6 y D8. **BAJA:** D0, D7, D9. **De negocio** (el agente solo recomienda; decide el usuario): **D0, D1, D2, D4, D6**. **Cambian `docs/`:** D1 (CRE-08, SYN-11, `02` §13.2 y §13.4), D3 (`02` §6.4), D7 (`02` §17) y D0 (`04` §11: el change nuevo 22d).
>
> **Revisión.** Decisiones (0.1) y textos de ayuda y de pantalla (0.2) antes del apply. El usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Teléfono (22a, 22b).** `domain/ruta/disponiblesLocales.ts` calcula saldo y stock como bootstrap + movimientos de la jornada con `estado_operacion = 'PENDIENTE'`; el 22b no cambia ese campo (ADR-064 D4), así que una venta aceptada sigue contando y, tras «Actualizar datos», cuenta dos veces. `sync/aplicarResultados.ts` escribe `cola.estado`, `error_codigo`, `resultado_en` y `ventas.estado_envio` en una transacción. La pantalla «Sincronización» lista «Con observaciones» y «Rechazadas» con un texto general y el código (ADR-064 D8). Stock y la ficha del cliente muestran los valores del bootstrap; solo Vender usa los locales.
- **Servidor.** `comando` guarda `jornada_id`, `dispositivo_id` y `secuencia` con el índice `ix_comando__org_dispositivo_secuencia`. El bootstrap se lee en una sola foto `REPEATABLE READ READ ONLY` (ADR-062). El lote responde por ítem `operation_id`, `estado`, `resultado` y `error_codigo`, **sin** las observaciones, aunque la spec `sync/lote-de-comandos` ya dice «y las observaciones». Las observaciones viven en `observacion` (código del catálogo SYN-07, detalle JSON), unidas al comando. `02` §17 ya se cumple en parte: el lote registra `lote_tamano` y cada comando su duración, resultado y reintentos.
- **INV-17** tiene pruebas dispersas que lo citan (ventas, cobranzas, permisos, cartera, jornada liberada), pero ninguna que recorra todas las reglas de SYN-05.

Lo que `docs/` **no** resuelve: cómo dejar de contar dos veces sin perder lo que el servidor todavía no tiene (D1); qué hacer con una venta rechazada (D2); cómo llega el detalle de las observaciones (D3); dónde se ve (D4); qué dice cada código (D5); si las pantallas de consulta muestran los disponibles locales (D6); qué métrica falta (D7); cómo se cierra INV-17 (D8); la ayuda (D9). Y el alcance (D0).

## Goals / Non-Goals

**Goals:** saldo y stock locales exactos después de sincronizar y actualizar, aunque se pierda una respuesta; que el vendedor entienda qué anotó o por qué rechazó el sistema cada venta, sin señal; disponibles locales en Stock, Productos y la ficha; cerrar INV-17 y las métricas de `02` §17.

**Non-Goals:** la anulación sin conexión (D0 = A la pasa al 22d); reenviar a mano un rechazado; resolver observaciones (25); la cobranza independiente sin conexión (23), aunque la regla de D1 ya la cubre; métricas en el teléfono.

## Decisions

### D0 — Alcance y división · alcance · BAJA · de negocio · `04` §11

**Resultado (2026-11-02): aprobada la opción A.**

`04` §11 pone en el 22c cuatro frentes: disponibles locales y su conciliación, anulación sin conexión (VTA-24), pantalla de conflictos y métricas; y advierte: «Si 22b o 22c se desbordan: pausar, revisar el alcance y dividir». La anulación sin conexión sola es del tamaño del change 19: comando `OFFLINE` con reglas nuevas en el servidor (jornada de la venta, venta inexistente, ya anulada, motivo dado de baja, ubicación tomada al sincronizar), efectos locales inversos en Dexie, pantalla de anulación en `/ruta` con devolución y consumidor final, y su interacción con la cola y la conciliación.

- **A (recomendada). Dividir.** Este change (22c) entrega conciliación, disponibles en pantallas, observaciones y rechazos, métricas y el cierre de INV-17, en **cuatro lotes**: **Lote 1** servidor (marca de secuencia en el bootstrap, observaciones en el resultado del lote, resumen por lote, fixture de códigos, prueba de INV-17); **Lote 2** núcleo del teléfono (tipos, resultados con observaciones, regla de conciliación); **Lote 3** pantallas y ayuda; **Lote 4** punta a punta, ADR, docs, cobertura, suites y prueba manual. Se agrega al roadmap el **22d `anulacion-sin-conexion`** (VTA-24, deuda del 19, ADR-058), que depende del 22c y va antes del 23. Consecuencia: el 22c se prueba solo; la regla de conciliación (D1) ya es por operación, así que el 22d solo suma tipos de movimiento; hay una prueba manual más.
- **B. Todo en el 22c**, en seis lotes (los cuatro de A más servidor y teléfono de la anulación). Si se elige B, se agregan antes del apply estas decisiones (con la recomendación entre paréntesis): «jornada en curso» = la venta y la anulación con la jornada del sobre, si no `JORNADA_AJENA` (A); venta inexistente = `VENTA_INEXISTENTE`, rechazo por dependencia inexistente (A); ya anulada = rechazo `VENTA_YA_ANULADA` (A); motivo dado de baja después del bootstrap = se acepta (A, como ADR-063 D11); ubicación tomada al sincronizar = se acepta con `UBICACION_TOMADA_AL_SINCRONIZAR` (A, cambia SYN-07); efectos locales = movimientos inversos con la operación de la anulación (A); en `/ruta` la anulación va siempre por la cola (A, como ADR-063 D1). Consecuencia: un solo change, el más grande del proyecto, contra la advertencia de `04`.

### D1 — Cómo se dejan de contar las operaciones que el bootstrap ya incluye · negocio · MEDIA · CRE-08, RUT-04, SYN-11

**Resultado (2026-11-02): aprobada la opción A.**

El saldo y el stock del bootstrap ya incluyen toda venta que el servidor procesó antes de la foto. El teléfono tiene que dejar de sumarlas, pero no antes (si no, «olvida» la venta entre la sincronización y la próxima actualización: ADR-064 D4 opción C).

- **A (recomendada). Marca de secuencia por jornada.** El bootstrap trae, dentro de la sesión, `secuencia_procesada`: la mayor `secuencia` de los comandos de la jornada del bootstrap (de ese usuario y ese dispositivo) que el servidor tiene registrados en la foto (`NULL` si ninguno). El teléfono la guarda con la sesión. Un movimiento local de la jornada cuenta si y solo si la secuencia de su operación es **mayor** que la marca, o su operación es una venta «Rechazada» (D2). La cola de una jornada se procesa en orden (`02` §6.4) y un corte transitorio detiene el lote, así que todo comando con secuencia menor o igual ya fue procesado (o rechazado sin efecto). Consecuencia: exacto aunque se pierda la respuesta del lote (la foto sabe lo que el teléfono todavía no); el bootstrap no toca `movimientos_locales` (`02` §13.4 sigue igual); un bootstrap sin la marca (anterior al 22c) cuenta todo, como hoy; la consulta usa el índice existente, sin migración; sirve igual para la cobranza (23) y la anulación (22d).
- **B. Orden en el teléfono.** Al aplicar un bootstrap pedido después de recibir un `ACEPTADO`, esas operaciones dejan de contar; sincronización y bootstrap bajo el mismo candado. Consecuencia: sin cambio en el servidor, pero con la respuesta perdida la venta cuenta dos veces hasta otro bootstrap, y depende del orden entre pestañas.
- **C. Lista de operaciones.** El bootstrap trae los `operation_id` de la jornada ya procesados. Consecuencia: exacto, pero crece con cada venta del día y repite lo que la marca resume.

### D2 — Una venta rechazada en el saldo y el stock locales · negocio · MEDIA · SYN-06, SYN-09, RUT-04

**Resultado (2026-11-02): aprobada la opción A.**

**Precisión aprobada 2026-11-02:** una venta rechazada sigue contando **completa** (stock, débito y su cobro en el momento, todos con el mismo `operation_id`) hasta que termine la jornada; así el cobro en el momento no deja de restar y el teléfono no muestra al cliente debiendo toda la venta. La cobranza suelta sin conexión llega en el change 23, que decidirá su propia regla. Un movimiento cuya operación no está en la cola sigue contando (aprobado así).

Una venta rechazada no tiene efecto en el servidor, pero la mercadería ya se entregó y el cliente la debe.

- **A (recomendada). Sigue contando** en el saldo y el stock locales de su jornada (no le aplica la marca de D1), hasta que la jornada termine. Consecuencia: lo conservador (el teléfono no ofrece mercadería que no está ni crédito de más); la diferencia con el servidor la corrige administración y la rendición (24) la muestra en el conteo; el texto de «Rechazada» lo dice (D9).
- **B. Deja de contar** al recibir el rechazo, como en el servidor. Consecuencia: el teléfono puede ofrecer stock que ya no está en el vehículo y crédito que el cliente ya usó.

### D3 — Cómo llega el detalle de las observaciones · técnica · MEDIA · SYN-04, SYN-07, `02` §6.4

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada). En el resultado del lote.** Cada ítem suma `observaciones`: lista de `codigo`, `operacion_tipo`, `operacion_id` y `detalle` (vacía si no hay), leída de `observacion` por el comando; el reenvío de un comando ya procesado devuelve las mismas (INV-06). El teléfono las guarda en la fila de `cola`, en la misma transacción que el resultado (INV-01), sin versión nueva de Dexie (no hay índice nuevo). Expone solo lo del propio comando del usuario autenticado. Consecuencia: el detalle queda en el teléfono y se ve sin señal; es un campo agregado, compatible con el teléfono del 22b. Las ventas aceptadas antes del 22c no tienen el detalle guardado: muestran «El detalle no está en el teléfono; consultalo con administración.».
- **B. Lectura aparte** (`GET /api/v1/sync/comandos/{operation_id}/observaciones`) al abrir el detalle. Consecuencia: sin señal no se ve; un endpoint y un permiso más.
- **C. Solo los códigos** en el resultado. Consecuencia: sin producto, medio ni autorizador, varias observaciones no se entienden.

### D4 — Dónde se ven las observaciones y los rechazos («pantalla de conflictos») · negocio · MEDIA · `02` §13.3

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada). Sin pantalla nueva.** «Sincronización» sigue con su lista de «Con observaciones» y «Rechazadas» (ADR-064 D8) y cada fila lleva un resumen (primera observación traducida o el texto del rechazo); el **detalle de la venta** («Venta guardada», al que se llega desde esa lista y desde «Ventas de hoy») suma la sección «Observaciones» (todas, traducidas) o «Motivo del rechazo» (texto, código y el aviso de que sigue guardada). Consecuencia: un solo lugar para cada venta; no hay ruta nueva que precachear.
- **B. Pantalla nueva `/ruta/conflictos`** con todas las observaciones y rechazos. Consecuencia: duplica la lista de «Sincronización».

### D5 — Qué dice cada código · interfaz · MEDIA · SYN-06, SYN-07

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada). Tabla cerrada y fixture compartido.** `shared/fixtures/sync/codigos-de-sincronizacion.json` lista los 16 códigos de SYN-07 y los códigos de rechazo que puede recibir una venta sin conexión (bus: `JORNADA_INEXISTENTE`, `JORNADA_REQUERIDA`, `JORNADA_AJENA`, `DISPOSITIVO_REVOCADO`, `COMANDO_INCONSISTENTE`, `MODO_NO_ADMITIDO_PARA_TIPO`, `TIPO_DE_COMANDO_DESCONOCIDO`, `VERSION_DE_COMANDO_SIN_HANDLER`, `CONTENIDO_DE_COMANDO_INVALIDO`; venta: `TOTALES_INCONSISTENTES`, `CREDITO_INCONSISTENTE`, `VENTA_DUPLICADA`, `NUMERO_DUPLICADO` y las validaciones de contenido; la lista final la fija una prueba del Lote 1). Una prueba del servidor exige que los de SYN-07 sean exactamente los del catálogo de observaciones y que cada código de rechazo exista en el servidor; una de Vitest, que cada código tenga su texto. Un código desconocido muestra «El sistema no aceptó esta venta.» con el código. Textos propuestos (pantalla, sin ejemplos; se aprueban en 0.2; `{…}` sale del detalle con los nombres de la base local, o «un producto» si ya no está):
  - Observaciones: `STOCK_NEGATIVO` «Quedó stock negativo de {producto}.» · `EXCESO_CREDITO_ADVERTIDO` «La venta superó el crédito del cliente.» · `EXCESO_CREDITO_AUTORIZADO_OFFLINE` «La venta superó el crédito dentro de la tolerancia sin señal.» · `EXCESO_CREDITO_DETECTADO_SYNC` «Con la deuda real del cliente, la venta superó su crédito.» · `LISTA_NO_VIGENTE` «Los precios no eran los de la versión vigente de la lista en ese momento.» · `DESCUENTO_DIFIERE` «El descuento no coincide con el que calcula el sistema.» · `CLIENTE_NO_HABILITADO` «El cliente estaba suspendido o inactivo cuando llegó la venta.» · `PERMISO_REVOCADO` «Cuando llegó la operación, tu usuario ya no tenía el permiso.» · `JORNADA_LIBERADA` «La jornada había sido liberada cuando llegó la venta.» · `ANULACION_COMPRA_SIN_RECALCULO` «La anulación de la compra no recalculó el costo.» · `MEDIO_INACTIVO` «El medio {medio} estaba dado de baja cuando llegó el cobro.» · `REFERENCIA_FALTANTE` «El cobro con {medio} llegó sin la referencia que pide ese medio.» · `VENTA_SIN_COSTO` «{producto} no tenía costo; la línea quedó sin costo.» · `CONSUMIDOR_FINAL_CON_DEUDA` «La venta al consumidor final quedó con deuda.» · `UBICACION_TOMADA_AL_SINCRONIZAR` «Cuando llegó la venta, el vehículo estaba en rendición o en la jornada de otro vendedor.» · `AUTORIZACION_OFFLINE` «{autorizador} autorizó el {descuento | exceso de crédito} sin señal.»
  - Rechazos (siempre seguidos de «Sigue guardada en el teléfono; avisá a administración.»): `JORNADA_INEXISTENTE` «La jornada de la venta no existe en el sistema.» · `JORNADA_REQUERIDA` «La venta llegó sin jornada.» · `JORNADA_AJENA` «La jornada de la venta es de otro usuario o de otro teléfono.» · `DISPOSITIVO_REVOCADO` «Este teléfono fue dado de baja; la venta quedó para revisión.» · `COMANDO_INCONSISTENTE`, `VENTA_DUPLICADA`, `NUMERO_DUPLICADO` «El sistema ya tenía otra venta con el mismo identificador o número.» · `TOTALES_INCONSISTENTES` «Los importes de la venta no cierran con el cálculo del sistema.» · `CREDITO_INCONSISTENTE` «La evaluación de crédito del teléfono no es coherente.» · el resto (contenido, tipo, versión, modo) «La venta llegó con datos incompletos o inválidos.»
  Consecuencia: un código nuevo del servidor sin texto rompe una prueba, no la pantalla.
- **B. Texto general y código** (como en el 22b) también para las observaciones. Consecuencia: el vendedor no sabe qué se anotó.

### D6 — Disponibles locales en las pantallas de consulta · negocio · MEDIA · CRE-08, RUT-04

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada).** Stock, la columna de stock de Productos y la ficha del cliente (saldo y disponible) muestran los valores locales (bootstrap + lo que cuenta por D1 y D2), con la hora de los datos y la leyenda «Incluye tus ventas desde la última actualización» cuando hay movimientos que cuentan. Consecuencia: el vendedor ve lo mismo en la ficha que en Vender; sin señal opera con números coherentes.
- **B. Quedan los del bootstrap** (como hoy); solo Vender usa los locales. Consecuencia: la ficha y Stock contradicen a Vender después de la primera venta.

### D7 — Métricas de lote · técnica · BAJA · `02` §17

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada).** Además del registro de entrada (`lote_tamano`), un registro de cierre por lote: tamaño, procesados, aceptados, con observaciones, rechazados, si se cortó por un transitorio y la duración, sin contenido. Consecuencia: «comandos por resultado» y «tamaño de lotes» quedan en una línea por lote; prueba con `caplog`.
- **B. Nada nuevo:** el registro de entrada ya cumple «tamaño de lotes». Consecuencia: el corte por transitorio y el reparto por resultado del lote solo se reconstruyen sumando líneas por comando.

### D8 — Cómo se cierra INV-17 · técnica · MEDIA · SYN-05, INV-17

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada). Matriz de integración.** `backend/tests/integration/test_inv17_operaciones_sin_conexion_no_se_rechazan.py`, contra PostgreSQL real y por el lote: un caso por regla de SYN-05 para la venta (stock, crédito, lista, descuentos, cliente suspendido e inactivo, permiso revocado, medio desactivado, referencia faltante, producto y presentación desactivados, ubicación tomada, motivo dado de baja) y para la cobranza (cliente, permiso, medio, referencia), y un caso con todas a la vez; cada uno `ACEPTADO_CON_OBSERVACIONES` con su observación; más dos casos de control: un malformado (`TOTALES_INCONSISTENTES`) sí se rechaza. Todos citan INV-17. Consecuencia: la cobertura de INV-17 queda en un lugar y se lee como la lista de SYN-05.
- **B. Propiedad con Hypothesis** sobre combinaciones de violaciones. Consecuencia: más combinaciones, pero lenta contra la base real y más difícil de leer qué regla falló.

### D9 — Ayuda contextual · interfaz · BAJA · ADR-051

**Resultado (2026-11-02): aprobada la opción A.**

- **A (recomendada).** Sin ejemplos. **Nueva:**
  - `ruta.observacionesYRechazos` — **Observaciones y rechazos**: «Muestra qué anotó el sistema en cada venta enviada y por qué no aceptó las rechazadas. Las observaciones las revisa administración; no tenés que hacer nada. Una venta rechazada no se vuelve a enviar sola.» (SYN-04, SYN-07, SYN-08, SYN-09)
  **Revisadas:**
  - `ruta.stockDelVehiculo` — **Stock del vehículo**: «Es el stock de la última actualización de datos menos lo que vendiste desde el teléfono después. Si no alcanza, la venta no se confirma: actualizá los datos con señal.» (STK-06, RUT-04, ADR-065) — frase final devuelta por decisión del usuario del 2026-11-03 (Vender sigue frenando sin `PERMITIR_STOCK_NEGATIVO`).
  - `ruta.creditoSinSenal` — **Crédito del cliente**: «Se calcula con la deuda de la última actualización de datos más lo que le vendiste y cobraste desde el teléfono después.» (CRE-08, CRE-09, ADR-065)
  - `ruta.ventaConObservaciones` — **Con observaciones**: «El sistema aceptó la venta y anotó algo para que administración lo revise. En el detalle de la venta ves qué anotó. La venta vale igual; no tenés que hacer nada.» (SYN-04, SYN-05, SYN-08)
  - `ruta.ventaRechazada` — **Rechazada**: «El sistema no aceptó la venta por un problema de datos, no por stock ni por crédito. En el detalle ves el motivo. Sigue guardada, no se vuelve a enviar sola y el teléfono la sigue descontando del stock y de la cuenta del cliente: avisá a administración.» (SYN-06, SYN-09, ADR-065) — con D2 = B se quita «y el teléfono la sigue descontando…».
  Consecuencia: la prueba de claves y de IDs citados cubre las nuevas; ADR-065 existe como *Propuesto*.
- **B. Sin ayudas nuevas ni revisadas.** Consecuencia: los textos actuales siguen diciendo «lo que bajó al abrir la jornada», que deja de ser cierto.

## Risks / Trade-offs

- [Una operación con secuencia menor que la marca quedó sin procesar] → no ocurre dentro de una jornada: la cola propia se envía por secuencia y un transitorio corta el lote (`02` §6.4); una prueba del servidor lo fija (corte a mitad de lote → la marca es la del último procesado).
- [El reloj del teléfono] → D1 no usa horas, solo secuencias.
- [Respuesta perdida de un rechazo] → hasta el reenvío la venta deja de contar tras un bootstrap y vuelve a contar al recibir el rechazo (D2); el reenvío es automático.
- [El detalle de una observación nombra un producto o medio que ya no está en la base local] → el texto usa «un producto» / «un medio».
- [Un código de rechazo nuevo sin texto] → la prueba del fixture falla; en producción, texto general con el código.
- [El change sigue grande] → D0 = A saca la anulación; si el Lote 2 se desborda, se corta ahí (`04` §14).

## Migration Plan

Sin migración de servidor (el índice `ix_comando__org_dispositivo_secuencia` alcanza) y sin versión nueva de Dexie (campos nuevos en `sesion` y en filas de `cola`, sin índices). El resultado del lote y el bootstrap solo agregan campos: el teléfono del 22b los ignora y uno del 22c con un bootstrap viejo (sin marca) cuenta todo, como hoy. Volver atrás: el teléfono anterior vuelve al doble conteo conservador.

## Open Questions

Ninguna que cambie lo que se construye si se aprueba D0 = A. Con D0 = B se agregan las decisiones de la anulación listadas en D0.
