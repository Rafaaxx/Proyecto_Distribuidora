# Tareas — 19-venta-anulacion

> Modo TDD estricto: en cada tarea de los grupos 1 a 13, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como **red de seguridad** y se anota la línea base; una falla previa se informa y no se arregla de paso. **Las tareas siguen la opción A de cada decisión de `design.md` (pendientes de aprobación, tarea 0.1); si el usuario elige otra, se revisan specs, tareas y ADR-058 antes de empezar.**
>
> **Dónde va el código:** dominio puro de la anulación en `backend/app/modules/ventas/domain/anulacion.py` y `frontend/src/domain/ventas/anulacion.ts` (D17); transacción en `ventas/service.py::anular_venta` y `ventas/repository.py`; comando en `ventas/commands.py`; ruta en `ventas/api.py`; cobranza en `cobranzas/service.py` (`tomar_cobranza_de_venta`, `anular_cobranza_de_venta`, D9); reingreso en `stock/domain/movimientos.py` y `stock/service.py` (D5, D7). Ningún módulo importa modelos ni repositorios ajenos; `ventas ──► cobranzas, stock, cuentas_corrientes, configuracion` ya está permitido (`02` §5.3), así que `lint-imports` no cambia de contratos.
>
> **Lotes de apply (cuatro, `design.md` D0):** Lote 1 = grupos 1 y 2 (fixtures y dominio puro). Lote 2 = grupos 3 a 6 (migración, modelos, siembra, stock, cobranzas). Lote 3 = grupos 7 y 8 (**CRÍTICO**: comando, transacción, auditoría, lecturas). Lote 4 = grupos 9 a 16 (pantallas, ayuda, concurrencia, propiedades, cobertura, ADR, docs y prueba manual). **No se frena entre lotes**: el usuario revisa con todo el change implementado, salvo en los puntos de control.
>
> **Puntos de control (se detiene y se espera la respuesta del usuario):** **0.1** (decisiones D0 a D19, con aprobación explícita de las críticas y altas y de los códigos nuevos), **0.2** (textos de ayuda; bloquea solo el grupo 10) y **7.1** (borrador del orden de la transacción y de la precedencia de rechazos, D10, CRÍTICO). Cualquier ampliación de alcance que aparezca durante el apply se detiene y se consulta.
>
> **Pruebas:** en cada lote se corren solo las pruebas afectadas; las suites completas, una sola vez, en 13.1. `pytest` por carpeta con `backend/.venv`; las de frontend, con Docker detenido. Fixtures compartidos **antes** del código (grupo 1).
>
> **Gobernanza:** MEDIA/ALTA (dinero y libros). Crítica: D10. Altas: D1, D4, D5, D6, D9, D14, D15, D19.

## 0. Aprobación (bloqueante)

- [x] 0.1 **Punto de control.** *(Aprobado por el usuario el 2026-10-24: D0 a D19 en la opción A, incluidos D4 tras aclarar que con cobro quedan las dos opciones —devolver o dejar a favor—, el filtro por estado, los motivos de D12 y los tres códigos nuevos.)* El usuario aprueba D0 a D19 de `design.md` (opción por decisión), con aprobación explícita de la crítica (D10) y de las altas (D1, D4, D5, D6, D9, D14, D15, D19), de las de negocio (D2, D3, D4, D5, D6, D7, D12, D13), del alcance extra (filtro por estado, D14), de los nombres de los motivos (D12) y de los códigos nuevos: `VENTA_YA_ANULADA` (409), `DEVOLUCION_INVALIDA` (422), `CONSUMIDOR_FINAL_SIN_DEVOLUCION` (409). Se anota fecha y opción en cada decisión y en ADR-058; si alguna cambia, se revisan specs, tareas y `propuesta-docs.md` antes de seguir.
- [x] 0.2 **Punto de control.** *(Aprobado el 2026-10-24: los seis textos y la revisión de `cobranzas.anulacion` tal como están en D18, sin ejemplos.)* El usuario revisa los seis textos de D18 y la revisión de `cobranzas.anulacion`. Se anota fecha y lo elegido. Bloquea solo el grupo 10.

