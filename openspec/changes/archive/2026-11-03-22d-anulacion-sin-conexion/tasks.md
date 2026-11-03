# Tareas — 22d-anulacion-sin-conexion

> Modo TDD estricto: en cada tarea de los grupos 1 a 15, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Ninguna aserción trivial. Las tareas reflejan las opciones **recomendadas** (A); si 0.1 cambia alguna, se ajustan antes del apply.
>
> **Dónde va el código:** backend en `app/modules/ventas/` (`commands.py`, `service.py`, `domain/anulacion.py`, `domain/errores.py`) y `app/modules/stock/service.py` (reingreso aceptado sobre ubicación tomada sin conexión); pruebas en `tests/unit`, `tests/integration`, `tests/concurrency`; **sin migración** ni permisos nuevos. Frontend en `lib/dispositivo/db.ts` (**Dexie v4**), `sync/` (`anularVentaLocal.ts` nuevo, `aplicarResultados.ts`, `sincronizar.ts`, `actualizarDatos.ts`, `aplicarBootstrap.ts`, estado de la jornada nuevo, `ventasPendientes.ts`), `domain/ruta/` (movimientos inversos, `disponiblesLocales.ts`, `textosDeSincronizacion.ts`), `domain/ventas/notaDesdeLocal.ts`, `areas/ruta/` (detalle, pantalla de anulación nueva, «Ventas de hoy», «Sincronización», inicio, ficha, Vender, sesión), `ayuda/textos.ts` y `api/schema.gen.ts` regenerado. Fixtures de contrato en `shared/fixtures/sync/`.
>
> **Lotes de apply (`design.md` D0 = A):** Lote 1 = grupos 1 a 4 (servidor). Lote 2 = grupos 5 a 9 (núcleo del teléfono). Lote 3 = grupos 10 a 14 (pantallas y ayuda). Lote 4 = grupos 15 a 21 (punta a punta, ADR, docs, spec restituida, cobertura, suites y prueba manual). Un subagente nuevo por lote, en secuencia. **No se frena entre lotes**: el resumen de cada lote informa las comprobaciones automáticas y el usuario revisa con todo el change implementado.
>
> **Pruebas:** en cada lote solo las afectadas; las suites completas una sola vez, en 19.1. `pytest` por carpeta con `backend/.venv`; frontend con Docker detenido. Base local con `fake-indexeddb`; servidor simulado con `fetch` de prueba. **Sin fixtures de cálculo nuevos** (no cambia ninguna regla de cálculo).

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones (aprobadas D0 a D13 en A el 2026-11-03, incl. D2; la prueba manual usa `sup01`; Vendedor sin `ANULAR_VENTA` por defecto): el usuario revisa D0 a D13 de `design.md` (**CRÍTICA: D2**; ALTAS: D1, D3, D7; de negocio: D0, D2, D5, D7, D9). Se anota el resultado en `design.md` y en ADR-066, y se ajustan proposal, specs y tareas si alguna opción cambia (con D0 = B se separan los grupos 9, 13 y la parte de jornada de 14 a un change 22e).
- [x] 0.2 Textos (aprobados sin ejemplos el 2026-11-03): el usuario aprueba, **sin ejemplos**, las claves nuevas `ruta.anularVenta`, `ruta.anulacionRechazada` y `ruta.jornadaNoAbierta` y las revisadas `ruta.stockDelVehiculo`, `ruta.creditoSinSenal`, `ruta.sincronizar` y `ruta.observacionesYRechazos` (D12); los textos de los rechazos y observaciones de la anulación (D11); los avisos de la jornada no abierta (D9); y «Anular venta», «Anulada», «Anulación de {número}», «¿Anular la venta {número}?» y «N ventas y M anulaciones sin enviar» (D10).

## 1. VENTA_ANULAR sin conexión: contrato y jornada en curso (Lote 1)

- [x] 1.1 Red de seguridad: suites de anulación de venta (`tests/unit`, `tests/integration`, `tests/concurrency`) y del lote. RED en `backend/tests/integration/test_venta_anular_offline.py` (spec `ventas/anulacion-de-venta`, «Una venta de la jornada en curso se anula sin conexión», sus seis escenarios, y spec `sync/lote-de-comandos`, «VENTA_ANULAR se acepta por el lote sin conexión», sus seis escenarios; D1, D4; cita VTA-24, SYN-03, SYN-06, SYN-10, INV-06, INV-19, INV-21): por el lote con PostgreSQL real, anulación aceptada; venta y anulación en el mismo lote; venta de otra jornada `JORNADA_AJENA`; venta rechazada antes y de otra organización `VENTA_INEXISTENTE`; sin jornada y jornada ajena del sobre; un rechazo no corta el lote; doble envío; por REST sigue `ONLINE`. GREEN: `admite_offline=True` y `OperacionObservable("VENTA", "venta_id")` en el catálogo; error `VentaInexistenteError` (`VENTA_INEXISTENTE`) en `ventas/domain/errores.py`; regla de la jornada en curso en el dominio (función pura con prueba unitaria) y modo en `anular_venta`; el permiso sin conexión no rechaza en el handler (lo anota el bus).

