# Diseño técnico — 21-pwa-y-bootstrap

> **Estado: APROBADAS (2026-10-30).** El usuario aprobó D0 a D21 con la opción A, **salvo D14 = B** (el PIN se pide solo al abrir la aplicación). Cada decisión conserva sus opciones y consecuencias; la elegida se marca **APROBADA**. Se documenta en **ADR-062** (*Propuesto* hasta el archivo, en `docs/adr/ADR-062-pwa-bootstrap-y-sesion-local.md`) y en `propuesta-docs.md`.
>
> **Gobernanza.** **ALTA** (seguridad de la sesión y de las credenciales en el dispositivo): D8, D13, D14, D15, D16. **MEDIA:** D1 a D7, D10, D11, D17, D18, D20. **BAJA:** D0, D9, D12, D19, D21. **De negocio** (el agente solo recomienda; decide el usuario): **D2, D4, D5, D6, D7, D8, D11, D12, D13, D14, D15, D16, D19**.
>
> **Revisión.** El usuario aprueba las decisiones y los textos de ayuda antes del apply (tareas 0.1 a 0.3) y revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Lecturas del 18a/18b** en `ventas/queries.py`: `contexto_de_venta` (tope, permisos, motivos de `DESCUENTO_MANUAL`, autorizadores sin derivación), `descuentos_aplicables` (reglas vigentes *ahora*), `credito_para_vender` (por cliente), `versiones_elegibles` (vigente e históricas de una lista), `numeracion_del_dispositivo`. Ninguna sirve tal cual para el bootstrap: son de a un cliente o una lista, o miran solo "ahora".
- **Servicios ya públicos** para el 21: `clientes/service.py::listar_cartera` y `resolver_datos_de_credito` (20b, 18b), `configuracion/service.py::listar_motivos_activos`, `listar_alicuotas_activas`, `listar_medios_pago_activos` (20c, 17b), `catalogo/service.py::productos_activos_para_vender` y `presentaciones_para_venta`, `stock/service.py::stock_de_ubicacion_para_vender` y `jornada_abierta_con_ubicacion_de`, `cuentas_corrientes/service.py::obtener_saldo` (de a uno), `identidad/service.py::listar_permisos_del_usuario`, `listar_autorizadores_disponibles`, `obtener_configuracion`.
- **PIN de autorización** (ADR-019, ADR-055): `usuario.pin_autorizacion_hash/sal/iteraciones`, PBKDF2-HMAC-SHA256, sal de 32 bytes, 600 000 iteraciones (`core/seguridad.py`). Web Crypto deriva lo mismo (`crypto.subtle.deriveBits` con `PBKDF2`/`SHA-256`).
- **Frontend:** `/ruta` es un placeholder con carga diferida; `lib/dispositivo/db.ts` es Dexie v1 con solo `meta` (`dispositivo_id`); `lib/api/httpClient.ts` y `lib/auth/tokenStore.ts` (token en memoria, renovación única) sirven a las dos áreas; el login, "Mi contraseña" y "Abrir jornada" viven en `/admin`; la ayuda (`ayuda/textos.ts`, `TemaDeAyudaVista`) está preparada para que `/ruta` monte la suya (ADR-051). `pdfmake` ya se carga con `import()` dinámico (ADR-059). `vite-plugin-pwa` **no** está instalado.
- **Módulos (`02` §5.3):** `sync ──► todos los módulos con comandos`, solo por `service.py`.

Lo que `docs/` **no** resuelve (cada punto es una decisión): dónde vive el bootstrap (D1); quién lo pide y cuándo (D2, D11); coherencia de la lectura (D3); qué clientes, listas, versiones y reglas baja (D4 a D6); costos (D7); qué autorizadores (D8); forma del contrato (D9); esquema local (D10); login, PIN, bloqueo, cierre de sesión y cambio de usuario (D12 a D16); service worker y persistencia (D17, D18); pantallas (D19); cómo probar en el teléfono (D20); ayuda (D21).

## Goals / Non-Goals

