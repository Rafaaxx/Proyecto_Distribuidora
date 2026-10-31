# Change 21-pwa-y-bootstrap

## Qué resuelve este change

Convierte `/ruta` en una aplicación instalable que abre sin señal: el vendedor inicia sesión en el teléfono, abre su jornada, descarga los datos del día a la base local y los consulta con o sin conexión, desbloqueando con un PIN propio del dispositivo.

## Why

`04` §11 (fila 21) y las deudas nominadas por los changes 13, 15, 16, 16b, 17, 18a, 18b, 20, 20b y 20c: no existe `GET /api/v1/sync/bootstrap` (SYN-11, ADR-006), `/ruta` es un placeholder, no hay service worker, ni base local más allá de `meta`, ni sesión local con PIN (SEG-03, SEG-04, ADR-011). El 22a (confirmación local) necesita todo esto: sin bootstrap no hay datos para vender sin conexión.

## What Changes

- **Bootstrap** (`design.md` D1 a D9): `GET /api/v1/sync/bootstrap?since=` (since aceptado e ignorado, ADR-006), una sola respuesta leída en una misma foto, solo para quien tiene una jornada `ABIERTA` en el dispositivo del token. Incluye productos y presentaciones activos (con `categoria_id`, `marca_id`, alícuota), clientes no inactivos con cartera ("vacía = todos"), saldo y crédito resuelto, versiones de lista elegibles con `unidades_referencia`, reglas de descuento activas con alcances, stock de la ubicación tomada, permisos, tope y contexto de venta, autorizadores con la derivación de su PIN, medios, motivos y alícuotas activos, configuración de la organización y de la nota (nombre, CUIT, domicilio, teléfono, mostrar saldo), numeración del dispositivo y jornada. Sin costos (D7).
- **Base local** (D10, D11): esquema Dexie v2 con las tablas maestras de `02` §13.2; el bootstrap las reemplaza en una sola transacción y no toca `meta.dispositivo_id` ni las tablas de operaciones (que llegan con el 22a). Se ejecuta tras abrir la jornada, al iniciar sesión con jornada abierta y con "Actualizar datos".
- **Sesión local** (D12 a D16): login propio de `/ruta`; PIN de desbloqueo definido con conexión, derivado con PBKDF2 (Web Crypto) y guardado solo en el dispositivo; se pide solo al abrir la app (D14-B; sin regla de segundo plano, riesgo aceptado); superados `intentos_pin_max` fallos la sesión local se bloquea y exige login (SEG-04).
- **PWA** (D17, D18): vite-plugin-pwa con precache del shell de `/ruta`, de la ayuda y del fragmento de pdfmake, sin cachear la API; aviso de versión nueva sin recarga automática; almacenamiento persistente con advertencia si se niega.
- **Pantallas de `/ruta`** (D19, D21): inicio con estado de conexión y de los datos, abrir jornada, clientes (cartera primero, búsqueda en todos), productos con precio, stock del vehículo, "Mi cuenta" (Mi contraseña, cambiar PIN, cerrar sesión) y ayuda `/ruta/ayuda/:tema`, todas leyendo de Dexie.
- **ADR-062** (*Propuesto*) y `propuesta-docs.md`.

## Decisiones

`design.md` D0 a D21, **APROBADAS el 2026-10-30** con la opción A, salvo D14 = B (PIN solo al abrir la app); aún no están en `docs/` (se aplican al archivar). De negocio (decide el usuario): D2, D4, D5, D6, D7, D8, D11, D13, D14, D15, D16, D19. **D20** (cómo probar en el teléfono real con HTTPS): prueba manual en un Android real; los vendedores usan Android hoy y la aplicación debe seguir siendo compatible con iPhone/Safari (`04` §11). Gobernanza **ALTA** en la sesión local y las derivaciones de PIN; **MEDIA** en el resto.

## No incluye

Venta, cobranza o anulación desde `/ruta` y sin conexión, cola y verificación local del PIN de supervisor (22a, 22c, 23); motor de sincronización y Web Locks (22b); bootstrap incremental (etapa 4); cifrado de IndexedDB (ADR-011, etapa 4); "Mi PIN" de autorización en `/ruta`; costos en el teléfono.

## Reglas e invariantes

- **SYN-10, SYN-11, RUT-03, SEG-01, SEG-03, SEG-04, ADR-006, ADR-011, ADR-027, ADR-028, ADR-051, ADR-059, ADR-060, `01` §19 (cartera).**
- **INV-21/INV-02:** el bootstrap filtra todo por la organización y el usuario del token; prueba que lo cita. **INV-03:** importes y porcentajes como string. **INV-04:** stock en enteros. **INV-12/INV-13:** stock y saldo bajados iguales a la suma de sus movimientos. **INV-01** (local): el reemplazo de la base es todo o nada.
- No cambia ninguna regla de cálculo: **sin fixtures compartidos de cálculo**; se agrega un vector de prueba de la derivación PBKDF2 compartido entre Python y TypeScript (D8).

## Capabilities

### New Capabilities

- `sync/bootstrap`: endpoint, acceso, contenido y minimización de datos del bootstrap.
- `sync/base-local`: esquema Dexie, reemplazo atómico de los datos maestros y momentos del bootstrap.
- `identidad/sesion-local`: PIN de desbloqueo, bloqueo por intentos, cierre de sesión y cambio de usuario en el dispositivo.
- `sistema/aplicacion-instalable`: service worker, precache, actualización y almacenamiento persistente.
- `ruta/area-de-ruta`: login, inicio, apertura de jornada y pantallas de consulta de `/ruta`.

### Modified Capabilities

- `sistema/ayuda-contextual`: ayuda de `/ruta` sin conexión y "Ver más" interno en la aplicación instalada.

## Impact

Backend: `modules/sync` (bootstrap), lecturas nuevas en `service.py` de `catalogo`, `clientes`, `precios`, `descuentos`, `stock`, `cuentas_corrientes`, `identidad`, `configuracion`, `ventas`; sin migración. Frontend: `lib/dispositivo/db.ts` (v2), `sync/`, `areas/ruta/`, `ayuda/`, `vite.config.ts`; dependencia nueva `vite-plugin-pwa` (versión exacta; requiere reconstruir la imagen de Docker).
