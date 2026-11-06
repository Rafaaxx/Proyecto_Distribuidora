# Tareas — 25-observaciones-y-revision

> Modo TDD estricto: en cada tarea de los grupos 1 a 20, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Ninguna aserción trivial. Las tareas reflejan las decisiones **aprobadas** en 0.1: A en todas salvo **D9 = B** (la rendición se rechaza con `RECHAZOS_PENDIENTES`).
>
> **Dónde va el código:** backend en `sync/` con archivos propios del área: `sync/domain/revision.py` (puro), `sync/revision_repository.py`, `sync/revision_casos.py`, `sync/revision_commands.py`, `sync/revision_queries.py`, `sync/revision_api.py` (router `/observaciones`); `sync/service.py` (puertos de resumen, registro de rechazos en el lote); `sync/bootstrap.py`; `sync/models.py`; puertos registrados en `ventas/service.py`, `cobranzas/service.py`, `proveedores/service.py` y `stock/service.py`; `ventas/` (`PRODUCTO_DESACTIVADO`); migración nueva. Frontend en `areas/admin/revision/` (nueva), `features/revision/`, `domain/revision/`, `areas/admin/AdminLayout.tsx` y `AdminInicio.tsx`, los detalles de venta, cobranza, compra, transferencia y ajuste, `areas/admin/stock/` (aviso), `sync/` y `domain/ruta/` del teléfono, `ayuda/textos.ts`. Fixtures en `shared/fixtures/sync/`.
>
> **Lotes de apply (`design.md` D0 = A):** Lote 1 = grupos 1 a 3 (fixture, dominio, migración, modelos). Lote 2 = grupos 4 a 6 (resolución de observaciones, puertos, bandeja). Lote 3 = grupos 7 a 9b (registro, resolución y lectura de rechazos; la rendición que espera a los rechazos, D9 = B). Lote 4 = grupos 10 a 12 (`PRODUCTO_DESACTIVADO`, bootstrap, contratos). Lote 5 = grupos 13 a 15 (pantallas de `/admin`). Lote 6 = grupos 16 a 18 (teléfono, textos, ayuda). Lote 7 = grupos 19 a 26 (concurrencia, propiedades, ADR, docs, cobertura, suites, migración en desarrollo, prueba manual). Un subagente nuevo por lote, en secuencia. **No se frena entre lotes**: el resumen de cada lote informa las comprobaciones automáticas y el usuario revisa con todo el change implementado.
>
> **Pruebas:** en cada lote solo las afectadas; las suites completas una sola vez, en 23.1. `pytest` por carpeta con `backend/.venv`; frontend con Docker detenido. Integración y concurrencia con PostgreSQL real (Testcontainers), las de concurrencia con commits reales. Skills del proyecto (`.agents/skills/`): `sqlalchemy-alembic-expert-best-practices-code-review` en los grupos 2 y 3; `architecture-patterns` para los puertos y los archivos por área.

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones: el usuario revisa D0 a D13 de `design.md` (**CRÍTICAS: D6 y D7**; ALTAS: D1, D2, D5, D8, D9; de negocio: D0, D1, D3, D5, D6, D7, D8, D9, D10, D11). Se anota el resultado en `design.md` y en ADR-069, y se ajustan proposal, specs y tareas si alguna opción cambia. **Aprobadas el 2026-11-05: todas en A salvo D9 = B**; ajustados `design.md` (D9 y sus precisiones, riesgos), ADR-069, `proposal.md`, las specs `stock/rendicion-de-jornada`, `sync/rechazos-sin-conexion` y `sistema/ayuda-contextual`, `propuesta-docs.md` y estas tareas.
- [x] 0.2 Textos: **aprobados por el usuario el 2026-11-05** (incluidos los de D9 = B), junto con dos precisiones de D9: la cuarentena no bloquea la rendición y la cantidad `rechazos_pendientes` la ve quien puede leer la jornada aunque no tenga `REVISAR_OBSERVACIONES` (la lista sí lo exige). El usuario aprueba, **sin ejemplos**, los textos de D12 (pantallas, etiquetas que faltan, detalles legibles de cada código, errores —incluido `RECHAZOS_PENDIENTES`—, el aviso de la pantalla de conteo con «Ver rechazadas» y «Las resuelve quien revisa las observaciones.», y «Resuelta por administración» del teléfono) y las claves de ayuda de D13: nuevas `revision.bandeja`, `revision.resolver`, `revision.rechazadas`, `revision.cuarentena`, `revision.vinculo`, `stock.rechazadasDeLaJornada` y `ruta.rechazoResuelto`; revisadas `ventas.observaciones`, `cobranzas.observaciones`, `ruta.ventaRechazada` y los temas `ventas-observaciones` y `cobranzas-observaciones`.