## 1. Fixtures compartidos (Lote 1)

- [x] 1.1 Red de seguridad: `python -m pytest backend/tests/fixtures_compartidos/` y `npm run test -- tests/unit/calculo` en verde; anotar la línea base. Sumar a `shared/fixtures/calculo/cst-11-costo-promedio.json` los casos de anulación de venta (spec `costeo/costo-promedio`): el ejemplo de D5 (108 a $1.133,333333 + 72 a $1.050 → $1.100,000000); stock total previo 0; stock total previo −5; línea sin costo (no recalcula). Citan CST-11, CST-13, VTA-21.
- [x] 1.2 Escribir `shared/fixtures/calculo/vta-22-anulacion.json` (`"motor": "vta22"`) con el efecto en la cuenta (D4, D17): sin cobro ($150.000 + $80.000 → $150.000); cobro $20.000 con devolución ($150.000) y sin ($130.000); cobro mayor que el total; consumidor final ($4.300, saldo 0). Cada caso trae los movimientos esperados (`ANULACION_VENTA`, `ANULACION_COBRANZA`) y el saldo final, como string. Citan VTA-21, VTA-22, INV-19.
- [x] 1.3 RED: `backend/tests/fixtures_compartidos/test_vta22_anulacion_fixtures.py` y `frontend/tests/unit/calculo/vta22.fixtures.test.ts` descubren los casos `vta22` (fallan si no hay ninguno) y los corren contra un dominio que todavía no existe; los casos nuevos de `cst-11` corren con los cargadores existentes y pasan o fallan donde corresponda. Verificable: fallan por el dominio ausente, no por el cargador.

## 2. Dominio puro de la anulación (Lote 1)

- [x] 2.1 GREEN en `backend/app/modules/ventas/domain/anulacion.py` (spec `ventas/anulacion-de-venta`): `validar_venta_anulable(estado)` (`VENTA_YA_ANULADA`); `validar_devolucion(tiene_cobranza, devuelve_dinero, es_consumidor_final)` (`DEVOLUCION_INVALIDA`, `CONSUMIDOR_FINAL_SIN_DEVOLUCION`, D2, D3); `efecto_en_cuenta(total, importe_cobranza, devuelve)` (D4, casos `vta22`); `lineas_de_reingreso(lineas)` (una por línea, en su orden, con `costo_unitario` o nulo, D5). Errores nuevos en `ventas/domain/errores.py`. TRIANGULATE en `backend/tests/unit/test_ventas_domain_anulacion.py` más allá de los fixtures (dos casos por regla; precedencia de D10 entre estado y devolución). `domain/` sin FastAPI ni SQLAlchemy.
- [x] 2.2 GREEN en `frontend/src/domain/ventas/anulacion.ts` con `decimal.js` (gemela de `efecto_en_cuenta` y de "¿se pregunta por el dinero?", D16); pasa `vta22.fixtures.test.ts`. TRIANGULATE en `frontend/tests/unit/domain/ventas/anulacion.test.ts`. Ningún importe pasa a `number` salvo para formatear.

## 3. Migración (Lote 2)

- [x] 3.1 Red de seguridad: `tests/integration/test_alembic_integracion.py` y las pruebas de privilegios (INV-05); anotar la línea base. RED (citan INV-05, INV-02, VTA-20, `04` §2.1 punto 4): existe `venta_anulacion` con sus columnas, FK compuestas, `UNIQUE (organizacion_id, venta_id)` e índice (D11); `app_runtime` tiene `SELECT, INSERT` en `venta_anulacion`, `UPDATE` solo de `venta.estado` y ningún `DELETE`; los motivos de `ANULACION_VENTA` se siembran una vez en las organizaciones sin ninguno; la migración baja y vuelve a subir sobre una base con ventas confirmadas; el `downgrade` aborta con mensaje claro si hay una venta `ANULADA`.
- [x] 3.2 GREEN: revisión Alembic nueva sobre `c8d9e0f1a2b3` (D11, D12). `alembic upgrade head` y `downgrade -1` limpios.

## 4. Modelos y siembra (Lote 2)