## 2. Reglas sin conexión, jornada y efectos (Lote 1)

- [x] 2.1 RED en `backend/tests/integration/test_venta_anular_offline_reglas.py` (spec `ventas/anulacion-de-venta`, «Qué rechaza y qué acepta la anulación sin conexión», sus nueve escenarios; D2; cita VTA-20, VTA-22, STK-09, SYN-07, RUT-09, SYN-10, AUD-01, INV-06): ya anulada `VENTA_YA_ANULADA`; motivo dado de baja aceptado sin observación; motivo de otro ámbito `MOTIVO_INVALIDO`; `DEVOLUCION_INVALIDA`; `PERMISO_REVOCADO` y `JORNADA_LIBERADA` sobre la venta; camioneta tomada por otro al sincronizar con `UBICACION_TOMADA_AL_SINCRONIZAR`, reingreso sin jornada y la constancia en la auditoría; ubicación inactiva `UBICACION_INACTIVA`; reenvío con la misma observación. GREEN: validación del motivo sin conexión (activo no exigido, ámbito sí), reingreso `ANULACION_VENTA` aceptado sobre ubicación tomada sin conexión en `stock/service.py` (parámetro análogo a `venta_sin_conexion`, con prueba unitaria propia) y observaciones del handler.
- [x] 2.2 RED en `backend/tests/integration/test_venta_anular_offline_efectos.py` (spec `ventas/anulacion-de-venta`, «La anulación sin conexión lleva la jornada del sobre», escenarios 1 a 3; D3; **cita INV-19**, INV-01, INV-12, INV-13, VTA-22, COB-05, RUT-07): con la jornada abierta, anulación y reingreso con J1; con devolución, stock y saldo exactamente como antes de la venta; sin devolución, difiere solo en lo cobrado; con la jornada liberada, `venta_anulacion.jornada_id` es la del sobre. GREEN en `ventas/service.py` sin cambiar el orden de bloqueo (ADR-058 D10).

## 3. Concurrencia (Lote 1)

- [x] 3.1 RED en `backend/tests/concurrency/test_venta_anular_offline_concurrencia.py` (escenario «Anulación sin conexión contra una anulación con conexión»; cita INV-06, INV-12, INV-13, VTA-20): con commits reales, la anulación `OFFLINE` por el lote y la `ONLINE` por REST de la misma venta: una se acepta y la otra `VENTA_YA_ANULADA`; un solo reingreso y una sola acreditación; también el doble envío simultáneo del mismo `operation_id`. GREEN si hace falta (prueba de caracterización: **si hubiera que cambiar el orden de bloqueo, detenerse y consultar**).

## 4. Fixtures de contrato y OpenAPI (Lote 1)

- [x] 4.1 RED en `backend/tests/unit/test_fixture_venta_anular_offline.py` y su par de Vitest (cita SYN-01, VTA-24): `shared/fixtures/sync/venta-anular-offline.json` (sobre `OFFLINE` de `VENTA_ANULAR` con y sin devolución) lo acepta el esquema del lote y lo arma igual el teléfono. GREEN creando el fixture.
- [x] 4.2 RED ampliando `backend/tests/unit/test_fixture_codigos_de_sincronizacion.py` (D11; cita SYN-06, SYN-07): el fixture de códigos separa los rechazos por tipo de operación; cada código de rechazo de la anulación existe en el bus o en `ventas` (fijar la lista recorriendo el bus y `anular_venta`), incluido `VENTA_INEXISTENTE`. GREEN ampliando `shared/fixtures/sync/codigos-de-sincronizacion.json`. Regenerar `backend/openapi.json` y `frontend/src/api/schema.gen.ts`.

## 5. Base local v4 (Lote 2)

