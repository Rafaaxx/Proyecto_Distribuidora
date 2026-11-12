# Tareas — 23-cobranza-offline

> Modo TDD estricto: en cada tarea de los grupos 1 a 12, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Ninguna aserción trivial. Las tareas reflejan las opciones **recomendadas** (A); si 0.1 cambia alguna, se ajustan antes del apply.
>
> **Dónde va el código:** backend **solo pruebas** (`tests/unit`, `tests/integration`) y el fixture; **sin migración, sin permisos nuevos, sin código de producción en el servidor** (si una prueba lo exigiera, detenerse y consultar, D2). Frontend en `lib/dispositivo/db.ts` (**Dexie v5**), `sync/` (`registrarCobranzaLocal.ts` nuevo, `sobre.ts`, `aplicarResultados.ts`, `ventasPendientes.ts`), `domain/ruta/` (reglas de la cobranza nuevas, `disponiblesLocales.ts`, `textosDeSincronizacion.ts`, `avisoDeJornada.ts`), `areas/ruta/` (cobro, cobranza guardada, cobranzas de hoy, inicio, ficha, «Sincronización», sesión, editor de medios extraído de `PasoCobro.tsx`), `ayuda/textos.ts`. Fixtures de contrato en `shared/fixtures/sync/`.
>
> **Lotes de apply (`design.md` D0 = A):** Lote 1 = grupos 1 a 6 (contrato y núcleo). Lote 2 = grupos 7 a 12 (pantallas, corte, pendientes, textos y ayuda). Lote 3 = grupos 13 a 18 (punta a punta, ADR, docs, cobertura, suites y prueba manual). Un subagente nuevo por lote, en secuencia. **No se frena entre lotes**: el resumen de cada lote informa las comprobaciones automáticas y el usuario revisa con todo el change implementado.
>
> **Pruebas:** en cada lote solo las afectadas; las suites completas una sola vez, en 16.1. `pytest` por carpeta con `backend/.venv`; frontend con Docker detenido. Base local con `fake-indexeddb`; servidor simulado con `fetch` de prueba. **Sin fixtures de cálculo nuevos** (no cambia ninguna regla de cálculo). Skills del proyecto (`.agents/skills/`): ninguna aplica de forma directa (sin modelos, migraciones ni OpenAPI nuevos).

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones: el usuario revisa D0 a D12 de `design.md` (ninguna CRÍTICA; ALTAS: D2, D4, D6; de negocio: D0, D3, D4, D6, D7, D9). Se anota el resultado en `design.md` y en ADR-067, y se ajustan proposal, specs y tareas si alguna opción cambia.
- [x] 0.2 Textos: el usuario aprueba, **sin ejemplos**, las claves nuevas `ruta.cobrar`, `ruta.medios`, `ruta.saldoDespuesDelCobro` y `ruta.cobranzaRechazada` y las revisadas `ruta.creditoSinSenal`, `ruta.sincronizar`, `ruta.observacionesYRechazos`, `ruta.jornadaNoAbierta` y `ruta.versionMinima` (D12); los textos de rechazos y observaciones de la cobranza (D11); «Cobrar», «Confirmar cobranza», «¿Registrar la cobranza de {importe} a {cliente}?», «El cliente queda con {importe} a favor.», «¿Descartar la cobranza?», «Cobranza guardada», «Cobranzas de hoy», «Cobranza a {cliente}», «N ventas, M anulaciones y K cobranzas sin enviar» (D4, D8, D10) y «Lo que ya vendiste y cobraste se sigue enviando.» (D7).

## 1. Contrato del sobre de cobranza (Lote 1)

- [x] 1.1 Red de seguridad: `tests/integration/test_cobranzas_offline.py` y las del lote. RED en `backend/tests/unit/test_fixture_cobranza_registrar_offline.py` y su par de Vitest `frontend/tests/unit/sync/sobreDeCobranza.test.ts` (spec `sync/lote-de-comandos`, «La cobranza del teléfono se acepta por el lote con el contrato fijado»; D2; cita SYN-01, COB-01, INV-03): `shared/fixtures/sync/cobranza-registrar-offline.json` (sobre `OFFLINE` con un medio, con dos medios y referencia, con observación) lo acepta el esquema del lote y `armarSobreDeCobranza` lo arma igual. GREEN creando el fixture y la función en `sync/sobre.ts`.