- [x] 4.1 RED/GREEN: modelo `VentaAnulacion` en `ventas/models.py` (sin `relationship()`); actualizar el docstring de `Venta` (el `UPDATE` de `estado` ya existe). Siembra de los motivos de D12 para organizaciones nuevas en el lugar donde se siembran los demás ámbitos. Pruebas: organización nueva con los tres motivos; `GET /configuracion/motivos?ambito=ANULACION_VENTA` devuelve solo los activos de la organización (spec `organizacion/catalogos-configurables`; citan VTA-20, TR-09, INV-21).

## 5. Libro de stock (Lote 2)

- [x] 5.1 Red de seguridad: suites de `stock` y `costeo` (unitarias e integración del libro). RED en `backend/tests/unit/test_stock_domain_movimientos.py` y `backend/tests/integration/test_stock_anulacion_venta.py` (spec `stock/libro-de-stock`; citan STK-03, CST-11, CST-12, CAT-05, STK-09, ADR-058): ingreso `ANULACION_VENTA` con costo recalcula y deja historia; sin costo sube el stock total sin recalcular y sin historia, con costo nulo; cantidad negativa rechazada; producto inactivo aceptado solo para `ANULACION_VENTA`; ubicación inactiva rechazada; ubicación tomada sin `LIBERAR_UBICACION` rechazada con `UBICACION_TOMADA`. GREEN en `stock/domain/movimientos.py` y `stock/service.py` (D5, D7). Verificable: los casos `cst-11` de anulación de venta pasan contra el servicio real.

## 6. Cobranza de la venta (Lote 2)

- [x] 6.1 Red de seguridad: suites de `cobranzas`. RED en `backend/tests/integration/test_cobranzas_anular_de_venta.py` (spec `cobranzas/anulacion-de-cobranzas`; citan VTA-22, COB-05, CC-02, INV-05, INV-13): `tomar_cobranza_de_venta` toma `FOR UPDATE` la cobranza de origen `VENTA` (o `None`); `anular_cobranza_de_venta` la deja `ANULADA`, con su anulación con el motivo de la venta y `ANULACION_COBRANZA` por el importe completo; una cobranza ya anulada responde `COBRANZA_YA_ANULADA`; `COBRANZA_ANULAR` sigue respondiendo `COBRANZA_DE_VENTA`. GREEN en `cobranzas/service.py` y `cobranzas/repository.py` (D9), sin validar el ámbito `ANULACION_COBRANZA` en este camino.

## 7. Comando y transacción (Lote 3, CRÍTICO)

