# Diseño técnico — 22d-anulacion-sin-conexion

> **Estado: DECISIONES APROBADAS el 2026-11-03 (tarea 0.1): D0 a D13, todas en la opción A (recomendada), incluida D2 (CRÍTICA). Textos aprobados sin ejemplos (tarea 0.2): D9, D10, D11 y D12 como están redactados. Precisiones del usuario: la prueba manual usa `sup01`; el rol Vendedor NO recibe `ANULAR_VENTA` por defecto (se puede conceder desde «Roles y permisos» si hiciera falta); sin cambios de permisos.** Texto original: cada decisión tiene dos o tres opciones con sus consecuencias; la recomendada es **A**. Las decisiones se documentan en **ADR-066** (*Propuesto* hasta el archivo, `docs/adr/ADR-066-anulacion-sin-conexion-y-jornada-no-abierta.md`).
>
> **Gobernanza.** **CRÍTICA: D2** (el servidor acepta, sin conexión, un movimiento de dinero y de stock que con conexión rechazaría: ubicación tomada y motivo dado de baja). **ALTA:** D1, D3 (contrato y efectos del comando en el servidor) y D7 (qué cuenta en el crédito y el stock locales). **MEDIA:** D4, D5, D6, D8, D9, D10, D11. **BAJA:** D0, D12, D13. **De negocio** (el agente solo recomienda; decide el usuario): **D0, D2, D5, D7, D9**. Las que más conviene mirar: **D2, D7 y D9** (el texto del aviso). **Cambian `docs/`:** D1 (VTA-24, SYN-06, `02` §6.5), D2 (STK-09, SYN-07), D3 (`03` `venta_anulacion.jornada_id`), D6 (`02` §13.2), D7 (CRE-08), D8 y D9 (`02` §13.3, RUT-09).
>
> **Revisión.** Decisiones (0.1) y textos (0.2) antes del apply. El usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Servidor.** `ventas/service.py::anular_venta` (ADR-058) hace toda la anulación con conexión: venta `FOR UPDATE`, `VENTA_YA_ANULADA`, cobranza, motivo (`MOTIVO_INVALIDO` si está inactivo o es de otro ámbito), `DEVOLUCION_INVALIDA` y `CONSUMIDOR_FINAL_SIN_DEVOLUCION`, `saldo_cuenta`, reingreso por `stock_service.registrar_movimientos` (STK-09: `UBICACION_TOMADA` salvo `LIBERAR_UBICACION`; `UBICACION_INACTIVA`), `venta_anulacion` con la jornada del primer movimiento, acreditación y anulación de la cobranza. El catálogo declara `VENTA_ANULAR` con `admite_offline=False` y sin operación observable. El bus ya valida la jornada del sobre de todo comando `OFFLINE` (`JORNADA_REQUERIDA`, `JORNADA_AJENA`, `JORNADA_INEXISTENTE`) y anota `PERMISO_REVOCADO` y `JORNADA_LIBERADA`. La venta sin conexión (`VENTA_CONFIRMAR`) ya resuelve la ubicación tomada al sincronizar con `venta_sin_conexion` y `UBICACION_TOMADA_AL_SINCRONIZAR`, y guarda la jornada del sobre.
- **Teléfono (22a a 22c).** `sync/confirmarVentaLocal.ts` escribe venta, cobranza, movimientos, comando y contadores en una transacción; `domain/ruta/disponiblesLocales.ts` cuenta por operación con la secuencia procesada (D1 del 22c) y la rechazada completa (D2 del 22c); `sync/aplicarResultados.ts` escribe por `operation_id` el estado de `cola` y el de `ventas` (busca la venta por su `operation_id`, así que una anulación no la encontraría); `textosDeSincronizacion.ts` traduce los códigos con el fixture `codigos-de-sincronizacion.json`. Al entrar con señal, `sesion/entrada.ts` ya consulta `GET /stock/jornadas/actual` y, si no hay jornada abierta, el inicio deshabilita «Vender» (`sin_jornada`), pero solo en memoria y solo al entrar. `domain/ventas/notaDeVenta.ts` ya arma la marca «ANULADA»; el adaptador local pasa `anulacion: null`.
- **Spec faltante.** `openspec/specs/ventas/anulacion-de-venta/` está vacía: el archivo del change 19 no dejó la spec principal (sí está su delta en `openspec/changes/archive/2026-10-27-19-venta-anulacion/`).

