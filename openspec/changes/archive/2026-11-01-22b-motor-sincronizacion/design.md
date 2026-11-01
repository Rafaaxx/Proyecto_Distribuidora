# Diseño técnico — 22b-motor-sincronizacion

> **Estado: DECISIONES APROBADAS (2026-11-01).** El usuario aprobó D0 a D13 con la opción recomendada **A**, salvo **D6 = B** (también se sincroniza al volver la aplicación a primer plano). D11 se aprobó de forma explícita (gobernanza CRÍTICA). D4 se aprueba aceptando el doble conteo conservador hasta el 22c. Los textos de ayuda y de pantalla (tarea 0.2) fueron aprobados por el usuario (2026-11-01). Cada decisión conserva sus opciones y consecuencias; las decisiones se documentan en **ADR-064** (*Propuesto* hasta el archivo, `docs/adr/ADR-064-motor-de-sincronizacion-del-telefono.md`).
>
> **Gobernanza.** **CRÍTICA:** D11 (renovación del refresh token entre pestañas: dominio de autenticación; no se escribe código sin aprobación explícita). **ALTA:** D9 (límite local del PIN de supervisor). **MEDIA:** D1 a D8, D10, D12. **BAJA:** D0, D13. **De negocio** (el agente solo recomienda; decide el usuario): **D1, D4, D7, D8**.
>
> **Revisión.** Decisiones aprobadas (tarea 0.1); los textos de ayuda y de pantalla se aprueban antes del apply (tarea 0.2). El usuario revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Servidor (changes 04, 18b, 21):** `POST /api/v1/sync/comandos` acepta hasta 50 ítems, los ordena por `secuencia`, rechaza el lote entero con `COLA_AJENA` (403) si algún ítem declara otro usuario o dispositivo, responde un resultado por `operation_id` (`ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES`, `RECHAZADO` con `error_codigo`, o `ERROR_TRANSITORIO`, que corta el lote en ese ítem) y es idempotente por la reserva de `comando` (INV-06, cerrado del lado del servidor por el change 04). El lote admite al usuario inactivo con jornada pendiente (ADR-028). `GET /api/v1/version` (sin sesión) devuelve `version` y `app_version_minima` (configuración de despliegue; `null` = sin restricción). La respuesta del lote **no** trae el detalle de las observaciones (eso es del 22c y del 25). **Este change no necesita código de servidor.**
- **Teléfono (changes 21, 22a):** Dexie v3 con `cola` (`secuencia`, `&operation_id`, `estado`; hoy solo `PENDIENTE`), `ventas` (`estado_envio`), `cobranzas`, `movimientos_locales` (`estado_operacion`) y `intentos_pin`; `sync/sobre.ts` arma el sobre del lote; `sync/ventasPendientes.ts` cuenta por `sobre.usuario_id`; `lib/api/httpClient.ts` (`apiFetch` renueva una vez ante un 401; `renovarSesion`); `lib/conexion.ts` (`useConectado`); `areas/ruta/datos/lecturas.ts` lee con `liveQuery` de Dexie (sin `dexie-react-hooks`); `sync/appVersion.ts` lee `VITE_APP_VERSION`, que hoy **nadie define** (siempre `0.0.0`; el servidor usa `APP_VERSION`, `dev` por defecto).
- **Deudas del 22a (ADR-063, "Deudas nominadas"):** `pinSupervisor.ts` serializa con una cola de promesas de módulo (`enSerie`) que solo protege dentro de una pestaña: la lectura-derivación-escritura sobre `intentos_pin` no es atómica entre pestañas. La guarda del carrito (`contextoGuarda.ts`, `RutaLayout.tsx`) intercepta solo el menú inferior y «Cancelar»: la aplicación usa `BrowserRouter` (`app/App.tsx`), sin `useBlocker`.

Lo que `docs/` **no** resuelve (cada punto es una decisión): qué parte de la cola se envía (D1); cómo se comporta el bloqueo único y qué pasa sin Web Locks (D2); cómo se escriben los resultados (D3); qué pasa con los movimientos locales de una venta ya aceptada (D4); qué es transitorio y con qué espera (D5); el detalle de los disparadores (D6); el formato y la aplicación de la versión mínima en el teléfono (D7); dónde se ve el estado (D8); el límite del PIN entre pestañas (D9); la guarda completa (D10); la renovación entre pestañas (D11); cómo se prueba el criterio 8 (D12); la ayuda (D13).

