# Diseño técnico — 22a-cola-confirmacion-local

> **Estado: APROBADAS el 2026-10-31: A en todas las decisiones salvo D6 = C y D10 = B.** Cada decisión conserva sus opciones con consecuencias; la elegida se marca "(elegida)". Las decisiones se documentan en **ADR-063** (*Propuesto* hasta el archivo, `docs/adr/ADR-063-venta-en-ruta-y-cola-local.md`).
>
> **Gobernanza.** **ALTA:** D10 (verificación local del PIN de un supervisor). **MEDIA:** D1 a D9, D12, D15, D16. **BAJA:** D0, D11, D13, D14, D17. **De negocio** (el agente solo recomienda; decide el usuario): **D1, D6, D7, D8, D10, D11, D13, D14, D16**.
>
> **Revisión.** El usuario aprobó las decisiones y los textos de ayuda el 2026-10-31 (tareas 0.1 y 0.2) y revisa con todo el change implementado; no se frena entre lotes.

## Context

Ver `proposal.md` (Why). Lo que ya existe y este change **reutiliza sin duplicar**:

- **Motor de cálculo del frontend** (gemelo del servidor, `02` §10.4): `domain/calculo.ts` (`calcularVenta`, VTA-04), `domain/descuentos/` (DSC-03 a DSC-07, `manual.ts` para DSC-06), `domain/credito/evaluacion.ts` (`evaluarCredito` con modo `SIN_CONEXION`, tolerancia y resoluciones `TOLERANCIA_OFFLINE` y `PIN_SUPERVISOR`), con sus fixtures compartidos `prc22`, `dsc05`, `dsc06`, `vta04` y `cre01`.
- **Lógica pura de la venta de `/admin`** (18a, 18b): `domain/ventas/composicion.ts` (cajas y unidades), `pedido.ts`, `calculoDeVenta.ts` (consumidor final de contado, saldo resultante), `descuentosDeVenta.ts`, `creditoDeVenta.ts` (hoy fijo en `CON_CONEXION`), `autorizacionDeVenta.ts` (una credencial por persona, `completarSeleccion`), `formularioVenta.ts` (`construirSolicitudDeVenta`, esquema Zod), `numeracion.ts` (formato `PPP-NNNNNN`; hoy guarda el correlativo en `localStorage`).
- **Nota** (20): `domain/ventas/notaDeVenta.ts` (`armarNotaDeVenta` sobre `DatosDeNotaDeVenta`), `lib/nota/documento.ts`, `pdf.ts`, `compartir.ts`; adaptador de la API en `features/ventas/nota.ts`. pdfmake ya está en el precache (21).
- **Base local** (21): Dexie v2 con las tablas maestras (`lib/dispositivo/db.ts`, `TABLAS_MAESTRAS`), `sync/aplicarBootstrap.ts` (una transacción sobre la lista explícita), lecturas puras en `domain/ruta/lecturasLocales.ts`, derivación PBKDF2 con Web Crypto en `lib/sesionLocal/pin.ts` y el vector compartido `shared/fixtures/pin/`. El bootstrap trae `configuracion.intentos_pin_max`, `motivo_obligatorio_lista`, política y tolerancia de la organización, cada cliente con saldo y crédito resuelto, `contexto_venta` (tope, `puede_superar_credito`), autorizadores con permisos y derivación, permisos del usuario, numeración y jornada.
- **Servidor:** `VENTA_CONFIRMAR` ya se acepta por `POST /api/v1/sync/comandos` en `OFFLINE` (18a, 18b): congela precios, descuentos y la evaluación de crédito del dispositivo; no valida el momento; acepta un motivo de lista inactivo; emite las observaciones de SYN-07. El lote no admite credenciales (ADR-056). **Este change no necesita código de backend.**
- `areas/ruta/pwa/AvisoDeVersion.tsx` (`registerType: 'prompt'`, "El 22a agrega la guarda del carrito") y `sync/cierreDeSesion.ts` (borra la sesión y los maestros, nunca las operaciones).

