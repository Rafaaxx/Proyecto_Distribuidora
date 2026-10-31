# Tareas — 21-pwa-y-bootstrap

> Modo TDD estricto: en cada tarea de los grupos 1 a 15, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Ninguna aserción trivial. Las tareas están escritas con la opción **recomendada** de cada decisión de `design.md`; si el usuario elige otra en 0.1, se actualizan antes del apply (`openspec-update-change`).
>
> **Dónde va el código:** backend en `backend/app/modules/sync/` (`bootstrap.py`, `schemas.py`, `api.py`) y lecturas masivas nuevas en el `service.py` de `catalogo`, `clientes`, `precios`, `descuentos`, `stock`, `cuentas_corrientes`, `identidad` y `configuracion` (D1); sin migración. Frontend: `frontend/src/lib/dispositivo/db.ts` (Dexie v2), `frontend/src/sync/` (cliente y aplicación del bootstrap), `frontend/src/domain/ruta/` (lecturas puras: versión vigente, precio por presentación, cartera, cajas y unidades), `frontend/src/lib/sesionLocal/` (PIN), `frontend/src/areas/ruta/`, `frontend/src/ayuda/`, `frontend/src/components/ui/Ayuda.tsx`, `frontend/vite.config.ts`. Contratos de `lint-imports`: `sync` solo por `service.py` ajeno.
>
> **Lotes de apply (`design.md` D0):** Lote 1 = grupos 1 a 4 (bootstrap en el backend). Lote 2 = grupos 5 a 7 (base local y aplicación del bootstrap). Lote 3 = grupos 8 a 10 (sesión local). Lote 4 = grupos 11 a 15 (PWA, pantallas y ayuda). Lote 5 = grupos 16 a 20 (ADR, docs, cobertura, suites y prueba manual). Un subagente nuevo por lote, en secuencia. **No se frena entre lotes**: el resumen de cada lote informa las comprobaciones automáticas y el usuario revisa con todo el change implementado.
>
> **Gobernanza:** ALTA en los grupos 4.3, 8, 9 y 10 (derivaciones y sesión local): se implementa exactamente lo aprobado en 0.1; cualquier desvío se detiene y se consulta. MEDIA en el resto.
>
> **Pruebas:** en cada lote solo las afectadas; las suites completas una sola vez, en 18.1. `pytest` por carpeta con `backend/.venv`; frontend con Docker detenido. **Sin fixtures compartidos de cálculo** (no cambia ninguna regla de cálculo; las pantallas usan el motor existente). Se agrega un vector compartido de derivación PBKDF2 (4.3). Al instalar `vite-plugin-pwa`, reconstruir la imagen de Docker del frontend.

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones (aprobadas 2026-10-30: opción A en todas salvo D14 = B; teléfono: Android hoy, compatible con iPhone): el usuario revisa D0 a D21 de `design.md` (en especial las de negocio D2, D4 a D8, D11, D13 a D16, D19) y responde la pregunta de D20 (qué teléfono usa el vendedor). Código nuevo: ninguno (se reutiliza `JORNADA_REQUERIDA` con 409). Se anota fecha y opción en cada decisión y en ADR-062; si alguna difiere de la recomendada, se actualizan proposal, specs y tareas antes del apply. Verificable: `design.md` sin "PROPUESTAS" en el estado.
- [x] 0.2 Confirmar la versión exacta de `vite-plugin-pwa` compatible con Vite 8 (consulta de documentación actual) y anotarla en D17. Bloquea el grupo 11. (Hecho: `vite-plugin-pwa` 2.0.0, anotada en D17.)
- [x] 0.3 Textos de ayuda: el usuario revisa las cuatro claves de D21 (sin ejemplos) y las aprueba o corrige. Se anota en D21. Bloquea solo la tarea 15.2.

## 1. Lecturas masivas por módulo (Lote 1)