## Goals / Non-Goals

**Goals:** que las ventas confirmadas en el teléfono lleguen al servidor solas y en orden apenas haya señal, sin duplicarse aunque se sincronice dos veces o desde dos pestañas (`00` §9 criterio 8); que el vendedor vea siempre qué falta enviar, cuándo fue la última sincronización y qué volvió observado o rechazado; cerrar las dos deudas de pestañas y la de la guarda del carrito.

**Non-Goals:** conciliar los movimientos locales con un bootstrap posterior (22c, D4); mostrar el detalle de cada observación o resolver conflictos (22c, 25); reenviar a mano un rechazado; sincronizar en segundo plano desde el service worker (`02` §13.3 lo descarta); métricas de tamaño de lote (22c).

## Decisions

### D0 — Tamaño y lotes · alcance · BAJA

- **A (recomendada). Un change en cinco lotes**, sin frenar entre lotes: **Lote 1** núcleo del motor sin pantalla (selección, lote, aplicación de resultados, clasificación de errores, espera exponencial, Web Lock del envío) con sus pruebas de INV-06 del cliente; **Lote 2** pestañas: PIN de supervisor (D9) y renovación de sesión (D11, aprobada); **Lote 3** disparadores, versión mínima y estado visible (cabecera, inicio, pantalla «Sincronización»); **Lote 4** enrutador de datos y guarda completa del carrito, y ayuda; **Lote 5** prueba de concurrencia del servidor (criterio 8), ADR, docs, cobertura, suites completas y prueba manual. Consecuencia: el núcleo queda probado antes de la primera pantalla; lo de autenticación queda aislado en un lote.
- **B. Dos changes:** 22b1 (motor y pantallas) y 22b2 (deudas de pestañas y guarda). Consecuencia: el 22b1 se prueba antes, pero las deudas del 22a quedan otra vuelta abiertas y hay dos pruebas manuales.

### D1 — Qué parte de la cola se envía · negocio · MEDIA · `02` §6.4

- **A (recomendada).** Los comandos con `estado = PENDIENTE` cuyo `sobre.usuario_id` es el usuario de la sesión local **y** cuyo `sobre.dispositivo_id` es el de este teléfono, **de cualquier jornada**, en orden de `secuencia`, en lotes de hasta 50; se repite hasta vaciar la cola propia o hasta un corte (D5). Los de otro usuario no se tocan: quedan para cuando entre él (ADR-063 D16). Consecuencia: el servidor nunca recibe un lote con un ítem ajeno (no hay `COLA_AJENA`); una venta de una jornada anterior del mismo usuario también se envía (el servidor la acepta con `JORNADA_LIBERADA` si la jornada se liberó, RUT-09) y la rendición (RUT-05, change 24) encuentra la cola vacía.
- **B. Solo los de la jornada actual.** Consecuencia: una venta de una jornada anterior (por ejemplo, la jornada se liberó desde administración) queda sin enviar para siempre.

### D2 — Una sola sincronización a la vez · técnica · MEDIA · `02` §13.3

- **A (recomendada).** Web Lock exclusivo `distribuidora:sync` pedido con `ifAvailable`: si otra pestaña lo tiene, esta **no espera** y muestra «Sincronizando en otra pestaña»; ve el avance porque el estado vive en Dexie (`liveQuery`). Si un disparador llega mientras la propia pestaña sincroniza, se anota «repetir al terminar» y se hace una vuelta más (así una venta confirmada durante el envío sale en seguida). **Sin Web Locks** (navegador viejo): un candado dentro de la pestaña; dos pestañas podrían enviar a la vez, y eso es seguro porque el servidor no duplica (INV-06) y aplicar el mismo resultado dos veces deja lo mismo. Consecuencia: nunca hay dos envíos de la misma pestaña; entre pestañas, los hay solo en navegadores sin Web Locks, sin efecto duplicado.
- **B. Esperar el candado** (sin `ifAvailable`). Consecuencia: cada pestaña encola su vuelta detrás de la otra; vueltas repetidas sin nada que enviar.
- **C. Sin Web Locks, no sincronizar** y avisar «Actualizá el navegador». Consecuencia: cumple el DEBE literal de `02` §13.3, pero deja ventas sin enviar en un teléfono que podría enviarlas sin riesgo.