- [x] 7.1 **Punto de control CRÍTICO (D10).** *(Aprobado por el usuario el 2026-10-27: orden y precedencia de D10 opción A tal como están en design.md.)* Antes de escribir el servicio, mostrar al usuario el borrador del orden de `anular_venta` (venta `FOR UPDATE` → cobranza `FOR UPDATE` → motivo y devolución → `saldo_cuenta` → stock → escrituras → auditoría) y la precedencia de rechazos, contrastado con `02` §7.3 y con `COBRANZA_ANULAR` y `COMPRA_ANULAR`. Sin código antes de su confirmación.
- [x] 7.2 RED en `backend/tests/integration/test_ventas_anular.py` (spec `ventas/anulacion-de-venta`, un caso por escenario; citan VTA-20, VTA-21, VTA-22, INV-01, INV-06, INV-10, INV-13, INV-19, INV-21, CLI-03, STK-09): sin cobro; con y sin devolución con el ejemplo de `01` §9.2; cobro mayor; `DEVOLUCION_INVALIDA` en los dos sentidos; consumidor final; `VENTA_YA_ANULADA`; doble envío; 403 sin `ANULAR_VENTA`; `MOTIVO_INVALIDO`; `OBSERVACION_INVALIDA`; 404 de otra organización (venta y motivo); valores congelados intactos; ubicación tomada (`ges01`-like sin `LIBERAR_UBICACION`, y supervisor con la constancia); jornada propia abierta; venta de jornada cerrada; ubicación inactiva; producto y cliente inactivos; línea sin costo; dos líneas del mismo producto; falla inyectada después de cada efecto; precedencia; `OFFLINE` en el lote rechazado.
- [x] 7.3 GREEN en `ventas/service.py::anular_venta` y `ventas/repository.py` (lectura sin bloquear, `FOR UPDATE`, inserción de `venta_anulacion`, `UPDATE` de estado) según el orden aprobado en 7.1; jornada de la anulación (D8) desde el resultado del movimiento.
- [x] 7.4 GREEN en `ventas/commands.py`: `VentaAnularContenidoV1` (`extra="forbid"`, `devuelve_dinero: StrictBool | None`), `manejar_venta_anular` sin `commit`, `registrar_handler("VENTA_ANULAR", 1, …)` y `declarar_tipo("VENTA_ANULAR", admite_online=True, admite_offline=False, permisos=("ANULAR_VENTA",))` (D1, D19). Resultado con importes como string (INV-03). Prueba en `tests/unit/test_catalogo_tipos_permisos.py` y en el ratchet de rutas (spec `sistema/pipeline-de-comandos`).
- [x] 7.5 GREEN en `ventas/api.py`: `POST /api/v1/ventas/{venta_id}/anulacion` con `requiere_permiso("ANULAR_VENTA")`, endpoint síncrono, `organizacion_id` del token; Problem Details con los códigos nuevos. Pruebas REST de 200 (como `POST /cobranzas/{id}/anulacion`), 403, 404, 409 y 422.
- [x] 7.6 Auditoría (D15): RED en `tests/integration/test_ventas_anular_auditoria.py` (citan AUD-01, AUD-02, SYN-08): una fila `VENTA_ANULAR` con motivo, usuario, dispositivo y `operation_id`; observación con la cobranza anulada y con la constancia de ubicación tomada cuando corresponde; sin observaciones nuevas de SYN-07; las pendientes de la venta siguen pendientes. GREEN con `DatosDeAuditoria`.

## 8. Lecturas (Lote 3)

- [x] 8.1 RED en `backend/tests/integration/test_ventas_lecturas_anulacion.py` (spec `ventas/administracion-de-ventas`; citan VTA-20, VTA-22, REP-02, `01` §19, INV-21): el detalle trae el bloque `anulacion` (nulo si no está anulada) con nombres de usuario y motivo; `GET /ventas?estado=ANULADA` filtra y un valor fuera del catálogo es 422. GREEN en `ventas/queries.py`, `schemas.py` y `api.py`. Regenerar `openapi.json` y `frontend/src/api/schema.gen.ts`; `npm run typecheck` en verde.

## 9. Pantallas (Lote 4)

- [x] 9.1 RED en `frontend/tests/unit/ventas/` (Vitest, Testing Library): "Anular venta" solo con `ANULAR_VENTA` y la venta `CONFIRMADA`; el diálogo pide motivo, observación y, solo con cobranza confirmada, la devolución; consumidor final con la devolución fija; resumen del efecto con `domain/ventas/anulacion.ts`; errores `VENTA_YA_ANULADA`, `UBICACION_TOMADA`, `UBICACION_INACTIVA`, `MOTIVO_INVALIDO` con su texto. GREEN en `features/ventas/` (api, hooks con invalidación del detalle y del listado, errores) y `areas/admin/ventas/` (`DialogoDeAnulacion.tsx`, bloque "Anulación" en `VentaDetalleScreen.tsx`) (D16). Los componentes no calculan: usan el dominio.
- [x] 9.2 GREEN en `VentasListScreen.tsx`: filtro por estado (D14). Verificable: `typecheck`, `lint`, `build` y las pruebas de componentes de los escenarios de la spec.

## 10. Ayuda contextual (Lote 4)

- [x] 10.1 Cargar en `frontend/src/ayuda/textos.ts` las seis claves aprobadas en 0.2 (`ventas.anulacion`, `ventas.devolverDinero`, `ventas.motivoAnulacion`, `ventas.consumidorFinalAnulacion`, `ventas.reingresoUbicacion`, `ventas.costoAnulacion`, esta última solo con `VER_COSTOS`) y revisar `cobranzas.anulacion` (ADR-051; spec `sistema/ayuda-contextual`). Verificable: la prueba de trazabilidad en verde (ADR-058 debe existir en `docs/adr/`).

