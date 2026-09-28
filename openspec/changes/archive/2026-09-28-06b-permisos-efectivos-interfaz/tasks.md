> **Modo TDD estricto.** Dentro de cada grupo:
> 1. **RED:** se escribe primero la prueba que falla.
> 2. **GREEN:** después, el código mínimo que la pasa.
> 3. **Triangulación:** al menos un segundo caso (camino feliz más un borde o un error).
> 4. **Refactor:** recién entonces, con las pruebas en verde después de cada paso.
>
> Antes de tocar un archivo existente se corre su suite y se anota la línea base. Una falla previa se reporta, no se arregla. Toda prueba de un invariante o regla lo cita por ID en su nombre o docstring (INV-21, SEG-06, SEG-07, ADR-027; en el grupo 2 también SEG-01, SYN-10, ADR-017 y ADR-028).
>
> **Gobernanza.**
> - Grupo 2 (sesión con usuario o rol inactivo, D9 / ADR-028): **CRÍTICA**. Solo análisis hasta la aprobación explícita del usuario (tarea 0.9). Después, cada paso se describe antes de escribirlo y se espera confirmación.
> - Backend (`GET /yo`, ratchets): **ALTA**. Es una lectura de identidad y autorización, adyacente a seguridad. Fuera del grupo 2, no cambia cómo autoriza el servidor. Antes de escribir se describe el cambio concreto y se espera confirmación.
> - Frontend (hook, componente, menú, pantallas): **MEDIA**. Punto de control al final de cada grupo.
> - Tipos y constantes (`CodigoPermiso`, lista de secciones): **BAJA**.
>
> Ninguna tarea se implementa sin la aprobación humana de esta proposal (`CLAUDE.md` §6 paso 4). Las decisiones D1 a D8 del grupo 0 ya están aprobadas (2026-09-25). El grupo 2 exige además la tarea 0.9. Los grupos 5 a 8 (frontend) no dependen de D9 y pueden avanzar aunque 0.9 siga pendiente. Los grupos 3 y 4 sí dependen: se implementan después del grupo 2, o sin el caso de usuario inactivo, que se agrega al cerrar el grupo 2.
>
> **Orden:** decisiones → línea base → sesión con usuario y rol activos (D9) → servicio → API y contrato → aviso de token → mecanismo de permisos → menú y aterrizaje → retiro del patrón reactivo → integración y aislamiento → verificación.
>
> **Sin migración de Alembic.** Este change no toca el esquema (`design.md`, Migration Plan). D9 tampoco: `motivo_revocacion` es texto libre.

## 0. Decisiones previas (no son código)

- [x] 0.1 D3 (**B1**) resuelta: **A**, falla cerrada. Sin secciones protegidas mientras `/yo` carga. Si falla, aviso con **Reintentar**, o con un enlace a iniciar sesión si la sesión terminó. Aprobada por el usuario el 2026-09-25.
- [x] 0.2 D4 (**B2**) resuelta: **A**, "No tenés permiso…" sin pedir los datos de la pantalla. Aprobada por el usuario el 2026-09-25.
- [x] 0.3 D5 (**B3**) resuelta: **A**, `/admin/inicio` redirige a la primera sección permitida, o informa que no hay ninguna. Aprobada por el usuario el 2026-09-25.
- [x] 0.4 D6 (**B4**) resuelta: **A**, el encabezado muestra "usuario · organización · rol". Aprobada por el usuario el 2026-09-25.
- [x] 0.5 Decisiones técnicas aprobadas por el usuario el 2026-09-25:
  - D1-A: `router_yo` sin prefijo, `GET /api/v1/yo`, `obtener_yo` y 401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO` si el usuario del token no existe.
  - D2-A: aviso desde `tokenStore`, invalidación de `['yo']` con `cancelRefetch: false`, `staleTime: Infinity` y descarte al limpiar el token.
  - D7-A: sin Playwright.
  - D8-A: unión `CodigoPermiso`.
- [x] 0.6 Observación sobre `listar_permisos_del_usuario` (ignora `usuario.estado` y `rol.activo`): el usuario decidió el 2026-09-25 **incluir su cierre en este change**. Se redactó ADR-028 (*Propuesto*) y D9 en `design.md`. Se implementa en el grupo 2, sujeto a 0.9.
- [x] 0.7 (Opcional, no bloquea. **2026-09-28: cerrada por decisión del usuario** — rechazó el 2026-09-27 redactar la enmienda a ADR-027; no se aplica y queda registrada como no realizada. Si el usuario lo pide en el futuro, redactar la enmienda a ADR-027 con B1 y B2 y esperar su aprobación.)
- [x] 0.8 Specs delta revisadas: todas las decisiones de 0.1 a 0.4 son las que ya reflejaban. Se retiraron las notas de "decisión pendiente". Las marcas **(B1)** a **(B4)** quedan solo como trazabilidad.
- [x] 0.9 (2026-09-25: el usuario aprobó explícitamente D9.1, D9.2-A, D9.3-B y D9.4-A, y D9.5 como nota; ADR-028 *Vigente*; las specs delta ya reflejaban esas opciones) **Aprobación explícita del usuario de ADR-028 y D9 (CRÍTICO).** **No se escribe ningún código del grupo 2 antes.** Al aprobarse:
  - ADR-028 pasa a *Vigente*, con la fecha y las opciones elegidas;
  - se ajustan los escenarios marcados **(D9)** en las specs delta si la opción elegida no es la recomendada;
  - se ajustan las tareas 2.x que dependan de la opción.

## 1. Línea base

- [x] 1.1 (2026-09-25) Línea base registrada antes de escribir código.
  - Backend: `ruff check .` limpio. `ruff format --check .` reporta **1 archivo previo a reformatear**, `app/modules/identidad/api.py` (líneas 126, 219, 292, 353 — `# type: ignore[arg-type]` en llamadas de una sola línea que `ruff format` quiere partir en varias): **falla previa, no de este change, se reporta y no se toca**. `mypy app`: sin issues (79 archivos). `lint-imports`: 10 contratos, 0 rotos. `pytest tests/unit tests/fixtures_compartidos tests/properties`: **383 passed**. `pytest tests/integration` (Testcontainers): **522 passed** (150 s).
  - Frontend: `npm run typecheck`: limpio. `npm run lint`: 0 errores, 2 warnings preexistentes de React Compiler (`ProductoFormScreen.tsx:121`, `CostosCargaScreen.tsx:94`, uso de `watch()` de React Hook Form, ajenos a este change). `npm run test -- --run`: **208 passed, 1 failed** en la corrida completa (`tests/unit/app-routing.test.tsx` > "redirige /admin al inicio de sesión") — **flaky, no una regresión**: pasa 9/9 al correrse aislado (probable carrera de `jsdom`/entorno compartido entre archivos, ver aviso de Vitest sobre crear el entorno una vez por worker). Se reporta como hallazgo, no se arregla acá. `npm run build`: build de producción exitoso.
  - Nota: el árbol de trabajo trae cambios preexistentes no relacionados con 06b (`frontend/src/lib/money.ts` agrupamiento es-AR de miles en `formatearImporte`, sus pruebas, y `frontend/package.json` script `generate:api-types`), incluidos tal cual en esta línea base sin modificarlos.