- [x] 1.1 Red de seguridad: suites de `clientes`, `cuentas_corrientes`, `catalogo`. RED en `backend/tests/integration/test_bootstrap_lecturas_clientes.py` (D4; cita `01` §19, CRE-01, CRE-03, CRE-06, INV-13, INV-21): `clientes/service.py` expone la lista de clientes `ACTIVO`/`SUSPENDIDO` y el consumidor final habilitado con su crédito resuelto (herencia de la organización aplicada, tolerancia como string) sin correo ni vendedor; `cuentas_corrientes/service.py` expone los saldos de todos los clientes de la organización **en una sola consulta SQL** (sin sumar en Python), iguales a la suma de sus movimientos; otra organización no aparece. GREEN en los dos `service.py`.
- [x] 1.2 Red de seguridad: suites de `precios`. RED en `backend/tests/integration/test_bootstrap_lecturas_precios.py` (D5, D6; cita PRC-20, PRC-21, PRC-22, INV-11, INV-21): `precios/service.py` expone, para un conjunto de listas y un momento, las versiones `PUBLICADA` no anuladas vigentes, programadas y (a pedido) históricas, con vigencias y precios (`precio_referencia`, `unidades_referencia`) de productos activos; sin borradores ni anuladas; las listas aplicables a un conjunto de clientes (asignadas más la predeterminada). GREEN en `precios/service.py`.
- [x] 1.3 Red de seguridad: suites de `descuentos`. RED en `backend/tests/integration/test_bootstrap_lecturas_descuentos.py` (D6; cita DSC-01, DSC-02): `descuentos/service.py` expone las reglas `ACTIVA` con vigencia no terminada a un momento (incluidas las que empiezan después), con nombre, alcances, prioridad, acumulable y vigencia; las vencidas, pausadas y borradores no. GREEN.
- [x] 1.4 RED en `backend/tests/integration/test_bootstrap_lecturas_identidad.py` (D8; cita `02` §12.4, ADR-011, SEG-05, INV-21): `identidad/service.py` expone los autorizadores con derivación (activos, rol activo, con permiso de autorización y PIN definido, distintos de quien pide) con sus permisos de autorización, hash, sal e iteraciones; sin PIN o inactivos no figuran; nunca devuelve contraseñas. GREEN.

## 2. Endpoint del bootstrap (Lote 1)

- [x] 2.1 RED en `backend/tests/integration/test_sync_bootstrap.py` (spec `sync/bootstrap`, requisito "El bootstrap se pide con una jornada abierta en el dispositivo"; D2; cita RUT-03, ADR-006, ADR-028, INV-21): `GET /api/v1/sync/bootstrap` con jornada `ABIERTA` propia en el dispositivo del token → 200; sin jornada, con jornada `EN_RENDICION` o abierta desde otro dispositivo → 409 `JORNADA_REQUERIDA`; usuario inactivo con token de la excepción de ADR-028 → rechazado; `since` ignorado; doble pedido igual salvo `generado_en` y sin escribir comando, auditoría ni cambio. GREEN en `sync/bootstrap.py`, `sync/schemas.py`, `sync/api.py` (D9).
- [x] 2.2 RED (mismo archivo; requisitos de catálogo, clientes, listas, reglas, contexto, sesión, configuración, stock y numeración; cita SYN-10, SYN-11, VTA-06, VTA-13, ADR-059, ADR-060, DSC-06, TR-09, INV-03, INV-04, INV-12): cada sección con los datos de los escenarios de la spec (productos con `categoria_id`, `marca_id`, alícuota y presentaciones; cartera y "vacía = todos"; versiones según `USAR_LISTA_ANTERIOR`; regla programada; tope propio; medios, motivos y alícuotas activos; permisos del momento con secciones vacías sin `VENDER`; stock de la ubicación tomada; prefijo y último correlativo; nombre, CUIT y parámetros de la nota); importes como string y cantidades como enteros. GREEN.
- [x] 2.3 RED (mismo archivo; requisito "filtra por organización y no expone costos"; D7; cita INV-21, INV-02, SYN-11, ADR-011): con dos organizaciones, nada de B en el bootstrap de A; `admin` con `VER_COSTOS` no recibe ningún costo ni margen (se verifica recorriendo las claves de la respuesta). Ratchet de rutas: la ruta nueva es de lectura y está en el recorrido de aislamiento (INV-21). GREEN.
- [x] 2.4 Regenerar `backend/openapi.json` y `frontend/src/api/schema.gen.ts`. Verificable: `npm run check:api-types` limpio; `lint-imports` y `mypy app` limpios.