### D3 — Cómo se escriben los resultados · técnica · MEDIA · SYN-04, SYN-09, INV-01

- **A (recomendada).** Una transacción `rw` de Dexie por respuesta de lote, sobre `cola` y `ventas`: para cada resultado (buscado por `operation_id`, nunca por posición), la fila de `cola` pasa a `ACEPTADO`, `ACEPTADO_CON_OBSERVACIONES` o `RECHAZADO` con `error_codigo` y el momento local del resultado, y la venta toma `estado_envio` `ACEPTADA`, `CON_OBSERVACIONES` o `RECHAZADA` (la cobranza de la venta viaja en el mismo comando y sigue el estado de su venta; no tiene campo propio). `ERROR_TRANSITORIO` y los ítems que el servidor no llegó a procesar quedan `PENDIENTE`. Un resultado de un `operation_id` desconocido se ignora y se registra en consola. **Nada se borra** (SYN-09): las filas de `cola` quedan como constancia (la rendición del 24 y la conciliación del 22c las leen). Un `RECHAZADO` no se vuelve a enviar solo. El tipo `ComandoEnCola.estado` se amplía; el índice `estado` ya existe, así que **no hace falta una versión 4** de Dexie. Consecuencia: o se aplican todos los resultados del lote o ninguno; si la aplicación se cierra a mitad, el reenvío devuelve los mismos resultados (INV-06).
- **B. Borrar de `cola` lo aceptado** (la venta queda con su estado). Consecuencia: menos filas, pero se pierde la constancia del resultado y el 22c no puede saber qué aceptó el servidor.

### D4 — Movimientos locales de una venta ya aceptada (frontera con el 22c) · negocio · MEDIA · CRE-08, RUT-04

Hoy el saldo y el stock locales son «bootstrap + movimientos de la jornada sin resultado» (ADR-063 D5); `04` asigna al 22c conciliarlos con un bootstrap posterior a una sincronización aceptada.

- **A (recomendada).** El 22b **no cambia** `estado_operacion` de los movimientos (el comentario de `db.ts` que dice que lo escribe el 22b se corrige: lo escribe el 22c): una venta aceptada sigue contando en el saldo y el stock locales hasta la conciliación del 22c. Consecuencia: sin «Actualizar datos», los números son correctos; **después de sincronizar y actualizar los datos**, una venta ya incluida en el bootstrap cuenta dos veces (saldo más alto y stock más bajo de lo real: lo conservador, nunca deja vender de más) hasta el 22c. La spec de `sync/cola-local` se ajusta a «con o sin resultado».
- **B. Conciliar en el 22b:** al aplicar un bootstrap pedido después de recibir el `ACEPTADO`, los movimientos de esas ventas dejan de contar (el bootstrap es una sola foto tomada después del commit). Consecuencia: números exactos desde ya, pero el bootstrap pasa a tocar `movimientos_locales`, contra el DEBE NO de `02` §13.4, y adelanta trabajo del 22c a un change que `04` advierte que puede desbordarse.
- **C. Dejar de contar al recibir el `ACEPTADO`.** Consecuencia: entre la sincronización y el próximo bootstrap el saldo y el stock locales «olvidan» la venta y dejan vender de más.

### D5 — Errores y espera exponencial · técnica · MEDIA · SYN-03, `02` §6.3, §6.4