Lo que `docs/` **no** resuelve (cada punto es una decisión): si la venta de `/ruta` va siempre por la cola (D1); la forma exacta del sobre y cómo se prueba sin el 22b (D2); las tablas v3 (D3); dónde se asignan número y secuencia (D4); qué movimientos locales cuentan y dónde termina el 22a frente al 22c (D5); qué hace el teléfono con el stock insuficiente (D6) y con el resto de las reglas que con conexión rechazan (D7); el detalle del consumidor final (D8); el modo de la evaluación de crédito (D9); el límite de intentos local del PIN de supervisor (D10); el motivo dado de baja (D11); la guarda del carrito (D12); los estados visibles (D13); las pantallas (D14); los datos congelados de la nota local (D15); el cierre de sesión con pendientes (D16); la ayuda (D17).

## Goals / Non-Goals

**Goals:** que el vendedor, con o sin señal, confirme en el teléfono la venta del criterio 5 de `00` §9 (cliente con saldo, cajas y unidades, regla de volumen, descuento manual, cobro parcial con dos medios), resuelva la del criterio 6 (exceso de crédito según la política) y comparta la nota sin señal (criterio 7); que cada venta quede en la cola, lista para el 22b, sin poder quedar a medias.

**Non-Goals:** enviar la cola ni aplicar resultados (22b); conciliar los movimientos locales con un bootstrap posterior a una sincronización aceptada, conflictos, anulación sin conexión (22c); cobranza independiente sin conexión (23); mover la venta con conexión de `/admin` (sigue igual).

## Decisions

### D0 — Tamaño y lotes · alcance · BAJA

- **A (recomendada, elegida). Un change en cinco lotes**, sin frenar entre lotes: **Lote 1** base local v3, sobre, confirmación atómica (núcleo sin pantalla) y fixture de contrato con su prueba en el backend; **Lote 2** saldo y stock locales y reglas locales (crédito, consumidor final, cliente, lista, descuento, stock) como funciones puras; **Lote 3** verificación local del PIN de supervisor con su límite; **Lote 4** pantallas (Vender, venta confirmada, Ventas de hoy, pendientes en el inicio), nota desde Dexie, guarda del carrito, cierre de sesión con pendientes y ayuda; **Lote 5** ADR, docs, cobertura, suites completas y prueba manual (escritorio y Android). Consecuencia: los cortes coinciden con capas independientes; el núcleo atómico queda probado antes de la primera pantalla.
- **B. Dos changes:** 22a1 (base, cola y reglas) y 22a2 (pantallas y nota). Consecuencia: el 22a1 no deja nada visible en el teléfono; dos propuestas y dos pruebas manuales.

### D1 — Camino de la venta en `/ruta` · negocio · MEDIA

- **A (recomendada, elegida). Toda venta de `/ruta` se confirma en el teléfono y va por la cola como `VENTA_CONFIRMAR` `OFFLINE`, haya o no señal.** Consecuencia: un solo camino, el de `02` §13.1 y §13.3 ("después de cada operación local, si hay conexión", sincroniza el 22b); la venta nunca espera a la red y se comporta igual en un pozo de señal; con señal, las reglas que rigen son las sin conexión (tolerancia de crédito, PIN verificado en el teléfono, observaciones en vez de rechazos) y la venta no llega al servidor hasta el 22b. `/admin` sigue vendiendo con conexión como hoy.
- **B. Con señal, `POST /api/v1/ventas` `ONLINE` (como `/admin`); sin señal, la cola.** Consecuencia: dos caminos en el teléfono con dos manejos de error (rechazos 409/403 con señal, observaciones sin ella); una señal intermitente puede dejar la venta en duda entre los dos; la tolerancia y el PIN se comportan distinto según la barra de señal.
- **C. `/ruta` vende solo sin señal y con señal deriva a `/admin`.** Consecuencia: el teléfono no tiene `/admin` (`02` §13.1); inviable.

