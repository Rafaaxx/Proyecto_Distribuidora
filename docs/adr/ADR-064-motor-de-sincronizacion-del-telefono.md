# ADR-064 — Motor de sincronización del teléfono, límites entre pestañas y guarda completa del carrito

| Campo | Valor |
| --- | --- |
| Estado | Vigente (2026-11-01, archivo del change 22b) |
| Fecha | 2026-11-01 |
| Referenciado en | `openspec/changes/22b-motor-sincronizacion/design.md` D0 a D13 y `specs/sync/motor-de-sincronizacion`, `specs/sync/cola-local`, `specs/identidad/pin-de-autorizacion`, `specs/identidad/sesion-local`, `specs/sistema/aplicacion-instalable`, `specs/ruta/area-de-ruta`, `specs/sistema/ayuda-contextual`; `01-dominio.md` SYN-02, SYN-03, SYN-04, SYN-06, SYN-09, SEG-05, VTA-07, RUT-05, RUT-09, INV-01, INV-06; `02-arquitectura.md` §6.4, §6.6, §12.1, §12.3, §12.4, §13.3, §13.4, §13.5; ADR-017, ADR-028, ADR-051, ADR-055, ADR-062, ADR-063 |

**Change 22b. Gobernanza CRÍTICA en la renovación de sesión entre pestañas (D11); ALTA en el límite local del PIN de supervisor entre pestañas (D9); MEDIA en el resto. Decisiones aprobadas por el usuario el 2026-11-01 (D11 de forma explícita); los textos de ayuda y de pantalla se aprobaron el 2026-11-01 (ver `design.md` D13 y 0.2). Estado Vigente desde el archivo del change (2026-11-01).**

## Contexto

`02` §13.3 exige un motor en el hilo principal, con una sola sincronización a la vez garantizada con Web Locks, lotes en orden (§6.4), resultados aplicados a la base local, reintentos con espera exponencial y el estado siempre visible; §6.6, la versión mínima de la aplicación. ADR-063 dejó al 22b enviar la cola por secuencia y solo la del usuario autenticado, escribir `estado_envio`, la versión mínima, el botón «Sincronizar», serializar los intentos del PIN de supervisor entre pestañas y la guarda del carrito para los enlaces y el botón atrás. `docs/` no resuelve qué parte de la cola se envía, cómo se comporta el bloqueo sin Web Locks, cómo se escriben los resultados, qué pasa con los movimientos locales de una venta aceptada, qué es transitorio y con qué espera, el formato de la versión, dónde se ve el estado, el detalle del límite del PIN entre pestañas, cómo se cubre toda navegación con el carrito abierto ni la renovación simultánea del refresh token desde dos pestañas.

## Decisión (aprobada el 2026-11-01: opciones A de `design.md`, salvo D6 = B)

1. **Lotes (D0).** Un change en cinco lotes.
2. **Cola propia (D1).** Pendientes del usuario y del dispositivo de la sesión, de cualquier jornada, por secuencia, de a 50.
3. **Bloqueo único (D2).** Web Lock `ifAvailable`; otra pestaña no espera; una vuelta más si llega un disparador durante el envío; sin Web Locks, candado de pestaña e idempotencia del servidor.
4. **Resultados (D3).** Una transacción Dexie por lote; `cola.estado` y `estado_envio` por `operation_id`; nada se borra; un rechazado no se reenvía solo; sin Dexie v4.
5. **Movimientos locales (D4).** El 22b no los toca: una venta aceptada sigue contando hasta la conciliación del 22c (doble conteo conservador tras un bootstrap posterior, aceptado por el usuario).
6. **Errores (D5).** Transitorios con espera 5-10-20-40-80-120 s (±20 %); sesión vencida sin reintento; errores del pedido sin espera.
7. **Disparadores (D6 = B).** Los de `02` §13.3 y, además, la vuelta de la aplicación a primer plano (`visibilitychange` a `visible`), todos solo con la sesión desbloqueada. Todos pasan por el bloqueo único (D2): varios disparadores durante un envío dan a lo sumo una vuelta más. La vuelta a primer plano, como «Sincronizar» y `online`, vuelve la espera exponencial a cero y envía en el momento.
8. **Versión mínima (D7).** `APP_VERSION` en la compilación, formato `X.Y.Z`; la última mínima conocida en `meta`; por debajo, se envía la cola y no se confirman ventas nuevas; sin formato o sin mínima, no restringe.
9. **Estado (D8).** Cabecera en toda pantalla, inicio con «Sincronizar» y pantalla «Sincronización».
10. **PIN entre pestañas (D9).** Web Lock por par alrededor de toda la verificación, con la derivación dentro, y conteo atómico en Dexie con nueva lectura; sin Web Locks, la transacción atómica y la nueva lectura del bloqueo antes de responder. **Límite inherente:** la sal y la derivación viven en el teléfono, así que la fuerza bruta fuera de la aplicación con acceso técnico sigue siendo el riesgo aceptado de `02` §12.4 (y de ADR-063 D10); esta decisión cierra el contador de la interfaz y no cambia ese riesgo.
11. **Guarda del carrito (D10).** `createBrowserRouter` con una ruta comodín sobre las rutas actuales, `useBlocker` en Vender y `beforeunload` con el carrito ocupado.
12. **Renovación entre pestañas (D11).** Web Lock alrededor de la renovación del refresh token; sin cambios en el servidor. Aprobada de forma explícita (gobernanza CRÍTICA).
13. **Criterio 8 (D12).** Prueba de concurrencia del servidor con commits reales y pruebas del cliente, todas citando INV-06.
14. **Ayuda (D13).** Cuatro claves nuevas y `ruta.ventaSinEnviar` revisada, sin ejemplos.