## 1. Fixture y dominio puro (Lote 1)

- [x] 1.1 Ampliar `shared/fixtures/sync/codigos-de-sincronizacion.json` **antes** del código (D10, D12; cita SYN-07, INV-17): `PRODUCTO_DESACTIVADO` en `observaciones`; RED ampliando `backend/tests/unit/test_fixture_codigos_de_sincronizacion.py` (el catálogo del servidor la incluye) y la prueba de textos del teléfono (`textosDeSincronizacion.test.ts`). GREEN en el lote 4 (servidor) y en el lote 6 (texto). `RECHAZOS_PENDIENTES` **no** va en este fixture: no es un resultado del lote sino un error REST de la rendición en `/admin` (su texto, en `features/stock/errores.ts`, 17.1).
- [x] 1.2 RED en `backend/tests/unit/sync/test_dominio_revision.py` (specs `sync/revision-de-observaciones` y `sync/rechazos-sin-conexion`, escenarios de validación; D1, D7; cita SYN-08, INV-01): funciones puras de `sync/domain/revision.py` que validan la lista (1 a 100, sin repetidos: `OBSERVACIONES_INVALIDAS`), el comentario (1 a 500 tras recortar: `COMENTARIO_INVALIDO`), las ya resueltas (`OBSERVACION_YA_RESUELTA` con los ids) y el vínculo admitido por tipo de comando (`VINCULO_INVALIDO`); errores de dominio con código estable. GREEN.

## 2. Migración (Lote 1)

- [x] 2.1 RED en `backend/tests/integration/test_revision_migracion.py` (D2, D6, D7, D10; cita INV-02, INV-05, INV-21, `04` §2.1 punto 4): la revisión nueva (sobre el head actual) crea `comando_rechazado` con FK compuestas (usuario, dispositivo, jornada nulable), `UNIQUE (organizacion_id, operation_id)`, `CHECK` de estado y de coherencia de la resolución y del vínculo, índice parcial de pendientes por jornada; `app_runtime` con `SELECT, INSERT` y `UPDATE` solo de las columnas de la resolución, sin `DELETE`; en `observacion` quita el `UPDATE` de tabla, da `UPDATE (estado, resuelto_por_id, resuelto_en, comentario)`, agrega `ck_observacion__resolucion_coherente` y `ck_observacion__comentario` y `PRODUCTO_DESACTIVADO` en `ck_observacion__codigo`; en `comando_cuarentena` agrega `comentario`, `vinculo_tipo`, `vinculo_id`, `UPDATE` por columna y `CHECK` de coherencia; sube y baja limpia sobre una base con datos (observaciones pendientes previas siguen válidas) y el `downgrade` aborta con mensaje claro si hay rechazos, resoluciones, revisiones o `PRODUCTO_DESACTIVADO`. GREEN.

## 3. Modelos (Lote 1)

- [x] 3.1 RED en `backend/tests/integration/test_revision_modelos.py` (cita INV-05): modelo `ComandoRechazado`, columnas nuevas de `ComandoCuarentena`, `CODIGOS_OBSERVACION` con `PRODUCTO_DESACTIVADO`; `test_modelos_coinciden_con_migracion` sin diferencias; con `app_runtime`, `UPDATE` del código o del detalle de una observación y `DELETE` de cualquiera de las tres tablas rechazados por la base. GREEN.

## 4. `OBSERVACION_RESOLVER` (Lote 2)

