# ADR-062 — PWA, bootstrap en una foto con jornada abierta, base local con reemplazo atómico y sesión local con PIN de 6 dígitos

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-10-31, archivo del change 21) |
| Fecha | 2026-10-30 |
| Referenciado en | `openspec/changes/21-pwa-y-bootstrap/design.md` D0 a D21 y `specs/sync/bootstrap`, `specs/sync/base-local`, `specs/identidad/sesion-local`, `specs/sistema/aplicacion-instalable`, `specs/ruta/area-de-ruta`, `specs/sistema/ayuda-contextual`; `01-dominio.md` §19, RUT-03, SYN-10, SYN-11, SEG-01, SEG-03, SEG-04, PRC-20, PRC-21, INV-01, INV-02, INV-03, INV-04, INV-12, INV-13, INV-21; `02-arquitectura.md` §5.3, §7.1, §12.3, §12.4, §13; ADR-006, ADR-011, ADR-019, ADR-027, ADR-028, ADR-049, ADR-051, ADR-055, ADR-059, ADR-060 |

**Change 21. Gobernanza ALTA en la sesión local y las derivaciones (D8, D13 a D16); MEDIA en el resto. Decisiones aprobadas por el usuario el 2026-10-30 (A, salvo D14 = B). Compatibilidad: los vendedores usan Android hoy y la aplicación debe seguir funcionando en iPhone/Safari (instalación por "Compartir > Agregar a inicio", persistencia según Safari).**

## Contexto

SYN-11 y ADR-006 definen qué baja el bootstrap y que se descarga completo al abrir la jornada, y ADR-011 que la sesión sin conexión se desbloquea con un PIN derivado con PBKDF2. No resuelven: quién puede pedir el bootstrap, si sus secciones deben ser de un mismo instante, qué clientes, listas, versiones y reglas se bajan, si se bajan costos y qué autorizadores; el esquema de la base local; el largo del PIN de desbloqueo, cuándo se pide, cómo se cuentan los fallos, qué pasa al cerrar sesión o al cambiar de usuario; el alcance del service worker; y cómo se prueba en el teléfono con HTTPS. Los changes 13, 15, 16, 16b, 17, 18a, 18b, 20, 20b y 20c nominaron al 21 el contenido del bootstrap y las pantallas de `/ruta`.

## Decisión (aprobada el 2026-10-30: opción A en todas salvo D14 = B)

1. **Lotes (D0).** Un change en cinco lotes, excepción de tamaño como el 17 y el 18a.
2. **Dónde (D1).** `GET /api/v1/sync/bootstrap` en el módulo `sync`, que compone solo por el `service.py` de cada módulo.
3. **Acceso (D2).** Sesión habilitada (ADR-028) y jornada `ABIERTA` propia en el dispositivo del token; sin ella, 409 `JORNADA_REQUERIDA`. Las secciones se filtran por permiso. `since` se acepta y se ignora (ADR-006).
4. **Una foto (D3).** Transacción `REPEATABLE READ READ ONLY` solo para el bootstrap: excepción de solo lectura a `02` §7.1.
5. **Clientes (D4).** `ACTIVO`, `SUSPENDIDO` y el consumidor final habilitado, con `en_cartera` ("vacía = todos"), datos de contacto, saldo y crédito resuelto; sin correo ni vendedor.
6. **Listas (D5, D6).** Sin `USAR_LISTA_ANTERIOR`: la predeterminada y las asignadas a los clientes bajados, con la vigente y las programadas; con el permiso: todas las activas con vigentes, programadas e históricas elegibles. Las reglas `ACTIVA` no vencidas, incluidas las que empiezan más tarde. El dispositivo elige por el momento de la operación.
7. **Sin costos (D7)**, ni con `VER_COSTOS`.
8. **Autorizadores (D8).** Con `VENDER`: activos, de rol activo, con permiso de autorización y PIN definido, con hash, sal e iteraciones; vector de prueba compartido Python–Web Crypto.
9. **Contrato (D9).** Una respuesta con secciones; importes y porcentajes como string.
10. **Base local (D10).** Dexie v2 con las tablas maestras; el bootstrap las reemplaza en una sola transacción sobre una lista explícita; las tablas de operaciones llegan con el 22a.
11. **Momentos (D11).** Tras abrir la jornada en `/ruta`, al iniciar sesión o desbloquear con conexión si faltan los datos de la jornada abierta, y con "Actualizar datos".
12. **Login (D12).** Pantalla propia `/ruta/login` sobre el mismo endpoint.
13. **PIN de desbloqueo (D13).** Exactamente 6 dígitos, sin triviales (regla de ADR-055), PBKDF2-SHA256 con Web Crypto, sal de 32 bytes y 600 000 iteraciones, solo en el dispositivo.
14. **Cuándo (D14).** Solo al abrir la aplicación (arranque o recarga), con o sin conexión; no al volver de segundo plano. Aprobado el 2026-10-30 (opción B). Consecuencia aceptada por el usuario: con el teléfono desbloqueado y la aplicación abierta o en segundo plano se puede usar sin PIN.
15. **Bloqueo (D15).** Fallos contados en la base local; con 10 fallos (constante fija en código, aprobada el 2026-10-30; no usa `intentos_pin_max`, que queda para los fallos de un usuario contra el PIN de un mismo supervisor, en línea) se borra la derivación y se exige login con conexión; nada pendiente se pierde. Precisa el alcance de `intentos_pin_max` de `01` §4 y ADR-011 sin modificar ADR-011: su texto trata la verificación en línea contra el supervisor, que no cambia.
16. **Una sesión por dispositivo (D16).** Cerrar sesión (con conexión) y el login de otro usuario borran sesión, PIN y datos maestros; nunca operaciones pendientes.
17. **Service worker (D17).** `vite-plugin-pwa`, `generateSW`, `registerType: 'prompt'`; precache del shell, `/ruta`, la ayuda y pdfmake, sin `/admin` ni la API; aviso de versión nueva sin recarga automática; manifiesto con `start_url: /ruta`.
18. **Persistencia (D18).** `navigator.storage.persist()` tras el primer bootstrap y en cada arranque hasta que se conceda; advertencia si se niega.
19. **Pantallas (D19).** Inicio, Abrir jornada, Clientes, Productos, Stock, Mi cuenta y Ayuda, todas de consulta; la venta sigue en `/admin` hasta el 22a.
20. **Teléfono real (D20).** Perfil opcional de Docker Compose con Caddy de desarrollo (`tls internal`) en la red local.
21. **Ayuda (D21).** `/ruta/ayuda/:tema`; "Ver más" interno en `/ruta` y en la aplicación instalada; cuatro claves nuevas sin ejemplos.

