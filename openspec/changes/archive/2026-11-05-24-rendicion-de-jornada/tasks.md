# Tareas — 24-rendicion-de-jornada

> Modo TDD estricto: en cada tarea de los grupos 1 a 18, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. Ninguna aserción trivial. Las tareas reflejan las opciones **recomendadas** (A); si 0.1 cambia alguna, se ajustan antes del apply.
>
> **Dónde va el código:** backend en `stock/` con archivos propios del área (ADR-049 punto 2): `stock/domain/rendicion.py` (puro), `stock/rendicion_repository.py`, `stock/rendicion_casos.py` (nunca importa `service.py`) y `stock/rendicion_commands.py`; `stock/service.py` (puerta del libro y delegación), `stock/jornadas_*` (entrega y cierre), `ventas/` y `cobranzas/` (observación tardía, solo por `service.py` ajeno), `sync/models.py` (catálogo), migración nueva. Frontend en `areas/admin/stock/`, `features/stock/`, `domain/stock/`, `areas/ruta/` (inicio), `sync/` (entrega local, sobre, resultados, estado de jornada), `domain/ruta/`, `ayuda/textos.ts`. Fixtures en `shared/fixtures/`.
>
> **Lotes de apply (`design.md` D0 = A):** Lote 1 = grupos 1 a 3 (fixture, dominio, migración, modelos). Lote 2 = grupos 4 y 5 (entrega). Lote 3 = grupos 6 a 8 (puerta, rendición, tardíos). Lote 4 = grupos 9 a 11 (cierre con remanente, resumen, contratos). Lote 5 = grupos 12 a 16 (pantallas, teléfono, textos, ayuda). Lote 6 = grupos 17 a 23 (concurrencia, propiedades, ADR, docs, cobertura, suites, prueba manual). Un subagente nuevo por lote, en secuencia. **No se frena entre lotes**: el resumen de cada lote informa las comprobaciones automáticas y el usuario revisa con todo el change implementado.
>
> **Pruebas:** en cada lote solo las afectadas; las suites completas una sola vez, en 21.1. `pytest` por carpeta con `backend/.venv`; frontend con Docker detenido. Integración y concurrencia con PostgreSQL real (Testcontainers), las de concurrencia con commits reales. Skills del proyecto (`.agents/skills/`): `sqlalchemy-alembic-expert-best-practices-code-review` en los grupos 2 y 3; `architecture-patterns` para los archivos por área.

## 0. Aprobación (bloqueante)