- [x] 4.1 Red de seguridad: suites de `sync` (observaciones, lote, cuarentena). RED en `backend/tests/integration/test_observacion_resolver.py` (spec `sync/revision-de-observaciones`, «Las observaciones se resuelven con un comentario y sin tocar la operación», sus escenarios salvo la concurrencia; D1; cita SYN-08, INV-01, INV-06, INV-21): `OBSERVACION_RESOLVER` v1 (`ONLINE`, `REVISAR_OBSERVACIONES`) en `sync/revision_commands.py` y `revision_casos.py`, filas `FOR UPDATE` en orden de `id`; `POST /api/v1/observaciones/resolucion`; 403, 404, 409, 422; auditoría única del bus; doble envío; la venta, el comando y los libros sin cambios. GREEN.

## 5. Puertos de resumen (Lote 2)

- [x] 5.1 RED en `backend/tests/integration/test_resumen_de_operaciones.py` (D4; cita INV-21, `02` §5.3): los resumidores de operación de `VENTA`, `COBRANZA`, `COMPRA`, `TRANSFERENCIA` y `AJUSTE_STOCK` registrados por cada `service.py` devuelven título, cliente o proveedor, total (string) y momento en **una consulta por tipo**; nunca de otra organización; sin puerto, resumen nulo. GREEN.

## 6. Bandeja y resumen (Lote 2)

- [x] 6.1 RED en `backend/tests/integration/test_bandeja_de_observaciones.py` (spec `sync/revision-de-observaciones`, «La bandeja muestra las observaciones por operación», sus seis escenarios; D3; cita SYN-07, SYN-08, CRE-09, DSC-09, INV-21): `GET /api/v1/observaciones` agrupado por operación con SQL en la base, filtros, cursor, detalle de cada código (incluidos `DESCUENTO_DIFIERE` con causas, `AUTORIZACION_OFFLINE`, `EXCESO_CREDITO_DETECTADO_SYNC`, `CONSUMIDOR_FINAL_CON_DEUDA`, `MEDIO_INACTIVO`, `REFERENCIA_FALTANTE`, `JORNADA_RENDIDA`, `UBICACION_TOMADA_AL_SINCRONIZAR`, `VENTA_SIN_COSTO`), resolución de las resueltas, 403 sin permiso. GREEN.
- [x] 6.2 RED en `backend/tests/integration/test_resumen_de_pendientes.py` (spec «Administración ve un aviso de lo pendiente», escenarios del servidor; D5; cita CRE-09): `GET /api/v1/observaciones/resumen` con pendientes por código, rechazos y cuarentenas pendientes; solo la organización del token; 403. GREEN.

## 7. Registro de rechazos en el lote (Lote 3)

- [x] 7.1 Red de seguridad: suites del lote, de la cuarentena, de ventas, anulaciones, cobranzas y entrega sin conexión. RED en `backend/tests/integration/test_registro_de_rechazos.py` (spec `sync/rechazos-sin-conexion`, «El lote guarda cada rechazo sin conexión», sus ocho escenarios; D6; cita SYN-03, SYN-05, SYN-06, INV-06, INV-08, INV-21): `_procesar_lote` guarda en transacción aparte cada ítem `OFFLINE` rechazado (antes o dentro del handler, y con fila de comando), con contenido, código y jornada si existe; no guarda credenciales, cola ajena ni dispositivo revocado; `ON CONFLICT DO NOTHING`; falla transitoria inyectada al guardar → `ERROR_TRANSITORIO` y corte. Si hiciera falta cambiar el orden o la forma de la respuesta del lote, **detenerse y consultar**. GREEN.

## 8. `RECHAZO_RESOLVER` (Lote 3)