- **A (recomendada).** Clasificación:

  | Caso | Qué hace |
  | --- | --- |
  | Sin red (`fetch` falla), 5xx, 429 o un ítem `ERROR_TRANSITORIO` | **Transitorio:** corta el ciclo y programa el próximo intento con espera exponencial: 5 s, 10 s, 20 s, 40 s, 80 s y luego 120 s fijo, con ±20 % al azar. |
  | 401 después de la renovación de `apiFetch` | **Sesión vencida:** corta y no reintenta solo; muestra «Iniciá sesión con señal para enviar las ventas» (la cola se conserva, `02` §12.3). |
  | 403 `COLA_AJENA`, 422 u otro 4xx | **Error del teléfono:** corta, muestra «No se pudo enviar» con el código y no reintenta con espera; vuelve a probar con el próximo disparador. |

  Un ciclo que llega al final sin corte es una **sincronización exitosa**: guarda su momento en `meta` y vuelve la espera a cero. «Sincronizar», el evento `online` y la vuelta a primer plano (D6 = B) también vuelven la espera a cero y prueban en el momento. El estado (último éxito, último error con su tipo y código) vive en `meta` para que lo vean todas las pestañas. Consecuencia: con señal intermitente los intentos se espacian hasta 2 minutos (el mismo ritmo del disparador periódico); un error que no se arregla reintentando no martilla al servidor.
- **B. Reintento a intervalo fijo de 2 minutos.** Consecuencia: más simple, pero contra «espera exponencial» de `02` §13.3 y lento tras un corte breve.

### D6 — Disparadores · técnica · MEDIA · `02` §13.3

- **A. Exactamente los de `02` §13.3**, con la sesión local desbloqueada: al abrir la aplicación (cuando el PIN desbloquea o el login termina), en el evento `online`, después de cada venta confirmada (si `navigator.onLine`), cada 2 minutos mientras la aplicación está abierta y con «Sincronizar». Con la sesión bloqueada o sin usuario local no se sincroniza. Consecuencia: el motor siempre sabe de quién es la cola; volver de segundo plano no dispara por sí mismo (el temporizador vence al volver).
- **B (aprobada, 2026-11-01). Los de A y, además, al volver la aplicación a primer plano:** el evento `visibilitychange` con `document.visibilityState === 'visible'` dispara una sincronización **solo con la sesión local desbloqueada** (oculta, bloqueada o sin usuario local no dispara). Es un disparador más del mismo motor: pasa por el bloqueo único de D2 (si otra pestaña sincroniza, esta no espera; si la propia pestaña está sincronizando, solo anota «repetir al terminar», que es una marca y no un contador, así que varios disparadores durante un envío producen **a lo sumo una vuelta más**) y, como «Sincronizar» y el evento `online`, **vuelve la espera exponencial de D5 a cero y envía en el momento** (decisión del usuario, 2026-11-01; el disparador posterior a una venta y el periódico sí respetan la espera vigente). Como `02` §13.3 no lo nombra, la tarea 17.1 propone agregarlo a `docs/`. Consecuencia: envía apenas el vendedor vuelve a la aplicación, sin martillar al servidor ni apilar vueltas.

### D7 — Versión mínima de la aplicación · negocio · MEDIA · `02` §6.6

- **A (recomendada).** La compilación toma su versión de `APP_VERSION` (la misma variable del backend) y la expone como `VITE_APP_VERSION`; formato `X.Y.Z` comparado por números. Al empezar cada ciclo el motor pide `GET /api/v1/version` y guarda en `meta` la última `app_version_minima` conocida (así el bloqueo sigue sin señal). Si la versión propia es menor que la mínima: la cola **se sigue enviando**, «Vender» queda deshabilitado con «Esta versión ya no puede confirmar ventas nuevas: actualizá la aplicación» y la confirmación también lo revisa (por si el aviso llegó con el carrito abierto: no se pierde el carrito, solo no se confirma). Si alguna de las dos versiones no tiene formato `X.Y.Z` (por ejemplo `dev`) o la mínima es `null`, no hay restricción. Consecuencia: el servidor no cambia (no puede distinguir una venta vieja encolada de una nueva, spec `sistema/salud-y-version`); el bloqueo es del teléfono.
- **B. Consultar la mínima solo en el bootstrap** (campo nuevo en la respuesta). Consecuencia: código de servidor nuevo; un teléfono que no actualiza datos en días no se entera.
- **C. Que el servidor rechace los comandos de una versión menor.** Consecuencia: contra `02` §6.6 (la cola de una aplicación vieja debe poder vaciarse).