### D2 — Sobre del comando y prueba de contrato · técnica · MEDIA

- **A (recomendada, elegida).** El sobre es el del lote (`02` §6.2, `ItemLoteComandoRequest`): `operation_id` UUIDv7 (`lib/api/operationId.ts`), `tipo = VENTA_CONFIRMAR`, `version = 1`, `modo = OFFLINE`, `usuario_id` y `dispositivo_id` de la sesión local, `jornada_id` del bootstrap, `occurred_at` del reloj del teléfono al confirmar (UTC, ISO), `secuencia` (D4), `app_version` de la compilación y `contenido` = `VentaConfirmarRequest` sin `credenciales` y con `credito` completo (D9). La huella la calcula el servidor. Un **fixture de contrato** `shared/fixtures/sync/venta-confirmar-offline.json` (con identificadores simbólicos) lo producen las funciones puras del teléfono (Vitest compara) y el backend lo valida con los esquemas del lote y de la venta y, en una prueba de integración, lo envía al lote con identificadores reales y espera `ACEPTADO`. Por qué: la app no circulará hasta completar el sistema, así que esta prueba es la única verificación, antes del 22b, de que lo que arma el teléfono lo acepta el servidor, y el 22b la reutiliza como base. Consecuencia: el 22b no descubre un sobre mal armado recién al enviar; no hay código nuevo en el servidor.
- **B. Sin prueba del lado del servidor hasta el 22b.** Consecuencia: menos trabajo hoy; un campo mal nombrado recién se descubriría en el 22b.

### D3 — Base local v3 · técnica · MEDIA

- **A (recomendada, elegida). Versión 3 de Dexie** con cinco tablas que el bootstrap no toca (`TABLAS_MAESTRAS` no cambia):
  - `ventas` (`venta_id`; índices `jornada_id`, `estado_envio`, `numero`): el contenido enviado, el resultado del cálculo local (líneas con bruto, descuentos, neto, IVA; totales), la evaluación de crédito y los **datos congelados de la nota** (D15), `operation_id`, `occurred_at`, `estado_envio` (D13).
  - `cobranzas` (`cobranza_id`; índice `venta_id`): la cobranza de la venta con sus medios (el 23 suma las independientes).
  - `movimientos_locales` (`++id`; índices `operation_id`, `[jornada_id+producto_id]`, `[jornada_id+cliente_id]`): tipo (`VENTA_STOCK`, `VENTA_DEBITO`, `COBRANZA_CREDITO`), cantidad base entera o importe string, estado de la operación.
  - `cola` (`secuencia`; índices `operation_id` único, `estado`): el sobre completo y su estado.
  - `intentos_pin` (`[usuario_id+autorizador_id]`): fallos contados y la derivación contra la que se contaron (D10); no guarda horas.
  - `meta` suma `ultimo_correlativo` y `ultima_secuencia`.
  Consecuencia: es la tabla de `02` §13.2 con `cobranzas` separada; la nota y "Ventas de hoy" leen `ventas` sin abrir la cola; la prueba del 21 se amplía a las cinco tablas.
- **B. Solo `cola` y `movimientos_locales`;** la venta se lee del contenido encolado. Consecuencia: menos tablas, pero el 22b borra o marca filas de la cola al recibir el resultado y la venta (y su nota) dejaría de existir en el teléfono, contra SYN-09.

### D4 — Transacción de confirmación, número y secuencia · técnica · MEDIA · INV-01

