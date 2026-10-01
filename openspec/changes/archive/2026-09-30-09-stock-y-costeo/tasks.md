# Tareas — 09-stock-y-costeo

> Modo TDD estricto en la implementación: en cada tarea de los grupos 2 a 8, la prueba que falla se escribe antes que el código (RED → GREEN → TRIANGULATE → REFACTOR). El grupo 9 completa la cobertura por escenario e invariante, no la reemplaza. Las tareas están escritas con la opción A de cada decisión, aprobada el 2026-09-30 (tarea 0.1).

## 0. Aprobación

- [x] 0.1 (aprobada 2026-09-30, opción A en D1 a D15, sin cambios a proposal/specs/tareas) El usuario revisa y aprueba (o cambia) D1 a D15 de `design.md` (gobernanza ALTA: stock valorizado y costos); se anota la fecha y la opción elegida en cada decisión, y la resolución de la contradicción de D14 (`CLAUDE.md` §4 vs. spec `sistema/calculo-compartido`). Si alguna decisión cambia respecto de la recomendada, se actualizan proposal, specs y tareas con `/opsx:update`. Verificable: `design.md` sin decisiones "Pendiente".

## 1. Migración

- [x] 1.1 Crear la revisión de Alembic con `ubicacion`, `costo_producto`, `costo_producto_mov`, `stock_saldo` y `stock_movimiento` según `03` §7/§9 y `design.md` D7, D10, D12 y D13: `organizacion_id NOT NULL`, `UNIQUE (organizacion_id, id)` en tablas con `id`, PK compuestas que empiezan por `organizacion_id` en los saldos (ADR-035 punto 6), FK compuestas a `producto`, `ubicacion`, `usuario`, `dispositivo` y `motivo`, `jornada_id` sin FK, `ux_ubicacion__nombre`, `ck_ubicacion__vehiculo_requiere_toma`, `ck_stock_movimiento__cantidad_no_cero`, `CHECK` de catálogo de `tipo`/`origen_tipo`, `CHECK (costo_promedio IS NULL OR costo_promedio > 0)`, `integer` en cantidades, `numeric(18,6)` en costos, `timestamptz`, índices de `03` §9/§16 (kardex `(organizacion_id, producto_id, ubicacion_id, occurred_at, id)`, origen, `ix_stock_saldo__ubicacion`) y `GRANT` de ADR-020 (`SELECT, INSERT` en libros; `SELECT, INSERT, UPDATE` en saldos y `ubicacion`). `downgrade` elimina las cinco tablas. Verificable con `alembic upgrade head`/`downgrade -1` limpios y `tests/integration/test_stock_migracion.py` (RED antes de la migración).

## 2. Modelos y registro

- [x] 2.1 Declarar los modelos en `backend/app/modules/stock/models.py` y `backend/app/modules/costeo/models.py` iguales a la migración, sin carga diferida; registrar ambos módulos en `alembic/env.py` y `app/main.py`. Verificable con `alembic revision --autogenerate` sin diferencias.
- [x] 2.2 Contratos de import-linter: `stock.domain` y `costeo.domain` sin infraestructura; `costeo` sin módulos de negocio (salvo `identidad`/`auditoria` si hiciera falta); `stock` solo alcanza a `catalogo` y `costeo` por su `service.py` (`02` §5.3). Verificable con `lint-imports` en verde.

## 3. Fixtures compartidos de CST-11 (antes del cálculo)

- [x] 3.1 Agregar `shared/fixtures/calculo/cst-11-costo-promedio.json` (D14): ejemplo completo de `01` §6.2 (60 a $1.000 → $1.000; +60 a $1.100 → $1.050; egreso 72 → $1.050; +60 a $1.200 con 48 → $1.133,333333), stock previo cero y negativo, redondeo `ROUND_HALF_UP` a 6 decimales solo al final. Agregar `backend/tests/fixtures_compartidos/test_cst11_costo_promedio_fixtures.py` y `frontend/tests/unit/calculo/cst11.fixtures.test.ts` en RED. Verificable: ambas suites fallan por falta de implementación, no por formato.

## 4. Dominio

- [x] 4.1 `costeo/domain/`: función pura de CST-11 (ingreso) y de egreso (CST-12), con errores de dominio con código estable (`COSTO_INVALIDO`), usando `core/money.py::redondear_costo`. Verificable con `tests/unit/test_costeo_domain.py` y la suite de fixtures de 3.1 en verde en Python.
- [x] 4.2 `frontend/src/domain/costeo/costoPromedio.ts` con `decimal.js`/`lib/money.ts`, misma entrada y salida. Verificable con `npm run test -- tests/unit/calculo` en verde.
- [x] 4.3 `stock/domain/`: validación de ubicación (nombre normalizado, tipo, `VEHICULO_REQUIERE_TOMA`), de líneas de stock inicial (1 a 200, `PRODUCTO_REPETIDO`, cantidad entera ≠ 0, costo según signo, D5/D6), regla de corrección (`STOCK_INSUFICIENTE`, `PRODUCTO_CON_OPERACIONES`, D4) y de desactivación (`UBICACION_CON_STOCK`, D8), rango del kardex y cursor (D11). Verificable con `tests/unit/test_stock_domain.py` citando STK-02, STK-03, INV-04.
- [x] 4.4 Propiedad Hypothesis de dominio: aplicar movimientos uno por uno da la suma, independiente del orden, y el promedio de una secuencia de ingresos coincide con el cálculo ponderado exacto redondeado. Verificable con `tests/properties/test_inv12_stock_dominio.py` (cita INV-12 y CST-11).