### D8 — Dónde se ve el estado · negocio · MEDIA · `02` §13.3

- **A (recomendada).** (1) **Indicador en la cabecera de `/ruta`**, en toda pantalla: conexión y «N sin enviar» (o «Todo enviado»), con un aviso si hay rechazadas; tocarlo abre «Sincronización». (2) **Inicio:** el bloque actual de pendientes suma «Última sincronización: {hora}» y el botón **«Sincronizar»** (deshabilitado mientras sincroniza, con «Enviando…»). (3) **Pantalla «Sincronización»** (`/ruta/sincronizacion`): conexión, pendientes, última sincronización, último error con su texto y el botón, y la lista de ventas **Con observaciones** y **Rechazadas** (número, cliente, total, estado; en las rechazadas, el código), cada una con su detalle. En «Ventas de hoy» y en el detalle, las etiquetas son «Sin enviar», «Enviada», «Con observaciones» y «Rechazada». El rechazo muestra un texto general («El sistema no aceptó esta venta. Sigue guardada en el teléfono; avisá a administración.») y el código, sin traducir cada código (eso es del 22c). Consecuencia: cumple «muestra en todo momento» con poco espacio en el teléfono.
- **B. Todo en el inicio,** sin cabecera ni pantalla nueva. Consecuencia: fuera del inicio el vendedor no ve si quedó algo sin enviar.

### D9 — PIN de supervisor entre pestañas (deuda del 22a) · seguridad · ALTA · SEG-05, `02` §12.4

El problema: dos pestañas leen la misma fila de `intentos_pin` (por ejemplo, 2 fallos), derivan a la vez y escriben las dos «3»: se pierde un fallo y, con N pestañas, se llega a unos 5 × N intentos.

- **A (recomendada). Web Lock exclusivo por par** `distribuidora:pin:{usuario}:{supervisor}` alrededor de toda la verificación (leer el estado, ver el bloqueo, derivar, escribir), **con la derivación dentro del candado**, y la escritura del fallo en una transacción `rw` de Dexie que **vuelve a leer** la fila y suma sobre lo leído. Sin Web Locks: la misma transacción atómica y, **después de derivar y antes de responder, una nueva lectura del bloqueo**: si otra pestaña lo bloqueó mientras tanto, la respuesta es «bloqueado» aunque el PIN haya sido correcto o incorrecto. La cola de promesas actual queda solo para el camino sin Web Locks. Consecuencia: con Web Locks se verifican como máximo `intentos_pin_max` PIN por par en todo el teléfono; sin ellos ningún fallo se pierde y ninguna derivación de más da información (todas responden «bloqueado»). El candado por par deja verificar a la vez el PIN de dos supervisores distintos. La derivación (600 000 iteraciones) se serializa por par: dos intentos del mismo par esperan uno al otro, que es lo buscado.
- **B. Solo la transacción atómica con la nueva lectura** (sin Web Locks). Consecuencia: ningún fallo se pierde, pero con N pestañas se pueden **derivar** hasta `intentos_pin_max + N − 1` PIN (las de más responden «bloqueado»); menos código.
- **C. Solo Web Locks**, con la escritura como hoy. Consecuencia: correcto donde hay Web Locks; sin ellos vuelve el problema.

**Límite inherente (no es una decisión nueva).** La sal y la derivación del PIN de cada supervisor viven en el teléfono (bootstrap, SYN-11), así que quien tenga acceso técnico al navegador puede probar PIN fuera de la aplicación sin pasar por ningún contador. `02` §12.4 ya lo registra como **riesgo aceptado** («una derivación de un PIN numérico puede atacarse por fuerza bruta con acceso técnico al dispositivo»), con sus mitigaciones (longitud mínima, rotación, límite en la interfaz, observación `AUTORIZACION_OFFLINE` y auditoría), y ADR-063 D10 lo repite para el borrado de los datos del navegador. D9 cierra el contador de la interfaz; no cambia ese riesgo. ADR-064 lo cita.