- **A (recomendada, elegida). Una sola transacción `rw` de Dexie** sobre `meta`, `ventas`, `cobranzas`, `movimientos_locales` y `cola`: lee `ultimo_correlativo` y `ultima_secuencia`, asigna el número (`max(numeracion.ultimo_correlativo del bootstrap, meta.ultimo_correlativo) + 1`, VTA-06, `02` §7.7) y la secuencia siguiente, escribe venta, cobranza, movimientos y comando, y actualiza los dos contadores. Todo el cálculo y la verificación del PIN ocurren **antes**, fuera de la transacción (Dexie no admite esperas ajenas dentro de ella). Si algo falla, no queda nada y el carrito sigue abierto. El número se muestra **después** de confirmar. Reconfirmar (doble toque, reintento tras error) reutiliza el mismo `operation_id` y `venta_id` del carrito: si la venta ya existe, no se encola otra (INV-06 local). El correlativo de `/ruta` deja de usar `localStorage`. Consecuencia: número y cola sin huecos ni repeticiones aunque se cierre la aplicación a mitad.
- **B. Número propuesto al abrir el carrito** (como `/admin`) y reservado en `meta` aparte. Consecuencia: el vendedor ve el número antes, pero un carrito descartado deja un hueco y la reserva es una segunda escritura fuera de la transacción.

### D5 — Saldo y stock locales; frontera con el 22c · técnica · MEDIA

- **A (recomendada, elegida). El 22a calcula** saldo considerado = saldo del cliente en el bootstrap + movimientos locales de cuenta (débitos de venta menos cobranzas) **de la jornada del bootstrap** cuyas operaciones no tienen resultado del servidor (CRE-08, COB-04); stock disponible = stock del bootstrap − ventas locales de esa jornada sin resultado (RUT-04). En el 22a todas están pendientes, así que cuentan todas las de la jornada; las de otra jornada (de antes de un cambio de usuario) no cuentan. El 22c resuelve qué pasa con los movimientos de operaciones ya aceptadas cuando llega un bootstrap posterior (no contarlos dos veces) y la pantalla de conflictos. Consecuencia: la evaluación de crédito que se encola es la de CRE-08 (obligatoria sin conexión, CRE-09) y la segunda venta del criterio 6 ve la primera.
- **B. Solo los valores del bootstrap; los locales en el 22c.** Consecuencia: la segunda venta a un cliente ignora la primera y el crédito encolado contradice CRE-08 hasta el 22c.

### D6 — Stock insuficiente en el teléfono · negocio · MEDIA

`PERMITIR_STOCK_NEGATIVO` es un permiso de la operación con conexión (`01` §19, STK-05); sin conexión rige STK-06.

- **A. Bloquear** la línea que supera el disponible local (D5), sin excepción. Consecuencia: protege de un error de carga; si se cargó mercadería al vehículo después del bootstrap (RUT-02), sin señal el vendedor no puede venderla hasta "Actualizar datos", ni siquiera un superior que sale a vender.
- **B. Avisar y dejar confirmar a todos:** la línea muestra "Supera el stock del vehículo (quedan N)" y la confirmación pide "Vender igual"; el servidor deja `STOCK_NEGATIVO` (STK-06). Consecuencia: coherente con SYN-05 y con datos desactualizados, pero cualquier vendedor podría dejar stock negativo.
- **C (elegida, aprobada el 2026-10-31). Bloquear salvo `PERMITIR_STOCK_NEGATIVO`,** que viene en los `permisos` del bootstrap (`backend/app/modules/sync/bootstrap.py`). Sin el permiso, la línea que supera el stock del vehículo no se confirma y el mensaje indica actualizar los datos con señal. Con el permiso, la línea avisa "Supera el stock del vehículo (quedan N)" y la confirmación pide "Vender igual"; el servidor deja `STOCK_NEGATIVO` (STK-06) como red de seguridad. Motivo: un superior puede salir a vender, pero no todos deberían dejar stock negativo. Consecuencias: la matriz de `01` §19 hoy da el permiso solo a `admin`, pero los roles son configurables desde el 20b, así que se puede darlo a quien salga a vender; el permiso, definido como "Operar con stock negativo online", extiende su alcance a la verificación local de las ventas sin conexión (se registra en ADR-063 y se actualiza `01`, tarea 19.1); un vendedor con el stock del bootstrap desactualizado queda sin vender esa línea hasta "Actualizar datos".