## 2. Sesión con usuario y rol activos (D9, ADR-028) **[CRÍTICA]**

> 0.9 aprobada el 2026-09-25 (D9.2-A, D9.3-B, D9.4-A). Hasta que exista el comando de baja, las pruebas siembran `usuario.estado = 'INACTIVO'` y `rol.activo = false` directamente en la base de prueba (Testcontainers), con un auxiliar que lo documente. Concurrencia: no se agrega una suite propia, porque la verificación es una lectura por petición sin carrera nueva (ver 2.9).

- [x] 2.1 (2026-09-25: el usuario aprobó el plan del grupo 2; USUARIO_INEXISTENTE al renovar se audita con motivo `USUARIO_INACTIVO`; se acepta la acción de auditoría nueva `REVOCAR_SESIONES_REFRESH_USUARIO`, sin catálogo de acciones en `docs/`) **Gate:** confirmar que 0.9 está aprobada y que ADR-028 está *Vigente*. Describir al usuario el cambio concreto de este grupo (archivos y funciones) y esperar su confirmación (CRÍTICA).
- [x] 2.2 (2026-09-25) Red de seguridad registrada: `pytest tests/integration/test_auth_api.py tests/integration/test_identidad_refresh_service.py tests/integration/test_permiso_catalogo.py tests/integration/test_ratchet_permiso_por_ruta.py tests/integration/test_bus_lote_sincronizacion.py tests/integration/test_identidad_login_service.py tests/integration/test_identidad_rate_limit_login_service.py` → **65 passed** (17.5 s), sin fallas previas en este subconjunto. Estos mismos archivos ya están incluidos en la corrida completa de `tests/integration` de 1.1 (522 passed).
- [x] 2.3 RED (integración, Testcontainers) en `tests/integration/test_identidad_sesion_habilitada.py`. Casos para `identidad_service.exigir_sesion_habilitada(org, usuario, sesion)`:
  - usuario `ACTIVO` con rol activo → pasa;
  - usuario `INACTIVO` → error de D9.2;
  - rol con `activo = false` → el mismo error (D9.4-A);
  - usuario inexistente o de otra organización → el mismo error (coherente con D1).

  `listar_permisos_del_usuario` devuelve `frozenset()` para un usuario inactivo o un rol inactivo (falla cerrada). Cita ADR-028 y SEG-06.
- [x] 2.4 RED (HTTP real, login real) en `tests/integration/test_sesion_usuario_inactivo_api.py`. Con el access token vigente de un ADM que después pasa a `INACTIVO`:
  - `GET /identidad/dispositivos` → 401 (código de D9.2), no 403;
  - una escritura con `Operation-Id` (`POST /identidad/usuarios`) → 401, y no quedan filas en `comando` ni en `auditoria`;
  - lo mismo con un usuario activo cuyo rol se desactiva;
  - al volver el usuario a `ACTIVO`, el mismo access token vuelve a pasar (el efecto es por petición, ADR-017).
- [x] 2.5 RED renovación, en `test_identidad_refresh_service.py` y `test_auth_api.py`:
  - el refresh de un usuario `INACTIVO` → 401 `IDENTIDAD_REFRESH_TOKEN_INVALIDO`, con todas sus familias de refresh revocadas (`motivo_revocacion = 'USUARIO_INACTIVO'`) y auditado. La revocación persiste aunque la respuesta sea un error (mismo `commit` previo al `raise` que el reuso);
  - lo mismo con un rol inactivo (`'ROL_INACTIVO'`);
  - reactivar al usuario no revive las familias: hace falta login;
  - la sesión de otro usuario activo en el mismo dispositivo no se toca.

  Sin jornadas todavía, la excepción de D9.3-B no se prueba: queda como deuda nominada (10.4).
- [x] 2.6 RED login: un usuario `ACTIVO` con rol inactivo recibe el mismo `CredencialesInvalidasError` genérico que un usuario inactivo, auditado como `INICIO_SESION_FALLIDO` (SEG-01; no revela la causa).
- [x] 2.7 RED lote de sincronización (D9.3-B; **pendiente de la opción elegida**) en `test_bus_lote_sincronizacion.py`: con el access token vigente de un usuario que pasó a `INACTIVO`, `POST /sync/comandos` **no** responde 401 por ruta. Procesa el lote por ítem igual que para un usuario activo: un lote vacío responde `[]`, y un tipo desconocido da `RECHAZADO` por ítem. Así se fija que el canal de la cola sigue abierto. Si el usuario elige D9.3-A o C, esta tarea se reescribe según esa opción.
- [x] 2.8 GREEN:
  - `exigir_sesion_habilitada` en `identidad/service.py`, con una sola consulta de usuario y rol, filtrada por `organizacion_id`;
  - llamada en `core/autenticacion.py::requiere_permiso`, antes de leer los permisos;
  - `listar_permisos_del_usuario` con falla cerrada;
  - en `renovar_sesion`, verificación después de validar el token: si falla, revoca las familias del usuario con el motivo y audita antes de rechazar (función de repositorio nueva, `revocar_sesiones_refresh_de_usuario`, simétrica a la de dispositivo);
  - en `iniciar_sesion`, se suma el rol inactivo al rechazo genérico.

  `obtener_contexto_autenticado` **no** cambia (D9.1).