- [x] 8.1 RED en `backend/tests/integration/test_rechazo_resolver.py` (spec `sync/rechazos-sin-conexion`, «Un rechazo se resuelve con comentario y, si ocurrió, con su corrección», escenarios salvo la concurrencia; spec `sync/cuarentena-de-comandos`, sus cinco escenarios; D7; cita SYN-06, SYN-08, INV-05, INV-06, INV-21): `RECHAZO_RESOLVER` v1 (`ONLINE`, `REVISAR_OBSERVACIONES`) con `origen` `RECHAZO` o `CUARENTENA`, registro `FOR UPDATE`, vínculo validado por tipo y existencia por `ventas/service.py` y `cobranzas/service.py`; `POST /api/v1/observaciones/rechazos/{id}/resolucion`; nada se reenvía ni se crea; el reenvío del teléfono dado de baja sigue en `DISPOSITIVO_REVOCADO`. GREEN.

## 9. Lectura de rechazos (Lote 3)

- [x] 9.1 RED en `backend/tests/integration/test_lista_de_rechazos.py` (spec «Los rechazos se leen por organización y no se borran», sus cuatro escenarios; D4, D6; cita SYN-06, SYN-09, INV-05, INV-21): `GET /api/v1/observaciones/rechazos` y `GET /api/v1/observaciones/rechazos/{id}` con rechazos y cuarentenas, filtros (estado, origen, tipo, usuario, jornada), resumen del contenido por los resumidores de contenido (sin fallar con contenido mal formado o referencias inexistentes), «aceptada después» por cruce con `comando`, resolución. GREEN.

## 9b. La rendición espera a los rechazos (Lote 3)

- [x] 9b.1 Red de seguridad: suites de la rendición y de las jornadas del change 24 (`test_dominio_rendir.py`, `test_dominio_rendicion.py`, `test_jornadas_api.py`, `test_rendicion_concurrente.py`); anotar la línea base. RED en `backend/tests/unit/stock/test_dominio_rendir.py`: error de dominio `RECHAZOS_PENDIENTES` (409, código estable, con la cantidad en el detalle) y la regla pura «con cantidad > 0 no se rinde» (al menos dos casos: 0 y 1; y 2 con la cantidad en el detalle). GREEN en `stock/domain/`.
- [x] 9b.2 RED en `backend/tests/integration/test_rendicion_rechazos_pendientes.py` (spec `stock/rendicion-de-jornada`, sus escenarios del servidor salvo la concurrencia; spec `sync/rechazos-sin-conexion`, «Resolver el último rechazo de la jornada habilita la rendición» y «Cantidad pendiente por jornada»; D9 = B; cita RUT-05, RUT-06, SYN-06, SYN-08, INV-06, INV-21): `JORNADA_RENDIR` con un rechazo `PENDIENTE` de la jornada responde 409 `RECHAZOS_PENDIENTES` sin escribir nada (jornada `ABIERTA`, sin conteo ni `DIFERENCIA_RENDICION`, stock igual); resuelto con o sin vínculo, se acepta; rechazos de otra jornada, sin jornada, de otra organización y cuarentenas no bloquean; `JORNADA_ENTREGAR`, `JORNADA_CERRAR` y `JORNADA_LIBERAR` no se bloquean; el mismo `operation_id` se procesa de nuevo después de resolver; `GET /api/v1/stock/jornadas/{id}` devuelve `rechazos_pendientes`. El puerto lo declara `stock/service.py` y lo registra `sync/service.py`; prueba de que la aplicación lo tiene registrado y de que sin puerto la rendición falla (no se rinde sin comprobar). La comprobación va después de tomar la jornada `FOR UPDATE`, en una consulta aparte. GREEN en `stock/jornadas_casos.py`, `stock/service.py`, `sync/service.py` y el esquema de la jornada.

## 10. `PRODUCTO_DESACTIVADO` (Lote 4)

- [x] 10.1 Red de seguridad: suites de la venta sin conexión. RED en `backend/tests/integration/test_venta_offline_producto_desactivado.py` (spec `sync/observaciones`, «Una venta sin conexión de un producto desactivado se acepta con observación», sus tres escenarios; D10; cita SYN-05, SYN-07, INV-17, INV-06): la venta sin conexión con producto o presentación inactivos se acepta con una `PRODUCTO_DESACTIVADO` por línea; con conexión, sin cambios. GREEN en `ventas/` y en el catálogo de `sync/models.py` (cierra 1.1 del servidor).