## 11. Concurrencia (Lote 4)

- [x] 11.1 RED en `backend/tests/concurrency/test_ventas_anulacion_concurrencia.py` (commits reales de sesiones independientes; citan INV-05, INV-12, INV-13, `02` §7.3): dos anulaciones simultáneas de la misma venta (una gana, la otra `VENTA_YA_ANULADA`, una sola fila); anulación con devolución y `COBRANZA_ANULAR` de su cobranza (una sola anulación); anulación y venta del mismo producto al mismo cliente (sin interbloqueo; stock y saldo iguales a sus movimientos); anulación y desactivación del producto; anulación y `JORNADA_ABRIR` sobre la ubicación de la venta (o la anulación termina antes, o ve la ubicación tomada). GREEN si hace falta. Una falla intermitente es una condición de carrera real: no se ignora.

## 12. Propiedades (Lote 4)

- [x] 12.1 RED en `backend/tests/properties/test_ventas_anulacion_propiedades.py` (Hypothesis): confirmar y anular con devolución deja, con SQL, el stock por producto y ubicación y el saldo del cliente iguales a los de antes, y los libros solo crecen (cita INV-19, INV-12, INV-13, INV-05); sin devolución el saldo difiere exactamente en el importe de la cobranza (cita VTA-22). GREEN si hace falta.

## 13. Cobertura y suites completas (Lote 4)

- [x] 13.1 Cada escenario de las specs delta tiene al menos una prueba que lo nombra; INV-01, INV-05, INV-06, INV-10, INV-12, INV-13, INV-19 e INV-21 tienen prueba que los cita por ID (`04` §2.1 puntos 2 y 3). **Única corrida completa del change:** unitarias, integración, concurrencia, propiedades y fixtures compartidos; `ruff check`, `ruff format`, `mypy app`, `lint-imports`, `typecheck`, `lint`, `test` y `build` en verde, sin `skip` ni `xfail` sin justificación.

## 14. ADR (Lote 4)

- [x] 14.1 Completar `docs/adr/ADR-058-anulacion-de-venta.md` (borrador del propose, *Propuesto*) con lo aprobado en 0.1 y 0.2 y las precisiones del apply; anotar en ADR-052 (punto 79) y ADR-054 (punto 4) que sus deudas quedaron saldadas y en ADR-044 la exención de producto inactivo de `ANULACION_VENTA`. Pasa a *Vigente* al archivar.

## 15. Propuesta de docs (Lote 4)

- [x] 15.1 Completar `openspec/changes/19-venta-anulacion/propuesta-docs.md` con el texto actual y el propuesto de cada sección afectada de `docs/01` a `docs/04` según lo aprobado (VTA-21, VTA-22, VTA-24, INV-19, CST-12, STK-09, §20, `02` §6.5 y §7.3, `03` §12 y §4, `04` §9 y deudas nuevas). **No se aplica a `docs/`** sin el visto bueno del usuario.

## 16. Prueba manual (Lote 4)

- [x] 16.1 *(Prueba manual ejecutada por el usuario el 2026-10-27: todo OK.)* El orquestador le da al usuario, **en el chat** (sin crear archivos), el paso a paso de la prueba manual en el navegador con los usuarios de prueba existentes (`admin`, `sup01`/supervisor, `vendedor`/`vendedor2`, `ges01`): `alembic upgrade head`; venta sin cobro y su anulación (stock y cuenta); venta con cobro anulada con y sin devolución (saldo $150.000 / $130.000 del ejemplo); consumidor final; `vendedor` sin botón; `ges01` frente a una camioneta tomada por la jornada de `vendedor2` (`UBICACION_TOMADA`) y `sup01` que la anula; segunda anulación; detalle y listado con el filtro "Anuladas"; estado de cuenta del cliente; kardex y promedio con `admin` (`VER_COSTOS`); la cobranza de la venta en Cobranzas, sin botón propio. El usuario la ejecuta y reporta.