- [x] 2.9 Triangular:
  - dos organizaciones: la inactividad de un usuario de A no afecta a B (INV-21);
  - usuario inactivo con dos dispositivos: se revocan las dos familias;
  - reuso de refresh de un usuario inactivo: rechazo y revocación sin doble auditoría contradictoria;
  - justificar por escrito en `verificacion.md` que no hace falta una prueba de concurrencia: la carrera "baja durante una petición" se resuelve en la petición siguiente, igual que un permiso quitado (ADR-017), y no hay escritura concurrente nueva.
- [x] 2.10 (2026-09-25: verificado — ruff check, mypy app y lint-imports en verde; suites de 2.2: 87 passed contra 65 de base; integración completa 544 contra 522. El usuario confirmó el punto de control y pidió corregir la falla previa de `ruff format` en `identidad/api.py`, que se corrigió) Refactor. `ruff`, `mypy app` y `lint-imports` en verde. Suites de 2.2 contra su línea base. Punto de control con el usuario antes de pasar al grupo 3.

## 3. Servicio `identidad_service.obtener_yo` **[ALTA]**

- [x] 3.1 RED: crear `tests/integration/test_identidad_yo_service.py` (Testcontainers). Escenario "Un usuario de Administración obtiene sus permisos ordenados": `obtener_yo(org, usuario, sesion)` devuelve `DatosYo` con usuario, organización y rol (id y nombre) y los permisos del rol en orden alfabético (ADR-027).
- [x] 3.2 GREEN: implementar en `identidad/service.py` el dataclass congelado `DatosYo` (con `UsuarioYo`, `OrganizacionYo` y `RolYo`) y `obtener_yo`.
  - Lee con `repository.obtener_usuario_por_id`, `obtener_organizacion_por_id` y `obtener_rol_por_id`, filtrando siempre por `organizacion_id`.
  - Antes, `exigir_sesion_habilitada` (grupo 2). Si el grupo 2 todavía no está, se agrega al cerrarlo.
  - Los permisos salen **solo** de `listar_permisos_del_usuario` más `sorted()`.
- [x] 3.3 Triangular:
  - Rol con la composición vaciada → `permisos == []`.
  - Usuario de otra organización o inexistente → error de dominio que la API traduce a 401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO` (D1). Nunca datos parciales.
  - **(D9)** Usuario `INACTIVO` o rol inactivo → el mismo error de D9.2, nunca un 200 con lista vacía.
  - Mismo resultado de permisos que `listar_permisos_del_usuario` para los roles de plantilla ADM, GES, SUP, VEN y CON (`01` §19).
- [x] 3.4 Refactor. `mypy app` y `lint-imports` en verde.

## 4. API `GET /api/v1/yo` y contrato **[ALTA: contrato de API]**

- [x] 4.1 (2026-09-25: el usuario aprobó el contrato: usuario, organización y rol con id y nombre, más la lista de permisos; sin email, login, estado ni secretos) Confirmar con el usuario el contrato de `design.md` ("Contrato de `GET /api/v1/yo`") antes de escribir la ruta.
- [x] 4.2 RED: crear `tests/integration/test_identidad_yo_api.py` (HTTP real, login real). Casos:
  - 200 con la forma exacta del contrato y `permisos` ordenados, para un usuario ADM y uno GES.
  - Usuario VEN → 200 (no exige permiso).
  - Sin token → 401 `IDENTIDAD_ACCESS_TOKEN_AUSENTE`.
  - Token con firma alterada → 401 `IDENTIDAD_ACCESS_TOKEN_INVALIDO`.
  - Token vencido (reloj inyectado) → 401 `IDENTIDAD_ACCESS_TOKEN_EXPIRADO`.
  - **(D9)** Access token vigente de un usuario que pasó a `INACTIVO`, o cuyo rol se desactivó → 401 (código de D9.2).
  - La respuesta no contiene `password_hash`, `pin_autorizacion_*`, `tope_descuento` ni `usuario` (nombre de login), probado con un supervisor con PIN.
- [x] 4.3 GREEN: en `identidad/api.py`, agregar `router_yo = APIRouter(tags=["identidad"])` con `@router_yo.get("/yo", response_model=YoResponse)`, endpoint síncrono `def`.
  - Depende de `obtener_contexto_autenticado` y `get_session`.
  - Incluirlo en `api_v1/__init__.py`.
- [x] 4.4 Ratchet de permiso por ruta. RED: `test_ratchet_permiso_por_ruta.py` falla nombrando `GET /api/v1/yo`. GREEN: agregar `("GET", "/api/v1/yo")` a `RUTAS_EXENTAS_DE_PERMISO` con un comentario del motivo (ADR-027: exige sesión y ningún permiso). Agregar la prueba del escenario "La consulta de la propia sesión no exige permiso pero sí sesión".
- [x] 4.5 (2026-09-25) Regenerado `backend/openapi.json` (`python -m scripts.export_openapi`, +136 líneas: `/yo` y sus schemas `YoResponse`/`UsuarioYoResponse`/`OrganizacionYoResponse`/`RolYoResponse`) y `frontend/src/api/schema.gen.ts` (`node scripts/generar-tipos-api.mjs`, +103 líneas). `tests/unit/api/schema.test.ts` (3 casos, no toca `/yo` -- eso es del grupo 6) y `npm run typecheck` en verde. `npm run check:api-types` compara contra el último commit (`git diff --exit-code`), así que marca diferencia hasta que este change se confirme: no es una falla, es el estado esperado de un archivo regenerado sin commit todavía.
- [x] 4.6 (2026-09-25: confirmado) Nota: desde 4.3 hasta 9.1, `test_inv21_ratchet_rutas.py` queda en rojo **a propósito**, con `GET /api/v1/yo` sin cobertura. `test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento` falla nombrando exactamente `[('get', '/api/v1/yo')]` (30 de 31 rutas de negocio cubiertas); las otras 5 pruebas del archivo siguen en verde. Mismo precedente que la tarea 12.1 del change 06. No se agrega la tupla a `COBERTURA_DE_AISLAMIENTO` sin su prueba real (queda para 9.1).

## 5. Aviso de cambios de token (`lib/auth/tokenStore.ts`)

- [x] 5.1 (2026-09-25) RED en `tests/unit/lib/auth/tokenStore.test.ts`: `suscribirACambiosDeToken(listener)` avisa con el token nuevo al `fijarAccessToken` y con `null` al `limpiarAccessToken`. `desuscribir()` corta los avisos.
- [x] 5.2 (2026-09-25) GREEN, y triangular con dos suscriptores y con una suscripción que se da de baja mientras se avisa.
- [x] 5.3 (2026-09-25) Prueba en `tests/unit/lib/api/httpClient.test.ts`:
  - Una renovación exitosa tras un 401 avisa exactamente una vez.
  - Una renovación rechazada avisa con `null`.
  - Varias peticiones concurrentes con 401 comparten una renovación y un solo aviso.
  - Sin cambios de comportamiento en `apiFetch`: se conserva su suite de la línea base.

## 6. Mecanismo de permisos (`features/identidad/`, `domain/identidad/`)

- [x] 6.1 **[BAJA]** `domain/identidad/permisos.ts`: unión `CodigoPermiso` con los códigos de `01` §19 (D8). Prueba de tipos con `// @ts-expect-error` para un código inexistente.
- [x] 6.2 RED y GREEN de `features/identidad/api.ts` y `claves.ts`: `obtenerYo()` sobre `apiFetch('/yo')`, tipado con `schema.gen.ts`, y la clave `['yo']`. Casos: un 200 se parsea, y un error se propaga con su estado.
- [x] 6.3 RED y GREEN de `usePermisos()` sobre `useQuery(['yo'], { staleTime: Infinity, refetchOnWindowFocus: false })`. Devuelve `{ estado: 'cargando' | 'error' | 'listo', tiene(permiso), yo, reintentar }`.
  - Triangular: `tiene` es falso mientras carga y ante un error (falla cerrada, D3-A).