## 2. Caracterización del servidor (Lote 1)

- [x] 2.1 RED en `backend/tests/integration/test_cobranza_offline_desde_telefono.py` (spec `sync/lote-de-comandos`, sus seis escenarios; D2; cita COB-01 a COB-03, SYN-02, SYN-03, SYN-05, SYN-06, **INV-08**, **INV-06**, **INV-17**, INV-21): con PostgreSQL real, el sobre del fixture aceptado con la jornada del sobre ($150.000 → $100.000); venta y cobranza del mismo cliente en un lote, en orden; cliente inexistente rechazado y el lote sigue; medios que no suman, `MEDIOS_NO_SUMAN_IMPORTE`; doble envío igual. **Prueba de caracterización: si exige código de producción, detenerse y consultar.**
- [x] 2.2 RED ampliando `backend/tests/unit/test_fixture_codigos_de_sincronizacion.py` (D11; cita SYN-06, SYN-07): `rechazos_de_cobranza` y `observaciones_de_cobranza`; cada código existe en el bus, en `cobranzas` o en `configuracion/domain/medios.py` (fijar la lista recorriendo el bus y `registrar_cobranza`). GREEN ampliando `shared/fixtures/sync/codigos-de-sincronizacion.json`.

## 3. Base local v5 (Lote 1)

- [x] 3.1 Red de seguridad: suites de `lib/dispositivo` y `sync/`. RED en `frontend/tests/unit/lib/dispositivo/db.test.ts` (spec `sync/base-local`, sus tres escenarios; D5; cita INV-05, SYN-09, `02` §13.2, §13.4): una base v4 con sesión, PIN, datos, dos ventas con cobro, una anulación y la cola abre en v5 sin perder nada; los cobros viejos se leen como cobro de su venta; el bootstrap y el cierre de sesión no tocan cobranzas. GREEN: v5 en `db.ts` con `cobranzas: 'cobranza_id, venta_id, operation_id, cliente_id, jornada_id, estado_envio'`, `CobranzaLocal` con `origen`, `venta_id` nulable y los campos de la suelta; `TABLAS_MAESTRAS` sin cambios.

## 4. Reglas locales y cobranza local atómica (Lote 1)

- [x] 4.1 RED en `frontend/tests/unit/domain/ruta/cobranzaLocal.test.ts` (D3, D4; cita COB-01, COB-02, **INV-08**, INV-03, CLI-03, CC-04): función pura que valida el formulario (importe > 0 con hasta dos decimales, 1 a 20 medios activos con importe positivo, suma igual al importe, referencia exigida no vacía, observación hasta 500 recortada, consumidor final rechazado) y calcula saldo actual, resultante y si queda a favor, con `decimal.js`. GREEN en `domain/ruta/`, reutilizando la validación de medios de `armadoDeVentaLocal.ts` sin duplicarla (extraerla si hace falta).
- [x] 4.2 RED en `frontend/tests/unit/sync/registrarCobranzaLocal.test.ts` (spec `sync/cola-local`, «Registrar una cobranza local es una sola transacción», sus cuatro escenarios; D1, D5; **cita INV-01**, INV-06, SYN-01, SYN-03): con `fake-indexeddb`, una transacción escribe cobranza, `COBRANZA_CREDITO`, comando `COBRANZA_REGISTRAR` `OFFLINE` con la siguiente secuencia y la última secuencia; falla inyectada no deja nada; reconfirmar devuelve la existente; detrás de una venta sin enviar. GREEN en `sync/registrarCobranzaLocal.ts`, con el disparo de la sincronización como la venta.

## 5. Conciliación de la cobranza (Lote 1)

- [x] 5.1 RED en `frontend/tests/unit/domain/ruta/disponiblesLocales.test.ts` (spec `sync/cola-local`, «La cobranza local cuenta en el saldo local», sus siete escenarios; D6; cita CRE-08, COB-04, SYN-06, SYN-11, INV-06): $150.000 → $100.000 y disponible $100.000; incluida en el bootstrap no cuenta dos veces; pendiente después de actualizar cuenta; rechazada no cuenta; el cobro de una venta rechazada sigue contando; saldo a favor −$10.000; doble sincronización igual. GREEN en `disponiblesLocales.ts` (la operación conciliable sabe si es una cobranza independiente) y en `areas/ruta/datos/disponibles.ts`.