## 5. Repositorios y servicios

- [x] 5.1 `costeo/repository.py` y `costeo/service.py` sin `commit` (D9, D10): `bloquear_costos` (orden por `producto_id`, fila perezosa `INSERT ... ON CONFLICT DO NOTHING` + `FOR UPDATE`), `aplicar_ingreso` (CST-11 + `costo_producto_mov` + `stock_total`), `aplicar_egreso`, `obtener_promedio`, `producto_tiene_movimientos_distintos_de`. Verificable con `tests/integration/test_costeo_service.py` contra PostgreSQL real.
- [x] 5.2 `stock/repository.py` y `stock/service.py` sin `commit`: ubicaciones (crear, modificar, D7/D8), `registrar_movimientos` (reúne pares, bloquea costos y luego saldos en orden, `UPDATE ... WHERE cantidad_base >= :q` en egresos), `registrar_stock_inicial` (D4, D5, D6; producto activo por `catalogo/service.py`), stock por ubicación, kardex con `SUM(...) OVER` (D11) y `verificar_consistencia` (saldo vs. libro, `stock_total` vs. saldos). Violaciones de FK → 404; desbordes → error de dominio. Verificable con `tests/integration/test_stock_service.py` y `test_repositorios_organizacion_obligatoria.py`.

## 6. Comandos

- [x] 6.1 Registrar `UBICACION_CREAR`, `UBICACION_MODIFICAR` y `STOCK_INICIAL_REGISTRAR` v1 (`ONLINE`, `admite_offline=False`, permisos de D1/D2) con esquemas Pydantic estrictos (`extra="forbid"`, costos como string, cantidades enteras) y handlers en `stock/commands.py` sin `commit`, pasando `sobre.dispositivo_id`; auditoría única del bus (ADR-022). Verificable con `tests/integration/test_stock_comandos.py`.

## 7. API y ratchets

- [x] 7.1 Rutas de escritura dedicadas en `stock/api.py` (`POST /api/v1/stock/ubicaciones`, `PUT /api/v1/stock/ubicaciones/{id}` (reemplazo completo; aprobado el 2026-09-30, ADR-038), `POST /api/v1/stock/iniciales`) mirando `cuentas_corrientes/api.py`: `Operation-Id` obligatorio, `sync_service.procesar_comando`, 403, 404, `COMANDO_INCONSISTENTE`, `def`. Verificable con `tests/integration/test_stock_api.py`.
- [x] 7.2 Rutas de lectura (D3, D11): `GET /api/v1/stock/ubicaciones`, `GET /api/v1/stock/ubicaciones/{id}/saldos`, `GET /api/v1/stock/kardex?producto_id&ubicacion_id` (costos omitidos sin `VER_COSTOS`) y, en `catalogo/api.py`, `GET /api/v1/catalogo/productos/{producto_id}/costo` (`VER_COSTOS`; catalogo resuelve el producto en la organización, 404 si es ajeno o inexistente, y llama a `costeo/service.py`; sin ingresos, 200 con `costo_promedio` nulo; enmienda D3 del 2026-09-30). Verificable con `tests/integration/test_stock_api.py` usando ADM y VEN.
- [x] 7.3 Alta de las rutas en `test_ratchet_permiso_por_ruta.py`, `COBERTURA_DE_AISLAMIENTO` de `test_inv21_ratchet_rutas.py` y confirmación en `test_bus_cobertura_rutas_de_escritura.py`; regenerar `backend/openapi.json` y `frontend/src/api/schema.gen.ts`. Verificable con los ratchets en verde y tipos actualizados.

## 8. Frontend

- [x] 8.1 `frontend/src/features/stock/` con cliente de API y hooks de TanStack Query (ubicaciones, saldos, kardex paginado, stock inicial, promedio vía `GET /api/v1/catalogo/productos/{producto_id}/costo`), `usePermisos()` y `decimal.js`. Verificable con `npm run typecheck`.
- [x] 8.2 Pantallas de ubicaciones (listado, alta, edición, activar/desactivar) con mensajes del servidor. Verificable con sus pruebas en `tests/unit/areas/admin/stock/`.
- [x] 8.3 Pantalla de stock por ubicación (CAT-08, promedio, leído de `GET /api/v1/catalogo/productos/{producto_id}/costo`, solo con `VER_COSTOS`) y de kardex (período, saldo anterior, "cargar más"). Verificable con sus pruebas.
- [x] 8.4 Formulario de stock inicial (D5, D15): varias líneas, cajas + unidades a base entera, `operation_id` por envío reutilizado en reintento, aviso de conexión requerida, previsualización del promedio con `costoPromedio.ts` solo con `VER_COSTOS`. Verificable con su prueba.
- [x] 8.5 `npm run typecheck`, `npm run lint`, `npm run test` y `npm run build` en verde.