**Goals:** que el vendedor abra la jornada en `/ruta`, baje los datos del día en una sola descarga coherente y los consulte sin señal tras desbloquear con su PIN, con la aplicación instalada y la base local protegida del borrado.

**Non-Goals:** operar sin conexión (vender, cobrar, anular, cola, verificar el PIN de un supervisor: 22a a 23); sincronización (22b); bootstrap incremental (etapa 4); cifrado local (etapa 4); mover la venta con conexión de `/admin` a `/ruta`.

## Decisions

### D0 — Tamaño y lotes · alcance · BAJA

- **A (recomendada). Un change en cinco lotes**, sin frenar entre lotes, anotado como excepción de tamaño como el 17 y el 18a: **Lote 1** bootstrap en el backend; **Lote 2** base local y aplicación del bootstrap; **Lote 3** sesión local (login de ruta, PIN, bloqueo, cierre y cambio de usuario); **Lote 4** PWA y pantallas de `/ruta` con su ayuda; **Lote 5** ADR, docs, cobertura, suites completas y prueba manual (escritorio y teléfono real). Consecuencia: pasa de tres días; los cortes coinciden con capas independientes.
- **B. Dos changes:** 21a (bootstrap y base local) y 21b (PWA, sesión local y pantallas). Consecuencia: el 21a no deja nada visible en el teléfono; dos propuestas, dos archivos y dos pruebas manuales.
- **C. Un lote único.** Consecuencia: un subagente con todo el contexto; contra la preferencia de un subagente por lote.

### D1 — Dónde vive el bootstrap · técnica · MEDIA

- **A (recomendada). En `sync`** (`modules/sync/bootstrap.py` + ruta en `sync/api.py`), que compone **solo por `service.py`** de cada módulo; cada módulo agrega a su `service.py` la lectura masiva que falte (saldos de todos los clientes en una consulta, crédito resuelto de todos, versiones con precios de varias listas, reglas no vencidas). Consecuencia: respeta `02` §5.3 (`sync ──► todos`) sin contrato nuevo de `import-linter`; `ventas` no crece.
- **B. En `ventas/queries.py`**, junto al contexto de venta. Consecuencia: reutiliza más directo, pero `ventas` pasa a conocer stock de toda la ubicación, catálogos y configuración que no son de la venta; la cobranza sin conexión (23) dependería de `ventas`.
- **C. Módulo nuevo `ruta`.** Consecuencia: un módulo más en `02` §5 y en `import-linter` para una sola lectura.

### D2 — Quién pide el bootstrap · negocio · MEDIA

- **A (recomendada). Sesión habilitada y jornada `ABIERTA` propia en el dispositivo del token**, sin permiso adicional; sin ella, 409 `JORNADA_REQUERIDA` (el código que ya usa SYN-10). Cada sección se filtra por permiso (contexto de venta y autorizadores con `VENDER`; versiones anteriores con `USAR_LISTA_ANTERIOR`). Consecuencia: la jornada ya exigió `ABRIR_JORNADA`; un rol de solo cobranza (23) también baja sus datos; `EN_RENDICION` no baja datos nuevos.
- **B. Como A, más `VENDER` o `REGISTRAR_COBRANZA`.** Consecuencia: un permiso explícito; un vendedor que perdió `VENDER` con la jornada abierta no puede ni consultar sus datos.
- **C. Sin exigir jornada** (sin stock si no hay). Consecuencia: cualquiera baja todos los clientes y precios al teléfono; contra RUT-03 y la minimización de ADR-011.

### D3 — Una foto coherente · técnica · MEDIA

- **A (recomendada). Una transacción `REPEATABLE READ READ ONLY`** solo para el bootstrap (excepción de solo lectura a `02` §7.1, en ADR-062). Consecuencia: stock, saldos, precios y reglas del mismo instante; sin bloqueos; prueba de concurrencia con commits reales.
- **B. `READ COMMITTED` como todo el sistema.** Consecuencia: una venta confirmada en medio puede dejar el saldo del cliente después y el stock antes; el 22c calcularía disponibles locales con datos mezclados.

### D4 — Qué clientes y qué datos · negocio · MEDIA

