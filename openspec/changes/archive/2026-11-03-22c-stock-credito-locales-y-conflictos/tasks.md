# Tareas — 22c-stock-credito-locales-y-conflictos

> Modo TDD estricto: en cada tarea de los grupos 1 a 12, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Ninguna aserción trivial. Las tareas reflejan las opciones **recomendadas** (A); si 0.1 cambia alguna, se ajustan antes del apply.
>
> **Dónde va el código:** backend en `app/modules/sync/` (`bootstrap.py`, `schemas.py`, `service.py`, `api.py`, `repository.py`) y pruebas en `tests/unit`, `tests/integration`; **sin migración** (alcanza `ix_comando__org_dispositivo_secuencia`) ni permisos nuevos. Frontend en `lib/dispositivo/db.ts` (tipos; **sin Dexie v4**), `sync/aplicarResultados.ts`, `sync/aplicarBootstrap.ts`, `sync/clienteLote.ts`, `domain/ruta/disponiblesLocales.ts`, `domain/ruta/` (traducción de códigos, función pura nueva), `areas/ruta/datos/`, `areas/ruta/` (Stock, Productos, ficha, «Sincronización», «Venta guardada»), `ayuda/textos.ts` y `api/schema.gen.ts` regenerado. Fixture de contrato nuevo en `shared/fixtures/sync/`.
>
> **Lotes de apply (`design.md` D0 = A):** Lote 1 = grupos 1 a 4 (servidor). Lote 2 = grupos 5 a 7 (núcleo del teléfono). Lote 3 = grupos 8 a 10 (pantallas y ayuda). Lote 4 = grupos 11 a 16 (punta a punta, ADR, docs, cobertura, suites y prueba manual). Un subagente nuevo por lote, en secuencia. **No se frena entre lotes**: el resumen de cada lote informa las comprobaciones automáticas y el usuario revisa con todo el change implementado.
>
> **Pruebas:** en cada lote solo las afectadas; las suites completas una sola vez, en 14.1. `pytest` por carpeta con `backend/.venv`; frontend con Docker detenido. Base local con `fake-indexeddb`; servidor simulado con `fetch` de prueba. **Sin fixtures de cálculo nuevos** (no cambia ninguna regla de cálculo).

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones (aprobadas 2026-11-02: D0 a D9 en A): el usuario revisa D0 a D9 de `design.md` (de negocio: D0, D1, D2, D4, D6; ninguna CRÍTICA). Se anota el resultado en `design.md` y en ADR-065, y se ajustan proposal, specs y tareas si alguna opción cambia. Con **D0 = B** se agregan antes del apply las decisiones y los grupos de la anulación sin conexión (lista en D0).
- [x] 0.2 Textos (aprobados 2026-11-02 tal como en design.md): el usuario aprueba, **sin ejemplos**, la clave nueva `ruta.observacionesYRechazos` y las revisadas `ruta.stockDelVehiculo`, `ruta.creditoSinSenal`, `ruta.ventaConObservaciones` y `ruta.ventaRechazada` (D9), los textos de pantalla de las 16 observaciones y de los rechazos (D5), y «Incluye tus ventas desde la última actualización», «El detalle no está en el teléfono; consultalo con administración.», «1 más» / «N más» y los reemplazos «un producto», «un medio» y «un supervisor» (D4, D6).

## 1. Secuencia procesada en el bootstrap (Lote 1)

- [x] 1.1 Red de seguridad: suites del bootstrap (`tests/unit` y `tests/integration` de `sync/bootstrap`). RED en `backend/tests/integration/test_bootstrap_secuencia_procesada.py` (spec `sync/bootstrap`, «El bootstrap informa la secuencia procesada de la jornada», sus cinco escenarios; D1; cita SYN-11, CRE-08, RUT-04, INV-06, INV-21): con comandos reales por el lote, la marca es la mayor secuencia de la jornada, del usuario y del dispositivo; nula sin comandos; 8 tras un lote cortado en la 9 (transitorio inyectado); no mira otra jornada, otro dispositivo ni otra organización; con doble envío, 7 y el stock una vez. GREEN: consulta en `sync/repository.py` dentro de la misma transacción del bootstrap y campo `secuencia_procesada: int | None` en `SesionBootstrap`.