## 3. Foto coherente (Lote 1)

- [x] 3.1 RED en `backend/tests/concurrency/test_bootstrap_foto.py` (commits reales; D3; cita INV-12, INV-13): mientras un bootstrap está leyendo (pausa inyectada entre secciones), otra sesión confirma una venta desde la camioneta; el bootstrap trae saldo y stock ambos anteriores o ambos posteriores. GREEN: la ruta abre la transacción `REPEATABLE READ READ ONLY`. Una falla intermitente se investiga, no se ignora.

## 4. Derivación compartida (Lote 1)

- [x] 4.1 RED en `backend/tests/unit/test_pin_vector_compartido.py` (D8; cita `02` §12.4): con el vector fijo de `shared/fixtures/pin/derivacion.json` (PIN, sal hex, iteraciones, hash hex), `verificar_pin_autorizacion` da verdadero y con otro PIN falso. GREEN: crear el vector con `derivar_pin_autorizacion` y una sal fija.
- [x] 4.2 RED en `frontend/tests/unit/lib/sesionLocal/derivacion.test.ts`: la derivación con Web Crypto del mismo vector da el mismo hash. GREEN en `frontend/src/lib/sesionLocal/derivacion.ts` (PBKDF2-SHA256 con `crypto.subtle`, salida hex, comparación en tiempo constante).
- [x] 4.3 Revisión de gobernanza ALTA: confirmar que ninguna respuesta, log ni auditoría del bootstrap incluye PIN, contraseña ni `password_hash` (prueba que busca esos campos en la respuesta y en el log capturado). GREEN si hace falta.

## 5. Esquema local (Lote 2)

- [x] 5.1 Red de seguridad: `tests/unit/lib/dispositivo`. RED en `frontend/tests/unit/lib/dispositivo/db.test.ts` (D10; `fake-indexeddb`): la base abre en versión 2 con las tablas maestras y `meta`; una base v1 con `dispositivo_id` sube a v2 conservándolo (cita `02` §12.2). GREEN en `frontend/src/lib/dispositivo/db.ts`.

## 6. Aplicar el bootstrap (Lote 2)

- [x] 6.1 RED en `frontend/tests/unit/sync/aplicarBootstrap.test.ts` (spec `sync/base-local`, requisito "reemplaza los datos maestros en una sola transacción"; cita ADR-006, INV-01): reemplazo completo (desaparece el cliente que ya no viene), `meta.fecha_bootstrap` y `meta.jornada_id`, falla inyectada a mitad → queda completo el bootstrap anterior, `dispositivo_id` intacto, doble aplicación sin duplicados, y solo se tocan las tablas de la lista explícita. GREEN en `frontend/src/sync/aplicarBootstrap.ts` (adaptador de la respuesta tipada a filas locales; importes quedan como string).
- [x] 6.2 RED en `frontend/tests/unit/sync/clienteBootstrap.test.ts`: pide `GET /sync/bootstrap` con `apiFetch`; 409 `JORNADA_REQUERIDA`, error de red y 5xx se informan como resultados distintos sin tocar la base. GREEN en `frontend/src/sync/clienteBootstrap.ts`.

## 7. Lecturas locales puras (Lote 2)

