# Change 22b-motor-sincronizacion

## Qué resuelve este change

Las ventas que el teléfono confirmó (22a) llegan al servidor: el motor envía la cola del usuario en orden, de a una sincronización por vez aunque haya varias pestañas, reintenta con espera exponencial, escribe el resultado de cada venta y muestra el estado. Sincronizar dos veces no duplica nada (`00` §9 criterio 8).

## Why

`04` §11 (fila 22b) y deudas del 22a (ADR-063): enviar la cola por secuencia y solo la del usuario autenticado (`02` §6.4), escribir `estado_envio`, la versión mínima de la aplicación (`02` §6.6), el botón «Sincronizar», serializar los intentos del PIN de supervisor entre pestañas y la guarda del carrito para los enlaces y el botón atrás (`BrowserRouter` no admite `useBlocker`). Hoy las ventas de `/ruta` quedan «Sin enviar» para siempre.

## What Changes

- **Motor de sincronización** (`design.md` D1 a D6): elige los comandos pendientes del usuario y del dispositivo, los manda en lotes de hasta 50 por `POST /api/v1/sync/comandos`, aplica cada resultado en una transacción Dexie y reintenta los errores transitorios con espera exponencial. Un solo motor a la vez con Web Locks.
- **Disparadores** (D6 = B): al abrir la aplicación (sesión desbloqueada), al volver la aplicación a primer plano (`visibilitychange`, solo con la sesión desbloqueada), en el evento `online`, después de cada venta, cada 2 minutos y con «Sincronizar». Todos pasan por el mismo bloqueo único (D2). El de primer plano no figura en `02` §13.3: se propone agregarlo (`propuesta-docs.md`, tarea 17.1).
- **Resultados** (D3, D4): `estado_envio` pasa a `ACEPTADA`, `CON_OBSERVACIONES` o `RECHAZADA`; nada se borra (SYN-09); un rechazado no se reenvía solo.
- **Versión mínima** (D7): el teléfono consulta `GET /api/v1/version`; por debajo de la mínima sigue enviando la cola pero no confirma ventas nuevas.
- **Estado visible** (D8): indicador en la cabecera de `/ruta`, bloque en el inicio con «Sincronizar» y pantalla «Sincronización» con las ventas observadas o rechazadas.
- **PIN de supervisor entre pestañas** (D9): Web Lock por par (usuario, supervisor) y conteo atómico en Dexie; prueba que reproduce la pérdida de fallos.
- **Guarda completa del carrito** (D10): enrutador de datos (`createBrowserRouter`) y `useBlocker`.
- **Renovación de sesión entre pestañas** (D11, **CRÍTICA**: autenticación): una sola renovación a la vez con Web Locks, para que dos pestañas no reusen el mismo refresh token y revoquen la familia.
- **Pruebas de criterio 8** (D12) y **ayudas «(?)»** (D13).
- **ADR-064** (*Propuesto*).

## Decisiones

`design.md` D0 a D13, **aprobadas el 2026-11-01**: todas con la opción recomendada A salvo **D6 = B** (disparador al volver a primer plano). D11 (gobernanza **CRÍTICA**, renovación del refresh token) aprobada de forma explícita; D4 aprobada aceptando el doble conteo conservador hasta el 22c. De negocio (decidió el usuario): D1, D4, D7, D8. Gobernanza **ALTA** en D9 (PIN), **MEDIA** en el resto. Los textos de ayuda y de pantalla siguen pendientes de aprobación (tarea 0.2).

## No incluye

Conciliar los movimientos locales con un bootstrap posterior a una sincronización aceptada, la pantalla de conflictos con el detalle de las observaciones, la anulación sin conexión y las métricas de lote (22c); la cobranza independiente sin conexión (23); la bandeja de observaciones (25). Sin código de servidor nuevo: el lote, la idempotencia y la versión mínima ya existen (changes 04, 18b).

## Reglas e invariantes

- **SYN-02, SYN-03, SYN-04, SYN-06, SYN-09, SYN-10, SEG-05, VTA-07, RUT-05; `02` §6.4, §6.6, §12.1, §12.4, §13.3 (más el disparador de primer plano, D6 = B), §13.5; ADR-055, ADR-062, ADR-063.**
- **INV-06** (doble sincronización no duplica): prueba de concurrencia con commits reales de dos lotes simultáneos con la misma venta (una venta, stock, saldo, costo y utilidad correctos) y pruebas del cliente (dos pestañas, respuesta perdida y reenvío).
- **INV-01** (local): los resultados de un lote se aplican todos o ninguno.
- **INV-17**: el motor no reinterpreta resultados; una venta sin conexión rechazada solo puede serlo por SYN-06.
- **Sin cambios en reglas de cálculo:** no se agregan ni modifican fixtures de cálculo; se reutiliza el fixture de contrato `shared/fixtures/sync/venta-confirmar-offline.json`.

## Capabilities

### New Capabilities

- `sync/motor-de-sincronizacion`: selección de la cola propia, lotes, bloqueo único, resultados, reintentos, disparadores y versión mínima.

### Modified Capabilities

- `sync/cola-local`: el estado de envío cambia con el resultado; el saldo y el stock locales siguen contando lo enviado hasta el 22c.
- `identidad/pin-de-autorizacion`: el límite local vale entre pestañas.
- `identidad/sesion-local`: una sola renovación de sesión a la vez en el dispositivo.
- `sistema/aplicacion-instalable`: la guarda del carrito cubre toda navegación.
- `ruta/area-de-ruta`: estado de sincronización, «Sincronizar», pantalla «Sincronización» y bloqueo por versión mínima.
- `sistema/ayuda-contextual`: ayudas de la sincronización.

## Impact

Frontend: `sync/` (motor nuevo), `lib/dispositivo/db.ts` (tipos de la cola, `meta`), `lib/sesionLocal/pinSupervisor.ts`, `lib/api/httpClient.ts` (renovación), `app/App.tsx` (enrutador de datos), `areas/ruta/` (cabecera, inicio, pantalla nueva, Vender), `ayuda/textos.ts`, `vite.config.ts` (versión de la compilación); pruebas de `/ruta` que montan Vender pasan a `createMemoryRouter`. Backend: solo una prueba de concurrencia. Sin migración ni dependencias nuevas.