- [x] 0.1 Decisiones: el usuario revisa D0 a D12 de `design.md` (**CRÍTICAS: D1 y D3**; ALTAS: D2, D4, D5, D7; de negocio: D0, D1, D2, D4, D5, D6, D7, D8, D10). Se anota el resultado en `design.md` y en ADR-068, y se ajustan proposal, specs y tareas si alguna opción cambia.
- [x] 0.2 Textos: el usuario aprueba, **sin ejemplos**, las claves nuevas `stock.entregaDelDia`, `stock.rendicion`, `stock.esperado`, `stock.diferenciaRendicion`, `stock.resumenJornada`, `stock.remanente` y `ruta.terminarDia` y las revisadas `stock.tomaActual` y `ruta.sincronizar` (D12); los textos de D11 (`JORNADA_RENDIDA`, rechazos de la entrega con «Avisá a tu supervisor.», `JORNADA_SIN_ENTREGA`, `CONTEO_INCOMPLETO`, `ESPERADO_DIFIERE`, `UBICACION_CON_TOMA`); en el teléfono «Terminar el día», «¿Terminar el día? Después no vas a poder vender, anular ventas ni cobrar en esta jornada.», «Terminaste el día. Pasá a rendir con tu supervisor.», «Lo que falta enviar se envía antes de la entrega.» y «Entrega del día» (D10); en `/admin` «Entregada por el vendedor a las {hora}.», «El vendedor todavía no terminó el día en el teléfono.», «Rendición de {ubicación}», «Producto», «Esperado», «Contado», «Diferencia», «Agregar producto», «Observación», «Registrar rendición», «¿Registrar la rendición con {N} diferencias?», «¿Registrar la rendición sin diferencias?», «Resumen de la jornada», «Al abrir», «Ingresos», «Ventas», «Anulaciones», «Otros», «Valor de la diferencia», «Ventas: {n} por {total}», «Anuladas: {n} por {total}», «Cobranzas por medio de pago», «Cobranzas anuladas», «Llegaron después de la rendición», «Esta jornada no tiene conteo.», «Cerrar jornada», «Vas a cerrar la jornada de {ubicación} y liberar la ubicación.», «Devolver el remanente a», «Cantidad a devolver» y «Se transfieren {N} productos a {destino}.» (D4, D8, D9).
  - **2026-11-05: el usuario aprobó los textos no literales del apply tal como están en el código.** Aprobados: «No se pudo terminar el día. Probá de nuevo.»; «¿Terminar el día?» (título + cuerpo); «Se transfiere 1 producto a {destino}.»; «No tenés permiso para rendir jornadas.»; «La observación admite hasta {LIMITE} caracteres.»; «Esperado actualizado»; «Cajas» / «Unidades» / «Unidades base»; «Sin cobranzas.»; «No devolver el remanente»; «Ver transferencia»; «Indicá la cantidad que se devuelve de al menos un producto.»; «No hay stock suficiente para devolver esa cantidad.»; «Falta contar algún producto.» (reserva); «Total: …»; «Cargando el remanente…»; «No pudimos leer el remanente para precargar la devolución. Cerrá y volvé a abrir el diálogo.»; «Ver kardex de…»; «Buscar producto»; «Nombre o código»; «Elegí un producto»; y los genéricos (Cancelar, Confirmar, Cargando…, Volver…, errores de lectura, aria-labels, «Producto {id}»). Correcciones hechas ese día: el selector de la rendición dice «Agregar producto» (antes «Producto a agregar»); la entrega rechazada en «Sincronización» del teléfono ya no muestra el código crudo (queda el texto aprobado y «Avisá a tu supervisor.»); `JORNADA_RENDIDA` no necesita texto en `/admin` (es observación que solo llega al teléfono).

## 1. Fixture compartido y dominio puro (Lote 1)

- [x] 1.1 Crear `shared/fixtures/calculo/rut-06-rendicion.json` **antes** del cálculo (D2, D4; cita RUT-06, RUT-07, STK-04, INV-04): casos de conjunto a contar (saldo distinto de cero, movimiento en la ventana aunque el saldo sea cero), esperado = al abrir + ingresos − ventas + anulaciones + otros, diferencia con signo, sobrante fuera del conjunto, faltante de un producto, conteo vacío, `CONTEO_INCOMPLETO`, `PRODUCTO_REPETIDO`, `CANTIDAD_INVALIDA` y `ESPERADO_DIFIERE`, con los valores de las specs (Vino A 10 + 36 − 8 + 2 = 40; 37 contadas, −3).
- [x] 1.2 RED en `backend/tests/unit/stock/test_dominio_rendicion.py` y `backend/tests/fixtures_compartidos/test_rut06_rendicion.py` (spec `stock/rendicion-de-jornada`, «La rendición exige la entrega y el conteo físico» y «Las diferencias de la rendición quedan en el libro», escenarios de dominio; cita RUT-06, INV-04): funciones puras de `stock/domain/rendicion.py` que validan el conteo contra el conjunto y los esperados y devuelven las líneas y las diferencias; errores de dominio con código estable. GREEN.
- [x] 1.3 RED en `frontend/tests/unit/calculo/rendicion.test.ts` (mismo fixture; cita RUT-06): `domain/stock/rendicion.ts` calcula la diferencia de cada línea y detecta los faltantes del conjunto para la pantalla. GREEN.

## 2. Migración (Lote 1)