- [x] 7.1 RED en `frontend/tests/unit/domain/ruta/` (D6, D19; cita PRC-20, PRC-22, CAT-08, `01` §19, INV-03, INV-04): versión vigente de una lista en un momento (incluye programada que entra en vigencia; sin ninguna, "sin precio"); precio por presentación con el motor compartido existente (`domain/calculo.ts`, caja `"48000.00"` de 6 → unidad `"8000.00"`), sin `number`; orden de clientes con cartera y consumidor final primero y búsqueda por nombre, código o documento; disponible = límite − saldo (nulo sin límite); stock en cajas y unidades (20 de 6 → 3 y 2). GREEN en `frontend/src/domain/ruta/`.
- [x] 7.2 RED: hooks de lectura de Dexie (`useLiveQuery`) para inicio, clientes, productos y stock, que devuelven "sin datos" sin bootstrap. GREEN en `frontend/src/areas/ruta/datos/`.

## 8. PIN de desbloqueo (Lote 3)

- [x] 8.1 RED en `frontend/tests/unit/lib/sesionLocal/pin.test.ts` (spec `identidad/sesion-local`, requisito "se define con conexión y se guarda derivado"; D13; cita SEG-03, ADR-011, ADR-055): 6 dígitos exactos, dos veces iguales, triviales rechazados (111111, 123456, 654321); se guarda hash, sal de 32 bytes e iteraciones 600 000, nunca el PIN; ninguna petición lleva el PIN (espía de `fetch`). GREEN en `frontend/src/lib/sesionLocal/pin.ts`.
- [x] 8.2 RED (mismo archivo; requisitos "Los intentos fallidos bloquean la sesión local" y "Cambiar el PIN"; D15; cita SEG-04, SYN-09): cuenta persistida, recarga simulada no la reinicia, acierto la reinicia; al llegar al máximo (ver 8.3: 10) se borra la derivación y el estado pasa a "requiere login"; datos maestros intactos; cambio de PIN con el actual; actual incorrecto suma un fallo. GREEN.
- [x] 8.3 Decisión aprobada 2026-10-30 (D15): el bloqueo del PIN de desbloqueo es de **10 fallos, constante fija en código** (`INTENTOS_DESBLOQUEO_MAX` en `pin.ts`), sin usar `intentos_pin_max`. RED en `pin.test.ts` y `SesionRuta.test.tsx` (restantes 9; no cambia con `intentos_pin_max` de la organización; décimo fallo bloquea). GREEN en `frontend/src/lib/sesionLocal/pin.ts`. Artefactos y `propuesta-docs.md` actualizados.

## 9. Sesión local y login de ruta (Lote 3)

- [x] 9.1 Red de seguridad: suites de `areas/admin/auth` y `lib/api`. RED en `frontend/tests/unit/areas/ruta/LoginRutaScreen.test.tsx` (spec `ruta/area-de-ruta`, requisito "propio inicio de sesión"; D12; cita SEG-01, SEG-02, ADR-018): login con dispositivo, rechazos explicados, sin conexión avisa; no importa nada de `areas/admin` (prueba de importaciones). GREEN: mover `useLogin` a `features/identidad` sin romper `/admin`, y `frontend/src/areas/ruta/auth/LoginRutaScreen.tsx`.
- [x] 9.2 RED en `frontend/tests/unit/areas/ruta/SesionRuta.test.tsx` (requisito "El PIN desbloquea la sesión local"; D14; cita SEG-03, ADR-017): máquina de estados de `/ruta` (sin sesión → login → definir PIN → bootstrap pendiente → inicio; arranque con sesión → pedir PIN; sin señal desbloquea sin red; con señal renueva el token; refresh rechazado → login conservando la base; sin regla de segundo plano: volver de segundo plano NO pide el PIN, solo el arranque o la recarga). GREEN en `frontend/src/areas/ruta/sesion/`.
- [x] 9.3 RED (mismo archivo; D11; cita RUT-03): tras desbloquear o iniciar sesión con conexión, si `GET /stock/jornadas/actual` devuelve una jornada abierta propia distinta de `meta.jornada_id` (o no hay datos), se pide y aplica el bootstrap; sin jornada, el inicio ofrece abrirla. GREEN.