### D7 — Reglas que el teléfono aplica antes de encolar · negocio · MEDIA

- **A (recomendada, elegida). Las mismas que con conexión, con los datos y los permisos del bootstrap (SYN-10),** salvo stock (D6: bloqueo salvo `PERMITIR_STOCK_NEGATIVO`) y costo (el teléfono no lo tiene; el servidor deja `VENTA_SIN_COSTO`): cliente suspendido sin `VENDER_CLIENTE_SUSPENDIDO` no se vende (CLI-02; sin PIN de supervisor, igual que con conexión); otra lista o versión anterior solo con `USAR_LISTA_ANTERIOR` y, si la organización lo exige, motivo activo del bootstrap (PRC-21; versión anterior = publicada con vigencia desde no posterior al momento); producto sin precio en la versión no se ofrece (VTA-10); descuento manual con DSC-06 (habilitado, tope propio o del rol, motivo si se exige, autorización propia o con PIN, D10); crédito con D9; consumidor final con D8; de 1 a 200 líneas, de 0 a 20 medios que suman la cobranza, referencia donde el medio la pide. Consecuencia: el servidor solo observa lo que cambió entre el bootstrap y la sincronización; el teléfono no genera observaciones evitables.
- **B. Solo las que `docs/` asigna al teléfono** (consumidor final, crédito, descuento manual); el resto se encola y el servidor observa (`CLIENTE_NO_HABILITADO`, `LISTA_NO_VIGENTE`, `DESCUENTO_DIFIERE`). Consecuencia: menos validación local; la bandeja del 25 se llena de observaciones que el teléfono pudo evitar.

### D8 — Consumidor final · negocio · MEDIA · ADR-054 punto 24

- **A (recomendada, elegida). Bloquear la confirmación si la cobranza no es exactamente igual al total** (ni menos ni más), con el mismo texto que `/admin` ("Cargá una cobranza igual al total para poder confirmar"), siempre (por D1, toda venta de `/ruta` es sin conexión). Su crédito se evalúa con límite cero y queda `SIN_EXCESO` (CLI-03); no se muestra el panel de crédito. Consecuencia: el servidor nunca debería recibir `CONSUMIDOR_FINAL_CON_DEUDA` de un teléfono actualizado.
- **B. Bloquear solo si cobra menos;** de más se acepta como vuelto. Consecuencia: el servidor lo recibe igual con `CONSUMIDOR_FINAL_CON_DEUDA` (la cobranza no es igual al total) y un saldo a favor de un cliente genérico.

### D9 — Crédito del dispositivo · técnica · MEDIA

- **A (recomendada, elegida). Evaluación con `modo = SIN_CONEXION` siempre** (D1), con el saldo considerado de D5, el límite, la política y la tolerancia resueltos del bootstrap y los permisos del bootstrap (`puede_superar_credito`). El objeto `credito` encolado lleva `limite`, `saldo_considerado`, `politica`, `resolucion` (`SIN_EXCESO`, `ADVERTENCIA_ACEPTADA`, `TOLERANCIA_OFFLINE`, `PERMISO_PROPIO`, `PIN_SUPERVISOR`), `acepta_exceso` y `autorizador_id` cuando corresponde. `BLOQUEAR` no se confirma (CRE-07). `creditoDeVenta.ts` se generaliza para recibir el modo; `/admin` sigue con `CON_CONEXION`. Consecuencia: la gemela `cre01` ya cubre el modo (sin fixtures nuevos); con señal también rige la tolerancia.
- **B. `CON_CONEXION` cuando hay señal** aunque el comando viaje `OFFLINE`. Consecuencia: la tolerancia depende de la barra de señal; el servidor recibe `OFFLINE` sin tolerancia aplicada (coherente, pero sorprende al vendedor).

### D10 — PIN de un supervisor en el teléfono · seguridad · ALTA · negocio