- [x] 2.1 RED en `backend/tests/integration/test_rendicion_migracion.py` (D1, D4, D5, D7; cita INV-02, INV-05, INV-21): la revisión nueva (sobre el head actual) crea `rendicion` y `rendicion_linea` con FK compuestas, `UNIQUE (organizacion_id, jornada_id)`, `UNIQUE (rendicion, producto)`, `CHECK` de diferencia y de esperado, `cantidad_contada >= 0`, `costo_unitario numeric(18,6)` nulable; agrega a `jornada` `entregada_en`, `entrega_occurred_at`, `entrega_secuencia` con su `CHECK` de coherencia; rehace el `CHECK` de `observacion.codigo` con `JORNADA_RENDIDA`; `app_runtime` con `SELECT, INSERT` en las dos tablas (sin `UPDATE` ni `DELETE`) y `UPDATE` solo de las tres columnas nuevas de `jornada`; sube y baja limpia sobre una base con datos y el `downgrade` aborta con mensaje claro si hay rendiciones o entregas. GREEN.

## 3. Modelos (Lote 1)

- [x] 3.1 RED en `backend/tests/integration/test_rendicion_modelos.py` (cita INV-05): modelos `Rendicion` y `RendicionLinea` en `stock/models.py`, columnas nuevas de `Jornada`, carga de relaciones explícita; `UPDATE`/`DELETE` de `app_runtime` rechazados por la base. GREEN.

## 4. Entrega del día: handler (Lote 2)

- [x] 4.1 Red de seguridad: suites de jornadas y del lote. RED en `backend/tests/integration/test_jornada_entregar.py` (spec `stock/rendicion-de-jornada`, «La entrega del día marca la jornada como entregada», sus seis escenarios; D1; cita RUT-05, RUT-09, INV-06, INV-21): `JORNADA_ENTREGAR` v1 en `stock/jornadas_commands.py` (declarado `OFFLINE` solo, `ABRIR_JORNADA`), caso de uso en `jornadas_casos.py` con la jornada `FOR UPDATE`; `JORNADA_ESTADO_INVALIDO`, `JORNADA_YA_ENTREGADA`, `JORNADA_AJENA`, `PERMISO_REQUERIDO`; doble envío. GREEN.

## 5. Entrega por el lote (Lote 2)

- [x] 5.1 RED en `backend/tests/integration/test_entrega_por_lote.py` (spec `sync/lote-de-comandos`, sus cinco escenarios; D1; cita RUT-05, SYN-03, SYN-06, INV-06): entrega detrás de ventas y cobranza; error transitorio anterior la deja sin procesar; un rechazo anterior no la impide; `ONLINE` rechazado; doble sincronización. GREEN (sin cambios en el lote si no hace falta; si hiciera falta cambiar el orden del lote, **detenerse y consultar**).

## 6. La puerta del libro (Lote 3)

- [x] 6.1 Red de seguridad: suites del libro, de la toma y de costeo. RED en `backend/tests/integration/test_libro_diferencia_rendicion.py` y `test_toma_rendicion.py` (specs `stock/libro-de-stock` y `stock/toma-de-ubicacion`, sus seis escenarios; D3, D5; cita CST-12, CST-13, STK-05, STK-09, INV-03, INV-01): `registrar_movimientos` admite `DIFERENCIA_RENDICION` solo con origen `RENDICION`, al promedio vigente sin recalcular (`aplicar_ingreso_sin_recalculo` para el positivo), costo nulo sin promedio, nunca negativo; parámetro `rendicion_de_jornada` que falla cerrado y deja `jornada_id`; la excepción no alcanza a `STOCK_TRANSFERIR`. GREEN.

## 7. Rendición con conteo (Lote 3)

- [x] 7.1 Verificado: el bus resuelve el handler antes de la idempotencia, así que con v1 sin registrar, un `JORNADA_RENDIR` v1 (nuevo o reenviado) responde `VERSION_DE_COMANDO_SIN_HANDLER` (D2; aceptado por el usuario el 2026-11-04, sin tocar el bus). Prueba que lo afirma, incluido el reenvío de un `operation_id` ya aceptado, en `test_jornada_rendir_v2.py`.
- [x] 7.2 RED en `backend/tests/integration/test_jornada_rendir_v2.py` (spec `stock/rendicion-de-jornada`, «La rendición exige la entrega y el conteo físico» y «Las diferencias de la rendición quedan en el libro», sus diecisiete escenarios; spec `stock/jornadas`, el requisito modificado; D2, D3, D5; cita RUT-05, RUT-06, INV-01, INV-04, INV-05, INV-06, INV-12, INV-21): `JORNADA_RENDIR` v2 en `stock/rendicion_commands.py` y `rendicion_casos.py`: ubicación `FOR UPDATE`, jornada `FOR UPDATE`, entrega, conjunto a contar y esperados por SQL en la ventana, `CONTEO_INCOMPLETO`, `ESPERADO_DIFIERE`, sobrante, `PRODUCTO_INACTIVO`, rendición y líneas con sus componentes congelados y el costo, una llamada a la puerta, `EN_RENDICION`; v1 retirada; falla inyectada no deja nada. Ruta `POST /api/v1/stock/jornadas/{id}/rendicion` con el contenido v2. GREEN.
- [x] 7.3 Actualizar las pruebas del change 15 que usan `JORNADA_RENDIR` v1 para que entreguen y rindan con v2, sin cambiar lo que verifican (red de seguridad de `test_jornadas_*`).