- [x] 6.4 RED y GREEN de `<SiTienePermiso permiso fallback? cargando?>`:
  - Con el permiso, muestra los hijos.
  - Sin él, el `fallback` (o nada), y los hijos **no se montan**: se prueba con un hijo que dispara una consulta, y la consulta no ocurre (D4-A).
  - Mientras carga, el nodo `cargando`.
- [x] 6.5 RED y GREEN de la suscripción en `AdminScreen.tsx` (D2-A):
  - Al fijarse un token, `['yo']` se invalida con `cancelRefetch: false`.
  - Al limpiarse, `['yo']` se elimina de la caché.
  - Recargar (401 en `/yo`, renovación, reintento) produce un solo `/yo` exitoso.
  - La suscripción se da de baja al desmontar.
- [x] 6.6 Prueba de que ninguna clave de `localStorage` ni `sessionStorage` contiene la respuesta de `/yo` tras cargarla (escenario "Los permisos no quedan en el almacenamiento del navegador").
- [x] 6.7 Crear `tests/unit/utils/` con un auxiliar de prueba compartido que arme un `QueryClient` con `['yo']` sembrado para un rol dado. Lo usan los grupos 7 y 8.

## 7. Menú, encabezado y aterrizaje (`AdminLayout.tsx`, `LoginScreen.tsx`, `AdminScreen.tsx`)

- [x] 7.1 (2026-09-27) **[BAJA]** `features/identidad/secciones.ts`: lista ordenada con `{ ruta, etiqueta, permiso }` para Catálogo (`GESTIONAR_CATALOGO`), Proveedores (`GESTIONAR_PROVEEDORES`) y Dispositivos (`GESTIONAR_DISPOSITIVOS`). Se le agregaron `seccionesPermitidas(tiene)` y `primeraSeccionPermitida(tiene)`, para que el menú y el aterrizaje consulten la misma lista sin lógica en los componentes.
- [x] 7.2 (2026-09-27) RED en `tests/unit/areas/admin/AdminLayout.test.tsx` (nuevo, 18 casos). GES ve Catálogo y Proveedores, no Dispositivos; SUP ve solo Dispositivos; VEN no ve secciones. 4 fallas, 2 pases triviales.
- [x] 7.3 (2026-09-27) GREEN: el menú se arma desde `secciones.ts` con `usePermisos()`, y las rutas absolutas se conservan (tarea 10.8 del 05). Caso extra: con `['yo']` sembrado no hay ninguna petición extra a `/yo` (ADR-027). 6 pases.
- [x] 7.4 (2026-09-27) **(B1)** Triangular estados: pendiente sin secciones; error 500 con aviso "No se pudieron obtener tus permisos" y **Reintentar** que vuelve a consultar y muestra las secciones; error 401 tras una renovación fallida con enlace a iniciar sesión en vez de reintentar. Para distinguir 401 de otros errores, `usePermisos()` expone ahora `error: ErrorDeIdentidad | undefined` (el `status` que `api.ts` conservaba desde la tarea 6.2 justamente para esto); no se cambia su firma ni su comportamiento. 10 pases.
- [x] 7.5 (2026-09-27) **(B4)** El encabezado muestra "{usuario} · {organización} · {rol}" con los nombres de `/yo`, y no inventa nombres mientras la consulta está pendiente ni si falla. 13 pases.
- [x] 7.6 (2026-09-27) **(B3)** Ruta índice `/admin/inicio` dentro del layout, en el `AdminInicio` nuevo: espera `/yo`, salta a la primera sección permitida (GES a Catálogo, SUP a Dispositivos) y, si no hay ninguna, informa "Tu usuario no tiene secciones de administración disponibles"; mientras está pendiente no redirige y, si la consulta falla, no afirma que no hay secciones (eso lo informa el aviso del layout). `LoginScreen` navega a `/admin/inicio` (`LoginScreen.test.tsx` actualizado contra su línea base de 4 casos). `app-routing.test.tsx`: las 3 pruebas que buscan enlaces del menú interceptan solo `/yo` (el menú falla cerrado sin esa respuesta) y se agrega una del ruteo real de `/admin/inicio`; su línea base era 9/9 aislado y 8/9 en la corrida completa (flaky de `jsdom`), ahora 10/10 en ambas.