Lo que `docs/` **no** resuelve: el alcance (D0); el contrato sin conexión y la regla de la jornada en curso (D1; ADR-058 la anticipa); qué rechaza y qué acepta (D2); la jornada y los efectos (D3); si va por la cola (D4); qué ventas se anulan y con qué datos (D5); cómo se guarda (D6); cómo cuenta en los disponibles (D7); cómo se entera el teléfono de la jornada no abierta (D8) y qué corta y qué dice (D9); pantallas (D10); textos (D11); ayuda (D12); la spec faltante (D13).

## Goals / Non-Goals

**Goals:** anular sin señal con el mismo resultado en el servidor que con conexión; disponibles locales exactos con anulaciones, aunque se pierda una respuesta; que el teléfono deje de vender en cuanto sabe que su jornada no está abierta.

**Non-Goals:** cobranza suelta sin conexión (23); resolver rechazadas (25); contar anulaciones en la rendición (24); anular ventas que no están en el teléfono; avisos push o en segundo plano.

## Decisions

### D0 — Alcance y división · alcance · BAJA · de negocio · `04` §11

La fila del 22d trae dos frentes: la anulación sin conexión (servidor, base local, conciliación, pantallas) y el corte por jornada no abierta (solo teléfono, sin servidor nuevo).

- **A (recomendada). Un solo change en cuatro lotes**: **Lote 1** servidor (contrato, reglas, jornada, fixtures, pruebas de integración y concurrencia); **Lote 2** núcleo del teléfono (Dexie v4, anulación local, conciliación, resultados, estado de la jornada); **Lote 3** pantallas y ayuda; **Lote 4** punta a punta, ADR, docs, spec restituida, cobertura, suites y prueba manual. Consecuencia: del tamaño del 22c; el corte por jornada comparte la condición «jornada en curso» con la anulación (D5, D9), así que se prueba una sola vez.
- **B. Dividir:** 22d solo anulación y un **22e `jornada-no-abierta-en-el-telefono`**. Consecuencia: dos pruebas manuales y la condición de la jornada se toca dos veces.

### D1 — Contrato sin conexión y jornada en curso · técnica · ALTA · VTA-24, SYN-06, SYN-10, ADR-058

- **A (recomendada).** `VENTA_ANULAR` **v1** con el mismo contenido; el catálogo pasa a `admite_offline=True` con la venta como operación observable (`OperacionObservable("VENTA", "venta_id")`), así `PERMISO_REVOCADO` y `JORNADA_LIBERADA` del bus van sobre la venta. Por REST sigue `ONLINE`. Sin conexión: la venta debe tener la misma `jornada_id` que el sobre (si no, o si no tiene jornada, `JORNADA_AJENA`, 409 en el catálogo de errores); una venta inexistente o de otra organización es **`VENTA_INEXISTENTE`** (código nuevo, rechazo por dependencia inexistente con su fila de comando, de modo que el reenvío devuelve el mismo rechazo). Consecuencia: se cumple ADR-058 (sin v2); el texto del rechazo dice qué pasó; un código nuevo en `01` SYN-06 y en el fixture.
- **B.** Igual pero la venta inexistente responde `RECURSO_NO_ENCONTRADO`, como con conexión. Consecuencia: sin código nuevo, pero el teléfono no distingue «la venta no existe» de «el motivo no existe».

### D2 — Qué rechaza y qué acepta el servidor sin conexión · negocio · **CRÍTICA** · VTA-20 a VTA-22, STK-09, SYN-05, SYN-07

SYN-05 protege la venta y la cobranza sin conexión, no la anulación. Pero la anulación sin conexión también es un hecho consumado: la mercadería ya volvió al vehículo.