## 11. Rechazos resueltos en el bootstrap (Lote 4)

- [x] 11.1 RED en `backend/tests/integration/test_bootstrap_rechazos_resueltos.py` (spec `sync/bootstrap`, sus tres escenarios; D8; cita SYN-11, INV-21): `rechazos_resueltos` con los `operation_id` resueltos de la jornada, el usuario y el dispositivo, en la misma foto; sin comentario ni vínculo. GREEN en `sync/bootstrap.py` y `schemas.py`.

## 12. Contratos y límites (Lote 4)

- [x] 12.1 Ratchets y límites: `lint-imports` (`sync` no importa `ventas`, `cobranzas`, `proveedores` ni `stock` fuera de `service.py`; los puertos se registran desde cada `service.py`; los archivos `revision_*` no importan `service.py` propio salvo lo necesario), el catálogo de tipos (`OBSERVACION_RESOLVER` y `RECHAZO_RESOLVER` solo `ONLINE`, con `REVISAR_OBSERVACIONES`), el ratchet de permiso por ruta (las rutas nuevas con su permiso), el ratchet de motivos de auditoría (sin motivo), `stock` sin importar `sync` en sus casos de uso (el contador de rechazos llega por el puerto, D9 = B) y los tipos del cliente generados desde el OpenAPI (`npm run typecheck`, incluidos `RECHAZOS_PENDIENTES` y `rechazos_pendientes` de la jornada).

## 13. Bandeja «Observaciones» en `/admin` (Lote 5)

- [x] 13.1 RED en `frontend/tests/unit/domain/revision/detalleDeObservacion.test.ts` (D3, D12; cita SYN-07, DSC-09, CRE-09): `domain/revision/` traduce cada código a su etiqueta y su detalle legible (los de D12), con importes por `decimal.js` y formato de `lib/money.ts`; un código desconocido muestra el código. GREEN (y `domain/ventas/presentacion.ts` reutiliza estas etiquetas, con las que faltaban).
- [x] 13.2 RED en `frontend/tests/unit/areas/admin/revision/ObservacionesScreen.test.tsx` (D1, D3, D11; cita SYN-08, `01` §19, INV-01): `/admin/revision` pestaña «Observaciones» con filtros, una fila por operación, casillas, «Resolver {N} avisos» con comentario y confirmación, error `OBSERVACION_YA_RESUELTA` que recarga, mismo `operation_id` en el reintento, «Ver» solo si el usuario puede abrir la operación, sin la pantalla sin `REVISAR_OBSERVACIONES`. GREEN.

## 14. «Rechazadas» en `/admin` (Lote 5)

- [x] 14.1 RED en `frontend/tests/unit/areas/admin/revision/RechazadasScreen.test.tsx` (D7, D11; cita SYN-06, SYN-08, SYN-09): rechazos y cuarentenas con origen, tipo, vendedor, jornada, motivo traducido con los textos del fixture de códigos, lo que envió el teléfono, «Aceptada después», «Resolver» con comentario y «Vincular con» (búsqueda de venta por número o cobranza del cliente), `VINCULO_INVALIDO` y `RECHAZO_YA_RESUELTO`. GREEN.

## 15. Aviso, resolución en los detalles y rendición (Lote 5)