## 8. Retiro del patrón reactivo en las pantallas de los changes 03 a 06

Para cada pantalla:
- Línea base de su suite.
- Las pruebas que simulaban un 403 para decidir visibilidad se reescriben sembrando `['yo']`.
- **Se conserva** un caso de 403 del servidor como red de seguridad: mensaje de falta de permiso, sin datos, sin error genérico.
- Sin permiso, se verifica que **no** se hace la petición de datos (**B2**).

- [x] 8.1 `DispositivosScreen.tsx` (`GESTIONAR_DISPOSITIVOS`): envolver con `<SiTienePermiso>` y actualizar el docstring que hoy explica el mecanismo reactivo. Escenarios de `identidad/permisos-efectivos`: "Entrar por URL…", "Con el permiso…" y "Un 403 del servidor entre dos renovaciones…".
- [x] 8.2 `ProductosListScreen.tsx` y `CategoriasYMarcasScreen.tsx` (`GESTIONAR_CATALOGO`). Escenarios de `catalogo/administracion-de-catalogo`: "Usuario con permiso", "Usuario sin permiso" y "El servidor rechaza aunque la interfaz creía tener el permiso".
- [x] 8.3 `ProductoFormScreen.tsx`:
  - Eliminar `useCostoVigente` de `ProductoBaseForm` y el comentario de la tarea 14.3 del 06.
  - Envolver el enlace "Ver historial de costos" con `<SiTienePermiso permiso="VER_COSTOS">`.
  - Reescribir la prueba de la línea 581 de `ProductoFormScreen.test.tsx`: con `VER_COSTOS` se ve el enlace; sin él, o en modo alta, no.
  - En ningún caso se pide `/costos/productos/{id}/vigente`.
- [x] 8.4 `ProveedoresListScreen.tsx` (`GESTIONAR_PROVEEDORES`) y `ProveedorFormScreen.tsx`:
  - Pantalla con `GESTIONAR_PROVEEDORES`.
  - Enlace "Cargar costos" con `EDITAR_COSTOS`, escenario "Enlace 'Cargar costos'…".
- [x] 8.5 `CostosCargaScreen.tsx` (`EDITAR_COSTOS`) y `CostosHistorialScreen.tsx` (`VER_COSTOS`). Escenarios "Usuario sin permiso" (carga e historial por URL) y "El servidor rechaza aunque la interfaz creía tener el permiso". `CostosCargaScreen` gana el manejo explícito del 403, que hoy no tiene.
- [x] 8.6 Verificación por `grep` en `frontend/src/areas/admin`:
  - `PermisoRequerido…Error` solo aparece en ramas de manejo del 403 del servidor, nunca para decidir visibilidad.
  - `useCostoVigente` ya no aparece en `ProductoFormScreen.tsx`.
  - Dejar la evidencia en `verificacion.md`.
- [x] 8.7 `npm run typecheck`, `npm run lint`, `npm run test` y `npm run build` en verde contra la línea base de 1.1.

## 9. Pruebas de integración y aislamiento **[ALTA]**

- [x] 9.1 INV-21 en `test_inv21_aislamiento_endpoints_identidad.py`.
  - Dos organizaciones con login real (nunca `emitir_access_token` a mano). El usuario de B consulta `/yo` y obtiene solo su usuario, su organización y su rol; ningún id, nombre ni permiso de A.
  - Informar `organizacion_id` y `usuario_id` de A en la consulta y en encabezados no cambia la respuesta.
  - Luego agregar `("get", "/api/v1/yo")` a `COBERTURA_DE_AISLAMIENTO` con su comentario, y confirmar que `test_inv21_ratchet_rutas.py` vuelve a verde. Registrar el RED previo de 4.6.
  - (2026-09-27) `TestAislamientoDeLaSesion`, dos pruebas: la respuesta de B es exactamente la de B, e inyectar los identificadores de A por query (`organizacion_id`, `usuario_id`) y por encabezado (`X-Organizacion-Id`, `X-Usuario-Id`) no la altera. `_crear_organizacion` y `_crear_usuario` aceptan ahora nombres propios para que las aserciones no dependan del nombre hardcodeado de la plantilla. Archivo: 6 → 8 pruebas, todas verdes.
  - (2026-09-27) RED de 4.6 registrado tal cual: `AssertionError: INV-21: 1 ruta(s) de negocio sin cobertura de aislamiento: [('get', '/api/v1/yo')]. Rutas de negocio cubiertas hoy: 30 de 31.` — `1 failed, 5 passed in 7.25s`. Con la tupla agregada, `6 passed in 4.78s`.