- **A (recomendada).** **Rechaza** (sin efectos): `VENTA_YA_ANULADA`, `DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`, `OBSERVACION_INVALIDA`, `MOTIVO_INVALIDO` (de otra organización o de otro ámbito) y `UBICACION_INACTIVA` (igual que la venta sin conexión), además de las del bus y D1. **Acepta**: un motivo del ámbito dado de baja después del bootstrap, sin observación (como ADR-063 D11); permiso revocado (`PERMISO_REVOCADO`); jornada liberada (`JORNADA_LIBERADA`); ubicación tomada al sincronizar, por la propia jornada en rendición o por la de otro vendedor, con **`UBICACION_TOMADA_AL_SINCRONIZAR`** sobre la venta, reingreso sin jornada y la constancia en la auditoría (como la venta sin conexión, ADR-054). Consecuencia: el stock vuelve a la camioneta donde está físicamente; los rechazos son de datos o de un conflicto real (ya anulada) que el teléfono no puede evitar; SYN-07 y STK-09 nombran también la anulación; sin observaciones nuevas.
- **B. Como con conexión:** con la ubicación tomada, `UBICACION_TOMADA`; con el motivo dado de baja, `MOTIVO_INVALIDO`. Consecuencia: anulaciones hechas y entregadas que el sistema no registra; el teléfono las deja de contar (D7) aunque la mercadería esté en el vehículo.
- **C. Nunca rechaza por reglas de negocio** (también ya anulada se acepta sin efecto, con observación nueva). Consecuencia: un código nuevo en SYN-07 para un caso que administración ya resolvió.

### D3 — Jornada y efectos de la anulación en el servidor · técnica · ALTA · STK-09, RUT-07, ADR-058 D8 y D10

- **A (recomendada).** Mismo `anular_venta`, misma transacción del bus y **mismo orden de bloqueo** (ADR-058 D10, sin cambios), con un parámetro de modo. Sin conexión, `venta_anulacion.jornada_id` es la **jornada del sobre** (como `venta.jornada_id` sin conexión) y el reingreso lleva esa jornada solo si la ubicación es suya y está `ABIERTA`; si no, sin jornada. El resultado es el mismo que con conexión. `occurred_at` del dispositivo. Consecuencia: la rendición (24) cuenta las anulaciones por la jornada aunque haya sido liberada; sin migración (la columna ya es nulable).
- **B.** Jornada de la anulación tomada del movimiento, como con conexión. Consecuencia: una anulación con la jornada liberada queda sin jornada y la rendición del 24 no la ve.

### D4 — En `/ruta` la anulación va siempre por la cola · técnica · MEDIA · ADR-063 D1, SYN-03

- **A (recomendada).** Con o sin señal, se confirma en el teléfono y se encola `OFFLINE`; con señal se dispara la sincronización enseguida (como la venta). Consecuencia: un solo camino; el orden detrás de su venta lo garantiza la secuencia (SYN-03); el vendedor ve «Sin enviar» unos segundos.
- **B.** Con señal, `POST /ventas/{id}/anulacion` (`ONLINE`); sin señal, la cola. Consecuencia: dos caminos y la venta puede no haber llegado todavía al servidor (404).

### D5 — Qué ventas se anulan en el teléfono y con qué datos · negocio · MEDIA · VTA-20, VTA-22, VTA-24

- **A (recomendada).** Se ofrece con `ANULAR_VENTA` en los datos del día, venta de la jornada de la sesión, jornada no marcada como no abierta (D8), venta no anulada y **no «Rechazada»**, y aplicación no bloqueada por versión (`02` §6.6). Una «Sin enviar» sí se anula (se encola detrás). Pide motivo activo de `ANULACION_VENTA` del bootstrap, observación opcional (500) y, si hubo cobro en el acto, si se devuelve (consumidor final: siempre sí, fijo; sin cobro, no se pregunta), y confirma. Sin PIN de supervisor. Consecuencia: el teléfono no genera anulaciones que sabe que el servidor rechazará (una rechazada no existe en el servidor: la resuelve administración, 25).
- **B.** También anular una «Rechazada». Consecuencia: el comando vuelve siempre `VENTA_INEXISTENTE`; localmente se compensa (D7), pero suma un rechazo seguro.

### D6 — Cómo se guarda la anulación en el teléfono · técnica · MEDIA · `02` §13.2, INV-01