## Consecuencias

- El 22a agrega la venta y la cola sobre la base local sin rehacer el bootstrap; la versión 3 de Dexie suma las tablas de operaciones.
- `02` §7.1 gana una excepción de solo lectura; `02` §13 queda precisado (bootstrap, base local, service worker, sesión local).
- El teléfono lleva derivaciones de PIN de supervisores solo si el usuario puede vender (riesgo aceptado de ADR-011).

## Precisiones del apply

- **Respuesta 409.** `JORNADA_REQUERIDA` es una excepción propia del bootstrap (409); el error de validación del bus sigue siendo 422. La ruta usa `requiere_sesion` (sesión habilitada, ADR-028) y queda fuera del ratchet de permiso por ruta, igual que `/yo`.
- **Una foto.** La transacción `REPEATABLE READ READ ONLY` se fija con `SET TRANSACTION` antes de la primera lectura; hay una prueba de concurrencia que confirma escrituras en medio del pedido y verifica que las secciones sean del mismo instante.
- **Composición.** `sync` compone solo por el `service.py` de cada módulo (lecturas masivas nuevas en clientes, cuentas corrientes, catálogo, precios, descuentos, identidad y stock); el contexto de venta se recompone en `sync` porque `ventas.queries` le está vedado. `pyproject.toml` saca a `sync` del contrato de aislamiento de precios y ajusta el contrato de SQLAlchemy solo para `sync.bootstrap`.
- **Vector de prueba compartido.** `shared/fixtures/pin/derivacion.json` fija la derivación PBKDF2 (hash, sal, iteraciones) y lo corren Python (autorizadores) y TypeScript (`derivacion.ts`, Web Crypto).
- **Base local.** El saldo vive dentro de `clientes` (no hay tabla `saldos_clientes`); las lecturas de `/ruta` usan `liveQuery` de Dexie sin `dexie-react-hooks`. Los clientes se ordenan: consumidor final, cartera, resto. Las claves de `meta` del PIN son `pin_hash`, `pin_sal`, `pin_iteraciones` y `pin_intentos`; el borrado de sesión usa una lista explícita de tablas.
- **Bloqueo del PIN (aprobado 2026-10-30).** `INTENTOS_DESBLOQUEO_MAX = 10`, constante del código; `intentos_pin_max` (5) rige solo para el PIN de un supervisor en línea (punto 15).
- **Login de `/ruta`.** Función plana compartida con `/admin` (`features/identidad/login.ts`); `/ruta` no usa TanStack Query (`CLAUDE.md` §2). El refresh a pedido es `renovarSesion`, que distingue rechazo de corte de red.
- **Service worker.** `vite-plugin-pwa` 2.0.0 exacta (compatible con la versión de Vite del proyecto; Workbox 7.4.1). El código de `/admin` sale a `assets/admin/` y se excluye del precache por patrón; `/api/` y `/admin` están en `navigateFallbackDenylist`; sin `runtimeCaching`. Agregar la dependencia exige reconstruir la imagen Docker del frontend.
- **Teléfono real (D20).** El perfil `lan` de Docker Compose levanta Caddy con `tls internal` delante del frontend y del backend, sirviendo la compilación de producción del frontend (el service worker solo existe en la compilación); el paso a paso para confiar el certificado está en el chat de la prueba manual, sin archivo aparte.
- **Pruebas.** Las de precache corren el build real (`NODE_ENV=production`, entorno `node`); las de punta a punta son `test_bootstrap_flujo.py` (HTTP con PostgreSQL real) y `FlujoRuta.test.tsx` (`fake-indexeddb`, Web Crypto y `fetch` simulado). No se agregó Playwright: el repositorio todavía no lo tiene configurado.

## Alternativas consideradas

Las opciones B y C de cada decisión de `design.md`, con sus consecuencias.

## Deudas nominadas

- **Al 22a:** la guarda del carrito abierto frente a la versión nueva del service worker (`02` §13.5); las tablas de operaciones en Dexie y ampliar la prueba de que el bootstrap no las toca.