## 2. Observaciones en el resultado del lote (Lote 1)

- [x] 2.1 Red de seguridad: suites del lote. RED en `backend/tests/integration/test_lote_resultado_con_observaciones.py` (spec `sync/lote-de-comandos`, «El servidor devuelve un resultado por comando», escenarios nuevos; D3; cita SYN-04, SYN-07, SYN-02, INV-06): una venta sin conexión con `STOCK_NEGATIVO` y `MEDIO_INACTIVO` trae las dos con operación y detalle; aceptada sin observaciones y rechazada traen lista vacía; el reenvío devuelve las mismas y no registra otras; solo las del propio comando. GREEN: `observaciones` en `ResultadoItemLoteResponse` (y en el resultado interno del lote), leídas por `comando_id` también para el resultado guardado.

## 3. Registro de cierre del lote y fixture de códigos (Lote 1)

- [x] 3.1 RED en `backend/tests/unit/test_sync_metricas_de_lote.py` (spec `sistema/logging-estructurado`, «Métricas mínimas de comando en los registros», escenarios de cierre, corte, reenvío y contenido; D7; cita `02` §17, §18, INV-06): con `caplog`, el registro de cierre trae tamaño, procesados, aceptados, con observaciones, rechazados, corte y duración, sin contenido ni detalle de observaciones. GREEN en `sync/service.py`.
- [x] 3.2 RED en `backend/tests/unit/test_fixture_codigos_de_sincronizacion.py` (D5; cita SYN-06, SYN-07): `shared/fixtures/sync/codigos-de-sincronizacion.json` lista en `observaciones` exactamente los códigos del catálogo de observaciones del servidor, y cada código de `rechazos` es el `codigo` de un error del bus o de `ventas` (sin códigos inventados ni viejos). Fijar en esta tarea la lista de rechazos que puede recibir `VENTA_CONFIRMAR` `OFFLINE` recorriendo el bus y la validación de la venta. GREEN creando el fixture.

## 4. Cierre de INV-17 (Lote 1)

- [x] 4.1 RED en `backend/tests/integration/test_inv17_operaciones_sin_conexion_no_se_rechazan.py` (spec `sync/lote-de-comandos`, «Una venta o cobranza sin conexión nunca se rechaza por reglas de negocio», sus cinco escenarios; D8; **cita INV-17**, SYN-05, SYN-06, SYN-07, SYN-10, INV-06): matriz parametrizada por el lote con PostgreSQL real, un caso por regla de SYN-05 para la venta (stock, crédito, lista, descuentos, cliente suspendido e inactivo, permiso revocado, medio desactivado, referencia faltante, producto y presentación desactivados, ubicación tomada al sincronizar, motivo dado de baja) y para la cobranza; un caso con todas a la vez; `TOTALES_INCONSISTENTES` sí rechaza; el doble envío de una observada no duplica. GREEN: es una prueba de caracterización; **si hiciera falta tocar código de producción, detenerse y consultar**.

## 5. Tipos y resultados con observaciones en el teléfono (Lote 2)

- [x] 5.1 Red de seguridad: suites de `sync/` y `lib/dispositivo`. Regenerar `api/schema.gen.ts` desde el OpenAPI (bootstrap y lote). RED en `frontend/tests/unit/sync/clienteLote.test.ts` y `aplicarResultados.test.ts` (spec `sync/motor-de-sincronizacion`, «El resultado de cada operación se escribe en el teléfono», escenarios «Venta con observaciones», «Falla al escribir los resultados» y «Respuesta sin observaciones»; D3; **cita INV-01**, SYN-04, SYN-07): el cliente del lote lee `observaciones`; la fila de `cola` las guarda con el resultado en la misma transacción; con una falla inyectada no queda ninguna; sin la lista, `observaciones` queda sin dato. GREEN; `ComandoEnCola.observaciones?` en `db.ts`, prueba de que la base v3 abre igual.

## 6. Secuencia procesada en la base local (Lote 2)

- [x] 6.1 RED en `frontend/tests/unit/sync/aplicarBootstrap.test.ts` (spec `sync/cola-local`, «El bootstrap no toca los movimientos»; D1; cita SYN-09, SYN-11, `02` §13.4): la sesión local guarda `secuencia_procesada` (nula si falta); los movimientos, la cola y las ventas quedan iguales. GREEN en `sync/aplicarBootstrap.ts` y `SesionLocal`.