- **A (recomendada). Dexie v4 con la tabla `anulaciones`** (`venta_id` clave, `&operation_id`, `jornada_id`, `estado_envio`; motivo, observación, devolución, momento, nombre del motivo para la nota). Movimientos locales nuevos con el `operation_id` de la anulación: `ANULACION_STOCK` (+cantidad por línea), `ANULACION_CREDITO` (−total) y `ANULACION_COBRANZA_DEBITO` (+cobrado, solo con devolución). Una transacción escribe anulación, movimientos, comando y última secuencia; reconfirmar la misma venta devuelve la existente. `aplicarResultados` escribe el estado en `anulaciones` por `operation_id`. La v4 solo agrega una tabla (no toca las otras) y la tabla no está en `TABLAS_MAESTRAS`. Consecuencia: la anulación tiene su propio estado de envío; el resultado se encuentra por índice; el cambio de versión es aditivo.
- **B. Campo `anulacion` dentro de `VentaLocal`**, sin versión nueva. Consecuencia: el resultado se busca recorriendo la cola por `venta_id` del contenido; la venta mezcla dos estados de envío.

### D7 — La anulación en el saldo y el stock locales · negocio · ALTA · CRE-08, RUT-04, VTA-22, INV-19

- **A (recomendada).** Cuenta **desde que se confirma** por la regla de CRE-08 (su propia secuencia contra la secuencia procesada). Una anulación **rechazada deja de contar**, salvo que su venta también esté rechazada: entonces cuentan las dos y se compensan. Consecuencia: el vendedor puede volver a vender la mercadería devuelta enseguida; si el servidor la rechaza porque ya estaba anulada, el bootstrap trae la anulación de administración y no se cuenta dos veces; si la venta nunca existió, el teléfono queda como antes de venderla.
- **B. Cuenta solo cuando el servidor la acepta.** Consecuencia: lo conservador para el crédito, pero sin señal la mercadería devuelta no se puede vender en todo el día.
- **C. La rechazada sigue contando** (simétrica con la venta rechazada del 22c). Consecuencia: con `VENTA_YA_ANULADA` el teléfono suma dos veces la devolución.

### D8 — Cómo se entera el teléfono de que su jornada no está abierta · técnica · MEDIA · RUT-03, RUT-09, `02` §13.3

- **A (recomendada).** Al empezar cada ciclo de sincronización (todos los disparadores, también el periódico y con la cola vacía), junto a la versión mínima, `GET /api/v1/stock/jornadas/{jornada_id}` de la sesión (endpoint existente, `ABRIR_JORNADA`, que el vendedor ya necesita para abrirla). Además: `JORNADA_REQUERIDA` del bootstrap o de «Actualizar datos», la consulta al entrar (`sin_jornada`) y una `JORNADA_LIBERADA` en los resultados del lote. Se guarda en `meta` (`jornada_no_abierta`: jornada, estado o «desconocido», momento) y se ignora si la jornada de la sesión es otra (al aplicar el bootstrap de otra jornada se borra). Sin señal, 403, 404 o error: no cambia nada. Consecuencia: sin servidor nuevo; a lo sumo dos minutos de demora con señal; vale sin señal y tras recargar.
- **B. Endpoint nuevo** `GET /api/v1/sync/jornada` (cualquier sesión). Consecuencia: no depende de `ABRIR_JORNADA`, pero es un endpoint y una prueba de aislamiento más para lo mismo.
- **C. Solo el bootstrap y los resultados del lote.** Consecuencia: con la cola vacía y sin tocar «Actualizar datos», el teléfono no se entera.

### D9 — Qué corta y qué dice la jornada no abierta · negocio · MEDIA · RUT-09, `02` §6.6

- **A (recomendada).** Corta «Vender» (inicio y ficha; «Confirmar venta» no confirma y el carrito sigue, como la versión mínima) y «Anular venta». Sigue todo lo demás, y la cola. Con señal, el inicio ofrece «Abrir jornada». El aviso dice el estado: `LIBERADA` «Tu jornada fue liberada.»; `EN_RENDICION` «Tu jornada está en rendición.»; `CERRADA` «Tu jornada fue cerrada.»; desconocido «Tu jornada ya no está abierta.»; siempre seguido de «Lo que ya vendiste se sigue enviando.». Consecuencia: el texto pedido para la liberación, y no miente cuando la jornada se rindió o se cerró desde administración.
- **B. Un solo texto, «Tu jornada fue liberada.»**, para todo estado. Consecuencia: más simple, pero falso si la jornada se cerró o está en rendición.

### D10 — Pantallas · interfaz · MEDIA · VTA-13, SYN-09