- **A (recomendada). `ACTIVO` y `SUSPENDIDO` de toda la organización más el consumidor final si está habilitado**, con `en_cartera` ("vacía = todos"); código, nombre, razón social, documento, dirección, teléfono, estado, lista asignada, consumidor final, saldo y crédito resuelto (límite, política y tolerancia aplicables). Sin correo ni vendedor asignado. Consecuencia: cumple `01` §19 (buscar en todos, también sin conexión, INV-17); los datos de contacto alcanzan para la nota y para encontrar el negocio.
- **B. Solo la cartera y el consumidor final.** Consecuencia: menos datos personales en el teléfono, pero sin señal no puede venderle a un cliente fuera de su cartera, contra `01` §19.
- **C. Como A, con correo y vendedor.** Consecuencia: más datos sin uso en el teléfono.

### D5 — Qué listas y versiones · negocio · MEDIA

- **A (recomendada). Sin `USAR_LISTA_ANTERIOR`:** la predeterminada y las asignadas a los clientes bajados, con su versión vigente y las programadas (D6). **Con el permiso:** todas las listas activas con vigente, programadas y **todas** las históricas elegibles (PRC-21). Consecuencia: cada vendedor tiene lo que puede usar; con ~100 productos, decenas de versiones son pocos miles de filas (ADR-006).
- **B. Como A, pero solo las 3 históricas más recientes por lista.** Consecuencia: acota el tamaño; una versión más vieja, permitida por PRC-21, no se puede elegir sin conexión.
- **C. Siempre todas las listas y versiones, sin mirar el permiso.** Consecuencia: más simple; baja precios que el vendedor no puede usar.

### D6 — Lo que entra en vigencia durante la jornada · negocio · MEDIA

- **A (recomendada). Bajar también las versiones `PUBLICADA` programadas y las reglas `ACTIVA` que empiezan más tarde** (sin las anuladas ni las vencidas), cada una con su vigencia; el dispositivo elige por el momento de la operación (PRC-20). Consecuencia: una versión que arranca a las 14:00 se usa sin señal a las 14:05; si se anula después del bootstrap, la venta llega con `LISTA_NO_VIGENTE` (ya previsto).
- **B. Solo lo vigente al momento del bootstrap.** Consecuencia: a las 14:05 sin señal el dispositivo sigue con la versión vieja y toda venta llega con `LISTA_NO_VIGENTE`; las reglas nuevas no se aplican hasta actualizar.

### D7 — Costos en el teléfono · negocio · MEDIA

- **A (recomendada). Ningún costo**, ni con `VER_COSTOS`. Consecuencia: ninguna pantalla de `/ruta` los usa (el costo lo congela el servidor al sincronizar, ADR-054); minimiza lo que expone un teléfono perdido (ADR-011). SYN-11 lo permite, no lo exige.
- **B. Costo promedio por producto con `VER_COSTOS`.** Consecuencia: un dato sensible sin pantalla que lo use; habría que reenviarlo en cada cambio de promedio.

### D8 — Autorizadores y sus derivaciones · seguridad · ALTA

- **A (recomendada). Con `VENDER`:** usuarios activos, de rol activo, distintos de quien pide, con algún permiso de autorización de excepciones **y** PIN definido; con nombre, permisos de autorización (`AUTORIZAR_DESCUENTO`, `SUPERAR_CREDITO`, `VENDER_CLIENTE_SUSPENDIDO`, `USAR_LISTA_ANTERIOR`), hash, sal e iteraciones. Sin `VENDER`, vacío. Un **vector de prueba compartido** (`shared/fixtures/pin/`) prueba que Python y Web Crypto derivan lo mismo. Consecuencia: el 22a solo agrega la verificación local; quien no puede vender no lleva derivaciones (`02` §12.4, riesgo aceptado de ADR-011).
- **B. Como A, más los autorizadores sin PIN** (marcados). Consecuencia: la pantalla podría decir "sin PIN", pero baja nombres y permisos sin uso sin conexión.
- **C. Todos los supervisores, sin mirar el permiso de quien pide.** Consecuencia: más derivaciones expuestas a fuerza bruta en más teléfonos.