## 8. Lo que llega con la jornada rendida (Lote 3)

- [x] 8.1 RED en `backend/tests/integration/test_jornada_rendida_observacion.py` (spec `sync/observaciones`, sus cuatro escenarios; D7; cita SYN-05, SYN-07, INV-17, INV-06, VTA-24): `JORNADA_RENDIDA` en el catálogo de `sync/models.py`; la venta, la anulación y la cobranza sin conexión con la jornada `EN_RENDICION` o `CERRADA` se aceptan con la observación (detalle: jornada y momento), sin perder las que ya llevaban; doble envío. GREEN en `ventas/service.py` y `cobranzas/service.py` leyendo el estado por `stock/service.py`.
- [x] 8.2 RED ampliando `backend/tests/unit/test_fixture_codigos_de_sincronizacion.py` (D11; cita SYN-06, SYN-07): `JORNADA_RENDIDA` en `observaciones`, `observaciones_de_anulacion` y `observaciones_de_cobranza`; `rechazos_de_entrega` con códigos reales. GREEN ampliando `shared/fixtures/sync/codigos-de-sincronizacion.json`.

## 9. Cierre con remanente (Lote 4)

- [x] 9.1 RED en `backend/tests/integration/test_jornada_cerrar_v2.py` (spec `stock/rendicion-de-jornada`, «El cierre puede devolver el remanente», sus seis escenarios; spec `stock/toma-de-ubicacion`, «La devolución del cierre sale del vehículo tomado»; D3, D6; cita RUT-08, STK-07, STK-09, INV-01, INV-06, INV-16): `JORNADA_CERRAR` v2 con `devolucion` opcional; ubicación `FOR UPDATE` y jornada `FOR UPDATE`; transferencia común por `stock_service.transferir` con la excepción de la rendición; `UBICACION_CON_TOMA`, `UBICACIONES_IGUALES`, `STOCK_INSUFICIENTE` sin excepción, `TRANSFERIR_STOCK` exigido solo con devolución; la transferencia se anula con `STOCK_TRANSFERENCIA_ANULAR`; v1 sigue igual. GREEN.

## 10. Resumen (Lote 4)

- [x] 10.1 RED en `backend/tests/integration/test_resumen_de_jornada.py` (spec `stock/rendicion-de-jornada`, «El resumen de la jornada cuadra y se congela al rendir», sus ocho escenarios; D4, D8; cita RUT-07, STK-04, COB-01, COB-05, INV-03, INV-21, ADR-066): `GET /api/v1/stock/jornadas/{id}/resumen` con SQL en la base (ventana por registro; congelado tras rendir; ventas, anuladas por `venta_anulacion.jornada_id`, cobranzas por medio y anuladas, lo tardío aparte; valor solo con `VER_COSTOS`; sin conteo; ajena 404). Lecturas de `ventas` y `cobranzas` por su `service.py`. GREEN.
- [x] 10.2 RED en la prueba de lecturas de catálogo (D9; cita `01` §19): la lista de productos activos para agregar un sobrante se abre, solo en lectura, a `RENDIR_JORNADA`. GREEN.

## 11. Contratos y límites (Lote 4)

- [x] 11.1 Ratchets y límites: `lint-imports` (los archivos `rendicion_*` no importan `service.py` propio; `ventas` y `cobranzas` solo por `stock/service.py`), el catálogo de tipos (`JORNADA_ENTREGAR` solo `OFFLINE`, `JORNADA_RENDIR` sin v1), el ratchet de motivos de auditoría (la rendición no lleva motivo) y los tipos del cliente generados desde el OpenAPI (`npm run typecheck`).