- **A (recomendada).** «Anular venta» en «Venta guardada» lleva a `/ruta/ventas/:id/anular` (motivo, devolución, observación; «¿Anular la venta {número}?» antes de confirmar; precacheada como el resto de `/ruta`). El detalle suma la etiqueta «Anulada» y la sección «Anulación» (motivo, devolución, observación, estado de envío y su explicación). «Ventas de hoy» muestra «Anulada». «Sincronización» lista también las anulaciones con problemas como «Anulación de {número}». Lo pendiente: «N ventas y M anulaciones sin enviar» (solo ventas: «N ventas sin enviar»; solo anulaciones: «1 anulación sin enviar» / «M anulaciones sin enviar»), también en el aviso de cierre de sesión y en el de pendientes de otro usuario. La nota local de una venta anulada lleva la marca de VTA-13. Consecuencia: todo desde el detalle; la guarda del carrito no aplica (no hay carrito).
- **B. Diálogo dentro del detalle**, sin ruta propia, y sin marca en la nota. Consecuencia: el formulario no entra cómodo en un diálogo de teléfono y la nota local contradice VTA-13.

### D11 — Textos de rechazos y observaciones de la anulación · interfaz · MEDIA · SYN-06, SYN-07

- **A (recomendada).** El fixture `codigos-de-sincronizacion.json` suma los rechazos que puede recibir `VENTA_ANULAR` `OFFLINE` (la lista final la fija una prueba del Lote 1, recorriendo el bus y la anulación) y los textos se eligen por tipo de operación. Textos propuestos (sin ejemplos; se aprueban en 0.2):
  - Rechazos de la anulación, seguidos de «La venta sigue vigente en el teléfono; avisá a administración.»: `VENTA_INEXISTENTE` «El sistema no tiene la venta que se quiso anular.» · `VENTA_YA_ANULADA` «La venta ya estaba anulada en el sistema.» · `JORNADA_AJENA` «La venta es de otra jornada.» · `UBICACION_INACTIVA` «La ubicación de la venta está dada de baja.» · `MOTIVO_INVALIDO` «El motivo de la anulación no es válido.» · `DISPOSITIVO_REVOCADO` «Este teléfono fue dado de baja; la anulación quedó para revisión.» · el resto (`DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`, `OBSERVACION_INVALIDA`, contenido, tipo, versión, modo, inconsistente, jornada inexistente o requerida) «La anulación llegó con datos incompletos o inválidos.»
  - Observaciones de la anulación: `JORNADA_LIBERADA` «La jornada había sido liberada cuando llegó la anulación.» · `UBICACION_TOMADA_AL_SINCRONIZAR` «Cuando llegó la anulación, el vehículo estaba en rendición o en la jornada de otro vendedor.» · `PERMISO_REVOCADO` sin cambio («Cuando llegó la operación, tu usuario ya no tenía el permiso.»).
  Consecuencia: un código nuevo sin texto rompe una prueba, no la pantalla.
- **B. Los textos de la venta** también para la anulación. Consecuencia: «La venta llegó sin jornada» sobre una anulación confunde.

### D12 — Ayuda contextual · interfaz · BAJA · ADR-051