### D9 — Forma del contrato · contrato · BAJA

- **A (recomendada). Una respuesta con secciones:** `generado_en`, `sesion` (usuario, permisos, jornada, numeración), `configuracion` (organización y nota), `contexto_venta`, `catalogos` (medios, motivos de todos los ámbitos, alícuotas), `productos` (con presentaciones), `clientes`, `listas` (con versiones y precios), `reglas_descuento` (con alcances), `stock`, `autorizadores`. Importes y porcentajes como string. Esquemas Pydantic propios en `sync/schemas.py`; `schema.gen.ts` regenerado. Consecuencia: una sola foto (D3); el cliente aplica todo de una vez.
- **B. Un endpoint por sección.** Consecuencia: varias fotos distintas; contra D3.

### D10 — Base local · técnica · MEDIA

- **A (recomendada). Dexie v2 con las tablas maestras de `02` §13.2** (`sesion`, `configuracion`, `productos`, `presentaciones`, `clientes`, `listas`, `versiones`, `precios`, `reglas_descuento`, `stock`, `autorizadores`, `catalogos`) más `meta`; `ventas`, `cobranzas`, `movimientos_locales` y `cola` llegan con el 22a, cuando tengan consumidor. Aplicar el bootstrap = una transacción `rw` que vacía y rellena **una lista explícita** de tablas maestras y escribe `meta.fecha_bootstrap` y `meta.jornada_id`. Consecuencia: el "DEBE NO tocar" de `02` §13.4 queda garantizado por construcción (lista explícita) y probado; sin índices adivinados.
- **B. Crear ya todas las tablas de §13.2.** Consecuencia: índices de `cola` y `ventas` definidos sin conocer al 22a; una migración local menos.

### D11 — Cuándo se ejecuta el bootstrap · negocio · MEDIA

- **A (recomendada). Tras abrir la jornada desde `/ruta`; al iniciar sesión o desbloquear con conexión si la base no tiene datos de la jornada abierta del usuario en ese dispositivo (`GET /stock/jornadas/actual`); y con "Actualizar datos".** Consecuencia: una jornada abierta desde `/admin` o una recarga no dejan al vendedor sin datos; nunca reemplaza datos en segundo plano sin que el vendedor lo pida.
- **B. Solo al abrir.** Consecuencia: literal a RUT-03, pero un login nuevo con la jornada ya abierta deja el teléfono vacío.
- **C. Como A, más una actualización periódica con conexión.** Consecuencia: precios que cambian a mitad de la ruta sin aviso; con el 22a, choca con un carrito abierto.

### D12 — Login de `/ruta` · interfaz · BAJA

- **A (recomendada). Pantalla propia `/ruta/login`** sobre el mismo `POST /auth/login` y el `useLogin` existente movido a `features/identidad`, con diseño para teléfono. Consecuencia: el teléfono no descarga `/admin` (`02` §13.1).
- **B. Reusar `/admin/login` y redirigir.** Consecuencia: el teléfono descarga el bundle de administración.

### D13 — PIN de desbloqueo · seguridad · ALTA

- **A (recomendada). Exactamente 6 dígitos, dos veces, sin triviales** (misma regla de ADR-055: todos iguales o escalera de paso 1); PBKDF2-SHA256 con Web Crypto, sal de 32 bytes, **600 000 iteraciones** (las del servidor; ~1 s en un teléfono medio); guardado en `sesion` (hash, sal, iteraciones), nunca en claro ni enviado. Consecuencia: mismo largo que el PIN de supervisor (ADR-011); una regla para los dos PIN.
- **B. 4 a 6 dígitos y 210 000 iteraciones.** Consecuencia: más cómodo y rápido; 10 000 combinaciones de 4 dígitos ante un ataque con acceso técnico.
- **C. Contraseña alfanumérica local.** Consecuencia: más segura, incómoda en la calle.

### D14 — Cuándo se pide el PIN · seguridad · ALTA