## 9. Pruebas backend

- [x] 9.1 Integración por escenario de `specs/stock/stock-inicial` y `specs/stock/ubicaciones` (incluidos doble envío, `COMANDO_INCONSISTENTE`, sin `Operation-Id`, 403, 404, inactivos, contenido inválido, `OFFLINE` rechazado por el bus, correcciones de cantidad y costo, `PRODUCTO_CON_OPERACIONES` insertando otro tipo por el servicio). Verificable con `python -m pytest tests/integration/test_stock_comandos.py tests/integration/test_stock_api.py`.
- [x] 9.2 INV-12 con Hypothesis contra PostgreSQL real, más la falla inyectada a mitad de un comando de dos líneas (INV-01). Verificable con `python -m pytest tests/properties/test_inv12_stock_postgres.py` (cita INV-12).
- [x] 9.3 INV-04: cantidades enteras en el catálogo de columnas y rechazo de no enteros en la API. Verificable con `tests/integration/test_inv04_cantidades_enteras.py` (cita INV-04).
- [x] 9.4 INV-05: `stock_movimiento` y `costo_producto_mov` en `TABLAS_DE_LIBRO_DECLARADAS` de `test_inv05_dos_roles.py`, privilegios exactos y `UPDATE` sí sobre `stock_saldo`/`costo_producto`; prueba de que no hay rutas de edición del libro. Verificable con esas pruebas.
- [x] 9.5 INV-02/INV-21: `stock_saldo` y `costo_producto` pasan la prueba de PK compuesta; FK compuestas rechazan referencias ajenas; `tests/integration/test_inv21_aislamiento_endpoints_stock.py` para todas las rutas nuevas. Verificable con esas pruebas.
- [x] 9.6 Concurrencia con commits reales en `tests/concurrency/test_stock_concurrencia.py`: dos ingresos simultáneos del mismo producto y ubicación, primera fila de saldo y de costo creada una vez, productos en orden inverso sin deadlock, promedio correcto tras ingresos concurrentes. Verificable corriendo `python -m pytest tests/concurrency` aparte.
- [x] 9.7 Ciclo de migración con datos (`upgrade head → downgrade -1 → upgrade head`) en `test_stock_migracion.py`; INV-03 por `test_inv03_sin_punto_flotante.py` sin cambios.
- [x] 9.8 Suite completa: `python -m pytest -q --ignore=tests/concurrency`, `python -m pytest tests/concurrency`, `ruff check`, `ruff format --check`, `mypy app`, `lint-imports` y `python -m pytest tests/fixtures_compartidos/`, todo en verde.

## 10. ADRs, documentación y cierre

- [x] 10.1 Registrar en `docs/adr/` (desde ADR-036) las decisiones aprobadas que lo requieren: permisos de stock (D1-D3), reglas del stock inicial (D4-D6), ubicaciones (D7-D8), reparto de módulos, bloqueo y promedio nulo (D9-D10). Proponer (sin editar hasta confirmación del usuario, en `propuesta-docs.md`) el texto para `01` §8.1 (STK-10, corrección de stock inicial), §6.2 (egreso por stock inicial) y §19 (usos de permisos); `03` §2.3 (saldos sin `id`), §7 (`costo_promedio` nulo) y §9 (`ubicacion` con `actualizado_en`, `stock_movimiento` con `dispositivo_id` y `jornada_id` sin FK). Verificable con los ADR en *Propuesto* y la propuesta de texto revisada. **Hecho el 2026-09-30:** el usuario aprobó el texto; ADR-036 a ADR-039 pasaron a *Vigente* (ADR-002 anotado como matizado por ADR-039) y `propuesta-docs.md` §1 a §9 se aplicó a `docs/01`, `docs/02` y `docs/03` (en `docs/01` §19 cada una de las cuatro filas de permisos se reemplazó por separado, por no ser contiguas).
- [x] 10.2 Repasar la definición de terminado de `04` §2.1 en `verificacion.md`, con las notas de roadmap: para el 10 (importación reutiliza `registrar_stock_inicial`), para el 15 (FK de `stock_movimiento.jornada_id` y STK-09) y para el 18a (costo de una venta sin promedio, D10).
- [x] 10.3 Verificación manual en el navegador (último paso, la ejecuta el usuario): con un Administrador, crear un depósito y un vehículo (rechazo de vehículo sin toma), registrar stock inicial de 60 unidades de un producto a $1.000 en el depósito y 60 a $1.100 en el vehículo, ver promedio $1.050, corregir −12 en el depósito, ver el kardex con acumulados y filtro de período, intentar desactivar el depósito con stock (rechazo); con un Vendedor, ver stock y kardex sin costos y sin la acción de stock inicial, y comprobar 403 por API. Los pasos se escriben en `verificacion.md`.