## 7. Regla de conciliación (Lote 2)

- [x] 7.1 RED en `frontend/tests/unit/domain/ruta/disponiblesLocales.test.ts` (spec `sync/cola-local`, «El saldo y el stock locales suman lo que hizo el teléfono», todos sus escenarios; D1, D2; cita CRE-08, RUT-04, COB-04, SYN-06, INV-06, INV-03, INV-04): funciones puras que reciben los movimientos, la secuencia y el estado de cada operación y la marca: 150.000/50.000; 48 tras vender 15; otra jornada no cuenta; aceptada sin actualizar 48; con marca 7, 48 y no 33; respuesta perdida 48; marca 7 con secuencias 7 y 8 cuenta solo la 8; rechazada con marca 9 sigue descontando; sin marca cuenta todo; doble sincronización no cambia nada. GREEN en `domain/ruta/disponiblesLocales.ts`; deja de usarse `estado_operacion` (se documenta en `db.ts`).
- [x] 7.2 RED en `frontend/tests/unit/areas/ruta/datos/disponibles.test.ts` (mismos escenarios contra Dexie con `fake-indexeddb`): `leerSaldoConsiderado` y `leerStockDisponible` (y una lectura del stock de todos los productos para la pantalla) toman la secuencia y el estado de cada operación de `cola` por `operation_id` y la marca de la sesión. GREEN en `areas/ruta/datos/disponibles.ts`; Vender sigue verde sin cambiar sus aserciones salvo las del doble conteo.

## 8. Disponibles locales en consulta (Lote 3)

- [x] 8.1 Red de seguridad: suites de Stock, Productos y la ficha. RED en sus pruebas (spec `ruta/area-de-ruta`, «Productos y stock desde la base local» y «Clientes desde la base local con cartera primero», escenarios nuevos y ajustados; D6; cita RUT-04, CRE-08, COB-04, INV-03, INV-04): Stock y Productos muestran 48 botellas y la leyenda; después de actualizar, 48 y no 33; sin operaciones que cuenten, sin leyenda; la ficha muestra $150.000 / $50.000 y la leyenda; un stock negativo se muestra negativo. GREEN.

## 9. Observaciones y rechazos traducidos (Lote 3)

- [x] 9.1 RED en `frontend/tests/unit/domain/ruta/textosDeSincronizacion.test.ts` (D5; cita SYN-06, SYN-07): cada código del fixture `shared/fixtures/sync/codigos-de-sincronizacion.json` tiene su texto aprobado en 0.2; el texto se arma con el producto, el medio o el autorizador del detalle desde datos locales, o «un producto», «un medio», «un supervisor»; un código desconocido da «El sistema no aceptó esta venta.». GREEN en una función pura de `domain/ruta/`.
- [x] 9.2 RED en las pruebas de «Sincronización» y «Venta guardada» (spec `ruta/area-de-ruta`, «La pantalla de sincronización muestra lo pendiente y lo que volvió con problemas» y «El detalle de una venta explica sus observaciones o su rechazo», todos sus escenarios; D4; cita SYN-04, SYN-06, SYN-07, SYN-09): resumen con la primera observación y «1 más»; rechazo con texto, código y aviso; código desconocido; la fila abre el detalle; el detalle muestra todas las observaciones, el motivo del rechazo o «El detalle no está en el teléfono; consultalo con administración.», y nada en una «Enviada». GREEN.

## 10. Ayuda (Lote 3)

- [x] 10.1 RED en la prueba de claves de ayuda (spec `sistema/ayuda-contextual`, «Las pantallas de ruta explican los disponibles locales y las observaciones»; D9; ADR-051): `ruta.observacionesYRechazos` existe y `ruta.stockDelVehiculo`, `ruta.creditoSinSenal`, `ruta.ventaConObservaciones` y `ruta.ventaRechazada` tienen los textos aprobados en 0.2, sin ejemplos; todo ID citado existe (ADR-065 ya existe como *Propuesto*). GREEN en `ayuda/textos.ts` y en Stock, Productos, la ficha, «Sincronización» y «Venta guardada».