- **A (recomendada, no elegida). Al abrir la aplicación y al volver de segundo plano después de 5 minutos.** Consecuencia: un teléfono olvidado desbloqueado se cierra solo.
- **B (APROBADA 2026-10-30). Solo al abrir la aplicación (arranque en frío o recarga), con o sin conexión.** Con conexión, después del PIN se renueva el token. No hay constante de tiempo ni regla de segundo plano. Consecuencia aceptada por el usuario: si la aplicación queda abierta o en segundo plano con el teléfono desbloqueado, se puede usar sin PIN hasta que se cierre la aplicación.
- **C. Solo sin conexión** (con señal entra por el refresh). Consecuencia: el PIN no protege un teléfono con señal.

### D15 — Bloqueo por intentos · seguridad · ALTA

- **A (recomendada).** Cuenta en Dexie (sobrevive a recargas), se reinicia con un acierto; con **10 fallos** (APROBADO 2026-10-30: constante fija en código, como el tope de 20 de ADR-055; ya no usa `intentos_pin_max`, que sigue en 5 y rige solo para los fallos de un usuario contra el PIN de un mismo supervisor, en línea) se **borra la derivación** y se exige login con conexión; datos maestros y pendientes intactos; tras el login, PIN nuevo. Consecuencia: SEG-04 literal; borrar la derivación impide seguir probando aunque se manipule la cuenta en la interfaz.
- **B. Bloqueo temporal de 15 minutos y luego más intentos.** Consecuencia: SEG-04 dice "requiere inicio de sesión con conexión"; contradice la regla.

### D16 — Cerrar sesión y otro usuario · seguridad · ALTA

- **A (recomendada). Una sesión local por dispositivo.** "Cerrar sesión" solo con conexión: `POST /auth/logout` y borra sesión, derivación y datos maestros; nunca operaciones pendientes. Si inicia sesión otro usuario, se borran sesión, PIN y datos maestros del anterior antes de seguir; sus pendientes (22a) quedan para cuando vuelva (`02` §12.3). Consecuencia: los datos de un vendedor no quedan a la vista del siguiente.
- **B. Conservar los datos maestros al cambiar de usuario.** Consecuencia: el segundo usuario ve clientes, precios y derivaciones bajados con los permisos del primero.

### D17 — Service worker · técnica · MEDIA

- **A (recomendada). `vite-plugin-pwa` (versión exacta) con `generateSW`, `registerType: 'prompt'`**; precache del shell, los fragmentos de `/ruta`, la ayuda y pdfmake con sus fuentes; `globIgnores` del fragmento de `/admin` (nombre de fragmento fijo); `navigateFallback` a `index.html` con `navigateFallbackDenylist` para `/api/`; **sin `runtimeCaching`**; aviso "Hay una versión nueva" con "Actualizar"; manifiesto con `start_url: /ruta` y `display: standalone`. El 22a agrega la guarda del carrito abierto. Consecuencia: cumple `02` §13.5 con configuración, sin código de service worker propio.
  - **Versión elegida (tarea 0.2, 2026-10-30): `vite-plugin-pwa` 2.0.0, fijada exacta** (`devDependencies`, sin `^`). Verificada con `npm view`: `peerDependencies` `vite ^3.1.0 || … || ^7.0.0 || ^8.0.0` (el proyecto usa Vite `^8.3.0`), `workbox-build` y `workbox-window` `^7.4.1` (vienen como dependencias del paquete; última 7.4.1), `engines.node >=20.19.0` (la imagen del frontend usa Node 22). Hay que **reconstruir la imagen de Docker del frontend** (`docker compose build frontend`) por la dependencia nueva.
  - **Precisiones del apply (Lote 4):** (a) el código de `/admin` sale a `assets/admin/` con `build.rollupOptions.output.chunkFileNames` (todo fragmento que contenga un módulo de `src/areas/admin/`) y `globIgnores: ['assets/admin/**']`; los módulos compartidos de capas bajas (`features/`, `domain/`, `components/`) que Rollup deja en fragmentos comunes sí se precachean. La prueba `tests/unit/pwa/precache.test.ts` corre el build real y verifica el precache. (b) `navigateFallbackDenylist` lleva `/^\/api\//` **y `/^\/admin/`**: las navegaciones a `/admin` van siempre a la red, así un shell precacheado viejo nunca apunta a fragmentos de administración que ya no existen tras una publicación (no estaba en el texto original de D17; es una precisión sin efecto sobre `/ruta`). (c) Íconos del manifiesto generados en `frontend/public/` (192, 512, maskable y `apple-touch-icon` de 180 para iPhone); son provisorios, se reemplazan con el logo cuando exista. (d) El aviso de versión usa `virtual:pwa-register/react`; en Vitest se sustituye por `tests/unit/utils/pwaRegisterStub.ts` con `test.alias`.