- [x] 5.1 Red de seguridad: suites de `lib/dispositivo` y `sync/`. RED en `frontend/tests/unit/lib/dispositivo/db.test.ts` (spec `sync/base-local`, «La base local guarda las anulaciones del dispositivo», sus tres escenarios; D6; cita SYN-09, INV-05, `02` §13.2, §13.4): una base v3 con sesión, PIN, datos y dos ventas con su cola abre en v4 sin perder nada y con `anulaciones` vacía; el bootstrap no toca anulaciones; cerrar sesión no las borra. GREEN: v4 en `db.ts` con `anulaciones: 'venta_id, &operation_id, jornada_id, estado_envio'`, tipos `AnulacionLocal` y los tres tipos de movimiento nuevos; `TABLAS_MAESTRAS` sin cambios.

## 6. Anulación local atómica (Lote 2)

- [x] 6.1 RED en `frontend/tests/unit/domain/ruta/anulacionLocal.test.ts` (D6; cita VTA-21, VTA-22, INV-19, INV-03, INV-04): función pura que, con la venta local, su cobro y la devolución, deriva la anulación y sus movimientos inversos: ingreso por línea en unidad base, crédito del total y, con devolución, débito de lo cobrado; sin devolución, sin débito; el consumidor final siempre con devolución. GREEN en `domain/ruta/`.
- [x] 6.2 RED en `frontend/tests/unit/sync/anularVentaLocal.test.ts` (spec `sync/cola-local`, «Anular una venta local es una sola transacción», sus cuatro escenarios; D4, D6; **cita INV-01**, INV-06, SYN-01, SYN-03): con `fake-indexeddb`, una transacción escribe anulación, movimientos, comando `VENTA_ANULAR` `OFFLINE` con la siguiente secuencia y la última secuencia; con una falla inyectada no queda nada y la secuencia no avanza; reconfirmar devuelve la existente; la de una «Sin enviar» queda detrás. Armar el sobre igual que el fixture de 4.1. GREEN en `sync/anularVentaLocal.ts`.

## 7. Conciliación de la anulación (Lote 2)

- [x] 7.1 RED en `frontend/tests/unit/domain/ruta/disponiblesLocales.test.ts` (spec `sync/cola-local`, «La anulación local cuenta en el saldo y el stock locales», sus ocho escenarios; D7; cita CRE-08, RUT-04, VTA-22, **INV-19**, SYN-06, INV-06): 63 tras vender 15 y anular; $100.000/$100.000 con devolución; $80.000 sin devolución; venta incluida y anulación pendiente 63; anulación incluida 63 y no 78; anulación rechazada no cuenta; venta y anulación rechazadas se compensan; doble sincronización igual. GREEN en `disponiblesLocales.ts` (la operación conciliable conoce si es una anulación y si su venta está rechazada) y en `areas/ruta/datos/disponibles.ts`.

## 8. Resultados de la anulación (Lote 2)

- [x] 8.1 RED en `frontend/tests/unit/sync/aplicarResultados.test.ts` (spec `sync/motor-de-sincronizacion`, «El resultado de una anulación se escribe en el teléfono», sus cinco escenarios; D6; **cita INV-01**, INV-06, SYN-04, SYN-09): el resultado de una anulación cambia `anulaciones.estado_envio` y la cola, no la venta; observaciones guardadas; rechazo visible; falla inyectada no deja nada; reenvío igual. GREEN en `sync/aplicarResultados.ts`.

## 9. Estado de la jornada en el teléfono (Lote 2)

- [x] 9.1 RED en `frontend/tests/unit/sync/estadoDeJornada.test.ts` y `sincronizar.test.ts` (spec `sync/motor-de-sincronizacion`, «Con señal, el teléfono se entera de que su jornada ya no está abierta», sus siete escenarios; D8; cita RUT-03, RUT-09, SYN-07, SYN-09, INV-06): al empezar cada ciclo se consulta `GET /stock/jornadas/{id}` de la sesión y se guarda `LIBERADA`, `EN_RENDICION` o `CERRADA`; `ABIERTA`, sin red, 403, 404 o error no cambian nada; `JORNADA_REQUERIDA` de «Actualizar datos» y `sin_jornada` al entrar guardan «desconocido»; una `JORNADA_LIBERADA` en los resultados guarda `LIBERADA`; la cola se envía igual; el bootstrap de otra jornada lo borra; la consulta repetida no cambia nada. GREEN en `sync/` (módulo nuevo del estado, `sincronizar.ts`, `actualizarDatos.ts`, `aplicarResultados.ts`, `aplicarBootstrap.ts`, `areas/ruta/sesion/entrada.ts`).

## 10. Pantalla de anulación y detalle (Lote 3)