**Prueba que reproduce la pérdida.** Dos «pestañas» en Vitest = dos conexiones Dexie sobre la misma base de `fake-indexeddb` y dos copias del módulo (`vi.resetModules`), con una derivación lenta simulada para forzar la intercalación y un `navigator.locks` de prueba con exclusión real entre las dos copias. Con `intentos_pin_max = 5` y tres intentos fallidos simultáneos por pestaña: con el código actual la fila termina con menos fallos que los intentos incorrectos informados y más de 5 respuestas «incorrecto» (RED); con D9, exactamente 5 fallos contados, ninguna derivación más allá de la quinta con Web Locks, y el resto «bloqueado».

### D10 — Guarda completa del carrito (deuda del 22a) · técnica · MEDIA · VTA-07, `02` §13.5

- **A (recomendada).** `App.tsx` pasa a `createBrowserRouter` + `RouterProvider` con **una sola ruta comodín** que monta el `AppRoutes` actual: las rutas descendientes (`<Routes>` de `/ruta` y `/admin`, la carga diferida) no cambian. Vender usa `useBlocker` mientras el carrito está ocupado: cubre el menú inferior, los enlaces del cuerpo, «Ver más», el botón atrás del navegador y del teléfono, con el mismo diálogo «¿Descartar la venta?»; la intercepción a mano del menú en `RutaLayout` se quita (un solo camino). La navegación que hace la propia venta al confirmar (a «Venta guardada») no se bloquea. Mientras está ocupado, además, `beforeunload` pide el aviso del navegador al recargar o cerrar la pestaña (su texto lo pone el navegador). **Pruebas:** las de `/ruta` que montan Vender (`FlujoVentaRuta`, `FlujoRuta`, `VenderScreen`, el ayudante `rutaDePrueba.tsx`) pasan a `createMemoryRouter`; las de `/admin` siguen con `MemoryRouter` porque no usan `useBlocker`. Consecuencia: la guarda cubre toda navegación de la aplicación; cambio acotado al arranque y a unas pocas pruebas.
- **B. Mantener `BrowserRouter` e interceptar el historial a mano** (`popstate` y clics capturados). Consecuencia: sin migración, pero frágil (el botón atrás ya cambió la URL cuando se entera) y duplica lo que el enrutador hace.
- **C. Migrar todas las rutas a objetos con `lazy` del enrutador.** Consecuencia: aprovecha cargadores de datos que hoy no se usan; reescribe todas las rutas y casi cien pruebas.

### D11 — Renovación de sesión entre pestañas (riesgo hallado) · autenticación · CRÍTICA

El refresh token rota en cada uso y **reusar uno ya rotado revoca toda la familia del dispositivo** (`02` §12.1). El access token vive en memoria de cada pestaña, así que cada pestaña renueva por su cuenta: si dos pestañas renuevan **a la vez** con la misma cookie, la segunda llega con el token ya rotado y el servidor cierra la sesión en todas. El riesgo existe desde el 21, pero el 22b lo vuelve frecuente (sincronización cada 2 minutos y en cada `online`). El servidor no tiene período de gracia.

- **A (recomendada).** `renovarSesion` y la renovación interna de `apiFetch` toman el Web Lock exclusivo `distribuidora:renovacion`: dos pestañas renuevan **una después de la otra**; la segunda manda la cookie nueva, que es válida. Sin Web Locks queda como hoy. Sin cambios en el servidor ni en la cookie. Consecuencia: desaparece la revocación por renovaciones simultáneas en navegadores con Web Locks; cada pestaña sigue con su access token.
- **B. Dejarlo como está.** Consecuencia: con varias pestañas abiertas, una revocación de la familia de vez en cuando obliga a iniciar sesión con conexión (la cola se conserva, pero el vendedor sin señal queda sin poder enviar hasta tenerla).

### D12 — Cómo se prueba el criterio 8 (INV-06 de punta a punta) · técnica · MEDIA