- **B. `injectManifest` con un service worker escrito a mano.** Consecuencia: más control; más código que mantener sin necesidad hoy.
- **C. Precachear todo, `/admin` incluido.** Consecuencia: más simple; el teléfono descarga administración (contra `02` §13.1).

### D18 — Almacenamiento persistente · técnica · MEDIA

- **A (recomendada). Pedir `navigator.storage.persist()` tras el primer bootstrap y en cada arranque mientras no esté concedido**; advertencia permanente en el inicio si se niega o no existe, con su "(?)". Se adelanta del motor de sincronización (`02` §13.3) porque la fila del 21 en `04` §11 lo nombra. Consecuencia: Chrome lo concede a una aplicación instalada; Safari lo decide él.
- **B. Pedirlo solo una vez.** Consecuencia: si se concede después (instalada), la advertencia queda sin motivo.

### D19 — Pantallas de `/ruta` · negocio · BAJA

- **A (recomendada).** Inicio, Abrir jornada, Clientes (cartera primero, búsqueda en todos, ficha con saldo y disponible), Productos (precio por presentación de la versión vigente *ahora* de la lista predeterminada, stock de la camioneta), Stock, Mi cuenta (Mi contraseña, Cambiar PIN, Cerrar sesión) y Ayuda. **La venta sigue en `/admin`** hasta el 22a; "Mi PIN" de autorización sigue en `/admin`. Consecuencia: todo lo de `/ruta` es consulta; el 22a agrega la venta sin rehacer pantallas.
- **B. Como A, más la venta con conexión en `/ruta` leyendo de Dexie.** Consecuencia: adelanta medio 22a sin cola ni confirmación local.

### D20 — Probar en el teléfono real · técnica · MEDIA · **bloqueante para la prueba manual**

Service worker, Web Crypto y `storage.persist()` exigen HTTPS; la red local por `http://` no sirve (`04` §11: "probar en el teléfono real durante el 21").

- **A (recomendada). Perfil opcional de Docker Compose con Caddy de desarrollo** (`tls internal`) delante de Vite y del backend, en la IP de la red local; se instala y se confía el certificado raíz de Caddy en el teléfono (paso a paso para Android, que es el teléfono de prueba, y para iPhone como verificación futura u opcional). Consecuencia: todo local; adelanta parte del Caddy del 27a.
- **B. Túnel HTTPS temporal** (por ejemplo, un túnel rápido de Cloudflare) hacia Vite. Consecuencia: sin certificados; expone el entorno de desarrollo a internet mientras dura la prueba y depende de un servicio externo.
- **C. Esperar al entorno del 27a.** Consecuencia: contradice `04` §11; las limitaciones de Safari aparecen tarde.

**Respuesta del usuario (0.1, 2026-10-30):** los vendedores usan hoy **Android (Chrome)** y podrían pasar a iPhone. La aplicación debe seguir siendo compatible con iPhone/Safari: sin APIs solo de Android, instalación en iOS con "Compartir > Agregar a inicio" y persistencia según la política propia de Safari (D18). La prueba manual se hace en un Android real; los pasos para iPhone se documentan como verificación futura u opcional.

### D21 — Ayuda contextual · interfaz · BAJA · ADR-051