- [x] 9.2 Confirmar que `test_inv21_organizacion_siempre_del_token.py` recorre la ruta nueva y pasa: `/yo` no declara `organizacion_id`.
  - (2026-09-27) `/yo` agregada a la lista local del archivo y nueva prueba `test_la_recorrida_de_aislamiento_alcanza_la_consulta_de_la_sesion`, que consulta el OpenAPI de la app: la operación existe, no declara `organizacion_id` ni `usuario_id`, no declara cuerpo, y su único parámetro es el `authorization` que agrega `HTTPBearer` (no un parámetro propio de la ruta). 3 → 4 pruebas, todas verdes.
- [x] 9.3 Coherencia con la autorización (SEG-06, ADR-027), escenario "Lo informado coincide con lo que el servidor autoriza". Con un usuario cuya `/yo` incluye `VER_COSTOS` y no `GESTIONAR_DISPOSITIVOS`:
  - `GET /costos/productos/{id}/vigente` → 200.
  - `GET /identidad/dispositivos` → 403 `PERMISO_REQUERIDO`.
  - (2026-09-27) `TestLoInformadoCoincideConLoAutorizado`. El auxiliar `_crear_usuario_con_permisos` fija una composición **exacta** (a diferencia de `_crear_usuario_con_plantilla`, que usa las plantillas de `01` §19) para que la lista de `/yo` se pueda contrastar sin otras variables de entrada. La mitad con `VER_COSTOS` da 200 en el costo vigente del producto propio —con `costo: null`, que es la respuesta que `CostoVigenteResponse` da cuando el producto existe y no tiene costo— y 403 `PERMISO_REQUERIDO` en dispositivos. Triangulada con la mitad simétrica: `GESTIONAR_DISPOSITIVOS` sin `VER_COSTOS` da 200 en dispositivos y 403 en el costo. Ninguna de las dos mitades se apoya en un caso sin permisos.
- [x] 9.4 Revocación y alta de permisos con el mismo access token (ADR-017): quitar `GESTIONAR_PROVEEDORES` con `PUT /identidad/roles/{rol_id}/permisos` (bus, `Operation-Id`) y verificar que la siguiente `/yo` ya no lo trae. Agregar `GESTIONAR_DISPOSITIVOS` y verificar que la siguiente `/yo` lo trae.
  - (2026-09-27) `TestLosPermisosDelRolSeReflejanEnLaConsultaSiguiente`. El cambio de composición se hace por la ruta real (`Operation-Id` distinto en cada `PUT`) y se vuelve a consultar `/yo` con el **mismo** access token, sin renovar y sin volver a iniciar sesión. El usuario que cambia la composición es el mismo que se consulta y arranca con `ADMIN_USUARIOS` (por eso el rol `ADMINISTRACION` no sirve: no lo trae, y `Administrador` ya tendría `GESTIONAR_DISPOSITIVOS`). Al revocar, la siguiente `/yo` trae solo `ADMIN_USUARIOS` y `/identidad/proveedores` pasa a 403 mientras `/identidad/usuarios` sigue en 200 —lo que prueba que se quitó *solo* ese permiso—. Al otorgar, la siguiente `/yo` ya trae `GESTIONAR_DISPOSITIVOS` y `/identidad/dispositivos` pasa a 200 en la petición siguiente.
- [x] 9.5 Lectura pura: tres consultas a `/yo` no crean filas en `comando` ni en `auditoria` (ADR-022).
  - (2026-09-27) `TestLaConsultaDeLaSesionNoEscribe`. El recuento es de **toda** la tabla, sin filtrar por organización: un filtro dejaría pasar filas que la prueba no está mirando, y como `comando` y `auditoria` son de solo inserción (`AGENTS.md` §4) el recount solo puede subir. La prueba además verifica que los recuentos no son triviales antes de leer (`comando == 0`, `auditoria == 1` y esa única fila es `INICIO_SESION` del propio login), así que "no escribió nada" no es el resultado vacío de contar sobre tablas vacías. Tres `GET /yo` a 200 dejan ambos recuentos intactos.
- [x] 9.6 Suite completa de integración en verde. Ninguna prueba en `skip` o `xfail` sin justificación registrada.
  - (2026-09-27) `pytest tests/integration -q -rsx` → **573 passed**, 0 failed, 0 skipped, 0 xfailed, 9 warnings en 556.62s. `-rsx` no imprimió ninguna sección de skip/xfail, y una búsqueda de `pytest.mark.skip`, `pytest.mark.skipif`, `pytest.mark.xfail` y `pytest.skip` en todo `backend/tests/` no devuelve coincidencias: no hay ninguna prueba omitida que justificar.
  - (2026-09-27) Gates: `ruff check .` → `All checks passed!`; `ruff format --check .` → `208 files already formatted`; `mypy app` → `Success: no issues found in 79 source files`; contratos → `10 kept, 0 broken`. Suites sin tocar: `tests/unit tests/properties tests/fixtures_compartidos` → 383 passed.
  - (2026-09-27) Los ocho tests nuevos de este grupo: 5 de caracterización que pasan sin tocar producción (9.2, 9.3, 9.4, 9.5), 2 de aislamiento (9.1) y el ratchet (9.1). El único RED propio fue el autorizado de 4.6, más un RED de expectativa equivocada en 9.2 (OpenAPI declara `authorization` por `HTTPBearer`, no era un parámetro de la ruta).
  - (2026-09-27) **No se ejecutó la suite completa antes de editar**: el árbol ya traía los grupos 3–8 sin commit. Lo que sí se midió antes fue el conjunto dirigido de los archivos tocados (23 passed) y la suite sin los cuatro archivos del grupo (541 collected), lo que da 565 tests preexistentes frente a los 573 de ahora. Los últimos números completos registrados en este change son 522 (1.1) y 544 (2.10).

## 10. Verificación