## 6. Resultados de la cobranza (Lote 1)

- [x] 6.1 RED en `frontend/tests/unit/sync/aplicarResultados.test.ts` (spec `sync/motor-de-sincronizacion`, «El resultado de una cobranza se escribe en el teléfono», sus seis escenarios; D5, D7; **cita INV-01**, INV-06, SYN-04, SYN-09, RUT-09): el resultado cambia `cobranzas.estado_envio` y la cola, no las ventas; observaciones guardadas; rechazo visible; `JORNADA_LIBERADA` marca la jornada; falla inyectada no deja nada; reenvío igual. GREEN en `sync/aplicarResultados.ts`.

## 7. Pantalla de cobro (Lote 2)

- [x] 7.1 Red de seguridad: suites de inicio, ficha, Vender (`PasoCobro`) y guarda del carrito. RED en `frontend/tests/unit/areas/ruta/CobrarScreen.test.tsx` (spec `ruta/area-de-ruta`, «Se cobra a un cliente desde el teléfono», sus nueve escenarios; D3, D4, D8; cita COB-01, COB-02, INV-08, CLI-03, SYN-10, SEG-06, CC-04): «Cobrar» con permiso en inicio y ficha; selector sin consumidor final; validaciones; confirmación; saldo a favor; guarda «¿Descartar la cobranza?» y versión nueva en espera. GREEN: rutas `/ruta/cobrar` y `/ruta/cobranzas/:id`, editor de medios extraído de `PasoCobro.tsx` (la venta sigue igual: su suite en verde sin cambiar aserciones) y la guarda generalizada.

## 8. Cobranza guardada y Cobranzas de hoy (Lote 2)

- [x] 8.1 RED en `CobranzaGuardadaScreen.test.tsx` y `CobranzasDeHoyScreen.test.tsx` (spec `ruta/area-de-ruta`, «Las cobranzas se ven en las pantallas de ruta», escenarios «Cobranzas de hoy», «Cobranza con observaciones», «Código desconocido» y «Doble sincronización»; D8, D9; cita SYN-07, SYN-09, INV-06): lista de la jornada; detalle con medios, estado y explicación; sin comprobante. GREEN.

## 9. Textos de sincronización de la cobranza (Lote 2)

- [x] 9.1 RED en `frontend/tests/unit/domain/ruta/textosDeSincronizacion.test.ts` (D11; cita SYN-06, SYN-07): cada rechazo y observación de la cobranza del fixture tiene el texto aprobado en 0.2, elegido por tipo de operación, con el aviso del rechazo; código desconocido, texto general de la cobranza. GREEN.

## 10. Sincronización y pendientes (Lote 2)

- [x] 10.1 RED en las pruebas de «Sincronización», del inicio y de los avisos de cierre de sesión y de pendientes de otro (spec `ruta/area-de-ruta`, escenarios «Cobranza rechazada en Sincronización», «Pendientes» y «Solo cobranzas pendientes»; D10; cita SYN-06, SYN-09, INV-05): «Cobranza a {cliente}» con su texto y acceso al detalle; «2 ventas, 1 anulación y 1 cobranza sin enviar»; «Hay 3 cobranzas sin enviar de {vendedor}.». GREEN en `areas/ruta/datos/sincronizacion.ts`, `SincronizacionScreen.tsx`, `presentacion.ts` y `sync/ventasPendientes.ts`.

## 11. Corte de «Cobrar» (Lote 2)

- [x] 11.1 RED en las pruebas del inicio, la ficha y la pantalla de cobro (spec `ruta/area-de-ruta`, «Cobrar se corta con la jornada no abierta y por debajo de la versión mínima», sus cuatro escenarios; D7; cita RUT-09, `02` §6.6, INV-01): deshabilitado con jornada no abierta y con versión vieja; «Confirmar cobranza» no confirma y el formulario sigue; vale tras recargar; sin dato, normal; aviso «Lo que ya vendiste y cobraste se sigue enviando.». GREEN en `InicioScreen.tsx`, `ClienteFichaScreen.tsx`, la pantalla de cobro y `domain/ruta/avisoDeJornada.ts`.

## 12. Ayuda (Lote 2)