- [x] 10.1 Red de seguridad: suites de «Venta guardada», «Ventas de hoy», Vender, inicio y ficha. RED en `frontend/tests/unit/areas/ruta/AnularVentaScreen.test.tsx` y `VentaGuardadaScreen.test.tsx` (spec `ruta/area-de-ruta`, «Una venta de la jornada se anula desde el teléfono», sus ocho escenarios; D5, D10; cita VTA-20, VTA-22, VTA-24, CLI-03, SEG-06, INV-06): «Anular venta» solo con permiso, jornada de la sesión, no anulada, no «Rechazada», jornada no marcada y versión al día; motivo obligatorio del ámbito; observación hasta 500; devolución obligatoria con cobro, fija en consumidor final, ausente sin cobro; confirmación; doble toque. GREEN: ruta `/ruta/ventas/:id/anular` y lógica de habilitación en una función pura de `domain/ruta/`.
- [x] 10.2 RED en `VentaGuardadaScreen.test.tsx` y `VentasDeHoyScreen.test.tsx` (spec `ruta/area-de-ruta`, «Las anulaciones se ven en las pantallas de ruta», escenarios «Ventas de hoy», «Anulación con observaciones» y «Doble sincronización»; D10; cita VTA-20, SYN-07, INV-06): etiqueta «Anulada» y sección «Anulación» con motivo, devolución, observación, estado y explicación. GREEN.

## 11. Nota de una venta anulada en el teléfono (Lote 3)

- [x] 11.1 RED en `frontend/tests/unit/domain/ventas/notaDesdeLocal.test.ts` (escenario «Nota de una venta anulada»; D10; cita VTA-13, VTA-22): con la anulación local, el adaptador pasa la anulación (fecha, nombre del motivo guardado, devolución) y la nota lleva «ANULADA» y no lleva saldo; sin anulación, igual que hoy. GREEN en `domain/ventas/notaDesdeLocal.ts` y en `NotaSinSenal.tsx`.

## 12. Sincronización y pendientes (Lote 3)

- [x] 12.1 RED en `frontend/tests/unit/domain/ruta/textosDeSincronizacion.test.ts` (D11; cita SYN-06, SYN-07): cada rechazo y observación de la anulación del fixture tiene su texto aprobado en 0.2, elegido por tipo de operación, con el aviso «La venta sigue vigente en el teléfono; avisá a administración.»; un código desconocido de una anulación da el texto general. GREEN.
- [x] 12.2 RED en las pruebas de «Sincronización», del inicio y de los avisos de cierre de sesión y de pendientes de otro (spec `ruta/area-de-ruta`, escenarios «Anulación rechazada en Sincronización» y «Pendientes»; D10; cita SYN-06, SYN-09): la anulación con problemas como «Anulación de {número}» con su texto y acceso al detalle; «2 ventas y 1 anulación sin enviar»; el aviso de pendientes de otro nombra al vendedor también por la anulación. GREEN en `areas/ruta/datos/sincronizacion.ts`, `SincronizacionScreen.tsx`, `presentacion.ts` y `sync/ventasPendientes.ts`.

## 13. Corte por jornada no abierta (Lote 3)

- [x] 13.1 RED en las pruebas del inicio, la ficha y Vender (spec `ruta/area-de-ruta`, «Vender y anular se cortan cuando la jornada ya no está abierta», sus seis escenarios; D9; cita RUT-09, RUT-05, VTA-24, SYN-05, INV-01): aviso por estado y «Lo que ya vendiste se sigue enviando.»; «Vender» deshabilitado en el inicio y la ficha; «Confirmar venta» no confirma y el carrito sigue; sin «Anular venta»; vale tras recargar; sin dato guardado, vende como siempre; con señal se ofrece «Abrir jornada». GREEN en `InicioScreen.tsx`, `ClienteFichaScreen.tsx`, `VenderScreen.tsx` y una lectura en `areas/ruta/datos/`.

## 14. Ayuda (Lote 3)

- [x] 14.1 RED en la prueba de claves de ayuda (spec `sistema/ayuda-contextual`, «Las pantallas de ruta explican la anulación y la jornada no abierta», sus cinco escenarios; D12; ADR-051): las tres claves nuevas existen, las cuatro revisadas tienen los textos aprobados en 0.2, sin ejemplos, y todo ID citado existe (ADR-066 ya existe como *Propuesto*). GREEN en `ayuda/textos.ts` y en la pantalla de anulación (con `ventas.motivoAnulacion`, `ventas.devolverDinero`, `ventas.consumidorFinalAnulacion`), el detalle, «Sincronización» y el aviso de la jornada.

## 15. Prueba de punta a punta del cliente (Lote 4)