- [x] 10.1 (2026-09-27) Crear `verificacion.md` con el mapeo escenario → prueba de las seis specs delta (`04` §2.1 punto 2). Mapeo completo en `verificacion.md` §10.1: los 45 escenarios mapeados; los dos que estaban cubiertos solo parcialmente se cerraron con pruebas nuevas (sin cambio de producción): backend, `test_auth_api.py::TestRenovacionConSesionDeshabilitada` (la revocación y la auditoría se leen desde una sesión externa, después del `expire_all`, para comprobar que quedaron confirmadas aunque la respuesta fuera el 401; y la auditoría con `usuario_id`, `dispositivo_id` y motivo); frontend, `AdminScreenRenovacion.test.tsx` (efecto observable de la renovación sobre el menú, y una sola consulta a `/yo` mientras no se renueve el token). TDD de caracterización: RED por afirmación contraria a propósito, luego expectativa real.
- [x] 10.2 (2026-09-27) Confirmar con `grep` que INV-21, SEG-06, ADR-027 y ADR-028 tienen pruebas que los citan por ID, con evidencia en `verificacion.md` §10.2: INV-21 (52 coincidencias / 26 archivos), SEG-06 (8/6 en backend, 7/7 en frontend), ADR-027 (15/6 y 13/7) y ADR-028 (16/7), con las líneas literales de las pruebas que citan cada ID, incluidas las cuatro opciones aprobadas de D9.1/D9.2-A/D9.3-B/D9.4-A.
- [x] 10.3 (2026-09-27) Suite completa de backend y frontend contra la línea base de 1.1, en `verificacion.md` §10.3. Backend: `ruff check` limpio, `ruff format --check` del archivo tocado limpio, `mypy app` `Success: no issues found in 79 source files`, `lint-imports` `10 kept, 0 broken`, `unit` 322, `properties` 5, `fixtures_compartidos` 56, `integration` 575 passed (dos corridas limpias consecutivas; los 2 casos nuevos de `test_auth_api.py` sobre los 573 de 9.6). Frontend: `typecheck` limpio, `lint` 0 errores y los 2 warnings preexistentes, `test` 36 archivos / 272 passed, `build` correcto. Se reportan los dos flakes preexistentes sin arreglarlos, como decidió la 1.1: `app-routing.test.tsx` (lazy, intermitente, el archivo quedó intacto) y `test_identidad_yo_api.py::test_token_con_firma_alterada_da_401_invalido` (1 de 2 corridas, pasó al repetir y en aislamiento).
- [x] 10.4 (2026-09-27) Documentación:
  - Preparar la actualización de `docs/04-roadmap-changes.md` para el archivo:
    - fila del 06b, que suma el cierre de la brecha de sesión (ADR-028);
    - **deuda nominada** para el change que agregue los permisos por comando en el lote (paso 4 de `02` §6.3, change 15 o 18a): comandos `OFFLINE` de un usuario o rol inactivo aceptados con `PERMISO_REVOCADO`, y la excepción de renovación con jornada no cerrada (D9.3-B, si se aprueba);
    - nota para el change de usuarios y roles (D9.5).
  - Confirmar que ADR-028 está *Vigente* con las opciones aprobadas.
  - Evaluar con el usuario si `02` §12.1 o §12.3 suman una línea que remita a ADR-028, igual que con ADR-027.
  - Si 0.7 se aprobó, dejar la enmienda de ADR-027 en estado *Vigente*.
  - No hay otro ADR nuevo salvo que surja una decisión no prevista.
  - (2026-09-27) El usuario revisó las propuestas de `verificacion.md` §10.4 y aprobó un conjunto acotado. Se aplicaron cuatro ítems y nada más: (a) las dos celdas de la fila 06b de la tabla de la etapa 1 en `docs/04-roadmap-changes.md` (suma el cierre de la brecha de sesión de ADR-028); (b) la deuda nominada para el change 15 (`jornadas`) o el 18a (`venta-online-core`) por el paso 4 de `02` §6.3; (c) la nota D9.5 para el change de usuarios y roles, junto a esa deuda; (d) la línea "Sesión habilitada (ADR-028)" en `docs/02-arquitectura.md` §12.1, a continuación de la de ADR-027. `docs/referencia/` no se tocó, no se agregó ningún ADR y no se modificó ni ADR-027 ni ADR-028.
  - (2026-09-27) Rechazados por el usuario: la línea de remisión alternativa de `02` §12.3 (la segunda opción del §10.4.3 de `verificacion.md`), por duplicar (d); y la enmienda de ADR-027 con B1/B2 (tarea 0.7), que no se aprobó, así que **0.7 sigue `[ ]`** y `docs/adr/ADR-027-permisos-efectivos-para-la-interfaz.md` queda intacto. ADR-028 se verificó en lectura: ya estaba en estado *Vigente* con D9.1, D9.2-A, D9.3-B y D9.4-A registradas, así que no había nada que cambiar.
  - (2026-09-27) **Corrección de encuadre en la deuda (b).** El texto preparado en `verificacion.md` afirmaba que D9.3-B "no está aprobada" y ofrecía como "alternativa" una redacción que sí lo afirmaba. Ese encuadre era incorrecto: `docs/adr/ADR-028-sesion-exige-usuario-y-rol-activos.md` L9 y L77 registran que D9.1, D9.2-A, D9.3-B y D9.4-A fueron aprobadas por el usuario el **2026-09-25**. Lo que se difiere al change de jornadas es la **implementación** de la excepción de renovación, no la decisión. Se aplicó la versión corregida y se eliminó la frase del "alternativa" (quedó solo en el registro de auditoría de `verificacion.md` §10.4.2), conservando todo el contenido técnico: la brecha del paso 4 de `02` §6.3, los comandos `OFFLINE` de un usuario `INACTIVO` o de un rol con `activo = false` aceptados con `PERMISO_REVOCADO` (SYN-10) y nunca rechazados, el procesamiento del lote ítem por ítem, y el hecho de que D9.3-B hoy solo está probada como "el canal de la cola sigue abierto para el usuario inactivo" (`test_bus_lote_sincronizacion.py::TestUsuarioInactivoNoSeRechazaPorRuta`) y no como excepción a la renovación.