- [x] 15.1 RED en `AdminLayout.test.tsx` y `AdminInicio.test.tsx` (spec «Administración ve un aviso de lo pendiente», escenarios de pantalla; D5; cita CRE-09, SEG-06): «Revisión» con el total, tarjeta «Para revisar» con los excesos aparte y su acceso filtrado, refresco cada 60 s y al volver a la pestaña, nada sin permiso. GREEN.
- [x] 15.2 Red de seguridad: suites de los detalles. RED en las pruebas de `VentaDetalleScreen`, `CobranzaDetalleScreen` y los detalles de compra, transferencia y ajuste (D11; cita SYN-08): cada observación resuelta muestra «Resuelta por {usuario} el {fecha}: {comentario}»; las etiquetas y detalles nuevos. GREEN (los endpoints de detalle suman la resolución con el nombre del usuario).
- [x] 15.3 Red de seguridad: suites de `RendicionScreen` y `JornadaDetalleScreen`. RED en `RendicionScreen.test.tsx` y `JornadaDetalleScreen.test.tsx` (spec `stock/rendicion-de-jornada`, escenarios de pantalla: «Pantalla de conteo con rechazos pendientes», «Sin permiso de revisión», «Sin rechazos pendientes»; D9 = B; cita RUT-05, SEG-06): con `rechazos_pendientes` > 0, el aviso con singular y plural y «Registrar rendición» deshabilitado; con `REVISAR_OBSERVACIONES`, «Ver rechazadas» a «Rechazadas» filtrada por la jornada; sin ese permiso, «Las resuelve quien revisa las observaciones.», sin el acceso y sin pedir la lista; con 0, sin aviso y habilitado; si el envío responde `RECHAZOS_PENDIENTES`, su texto y la recarga de la cantidad (el conteo cargado no se pierde). GREEN.

## 16. Teléfono (Lote 6)

- [x] 16.1 Red de seguridad: suites de `sync/`, bootstrap local y `disponiblesLocales`. RED en `frontend/tests/unit/sync/rechazosResueltos.test.ts` y en la prueba de `disponiblesLocales` (spec `sync/cola-local`, sus cuatro escenarios; D8; cita CRE-08, SYN-09, INV-01, INV-06): con `fake-indexeddb`, aplicar el bootstrap guarda `rechazos_resueltos` en `meta` en la misma transacción; una venta rechazada resuelta deja de contar (stock, débito y cobro en el momento); falla inyectada no deja nada; sin versión nueva de Dexie. GREEN.
- [x] 16.2 RED en las pruebas de «Ventas de hoy», «Cobranzas de hoy», los detalles y «Sincronización» (spec `ruta/area-de-ruta`, sus tres escenarios; D8; cita SYN-09): «Resuelta por administración» junto a «Rechazada», también tras recargar sin señal; no se reenvía; «Anular» sigue sin ofrecerse en una «Rechazada». GREEN.

## 17. Textos (Lote 6)

- [x] 17.1 RED en `textosDeSincronizacion.test.ts` y en las pruebas de errores de `features/revision/` (D12; cita SYN-07): el texto de `PRODUCTO_DESACTIVADO` en el teléfono (cierra 1.1), los errores de la revisión con los textos aprobados en 0.2 y `RECHAZOS_PENDIENTES` en `features/stock/errores.ts` (prueba de errores de stock). GREEN.

## 18. Ayuda (Lote 6)

- [x] 18.1 RED en la prueba de claves de ayuda (spec `sistema/ayuda-contextual`, sus cinco escenarios; D13; ADR-051; `stock.rechazadasDeLaJornada` con el texto de D9 = B): las siete claves nuevas existen y las revisadas tienen los textos aprobados en 0.2, sin ejemplos, y todo ID citado existe (ADR-069 ya existe como *Propuesto*). GREEN en `ayuda/textos.ts` y en las pantallas.

## 19. Concurrencia (Lote 7)

- [x] 19.1 RED en `backend/tests/concurrency/test_revision_concurrente.py` (escenarios «Dos personas resuelven a la vez» y «Dos resoluciones a la vez»; D1, D7; cita INV-01, INV-06), con commits reales: dos resoluciones de la misma observación; dos resoluciones en bloque con listas cruzadas (sin interbloqueo por el orden de `id`); dos resoluciones del mismo rechazo; dos lotes simultáneos (reenvío) que registran el mismo rechazo dejan un solo registro. Escenario «Resolución y rendición a la vez» (spec `stock/rendicion-de-jornada`; D9 = B, precisión 5; cita RUT-05, INV-01): `RECHAZO_RESOLVER` del último rechazo y `JORNADA_RENDIR` a la vez terminan sin interbloqueo (la rendición toma la jornada y solo lee rechazos; la resolución toma el rechazo y no la jornada) y la rendición se acepta solo si vio el rechazo resuelto; un `INSERT` de rechazo de la jornada concurrente con la rendición espera por la FK (`FOR KEY SHARE`) y nunca queda una rendición aceptada que no vio un rechazo confirmado antes de su consulta. GREEN si hace falta.