> **Textos aprobados por el usuario el 2026-10-30**, incluida `ruta.almacenamiento` tal como está escrita; `ruta.pin` no menciona ningún bloqueo por tiempo.

**A (recomendada).** `/ruta/ayuda` y `/ruta/ayuda/:tema` con `TemaDeAyudaVista`; `Ayuda` recibe la base de la ruta ("Ver más" interno en `/ruta`; en `/admin`, interno si `display-mode: standalone`, otra pestaña si no). Apertura de jornada reutiliza `stock.tomaActual`. Cuatro claves nuevas, **sin ejemplos** (textos a aprobar en 0.3):

| Clave | Pantalla y campo | Reglas | Texto propuesto |
| --- | --- | --- | --- |
| `ruta.pin` | Definir, ingresar y cambiar PIN | SEG-03; SEG-04; ADR-011 | "El PIN abre la aplicación en este teléfono, con o sin señal. No es tu contraseña. Si lo errás varias veces seguidas, tenés que iniciar sesión con conexión y definir uno nuevo; lo que tengas pendiente no se pierde." |
| `ruta.datosDelDia` | Inicio · fecha de los datos y "Actualizar datos" | SYN-11; ADR-006 | "Los clientes, precios, saldos y stock se descargan al abrir la jornada. Hasta que los actualices, ves los de ese momento, aunque no tengas señal. Actualizar requiere conexión y no toca lo que tengas pendiente." |
| `ruta.almacenamiento` | Inicio · advertencia | `02` §13.3 | "Este navegador no garantiza conservar los datos de la aplicación y puede borrarlos si le falta espacio. Instalá la aplicación en la pantalla de inicio y actualizá los datos con conexión cuando puedas." |
| `ruta.cartera` | Clientes · lista | `01` §19; ADR-060 | "Primero ves tus clientes asignados. Podés buscar y venderle a cualquier cliente de la organización." |

**B. Solo `ruta.pin` y `ruta.datosDelDia`.** Consecuencia: la advertencia de almacenamiento y la cartera quedan sin explicar.

## Risks / Trade-offs

- **[D13-A: 600 000 iteraciones en un teléfono lento]** → se mide en el teléfono real (D20); si pasa de 2 s, se revisa la constante antes de archivar (las iteraciones se guardan con cada derivación, así que subirla o bajarla no rompe las existentes).
- **[D8: derivaciones en el teléfono]** → riesgo aceptado de ADR-011; mitigado por D8-A (solo con `VENDER`, solo con PIN), D16-A y la revocación del dispositivo.
- **[D3-A: `REPEATABLE READ` en una base ocupada]** → es de solo lectura y no toma bloqueos; una transacción de solo lectura no aborta por conflictos de serialización en PostgreSQL.
- **[D17: nombre de fragmento de `/admin`]** → prueba de build que lista el manifiesto de precache y falla si aparece código de `/admin`.
- **[D10: el 22a agrega tablas]** → la versión 3 de Dexie las agrega sin tocar las maestras; la prueba de "no toca" se amplía allí.
- **[D14-B: teléfono desbloqueado con la app en segundo plano]** → riesgo aceptado por el usuario (2026-10-30): se usa sin PIN hasta cerrar la aplicación; el PIN protege el arranque y la sesión local ante pérdida con la app cerrada.
- **[Safari]** → `storage.persist()` y la instalación difieren; D18-A avisa y D20 prueba en el teléfono real.
- **[Tamaño de la respuesta]** → con los volúmenes de ADR-006 es chica; se registra el tamaño en el log del endpoint (`02` §17) para ver si hace falta el incremental.

## Migration Plan

Sin migración de Alembic. Dexie pasa de la versión 1 a la 2 agregando tablas (la tabla `meta` y el `dispositivo_id` no cambian). Dependencia nueva `vite-plugin-pwa` con versión exacta: **reconstruir la imagen de Docker del frontend**. Volver atrás: quitar el registro del service worker y publicar un service worker que se desregistra (`selfDestroying`) si hiciera falta.

## Open Questions

- Ninguna. La pregunta del teléfono de D20 quedó respondida (Android hoy, compatible con iPhone).