## Precisiones del apply

Lo que quedó fijado al implementar, sin cambiar lo aprobado:

- **Nombres de los candados.** `distribuidora:sync` (sincronización, `ifAvailable`), `distribuidora:renovacion` (renovación del refresh token, exclusivo y con espera) y `distribuidora:pin:{usuario}:{autorizador}` (un candado por par para el PIN de supervisor). Envoltura en `src/lib/locks.ts`; sin `navigator.locks` cae a un candado dentro de la pestaña con la misma interfaz.
- **Renovación (D11).** La cookie del refresh token se lee dentro del candado, al enviar `/auth/refresh`: la pestaña que espera manda la que dejó la anterior, así que el refresh token rotado no se presenta dos veces y la familia no se revoca. El reuso real de un refresh ya rotado sigue revocando la familia (SEG-03). Sin cambios en el servidor.
- **PIN entre pestañas (D9).** La verificación completa (lectura del estado, derivación y escritura del fallo) corre bajo el candado del par y dentro de una transacción de lectura y escritura de Dexie; el bloqueo se vuelve a leer antes de responder, de modo que ninguna derivación de más pasa como correcta después del bloqueo.
- **Guarda del carrito (D10).** `createBrowserRouter` con una ruta comodín sobre las rutas actuales (`app/App.tsx`); `useBlocker` y `beforeunload` viven en `VenderScreen`, y la intercepción manual de enlaces que tenía `RutaLayout` se quitó. Una referencia `salidaLibre` (`useRef`) se enciende justo antes de las salidas propias (confirmar la venta, descartar a pedido) para que el bloqueador no pregunte "¿Descartar la venta?" por una navegación que la propia pantalla provoca; confirmar no pregunta.
- **Versión mínima (D7).** La compilación define `APP_VERSION` (por omisión `dev`, que no restringe nada); en `docker-compose.yml` el servicio de la compilación para el perfil `lan` la toma de la variable de entorno `APP_VERSION`. La última mínima conocida se guarda en `meta` y se consulta con `GET /api/v1/version`.
- **Pruebas del criterio 8 (D12).** Servidor: `backend/tests/concurrency/test_inv06_doble_sincronizacion_venta.py`, dos hilos con commits reales contra PostgreSQL; es una prueba de caracterización (el servidor ya garantizaba INV-06 por la clave única del comando; no se tocó código de producción). Cliente: `FlujoSincronizacion.test.tsx` de punta a punta y `dobleSincronizacion.test.ts`.
- **Trazabilidad.** `frontend/tests/unit/cobertura/escenariosDe22b.test.ts` exige que cada escenario de las siete specs delta tenga su prueba.

## Consecuencias

- Las ventas de `/ruta` llegan al servidor sin intervención del vendedor; la rendición (24) puede exigir la cola vacía (RUT-05).
- Hasta el 22c, después de sincronizar y actualizar los datos, el saldo y el stock locales cuentan dos veces las ventas aceptadas (D4).
- `02` §13.4 sigue: el bootstrap no toca las tablas de operaciones.
- La compilación de producción debe definir `APP_VERSION` con formato `X.Y.Z` para que la versión mínima tenga efecto.
- `02` §12.1, §12.4, §13.3 y §13.5 se precisan al archivar; en §13.3 se agrega el disparador de primer plano, que hoy no figura (D6 = B).

## Alternativas consideradas

Las opciones B y C de cada decisión de `design.md`, con sus consecuencias.

## Deudas nominadas

- **Al 22c:** conciliar los movimientos locales de las ventas aceptadas con un bootstrap posterior (D4); mostrar el detalle de las observaciones y traducir los códigos de rechazo en la pantalla de conflictos (D8).