## 20. Propiedades (Lote 7)

- [x] 20.1 RED en `backend/tests/properties/test_revision_propiedades.py` (spec «Resolver nunca altera la operación»; cita **SYN-08**, INV-05, INV-12, INV-13): para secuencias aleatorias de ventas y cobranzas sin conexión con observaciones y de resoluciones en bloque, con SQL, las operaciones, los libros y los comandos quedan iguales y solo cambian las columnas de la resolución. GREEN si hace falta.

## 21. ADR (Lote 7)

- [x] 21.1 Completar `docs/adr/ADR-069-revision-de-observaciones-y-rechazos.md` (borrador *Propuesto* creado con la propuesta) con lo aprobado en 0.1 y las precisiones del apply.

## 22. Propuesta de docs (Lote 7)

- [x] 22.1 Completar `openspec/changes/25-observaciones-y-revision/propuesta-docs.md` con las precisiones del apply. **No se aplica a `docs/`** sin el visto bueno del usuario. Al aplicarla, verificar que las filas de `01` conserven `| ID |` y `| etapa |`.

## 23. Cobertura y suites completas (Lote 7)

- [x] 23.1 Cada escenario de las nueve specs delta tiene al menos una prueba que lo nombra (`frontend/tests/unit/cobertura/escenariosDe25.test.ts`, como en el 24, con los del servidor por archivo); SYN-08, INV-01, INV-02, INV-05, INV-06, INV-17 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas (backend unit, integration, concurrency, properties y fixtures compartidos; frontend Vitest), `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación. `04` §2.1 punto 4: la migración sube y baja limpia sobre una base con datos (2.1).

## 24. Prueba de integración del servidor (Lote 7)

- [x] 24.1 Repasar que las pruebas de los grupos 4 a 11 (incluido 9b) corren juntas con la suite completa (orden y limpieza de datos), que las del lote, la cuarentena, la venta, la anulación, la cobranza y la entrega sin conexión de los changes 04, 18a, 22d, 23 y 24 siguen igual (las de la rendición del 24, sin rechazos pendientes, también), y que los fixtures de `shared/fixtures/sync/` se aceptan.

## 25. Migración en desarrollo (Lote 7)

- [x] 25.1 Correr `alembic upgrade head` sobre la base de desarrollo (`docker compose`) y, si cambió alguna dependencia, reconstruir la imagen del backend; confirmar que `/admin` arranca y que el login funciona.

## 26. Prueba manual (Lote 7)

- [x] 26.1 Probar a mano el flujo principal y dar al usuario el paso a paso en el chat (sin archivo aparte), con los usuarios de desarrollo existentes (`admin`, `sup01`, `ges01`, `vendedor`, `consulta`), en el build con el perfil `lan` en https://localhost: `vendedor` abre la jornada y, sin señal, vende más de lo que hay (stock negativo), a un cliente pasado de su límite y un producto que `admin` desactiva después del bootstrap; vuelve la señal y se envía; `sup01` ve el contador y la tarjeta con el exceso detectado, abre «Revisión», ve los avisos con su detalle y resuelve dos con un comentario; ve «Resuelta por…» en el detalle de la venta; una operación rechazada (sobre malformado enviado desde las herramientas del navegador, o una venta en cuarentena revocando el dispositivo de `vendedor2`) aparece en «Rechazadas» con lo que envió el teléfono; `vendedor` toca «Terminar el día» y la entrega se acepta igual; `sup01` abre la pantalla de conteo, ve el aviso y «Registrar rendición» deshabilitado, entra por «Ver rechazadas», carga la venta con conexión, resuelve vinculándola, vuelve y rinde (el esperado ya incluye la venta: sin faltante por ella); en el teléfono, tras «Actualizar datos», la venta dice «Resuelta por administración» y el stock local no la descuenta dos veces; `consulta` no ve «Revisión». No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5.