- **A. Como B, pero con bloqueo de 15 minutos desde el último fallo.** Consecuencia: paridad con el servidor, pero el bloqueo depende del reloj del teléfono y se esquiva adelantándolo.
- **B (elegida, aprobada el 2026-10-31).** El teléfono deriva el PIN escrito con PBKDF2-SHA256 (Web Crypto, misma función que el desbloqueo, sal e iteraciones del autorizador) y lo compara en tiempo constante con la derivación del bootstrap. El permiso del autorizador se revisa antes (sin el permiso no se ofrece y no cuenta). Los fallos se cuentan en `intentos_pin` por par (usuario local, autorizador): con `intentos_pin_max` fallos (5 por defecto, del bootstrap) ese PIN queda **bloqueado en ese teléfono hasta el próximo bootstrap** (abrir la jornada o "Actualizar datos"), **no por tiempo**: el reloj del teléfono se puede adelantar para saltar un bloqueo por tiempo, así que el estado no guarda ni compara horas. Un intento durante el bloqueo no verifica ni cuenta; un acierto no reinicia la cuenta. **Cualquier bootstrap nuevo** (con o sin PIN nuevo) **levanta el bloqueo y reinicia a cero las cuentas de todos los pares**. El PIN nunca se guarda ni viaja: la venta lleva solo `autorizador_id` y el servidor deja `AUTORIZACION_OFFLINE` (SYN-07). Una sola credencial por persona aunque autorice descuento y crédito. Consecuencias: no se esquiva cambiando la hora; un vendedor sin señal queda sin ese supervisor hasta actualizar datos; el acceso técnico al navegador (borrar sus datos) sigue siendo riesgo aceptado de `02` §12.4.
- **C. Sin límite local.** Consecuencia: contra `02` §12.4 ("límite de intentos en la interfaz").

### D11 — Motivo dado de baja en un comando sin conexión (deuda del 20c) · negocio · BAJA

- **A (recomendada, elegida). Se cierra en el 22a sin código nuevo:** el teléfono ofrece solo los motivos activos del bootstrap; si uno se da de baja después del bootstrap, la venta lo lleva igual y el servidor la acepta (ya implementado: el motivo de lista anterior "puede estar inactivo: la venta ya ocurrió", decisión del 2026-10-20; el del descuento manual tiene la causa `MOTIVO` de `DESCUENTO_DIFIERE`, DSC-09). La anulación sin conexión (22c) seguirá la misma regla. Se documenta en ADR-063 y en `04`. Consecuencia: ninguna observación nueva; un motivo inactivo en una venta de lista anterior no se marca para revisar.
- **B. Pasarla al 22c con una observación nueva `MOTIVO_INACTIVO`.** Consecuencia: código nuevo en el servidor y en SYN-07; la venta se marca para revisar por algo que no cambia nada de la operación.

### D12 — Guarda del carrito frente a la versión nueva · técnica · MEDIA · `02` §13.5

- **A (recomendada, elegida).** El carrito vive en memoria (VTA-07). Mientras tiene alguna línea o una confirmación en curso, el aviso dice "Hay una versión nueva: se instala al terminar la venta" sin botón; al confirmar o descartar el carrito vuelve "Actualizar". Salir de la pantalla de venta con líneas pide confirmación ("¿Descartar la venta?"). Consecuencia: nunca se recarga con un pedido a medias; un cierre forzado de la aplicación pierde el carrito (no hay nada confirmado que perder).
- **B. Guardar el borrador del carrito en Dexie** y permitir actualizar en cualquier momento. Consecuencia: el pedido sobrevive a la recarga, pero es un dato persistido más (VTA-07 habla del servidor; localmente agrega limpieza de borradores viejos y su versión de esquema).

### D13 — Estado de envío visible · negocio · BAJA