- [x] 12.1 RED en la prueba de claves de ayuda (spec `sistema/ayuda-contextual`, «Las pantallas de ruta explican la cobranza», sus cuatro escenarios; D12; ADR-051): las cuatro claves nuevas existen, las cinco revisadas tienen los textos aprobados en 0.2, sin ejemplos, y todo ID citado existe (ADR-067 ya existe como *Propuesto*). GREEN en `ayuda/textos.ts` y en las pantallas.

## 13. Prueba de punta a punta del cliente (Lote 3)

- [x] 13.1 RED en `frontend/tests/unit/areas/ruta/FlujoCobranzaSinConexion.test.tsx` (con `fake-indexeddb`, `fetch` simulado y temporizadores falsos; cita COB-04, CRE-08, INV-06, INV-08, SYN-03): bootstrap con Kiosco La Esquina debiendo $150.000 y límite $200.000 → cobranza de $50.000 sin red (saldo $100.000, disponible $100.000, «Sin enviar») → venta al mismo cliente sin red → vuelve la señal y se envían en orden → «Actualizar datos» con $100.000 más la venta y la marca → no cuenta dos veces → una segunda cobranza vuelve rechazada y deja de contar → «Sincronizar» otra vez no cambia nada. GREEN si hace falta.

## 14. ADR (Lote 3)

- [x] 14.1 Completar `docs/adr/ADR-067-cobranza-sin-conexion-en-el-telefono.md` (borrador *Propuesto* creado con la propuesta) con lo aprobado en 0.1 y las precisiones del apply.

## 15. Propuesta de docs (Lote 3)

- [x] 15.1 Crear `openspec/changes/23-cobranza-offline/propuesta-docs.md` con el texto actual y el propuesto: `01` COB-04 (la cobranza del teléfono: siempre por la cola, a quién, reglas locales), CRE-08 (la cobranza independiente rechazada deja de contar), RUT-09 («Cobrar» también se corta); `02` §6.6 («Cobrar» y la versión mínima), §13.2 (`cobranzas` en Dexie v5, cobranza independiente con estado de envío propio), §13.3 (cobranzas en «Sincronización» y en lo pendiente; el resultado de una cobranza); `04` §11 (fila del 23 terminada; deudas saldadas: ADR-052 deuda 3 y ADR-065 D2 / 22c «al 23»; deudas nuevas al 24 y al 25). **No se aplica a `docs/`** sin el visto bueno del usuario.

## 16. Cobertura y suites completas (Lote 3)

- [x] 16.1 Cada escenario de las seis specs delta tiene al menos una prueba que lo nombra (`frontend/tests/unit/cobertura/escenariosDe23.test.ts`, como en el 22d, con los del servidor por archivo); INV-01, INV-05, INV-06, INV-08, INV-17 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas (backend unit, integration, concurrency, properties y fixtures compartidos; frontend Vitest), `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación. `04` §2.1 punto 4 (migración): no aplica.

## 17. Prueba de integración del servidor (Lote 3)

- [x] 17.1 Repasar que las pruebas de 2.1 corren juntas con la suite completa (orden y limpieza de datos), que las de cobranzas del change 17 siguen igual (sin cambiar aserciones) y que los fixtures `venta-confirmar-offline.json`, `venta-anular-offline.json` y `cobranza-registrar-offline.json` se aceptan.

## 18. Prueba manual (Lote 3)

- [x] 18.1 Probar a mano el flujo principal y dar al usuario el paso a paso en el chat (sin archivo aparte), con los usuarios de desarrollo existentes (`admin`, `vendedor`), en el build con el perfil `lan` en https://localhost (la recarga sin señal no funciona en 5173), con el modo de dispositivo y «sin conexión»: `vendedor` abre la jornada en `/ruta` y anota saldo y crédito de un cliente; sin red cobra con dos medios (uno con referencia) y ve «Cobranza guardada», «Sin enviar», el saldo y el crédito actualizados en la ficha y la cobranza en «Cobranzas de hoy»; prueba que no confirma con medios que no suman ni sin la referencia exigida, y el aviso de saldo a favor; el consumidor final no ofrece «Cobrar»; recarga sin red y todo sigue; vuelve la red y se envía; `admin` ve la cobranza en `/admin/cobranzas` con la jornada; «Actualizar datos» no cuenta dos veces; con un medio dado de baja por `admin` después del bootstrap, una cobranza vuelve «Con observaciones» con su texto; `admin` libera la jornada y el teléfono corta «Cobrar» con el aviso. No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5.