- **A (recomendada).** (1) **Servidor, concurrencia con commits reales** (`backend/tests/concurrency/`): dos lotes simultáneos con el mismo sobre de `VENTA_CONFIRMAR` `OFFLINE` (el fixture de contrato con datos reales): una sola venta, y stock, saldo, costo congelado y utilidad iguales a los de un solo envío; cita **INV-06** y SYN-02. (2) **Cliente** (Vitest con `fake-indexeddb` y un servidor simulado idempotente): dos pestañas disparan a la vez y sale un solo lote; la respuesta se pierde después del commit, el reenvío trae el mismo resultado y la venta local queda una sola vez `ACEPTADA`; citan **INV-06**. (3) **Prueba manual**: «Sincronizar» dos veces seguidas y la consulta en `/admin`. Consecuencia: el criterio 8 queda cubierto en las dos puntas sin código de servidor nuevo.
- **B. Solo las pruebas del cliente** y la del change 04. Consecuencia: la del 04 usa un comando genérico; no prueba stock, saldo, costo y utilidad de una venta.

### D13 — Ayuda contextual · interfaz · BAJA · ADR-051

- **A (recomendada).** Cuatro claves nuevas de `/ruta`, **sin ejemplos**, y una revisada:
  - `ruta.sincronizar` — **Sincronizar**: «Envía al sistema las ventas sin enviar de tu usuario, en el orden en que las hiciste. Se hace sola al abrir la aplicación o volver a ella, al volver la señal, después de cada venta y cada 2 minutos. Enviar dos veces la misma venta no la duplica.» (SYN-02, SYN-03, INV-06)
  - `ruta.ventaConObservaciones` — **Con observaciones**: «El sistema aceptó la venta y anotó algo para que administración lo revise. La venta vale igual; no tenés que hacer nada.» (SYN-04, SYN-05, SYN-08)
  - `ruta.ventaRechazada` — **Rechazada**: «El sistema no aceptó la venta por un problema de datos, no por stock ni por crédito. Sigue guardada en el teléfono y no se vuelve a enviar sola: avisá a administración.» (SYN-06, SYN-09)
  - `ruta.versionMinima` — **Versión desactualizada**: «Esta versión de la aplicación ya no puede confirmar ventas nuevas. Las ventas guardadas se siguen enviando. Actualizá la aplicación para volver a vender.» (ADR-064)
  - **Revisada** `ruta.ventaSinEnviar` — **Sin enviar**: «La venta ya está confirmada y guardada en el teléfono. Se envía sola cuando haya señal, o con «Sincronizar»; hasta entonces no se borra.» (SYN-01, SYN-09)
  `ruta.pinSupervisor` no cambia (D9 no cambia lo que ve el vendedor). Consecuencia: la prueba de claves y de IDs citados de ADR-051 cubre las nuevas.
- **B. Sin ayudas nuevas.** Consecuencia: «Con observaciones» y «Rechazada» quedan sin explicar.

## Risks / Trade-offs

- [El servidor procesa el lote pero la respuesta se pierde] → el reenvío con el mismo `operation_id` devuelve el resultado guardado (INV-06); D3 lo aplica igual.
- [Dos pestañas sin Web Locks envían a la vez] → sin efecto duplicado (INV-06; D3 idempotente); D2.
- [Doble conteo de saldo y stock tras sincronizar y actualizar datos, hasta el 22c] → lo conservador (D4 = A); queda dicho en la spec y en ADR-064.
- [Renovaciones simultáneas revocan la sesión] → D11 (aprobada de forma explícita: dominio crítico).
- [La versión de la compilación no se define y queda `0.0.0`] → D7 toma `APP_VERSION`; una versión sin formato no restringe.
- [`useBlocker` exige el enrutador de datos y rompe las pruebas que montan Vender con `MemoryRouter`] → D10 acota la migración a esas pruebas.
- [Un rechazo por un dato que el teléfono armó mal se repite en cada venta] → el estado «Rechazada» con su código es visible desde la cabecera; el 22c agrega la pantalla de conflictos.

## Migration Plan

Sin migración de servidor ni versión nueva de Dexie (D3 solo amplía los valores de `cola.estado`; las filas del 22a ya están en `PENDIENTE`). La compilación de producción necesita `APP_VERSION` con formato `X.Y.Z` para que la versión mínima tenga efecto (D7); sin él no restringe nada. Volver atrás: la versión anterior lee `cola.estado` distinto de `PENDIENTE` como «no pendiente» y no lo reenvía.

## Open Questions

Ninguna que cambie lo que se construye.