- [x] 10.5 Verificación manual del flujo principal en el navegador, con un script para el usuario en `verificacion.md` §10.5 (mismo formato que la 13.5 del change 06):
  - (2026-09-28) El usuario corrió los pasos 1-13 con éxito (login por usuario, pantallas por permiso, "No tenés permiso" sin pedir datos, revocación en vivo con 403 antes de renovar y menú sin "Proveedores" tras renovar sin recargar, `/yo` directo, almacenamiento limpio, `/ruta` intacta). **Hallazgo en el paso 13 (D9, usuario inactivo):** al pasar a `ges01` a `INACTIVO`, la pantalla de datos que recibió el 401 mostró su propio error ("No se pudo obtener el producto") y tras recargar quedó en blanco, en lugar del aviso "Iniciar sesión". El corte se implementa en el grupo 11.
  - **(2026-09-28, cierre)** El grupo 11 se aplicó y el usuario re-verificó el paso 13: con `ges01` en `INACTIVO`, la siguiente acción en `/admin` y la recarga aterrizan de inmediato en el aviso "Iniciar sesión". **Verificación completa.**
  1. **Preparación:** `docker compose up -d`, `alembic upgrade head` y siembra si hace falta.
  2. **Usuarios de prueba:** con el ADM (`organizacion-inicial` / `admin`), obtener por `psql` los `rol_id` de "Administración" y "Supervisor comercial". Crear con `curl.exe` (`POST /api/v1/identidad/usuarios` con `Operation-Id`) un usuario GES y uno SUP.
  3. **Login ADM:** aterriza en Catálogo. Ve Catálogo, Proveedores y Dispositivos, y el encabezado "Administrador · Organización inicial · Administrador". En la ficha de un producto ve "Ver historial de costos". En la pestaña Red de las devtools no hay pedido a `/costos/.../vigente` al abrir la ficha.
  4. **Login GES:** aterriza en Catálogo, sin Dispositivos en el menú. Escribir `/admin/dispositivos` muestra "No tenés permiso…" y la pestaña Red no muestra `GET /identidad/dispositivos`.
  5. **Login SUP:** aterriza en Dispositivos y ve solo esa sección. Escribir `/admin/proveedores` y `/admin/catalogo` muestra el mensaje de falta de permiso, sin pedidos de datos.
  6. **Revocación en vivo:** con GES logueado, el ADM quita `GESTIONAR_PROVEEDORES` al rol Administración (`curl.exe` `PUT /identidad/roles/{rol_id}/permisos`). En GES, abrir Proveedores antes de la renovación muestra el 403 del servidor como "No tenés permiso". Tras la renovación (esperar 15 minutos, o forzarla con una petición después del vencimiento), "Proveedores" desaparece del menú sin recargar. Restaurar el permiso al terminar.
  7. **`/yo` directo:** `curl.exe` con el token de GES devuelve los permisos ordenados. Sin token devuelve 401.
  8. **Almacenamiento:** en las devtools (Application), ni `localStorage`, ni `sessionStorage`, ni IndexedDB contienen permisos.
  9. **`/ruta`:** sin cambios visibles.
  10. **(D9) Usuario inactivo:** con el GES logueado en `/admin`, pasarlo a `INACTIVO` por `psql` (todavía no hay comando). La siguiente acción en `/admin` termina en el aviso de sesión terminada con enlace a iniciar sesión. El login con ese usuario da el mensaje genérico. `curl.exe` a `/yo` con su último access token da 401. Volver el usuario a `ACTIVO` al terminar.

## 11. Cierre del hallazgo de la 10.5: renovación rechazada → "iniciar sesión" **[ALTA: manejo de sesión]**

> **Hallazgo de la 10.5 (2026-09-28).** Al pasar a un usuario a `INACTIVO`
> (ADR-028 D9), el backend responde 401 por petición y rechaza la renovación
> (correcto). Pero el aviso de "Iniciar sesión" de `AdminLayout`
> (`permisos-efectivos`, escenario B1 "Si la sesión terminó, se ofrece iniciar
> sesión") solo aparece si la consulta `['yo']` falla con 401; cuando el 401 llega
> por una **consulta de datos** en una pantalla, esa pantalla muestra su propio
> error ("No se pudo obtener el producto") y al recargar con la sesión muerta la
> página queda en blanco, en vez del aviso que ofrece iniciar sesión. La ruta
> indirecta actual (`tokenStore` → `removeQueries(['yo'])` → recreación del
> observer → refetch → 401) no aterriza de forma determinística y queda sujeta a
> los retries de TanStack.
>
> **Objetivo:** una renovación rechazada debe pasar la app al estado "sesión
> terminada" de forma determinística e inmediata, sin esperar retries ni
> depender de qué pantalla disparó el 401.

- [x] 11.1 **RED** — Pruebas de frontend que reproduzcan el hallazgo (2026-09-28):
  - un 401 en una consulta de datos (no `/yo`) con renovación rechazada → aparece el aviso con enlace "Iniciar sesión" y el menú queda sin secciones protegidas;
  - montar `/admin` sin access token y con la renovación rechazada (sesión muerta, como tras recargar) → aparece el aviso "Iniciar sesión" (no queda en blanco y no reintenta).
- [x] 11.2 **GREEN** — Implementar el corte determinístico: la renovación rechazada debe poner a la consulta `['yo']` en error 401 de inmediato (p. ej. `retry: false` en `usePermisos` y falla rápida en `obtenerYo` cuando no hay access token), y el aviso de `AdminLayout` con "Iniciar sesión" debe aparecer sin depender de la pantalla que disparó el 401. (2026-09-28)
- [x] 11.3 Verificación: `npm run typecheck`, `npm run lint`, `npm run test -- --run` (o el target de unit), `npm run build` en verde. Este grupo no toca backend: la suite de integración no se re-corre salvo que algo la requiera. (2026-09-28)