## 10. Cerrar sesión y cambio de usuario (Lote 3)

- [x] 10.1 RED en `frontend/tests/unit/areas/ruta/CierreDeSesion.test.tsx` (requisito "Cerrar sesión y cambiar de usuario"; D16; cita `02` §12.3): cerrar sesión con conexión llama `POST /auth/logout` y borra sesión, PIN y datos maestros (no `meta.dispositivo_id`); sin conexión deshabilitado con su motivo; login de otro usuario borra sesión, PIN y datos maestros del anterior antes de definir el PIN nuevo. GREEN en `frontend/src/areas/ruta/sesion/` y `frontend/src/sync/`.

## 11. Service worker y manifiesto (Lote 4)

- [x] 11.1 Requiere 0.2. Instalar `vite-plugin-pwa` con versión exacta y configurar `vite.config.ts` (D17): `generateSW`, `registerType: 'prompt'`, manifiesto (`start_url: /ruta`, `display: standalone`, íconos en `public/`), precache con `globIgnores` del fragmento de `/admin` (nombre de fragmento fijo con `manualChunks` o el patrón que corresponda), `navigateFallback` con `navigateFallbackDenylist` `/^\/api\//`, sin `runtimeCaching`. Reconstruir la imagen de Docker del frontend (pendiente: lo hace el usuario; ver D17).
- [x] 11.2 RED en `frontend/tests/unit/pwa/precache.test.ts` (spec `sistema/aplicacion-instalable`; cita `02` §13.1, §13.5, VTA-13): sobre la salida de `npm run build`, el manifiesto de precache incluye el shell, los fragmentos de `/ruta`, la ayuda y pdfmake con sus fuentes, y no incluye ningún fragmento de `/admin`; la configuración no tiene `runtimeCaching` y deniega `/api/`. GREEN ajustando la configuración.
- [x] 11.3 RED en `frontend/tests/unit/pwa/AvisoDeVersion.test.tsx` (requisito "Una versión nueva se aplica con aviso"): con `needRefresh` el aviso aparece y no se recarga hasta "Actualizar"; "Actualizar" llama a la actualización del service worker. GREEN en `frontend/src/areas/ruta/pwa/AvisoDeVersion.tsx` (registro con `virtual:pwa-register/react`, tipado).

## 12. Almacenamiento persistente (Lote 4)

- [x] 12.1 RED en `frontend/tests/unit/lib/almacenamiento.test.ts` (requisito "Se pide almacenamiento persistente"; D18; cita `02` §13.3, `00` §11): se pide tras el primer bootstrap y en cada arranque mientras `persisted()` sea falso; concedido → sin advertencia; negado o sin la API → advertencia. GREEN en `frontend/src/lib/almacenamiento.ts`.

## 13. Pantallas de inicio y jornada (Lote 4)

- [x] 13.1 Red de seguridad: suites de `features/stock` (apertura). RED en `frontend/tests/unit/areas/ruta/InicioScreen.test.tsx` (requisito "El inicio muestra la jornada, la conexión y los datos"; cita RUT-03, RUT-09, SYN-11): usuario, jornada y ubicación, conexión (`navigator.onLine` y eventos), hora de los datos, "Actualizar datos" deshabilitado sin conexión, error de bootstrap con "Reintentar", advertencia de almacenamiento, jornada liberada informada con conexión, accesos. GREEN en `frontend/src/areas/ruta/InicioScreen.tsx` y `RutaScreen.tsx` (rutas de `/ruta`).
- [x] 13.2 RED en `frontend/tests/unit/areas/ruta/AbrirJornadaScreen.test.tsx` (requisito "La jornada se abre desde el área de ruta"; cita RUT-01, RUT-03, INV-06, INV-16): solo con conexión y `ABRIR_JORNADA` (de la sesión); ubicaciones activas, con toma y libres; rechazos explicados con los mensajes de `features/stock/errores.ts`; reintento con el mismo `Operation-Id`; al abrir encadena el bootstrap. GREEN en `frontend/src/areas/ruta/jornada/AbrirJornadaScreen.tsx` reutilizando `features/stock/api.ts`.