## 12. Pantalla de conteo (Lote 5)

- [x] 12.1 Red de seguridad: suites de `JornadaDetalleScreen` y `features/stock`. RED en `frontend/tests/unit/areas/admin/stock/RendicionScreen.test.tsx` (D2, D9, D11; cita RUT-05, RUT-06, CAT-08, INV-04): `/admin/stock/jornadas/:id/rendicion` con esperado en cajas y unidades, contado, diferencia al escribir, «Agregar producto», observación, confirmación con y sin diferencias, `ESPERADO_DIFIERE` que recarga y marca, `CONTEO_INCOMPLETO` con los productos; reutiliza el `operation_id` en el reintento. GREEN.

## 13. Detalle, resumen y cierre en `/admin` (Lote 5)

- [x] 13.1 RED en `JornadaDetalleScreen.test.tsx` y `ResumenDeJornada.test.tsx` (D4, D8, D9; cita RUT-05, RUT-07, RUT-08, `01` §19): la entrega o su falta, «Rendir» deshabilitado sin entrega, el resumen con sus columnas y el dinero, lo tardío aparte, «Esta jornada no tiene conteo.», el valor solo con `VER_COSTOS`; el diálogo de cierre con «Devolver el remanente a» precargado, solo con `TRANSFERIR_STOCK`. Sin importes calculados en el frontend salvo con `decimal.js` para mostrar. GREEN.

## 14. «Terminar el día» en el teléfono (Lote 5)

- [x] 14.1 Red de seguridad: suites de `sync/`, inicio y `estadoDeJornada`. RED en `frontend/tests/unit/sync/terminarDia.test.ts` (spec `ruta/area-de-ruta`, «Terminar el día sin señal», «Falla al terminar el día» y «Doble toque»; D1, D10; **cita INV-01**, INV-06, SYN-03): con `fake-indexeddb`, una transacción encola `JORNADA_ENTREGAR` `OFFLINE` con la siguiente secuencia y guarda la marca `ENTREGADA` en `meta`; falla inyectada no deja nada; reconfirmar no encola otra. Sin versión nueva de Dexie. GREEN en `sync/` (`sobre.ts`, nuevo `terminarDia.ts`) y `sync/estadoDeJornada.ts`.
- [x] 14.2 RED en las pruebas del inicio, la ficha, Vender, Anular y Cobrar (spec `ruta/area-de-ruta`, «La marca sobrevive a la recarga» y «Sin permiso»; D10; cita RUT-05, SEG-06): «Terminar el día» con permiso, confirmación, corte de las tres acciones con los avisos, también tras recargar. GREEN en `InicioScreen.tsx` y `domain/ruta/avisoDeJornada.ts`.

## 15. Resultado de la entrega y textos (Lote 5)

- [x] 15.1 RED en `aplicarResultados.test.ts`, `textosDeSincronizacion.test.ts` y la prueba de «Sincronización» (spec `ruta/area-de-ruta`, «Entrega rechazada» y «Doble sincronización de la entrega»; D11; cita SYN-06, SYN-07, SYN-09, INV-06): el resultado de la entrega se escribe en la cola; «Entrega del día» con su texto; `JORNADA_RENDIDA` traducida en ventas, anulaciones y cobranzas. GREEN.

## 16. Ayuda (Lote 5)

- [x] 16.1 RED en la prueba de claves de ayuda (spec `sistema/ayuda-contextual`, sus cuatro escenarios; D12; ADR-051): las siete claves nuevas existen y las dos revisadas tienen los textos aprobados en 0.2, sin ejemplos, y todo ID citado existe (ADR-068 ya existe como *Propuesto*). GREEN en `ayuda/textos.ts` y en las pantallas.

## 17. Concurrencia (Lote 6)