- **A (recomendada, elegida).** Cada venta local tiene `estado_envio`: `PENDIENTE` ("Sin enviar"), `ACEPTADA`, `CON_OBSERVACIONES`, `RECHAZADA` (los tres últimos los escribe el 22b; en el 22a solo existe `PENDIENTE`). El inicio muestra "N ventas sin enviar" (o "Todo enviado"); "Ventas de hoy" y la venta confirmada muestran la etiqueta. No hay botón "Sincronizar" hasta el 22b. Consecuencia: la cola es visible desde el primer día y el 22b solo cambia estados.
- **B. Además, un botón "Sincronizar" deshabilitado** ("Disponible pronto"). Consecuencia: anuncia algo que no está.

### D14 — Pantallas de venta · negocio · BAJA

- **A (recomendada, elegida).** "Vender" desde el inicio y desde la ficha del cliente (solo con `VENDER`, jornada y datos del día). Una pantalla por pasos pensada para el teléfono: **Cliente** (cartera primero, búsqueda en todos; estado y crédito visibles) → **Pedido** (buscador de productos, cajas y unidades, precio de la versión vigente, "Otra lista" con `USAR_LISTA_ANTERIOR`, descuentos automáticos y manual general y por línea, aviso de stock) → **Cobro y confirmación** (medios con referencia, saldo resultante, panel de crédito, autorización con PIN, "Confirmar venta"). Luego **Venta guardada** (número, total, "Sin enviar", "Compartir nota", "Descargar nota", "Nueva venta"). **Ventas de hoy**: las ventas locales de la jornada (número, cliente, total, estado) con su detalle y la nota. Reutiliza la lógica pura de `/admin`; los componentes son nuevos (móvil). Consecuencia: cubre los criterios 5 a 7 de `00` §9.
- **B. Sin lista anterior ni descuento manual en el teléfono** en el 22a. Consecuencia: el criterio 5 (descuento manual) no se demuestra.

### D15 — Nota sin señal · técnica · MEDIA · ADR-059

- **A (recomendada, elegida). La venta local congela, al confirmar, todo lo que pide `DatosDeNotaDeVenta`:** nombre, CUIT, domicilio, teléfono, zona horaria y "mostrar saldo" de la organización; razón social, documento y dirección del cliente (o consumidor final); número, `occurred_at`, nombre del vendedor; modo impositivo; líneas con nombres de producto y presentación y los importes calculados; totales; cobranza con nombres de los medios; saldo resultante = `saldo_considerado + total − cobranza` (VTA-13; no para el consumidor final). Un adaptador puro `datosDeNotaDesdeLocal` lo pasa a la misma función de armado; el modo C sigue rechazado (`NOTA_MODO_C_NO_DISPONIBLE`, deuda de la etapa 4). Compartir usa `lib/nota/compartir.ts` (Web Share con archivos si el navegador lo admite; descarga siempre); sin señal funciona porque pdfmake está precacheado. Consecuencia: la reimpresión en el teléfono reproduce la original aunque cambien los maestros con un bootstrap; coincide con la del servidor porque el servidor congela la evaluación del dispositivo (CRE-10).
- **B. Armar la nota con los maestros actuales** de la base local en cada generación. Consecuencia: un bootstrap que cambia el nombre de un cliente o de un medio cambia la nota de una venta ya hecha, contra VTA-13.

### D16 — Cerrar sesión u otro usuario con ventas sin enviar · negocio · MEDIA

- **A (recomendada, elegida). Se permite con aviso:** "Tenés N ventas sin enviar. Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos." (cerrar sesión) y, al iniciar otro usuario, "Hay N ventas sin enviar de {nombre}; quedan guardadas". Nada pendiente se borra (SEG-04, ADR-062 punto 16; la cola es del usuario que la generó, `02` §6.4). Consecuencia: el 22b debe enviar solo la cola del usuario autenticado.
- **B. Bloquear el cierre de sesión mientras haya pendientes.** Consecuencia: hasta el 22b nadie podría cerrar sesión después de vender.

### D17 — Ayuda contextual · interfaz · BAJA · ADR-051