- **A (recomendada).** Sin ejemplos. **Nuevas:**
  - `ruta.anularVenta` — **Anular una venta**: «Deja sin efecto una venta de tu jornada, también sin señal: la mercadería vuelve al stock del vehículo y al cliente se le descuenta el total de su cuenta. Se anula entera y una sola vez, y se envía al sistema como las ventas.» (VTA-20, VTA-21, VTA-24, ADR-066)
  - `ruta.anulacionRechazada` — **Anulación rechazada**: «El sistema no aceptó la anulación. En el detalle ves el motivo. La venta sigue vigente: el teléfono la vuelve a descontar del stock y de la cuenta del cliente. No se vuelve a enviar sola: avisá a administración.» (SYN-06, SYN-09, VTA-24, ADR-066)
  - `ruta.jornadaNoAbierta` — **Jornada no abierta**: «El sistema avisó que tu jornada ya no está abierta. No podés vender ni anular ventas; lo que ya vendiste se sigue enviando. Para seguir vendiendo, abrí una jornada nueva con señal.» (RUT-09, RUT-03, ADR-066)
  **Revisadas:**
  - `ruta.stockDelVehiculo`: «Es el stock de la última actualización de datos menos lo que vendiste y más lo que anulaste desde el teléfono después. Si no alcanza, la venta no se confirma: actualizá los datos con señal.» (STK-06, RUT-04, ADR-065, ADR-066)
  - `ruta.creditoSinSenal`: «Se calcula con la deuda de la última actualización de datos más lo que le vendiste y cobraste, y menos lo que le anulaste, desde el teléfono después.» (CRE-08, CRE-09, ADR-065, ADR-066)
  - `ruta.sincronizar`: «Envía al sistema las ventas y anulaciones sin enviar de tu usuario, en el orden en que las hiciste. Se hace sola al abrir la aplicación o volver a ella, al volver la señal, después de cada venta o anulación y cada 2 minutos. Enviar dos veces lo mismo no lo duplica.» (SYN-02, SYN-03, INV-06)
  - `ruta.observacionesYRechazos`: «Muestra qué anotó el sistema en cada venta o anulación enviada y por qué no aceptó las rechazadas. Las observaciones las revisa administración; no tenés que hacer nada. Lo rechazado no se vuelve a enviar solo.» (SYN-04, SYN-07, SYN-08, SYN-09)
  **Reutilizadas sin cambio** en la pantalla de anulación: `ventas.motivoAnulacion`, `ventas.devolverDinero`, `ventas.consumidorFinalAnulacion`.
  Consecuencia: ADR-066 existe como *Propuesto* desde la propuesta, así la prueba de IDs citados pasa.
- **B. Sin ayudas nuevas ni revisadas.** Consecuencia: el stock y el crédito dicen «menos lo que vendiste», que deja de ser cierto.

### D13 — Spec principal `ventas/anulacion-de-venta` faltante · técnica · BAJA

- **A (recomendada).** En el Lote 4, antes de archivar, se restituye `openspec/specs/ventas/anulacion-de-venta/spec.md` copiando los requisitos del delta del change 19 (sin tocar el archivo de `archive/`), con su `## Purpose` y con el escenario «Modo sin conexión todavía no admitido» y el «solo en modo `ONLINE`» del primer requisito ajustados a «por REST, solo `ONLINE`; sin conexión, ver el requisito del 22d». El delta del 22d agrega sus requisitos al archivar. Consecuencia: la spec vigente queda completa y sin contradicción.
- **B. No restituir**: al archivar, la spec principal nace solo con los requisitos del 22d. Consecuencia: los requisitos con conexión del 19 quedan solo en `archive/`.

## Risks / Trade-offs

- [La venta y su anulación se cortan entre lotes] → la secuencia y el corte por transitorio (`02` §6.4) garantizan que la anulación nunca llega antes; prueba de integración con los dos en un lote y en lotes separados.
- [Anulación sin conexión y con conexión de la misma venta a la vez] → `FOR UPDATE` de la venta (ADR-058 D10): una gana y la otra `VENTA_YA_ANULADA`; prueba de concurrencia con commits reales.
- [El vendedor no tiene `ABRIR_JORNADA` al consultar la jornada] → 403 se ignora (D8); el bootstrap y `JORNADA_LIBERADA` siguen avisando.
- [Respuesta perdida de una anulación] → el bootstrap con la secuencia procesada la deja de contar sin depender de la respuesta (D7); el reenvío es automático e idempotente.
- [Dexie v4 en teléfonos con datos] → la versión solo agrega una tabla; prueba de que la v3 con ventas y cola abre en v4 sin perder nada.
- [`venta_anulacion.jornada_id` distinto entre modos] → documentado en `03` y en ADR-066; la rendición del 24 lo usa.

## Migration Plan

Sin migración del servidor (`venta_anulacion.jornada_id` ya es nulable; sin permisos nuevos). Dexie v4 aditiva. El teléfono anterior no anula sin conexión (no tiene el botón) y un servidor anterior rechazaría el `OFFLINE` con `MODO_NO_ADMITIDO_PARA_TIPO`: se despliega el servidor antes que el frontend, como siempre. Volver atrás: el servidor anterior rechaza las anulaciones `OFFLINE` pendientes con `MODO_NO_ADMITIDO_PARA_TIPO` (el teléfono las muestra rechazadas y dejan de contar).