## 14. Pantallas de consulta y cuenta (Lote 4)

- [x] 14.1 RED en `frontend/tests/unit/areas/ruta/ClientesScreen.test.tsx` (requisito "Clientes desde la base local con cartera primero"; cita `01` §19, CRE-01, CLI-02, INV-17): lista con cartera y consumidor final primero, búsqueda en todos, marca de suspendido, ficha con contacto, lista aplicable, saldo, disponible y hora de los datos, formato con `lib/money.ts`. GREEN en `frontend/src/areas/ruta/clientes/`.
- [x] 14.2 RED en `frontend/tests/unit/areas/ruta/ProductosYStock.test.tsx` (requisito "Productos y stock desde la base local"; cita PRC-20, PRC-22, CAT-08, INV-04): búsqueda, precio por presentación de la versión vigente *ahora* de la lista predeterminada o "Sin precio", versión programada tomada a su hora (reloj falso), stock en cajas y unidades, ningún costo. GREEN en `frontend/src/areas/ruta/productos/` y `stock/`.
- [x] 14.3 RED en `frontend/tests/unit/areas/ruta/MiCuentaRuta.test.tsx` (requisito "Mi cuenta en el área de ruta"; cita ADR-060, SEG-03): "Mi contraseña" con conexión reutilizando la lógica de `/admin` (movida a `features/identidad` si hace falta, sin romper `/admin`), deshabilitada sin conexión; "Cambiar PIN" con y sin conexión; "Cerrar sesión" (grupo 10). GREEN en `frontend/src/areas/ruta/cuenta/`.

## 15. Ayuda de ruta (Lote 4)

- [x] 15.1 RED en `frontend/tests/unit/ayuda/AyudaRuta.test.tsx` (spec `sistema/ayuda-contextual`, requisito "El área de ruta tiene su ayuda sin conexión"; D21; cita ADR-051): `/ruta/ayuda` y `/ruta/ayuda/:tema` con `TemaDeAyudaVista`; en `/ruta` "Ver más" navega en la misma ventana; en `/admin` con `display-mode: standalone` también, y sin él abre otra pestaña. GREEN en `frontend/src/components/ui/Ayuda.tsx` y `frontend/src/areas/ruta/ayuda/`.
- [x] 15.2 Requiere 0.3 y 16.1. RED: `tests/unit/ayuda/trazabilidad.test.ts` y las pruebas de pantalla de los grupos 9, 13 y 14 exigen `ruta.pin`, `ruta.datosDelDia`, `ruta.almacenamiento` y `ruta.cartera` con los textos aprobados, sin ejemplos, y el "(?)" de `stock.tomaActual` en Abrir jornada (requisito "Las pantallas de ruta explican el PIN, los datos del día, el almacenamiento y la cartera"). Revisar con `grep` si algún texto existente que cite RUT-03 o ADR-006 queda desactualizado (se informa; no se cambia sin aprobación). GREEN en `frontend/src/ayuda/textos.ts` y las pantallas.

## 16. ADR (Lote 5)

- [x] 16.1 Completar `docs/adr/ADR-062-pwa-bootstrap-y-sesion-local.md` (borrador *Propuesto* creado con la propuesta) con lo aprobado en 0.1 y las precisiones del apply. Va antes de 15.2, porque los textos de ayuda pueden citar ADR-062 y la prueba de trazabilidad exige que exista (si el Lote 4 llega antes, el ADR borrador ya existe y alcanza).

## 17. Pruebas de integración de punta a punta (Lote 5)