- **A (recomendada, elegida).** Se reutilizan las claves de la venta de `/admin` cuyo texto vale igual en el teléfono (`ventas.cajasYUnidades`, `ventas.precio`, `ventas.listaAnterior`, `ventas.cobranza`, `ventas.consumidorFinal`, `ventas.descuentoGeneral`, `ventas.descuentoPropio`, `ventas.topeDescuento`, `ventas.motivoDescuento`, `ventas.descuentosAutomaticos`, `ventas.politicaCredito`, `ventas.autorizacion`, `ventas.notaDeVenta`); **no** se reutilizan `ventas.stock` (dice que sin permiso no se confirma) ni `ventas.numero` (habla de proponer el número). Se agregan cinco claves de `/ruta`, **sin ejemplos**:
  - `ruta.ventaSinEnviar` — **Sin enviar**: "La venta ya está confirmada y guardada en el teléfono. Se envía al sistema cuando haya señal; hasta entonces no se borra." (SYN-01, SYN-09)
  - `ruta.creditoSinSenal` — **Crédito del cliente**: "Se calcula con la deuda que bajó al abrir la jornada más lo que le vendiste y cobraste desde el teléfono. El sistema lo vuelve a calcular cuando recibe la venta." (CRE-08, CRE-09; "Ver más" → `credito`)
  - `ruta.stockDelVehiculo` — **Stock del vehículo**: "Es lo que bajó al abrir la jornada menos lo que vendiste desde el teléfono. Si no alcanza, la venta no se confirma: actualizá los datos con señal." (STK-06, RUT-04; el aviso con "Vender igual" aparece solo para quien tiene `PERMITIR_STOCK_NEGATIVO` y no necesita un texto aparte)
  - `ruta.pinSupervisor` — **PIN del supervisor**: "El supervisor escribe su PIN en tu teléfono; no hace falta señal. Después de varios intentos fallidos ese PIN queda bloqueado en este teléfono hasta que se actualicen los datos." (SEG-05)
  - `ruta.numeroDeVenta` — **Número de venta**: "El teléfono le pone el número al confirmar: el prefijo del teléfono y el siguiente número de sus ventas." (VTA-06)
  Textos aprobados el 2026-10-31 (0.2). Consecuencia: la prueba de claves y de IDs citados de ADR-051 cubre las nuevas.
- **B. Sin ayudas nuevas,** solo las de `/admin`. Consecuencia: el estado "Sin enviar" y el PIN local quedan sin explicar.

## Risks / Trade-offs

- [El reloj del teléfono define `occurred_at` y la versión vigente local] → el servidor no valida el momento sin conexión; `LISTA_NO_VIGENTE` marca la versión que no correspondía. El bloqueo del PIN (D10 = B) no depende del reloj.
- [Hasta el 22b, las ventas de `/ruta` no llegan al servidor] → quedan visibles como "Sin enviar"; la prueba de contrato (D2) asegura que se aceptarán; `/admin` sigue vendiendo con conexión.
- [Una transacción Dexie que espera algo ajeno (Web Crypto, red) se cierra sola] → cálculo y PIN antes de abrirla (D4); prueba con falla inyectada.
- [Derivar el PIN con 600 000 iteraciones tarda en un teléfono modesto] → indicador "Verificando…" y un solo cálculo por intento.
- [Datos del bootstrap desactualizados (carga de mercadería, cliente reactivado)] → "Actualizar datos" con señal; D6 = C bloquea por stock a quien no tiene `PERMITIR_STOCK_NEGATIVO` hasta actualizar.
- [Almacenamiento no persistente: el navegador podría borrar la cola] → la advertencia del 21 sigue; el inicio la muestra junto a las ventas sin enviar.

## Migration Plan

Sin migración de servidor. Dexie pasa de v2 a v3 sumando tablas (sin transformar datos); una base v2 abre en v3 sin perder sesión ni maestros. Volver atrás exige borrar los datos del navegador (Dexie no baja de versión): se evita publicando el 22a junto con su prueba manual.

## Open Questions

Ninguna que cambie lo que se construye.