- [x] 17.1 RED en `backend/tests/concurrency/test_rendicion_concurrente.py` (spec `stock/rendicion-de-jornada`, «La rendición se serializa con los movimientos de su ubicación», sus dos escenarios; D3; cita INV-01, INV-12, INV-16, `02` §7.3), con commits reales: rendición contra venta sin conexión de la misma jornada; rendición contra liberación; dos rendiciones; cierre con devolución contra una transferencia al mismo depósito; entrega contra liberación. Sin interbloqueos ni efectos dobles. GREEN si hace falta.

## 18. Propiedades (Lote 6)

- [x] 18.1 RED en `backend/tests/properties/test_rendicion_propiedades.py` (spec «El stock cuadra con lo contado» y «El resumen cuadra»; cita INV-12, INV-05, RUT-07): para secuencias aleatorias de cargas, ventas, anulaciones y una rendición, con SQL, el stock de cada producto contado es lo contado y la suma de sus movimientos, el resumen cuadra y los libros solo crecen. GREEN si hace falta.

## 19. ADR (Lote 6)

- [x] 19.1 Completar `docs/adr/ADR-068-rendicion-de-jornada.md` (borrador *Propuesto* creado con la propuesta) con lo aprobado en 0.1 y las precisiones del apply.

## 20. Propuesta de docs (Lote 6)

- [x] 20.1 Completar `openspec/changes/24-rendicion-de-jornada/propuesta-docs.md` con las precisiones del apply. **No se aplica a `docs/`** sin el visto bueno del usuario. Al aplicarla, verificar que las filas de `01` conserven `| ID |` y `| etapa |`.

## 21. Cobertura y suites completas (Lote 6)

- [x] 21.1 Cada escenario de las ocho specs delta tiene al menos una prueba que lo nombra (`frontend/tests/unit/cobertura/escenariosDe24.test.ts`, como en el 23, con los del servidor por archivo); INV-01, INV-03, INV-04, INV-05, INV-06, INV-12, INV-16, INV-17 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). Suites completas (backend unit, integration, concurrency, properties y fixtures compartidos; frontend Vitest), `ruff`, `mypy`, `lint-imports`, `typecheck`, `lint` y `build` en verde, sin `skip` ni `xfail` sin justificación. `04` §2.1 punto 4: la migración sube y baja limpia sobre una base con datos (2.1).

## 22. Prueba de integración del servidor (Lote 6)

- [x] 22.1 Repasar que las pruebas de los grupos 4 a 10 corren juntas con la suite completa (orden y limpieza de datos), que las de jornadas, ventas sin conexión y cobranzas sin conexión de los changes 15, 22d y 23 siguen igual salvo lo ajustado en 7.3, y que los fixtures de `shared/fixtures/sync/` se aceptan.

## 22b. Acceso al kardex con saldo 0 (agregado aprobado 2026-11-05)

- [x] 22b.1 RED en `frontend/tests/unit/areas/admin/stock/StockPorUbicacionScreen.test.tsx`: «Ver kardex de…» visible siempre (ubicación vacía y con stock), ofrece productos activos e inactivos, «Buscar producto» filtra en el servidor, y sin permiso de lectura del catálogo no se ofrece ni se pide la lista. GREEN con `SelectorDeKardex.tsx` en `StockPorUbicacionScreen`. Solo frontend; sin texto de ayuda nuevo.

## 23. Prueba manual (Lote 6)

- [x] 23.1 Probar a mano el flujo principal y dar al usuario el paso a paso en el chat (sin archivo aparte), con los usuarios de desarrollo existentes (`admin`, `sup01`, `vendedor`), en el build con el perfil `lan` en https://localhost: `admin` carga "Camioneta 1" desde el depósito; `vendedor` abre la jornada en `/ruta`, vende, anula una venta y cobra, parte sin señal; sin señal toca «Terminar el día», ve el corte y los avisos; `sup01` ve «El vendedor todavía no terminó el día en el teléfono.» y «Rendir» deshabilitado; vuelve la señal, se envía todo y aparece la entrega; `sup01` cuenta con un faltante y un sobrante, ve las diferencias y el resumen (stock, ventas, anuladas, cobranzas por medio), cierra devolviendo el remanente al depósito y ve la transferencia; `admin` ve el kardex con `DIFERENCIA_RENDICION` y el valor de la diferencia. No se crea un archivo de verificación. Verificable: `04` §2.1 punto 5.