- [x] 15.1 RED en `frontend/tests/unit/areas/ruta/FlujoAnulacionSinConexion.test.tsx` (con `fake-indexeddb`, `fetch` simulado y temporizadores falsos; cita VTA-24, INV-19, INV-06, CRE-08, RUT-09): bootstrap con 63 botellas → venta de 15 sin red (48) → anulación sin red (63, «Anulada», «Sin enviar») → vuelve la señal y se envían en orden → «Actualizar datos» con 63 y marca → sigue 63 → la consulta de la jornada responde `LIBERADA` → aviso y «Vender» deshabilitado → «Sincronizar» otra vez no cambia nada. GREEN si hace falta.

## 16. ADR (Lote 4)

- [x] 16.1 Completar `docs/adr/ADR-066-anulacion-sin-conexion-y-jornada-no-abierta.md` (borrador *Propuesto* creado con la propuesta) con lo aprobado en 0.1 y las precisiones del apply.

## 17. Propuesta de docs (Lote 4)

- [x] 17.1 Crear `openspec/changes/22d-anulacion-sin-conexion/propuesta-docs.md` con el texto actual y el propuesto: `01` VTA-24 (modo `OFFLINE` habilitado, jornada en curso, venta inexistente), SYN-06 (`VENTA_INEXISTENTE`), SYN-07 y STK-09 (`UBICACION_TOMADA_AL_SINCRONIZAR` también sobre la anulación), RUT-09 (el teléfono corta la venta), CRE-08 (la anulación y su rechazo); `02` §6.5 (fila de `VENTA_ANULAR` y su párrafo), §13.2 (`anulaciones`, Dexie v4, movimientos nuevos, `meta.jornada_no_abierta`), §13.3 (consulta de la jornada en cada ciclo; anulaciones en «Sincronización»); `03` (`venta_anulacion.jornada_id` sin conexión); `04` §11 (fila del 22d terminada y deudas saldadas: ADR-058 «al 22c/22d» y la del 22c «al 22d»). **No se aplica a `docs/`** sin el visto bueno del usuario.

## 18. Spec principal restituida (Lote 4)

- [x] 18.1 Restituir `openspec/specs/ventas/anulacion-de-venta/spec.md` desde el delta del change 19 (`openspec/changes/archive/2026-10-27-19-venta-anulacion/specs/ventas/anulacion-de-venta/spec.md`, **sin modificar el archivo de `archive/`**), con su `## Purpose` y con el primer requisito y su escenario «Modo sin conexión todavía no admitido» ajustados a «por REST, solo `ONLINE`; sin conexión, ver "Una venta de la jornada en curso se anula sin conexión"» (D13). Verificable: `openspec validate 22d-anulacion-sin-conexion` y `openspec validate --specs` sin errores.

## 19. Cobertura y suites completas (Lote 4)

- [x] 19.1 Cada escenario de las siete specs delta tiene al menos una prueba que lo nombra (`frontend/tests/unit/cobertura/escenariosDe22d.test.ts`, como en el 22c, con los del servidor por archivo); INV-19, INV-01, INV-05, INV-06 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas (backend unit, integration, concurrency, properties y fixtures compartidos; frontend Vitest), `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación. `04` §2.1 punto 4 (migración): no aplica, sin migración.

## 20. Prueba de integración del servidor (Lote 4)

- [x] 20.1 Repasar que las pruebas de integración y concurrencia de 1.1 a 3.1 corren juntas con la suite completa (orden y limpieza de datos), que la anulación con conexión del change 19 sigue igual (sus pruebas en verde sin cambiar aserciones) y que los fixtures `venta-confirmar-offline.json` y `venta-anular-offline.json` se aceptan.

## 21. Prueba manual (Lote 4)

- [x] 21.1 Probar a mano el flujo principal y dar al usuario el paso a paso en el chat (sin archivo aparte), con los usuarios de desarrollo existentes (`admin`, `sup01`, `vendedor`), en el navegador de escritorio (modo de dispositivo y «sin conexión»): `sup01` abre la jornada en `/ruta` y anota stock y saldo de un cliente; sin red vende con cobro y la anula con devolución, y ve «Anulada», el stock y el crédito como antes y la nota con «ANULADA»; vuelve la red y se envían en orden; «Actualizar datos» no cuenta dos veces; una anulación de una venta que `admin` ya anuló desde `/admin` vuelve «Rechazada» con su texto y deja de contar; `vendedor` no ve «Anular venta»; con `vendedor` vendiendo con red, `admin` libera su jornada desde `/admin` y en menos de dos minutos (o con «Sincronizar») el teléfono avisa «Tu jornada fue liberada.» y deshabilita «Vender», sigue así sin red y tras recargar, y lo pendiente se envía. No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5.