- [x] 17.1 RED en `backend/tests/integration/test_bootstrap_flujo.py`: `vendedor` abre la jornada por el comando, pide el bootstrap y recibe la jornada, el stock cargado por la transferencia previa, su cartera y la versión vigente; se publica una versión programada y un nuevo bootstrap la trae; se libera la jornada y el bootstrap responde `JORNADA_REQUERIDA`. GREEN si hace falta.
- [x] 17.2 RED en `frontend/tests/unit/areas/ruta/FlujoRuta.test.tsx` (con `fake-indexeddb` y `fetch` simulado): login → PIN → abrir jornada → bootstrap → clientes y productos → sin red: recarga, PIN, datos visibles → diez fallos → login → PIN nuevo con los datos intactos. GREEN si hace falta.

## 18. Cobertura y suites completas (Lote 5)

- [x] 18.1 Cada escenario de las seis specs delta tiene al menos una prueba que lo nombra; INV-01 (reemplazo local), INV-02, INV-03, INV-04, INV-12, INV-13 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas, `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación.

## 19. Propuesta de docs (Lote 5)

- [x] 19.1 Completar `openspec/changes/21-pwa-y-bootstrap/propuesta-docs.md` (borrador con la opción recomendada) con lo aprobado en 0.1 y las precisiones del apply: `01` §13 (SYN-11 precisado), §14 (SEG-03, SEG-04 precisados), RUT-03; `02` §7.1 (excepción de solo lectura), §11 (ruta nueva), §12.3, §13.2 a §13.5; y `04` §11 (fila del 21 terminada, deudas saldadas y nuevas al 22a). **No se aplica a `docs/`** sin el visto bueno del usuario.

## 20. Prueba manual (Lote 5)

- [x] 20.1 Si se aprobó D20-A: agregar el perfil opcional de Docker Compose con Caddy de desarrollo (`tls internal`) y dar en el chat el paso a paso para confiar el certificado en el teléfono del vendedor.
- [x] 20.2 Probar a mano el flujo principal y dar al usuario el paso a paso en el chat (sin archivo aparte), con los usuarios de desarrollo existentes, primero en el navegador de escritorio (modo de dispositivo y "sin conexión" de las herramientas de desarrollo) y después en un teléfono Android real (Chrome): `admin` transfiere stock a "Camioneta 1" y asigna dos clientes a `vendedor`; `vendedor` entra a `/ruta`, inicia sesión, define su PIN (prueba un trivial y lo ve rechazado), abre la jornada sobre la camioneta y ve la hora de los datos; recorre Clientes (sus dos primero, busca otro), una ficha con saldo y disponible, Productos con precios por caja y unidad, y Stock en cajas y unidades; instala la aplicación; corta la red, cierra y vuelve a abrir: pide el PIN y muestra los datos; "Actualizar datos" y "Mi contraseña" deshabilitados; abre un "(?)" y su "Ver más" sin red; erra el PIN diez veces y queda pedido el login; con red vuelve a entrar y define otro PIN; `admin` publica una versión nueva y `vendedor` toca "Actualizar datos" y ve el precio nuevo; `vendedor2` inicia sesión en el mismo teléfono y no ve nada de `vendedor`; `sup01` libera la jornada de `vendedor2` y su inicio lo informa; se publica una build nueva y aparece el aviso de versión sin recargar sola; se mide cuánto tarda el PIN en el teléfono (D13). Verificación futura u opcional en iPhone (Safari): instalar con "Compartir > Agregar a inicio", confirmar que `/ruta` abre sin señal y observar si Safari concede el almacenamiento persistente (D18); se documenta el paso a paso en el chat sin ser requisito de cierre. No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5 y `04` §11 ("probar en el teléfono real durante el 21"). **Nota (2026-10-31):** hecha por el usuario 2026-10-31 en escritorio y Android (Chrome), todos los pasos OK. Desbloqueo con PIN casi instantáneo en el teléfono (D13). iPhone queda como verificación opcional futura. Correcciones hechas durante la prueba manual: `versionVigente` aceptaba solo `PUBLICADA` (ahora descarta `BORRADOR` y `ANULADA`); el globo del (?) usaba `window.innerWidth` (ahora `document.documentElement.clientWidth`); se agregó la meta `mobile-web-app-capable` en `index.html`.