## 11. Prueba de punta a punta del cliente (Lote 4)

- [x] 11.1 RED en `frontend/tests/unit/areas/ruta/FlujoConciliacion.test.tsx` (con `fake-indexeddb`, `fetch` simulado y temporizadores falsos; cita CRE-08, RUT-04, INV-06, SYN-07): bootstrap con 63 botellas → venta de 15 sin red (Stock muestra 48 con la leyenda) → vuelve la señal y se envía, con `STOCK_NEGATIVO` simulado → «Actualizar datos» con 48 y marca → Stock sigue en 48 sin leyenda → «Sincronización» y el detalle muestran la observación traducida → «Sincronizar» otra vez no cambia nada. GREEN si hace falta.

## 12. ADR (Lote 4)

- [x] 12.1 Completar `docs/adr/ADR-065-conciliacion-local-y-conflictos-en-el-telefono.md` (borrador *Propuesto* creado con la propuesta) con lo aprobado en 0.1 y las precisiones del apply.

## 13. Propuesta de docs (Lote 4)

- [x] 13.1 Crear `openspec/changes/22c-stock-credito-locales-y-conflictos/propuesta-docs.md` con el texto actual y el propuesto: `01` CRE-08 (regla de conciliación por secuencia procesada y venta rechazada), SYN-11 (la secuencia procesada), SYN-09 si cambia algo de lo visible; `02` §6.4 (observaciones en el resultado del lote), §13.2 (`sesion` con la marca; `cola` con las observaciones; `estado_operacion` sin uso), §13.3 (detalle traducido en «Sincronización» y en la venta), §13.4 (la marca, y que el bootstrap sigue sin tocar los movimientos), §17 (registro de cierre del lote); `04` §11 (fila del 22c terminada, fila nueva del **22d `anulacion-sin-conexion`** con D0 = A, la tabla de dependencias (22d depende de 22c y va antes del 23) y deudas saldadas: ADR-063 y ADR-064 «al 22c»; ADR-058 «al 22c» reasignada al 22d), y quitar el párrafo duplicado del 22b que quedó dentro de la tabla de §11 con «(fecha de archivo)». **No se aplica a `docs/`** sin el visto bueno del usuario.

## 14. Cobertura y suites completas (Lote 4)

- [x] 14.1 Cada escenario de las siete specs delta tiene al menos una prueba que lo nombra (`frontend/tests/unit/cobertura/escenariosDe22c.test.ts`, como en el 22b, con los del servidor por archivo); INV-17, INV-01 e INV-06 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas (backend unit, integration, concurrency, properties y fixtures compartidos; frontend Vitest), `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación. `04` §2.1 punto 4 (migración): no aplica, sin migración.

## 15. Prueba de integración del servidor (Lote 4)

- [x] 15.1 Repasar que las pruebas de integración de 1.1, 2.1 y 4.1 corren juntas con la suite completa (orden y limpieza de datos) y que el fixture de contrato del 22a (`venta-confirmar-offline.json`) sigue aceptado con la lista de observaciones vacía.

## 16. Prueba manual (Lote 4)

- [x] 16.1 Probar a mano el flujo principal y dar al usuario el paso a paso en el chat (sin archivo aparte), con los usuarios de desarrollo existentes (`admin`, `sup01`, `vendedor`), en el navegador de escritorio (modo de dispositivo y «sin conexión»): `vendedor` abre la jornada y anota el stock de un producto y el saldo de un cliente; sin red vende a ese cliente y ve en Stock, Productos y la ficha los valores locales con la leyenda; vuelve la red y se envía; «Actualizar datos» y los valores no se descuentan dos veces; una venta que deje stock negativo (con el permiso) vuelve «Con observaciones» y «Sincronización» y el detalle dicen qué se anotó; una venta rechazada (sobre manipulado o jornada liberada y cerrada desde `/admin`, según se pueda) muestra el motivo y sigue descontando; en el log del backend aparece el cierre de cada lote. No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5. **Hecha por el usuario el 2026-11-03: pasos 1 a 16 completos, sin errores** (un tropiezo inicial fue una sesión vieja de `admin` en el navegador, no un defecto).
