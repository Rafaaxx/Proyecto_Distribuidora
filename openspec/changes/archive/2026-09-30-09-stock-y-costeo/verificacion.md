# Verificación — 09-stock-y-costeo

> Documento de verificación del change (`tasks.md` grupos 9 y 10). Las secciones 9, 10.1 y 10.2 están completas; 10.1 fue aprobada por el usuario el 2026-09-30 y 10.3 (recorrido manual) la ejecutó el usuario el mismo día, sin desvíos. La definición de terminado de §10.2 se cumple completa.

## 9. Pruebas backend — resumen de evidencia

Detalle por tarea en `tasks.md` 9.1 a 9.8. Metodología: las pruebas del grupo 9 caracterizan código ya construido (grupos 2 a 7, en TDD estricto). Cada prueba nueva se probó capaz de fallar antes de darla por buena: mutando temporalmente el código de producción (y restaurándolo) o, donde la regla la sostienen dos capas, contra una expectativa equivocada. Un incidente de método, sin consecuencias: una mutación doble sobre un mismo archivo dejó `stock/repository.py` mutado (se perdió la copia intermedia); se restauró a mano y toda la suite posterior (unit, integration, properties, concurrency, `ruff`, `mypy`, `lint-imports`) corrió sobre el archivo restaurado.

| Tarea | Resultado |
| --- | --- |
| 9.1 (escenarios de `stock-inicial` y `ubicaciones`) | Los 18 escenarios de `stock-inicial` y los 13 de `ubicaciones` estaban cubiertos por los grupos 4 a 7, salvo cuatro brechas que se cerraron: ingreso en otra ubicación que recalcula el promedio por el bus, corrección de un costo mal cargado por el bus (−60 y +60 con stock previo cero), ubicación y producto inactivos por el bus y producto inactivo por HTTP, y `PRODUCTO_CON_OPERACIONES` por HTTP. El rechazo del bus al modo `OFFLINE`, el doble envío, `COMANDO_INCONSISTENTE`, el `Operation-Id` faltante y el 403 ya estaban cubiertos. |
| 9.2 (INV-12 con Hypothesis en PostgreSQL) | `tests/properties/test_inv12_stock_postgres.py`: propiedad sobre secuencias de comandos de 1 a 3 líneas (dos productos, tres ubicaciones, ingresos y egresos; 30 ejemplos): `stock_saldo` igual a la suma SQL del libro, `stock_total` igual a la suma de los saldos, ningún saldo negativo y `verificar_consistencia` vacía; los comandos rechazados por `STOCK_INSUFICIENTE` no dejan efectos. Más falla inyectada en la segunda línea de un comando de dos o tres (INV-01). |
| 9.3 (INV-04) | `tests/integration/test_inv04_cantidades_enteras.py`: toda columna de cantidad del catálogo es entera (con el conjunto mínimo de columnas exigido para que la regla no quede vacía), toda propiedad de cantidad del OpenAPI es `integer`, ambas con su prueba en negativo. El rechazo de no enteros por HTTP lo cubre `test_stock_api.py::TestStockInicialRegistrar` (con mutación). |
| 9.4 (INV-05) | `stock_movimiento` y `costo_producto_mov` en `TABLAS_DE_LIBRO_DECLARADAS`; privilegios exactos (`SELECT`/`INSERT` en los libros, `SELECT`/`INSERT`/`UPDATE` en `stock_saldo`, `costo_producto` y `ubicacion`); `UPDATE` y `DELETE` rechazados por la base en los libros; `DELETE` rechazado en los saldos; y una prueba unitaria de que ninguna ruta edita o borra el libro. |
| 9.5 (INV-02 / INV-21) | `stock_saldo` y `costo_producto` pasan la prueba de PK compuesta que empieza por `organizacion_id` y no tienen FK sin organización; las FK compuestas que rechazan referencias ajenas ya estaban en `test_stock_migracion.py`; archivo dedicado `test_inv21_aislamiento_endpoints_stock.py` con 10 pruebas para las siete rutas. |
| 9.6 (concurrencia) | `tests/concurrency/test_stock_concurrencia.py`: 10 pruebas con commits reales (ingresos simultáneos del mismo par, ingresos simultáneos en dos ubicaciones, primera fila de saldo y de costo, orden inverso de productos sin interbloqueo, dos egresos sobre un saldo que alcanza para uno, productos distintos que no se esperan y desactivación de ubicación contra ingreso). |
| 9.7 (migración con datos) | Ciclo `upgrade → downgrade -1 → upgrade` con movimientos, historia, saldo y costo confirmados; `test_inv03_sin_punto_flotante.py` sin cambios y en verde. |
| 9.8 (suite completa) | Ver la tabla de abajo. |

### Evidencia RED (mutación o expectativa equivocada) de las pruebas nuevas

| Prueba nueva | Cómo se probó que puede fallar | Resultado |
| --- | --- | --- |
| Ingreso en otra ubicación recalcula el promedio (bus) | `aplicar_ingreso` usa `stock_previo = 0` | falla |
| Corregir un costo mal cargado (bus) | `aplicar_ingreso` fuerza un stock previo mínimo de 1 y un promedio previo | falla |
| Ubicación y producto inactivos (bus) | Se anula `validar_ubicacion_activa`; por separado, `validar_producto_activo` | falla en cada una |
| `PRODUCTO_INACTIVO` por HTTP | Se anula `validar_producto_activo` | falla |
| `PRODUCTO_CON_OPERACIONES` por HTTP | La comprobación de otros tipos se cortocircuita a `False` | falla |
| `test_inv12_*_suma_sql_del_libro_en_cada_par` | El ingreso suma una unidad de más al saldo; por separado, el egreso no descuenta `stock_total` | falla en cada una |
| `test_inv12_inv01_*_falla_inyectada` | El servicio corta después de la primera línea (la falla inyectada nunca se dispara y `llamadas == 2` falla) | falla |
| `test_inv04_toda_columna_de_cantidad_del_esquema_es_entera` | `costo_producto_mov.cantidad` pasa a `Numeric(14,2)` en la migración | falla |
| `test_inv04_toda_propiedad_de_cantidad_del_openapi_es_integer` | Una `cantidad_base` de respuesta pasa a `float` | falla |
| Rechazo de cantidades no enteras por HTTP | La cantidad de la solicitud pasa de `StrictInt` a `int` (acepta `"12"`) | falla con el caso `"12"` |
| `test_inv05_los_libros_de_stock_y_costo_*` | `GRANT ... UPDATE` sobre `stock_movimiento`; `GRANT ... DELETE` sobre `costo_producto_mov` | falla en cada una |
| `test_inv05_app_runtime_no_puede_actualizar_ni_borrar_los_libros_*` (2) | Los mismos dos `GRANT` | falla en cada una (una por tabla) |
| `test_inv05_app_runtime_actualiza_los_saldos_*` (3) | `costo_producto` sin `UPDATE`; `stock_saldo` con `DELETE` | falla en cada una |
| `test_ninguna_ruta_edita_ni_borra_el_libro_de_stock_ni_el_de_costo` | Una ruta `DELETE /stock/kardex/{id}` en `stock/api.py` | falla; además una prueba en negativo con una app sintética |
| `test_los_saldos_de_stock_y_costo_cumplen_inv02_*` | `stock_saldo` con PK `(producto_id, organizacion_id, ubicacion_id)`; por separado, una FK simple a `producto` | falla en cada una |
| `test_inv21_aislamiento_endpoints_stock.py` (10) | El repositorio de ubicaciones deja de filtrar por organización; la ruta del costo deja de responder 404 al producto ajeno; el listado de ubicaciones deja de filtrar; el kardex deja de validar el producto | falla en cada una. La modificación de una ubicación ajena y el stock inicial en una ubicación ajena **no** cambian con la primera mutación porque las sostiene una segunda capa (el bloqueo `FOR UPDATE`/`FOR SHARE` por organización y la FK compuesta): es defensa en profundidad y no un defecto de la prueba. |
| Concurrencia: costo con 8 hilos en dos ubicaciones | Se quita `FOR UPDATE` de la fila de costo | falla la variante de 8 hilos (promedio perdido); la de 2 hilos no alcanza a exponerlo, igual que en el change 08 |
| Concurrencia: primera fila | Se quita `ON CONFLICT DO NOTHING` en `costo_producto`; por separado, en `stock_saldo` | falla en cada una |
| Concurrencia: orden inverso | `costeo` y `stock` dejan de ordenar los productos antes de bloquear | falla (interbloqueo real detectado por la prueba) |
| Concurrencia: dos egresos | La condición del `UPDATE` pasa de `cantidad_base >= :q` a `>= 0` | falla (saldo negativo) |
| Concurrencia: productos distintos | La ubicación se toma `FOR UPDATE` en lugar de `FOR SHARE` | falla ("B tuvo que esperar a A") |
| Concurrencia: desactivación contra ingreso | Se quita el `FOR SHARE` de la ubicación en el movimiento (y el `FOR UPDATE` en la modificación) | falla (ubicación inactiva con stock) |
| `test_el_ciclo_de_migracion_con_datos_*` | La bajada además borra `producto`; por separado, la bajada no elimina `stock_movimiento` | falla en cada una |

### 9.8 — Suite completa

| Comando | Resultado |
| --- | --- |
| `python -m pytest tests/unit tests/fixtures_compartidos` | **1057 passed** |
| `python -m pytest tests/integration` (aparte) | **1133 passed** (segunda corrida completa; en la primera, una prueba inestable conocida falló una vez, ver abajo) |
| `python -m pytest tests/properties` (aparte) | **22 passed** (20 previas + las 2 de INV-12 contra PostgreSQL) |
| `python -m pytest tests/concurrency` (aparte) | **27 passed** (17 previas + las 10 nuevas) |
| `python -m ruff check .` | sin hallazgos |
| `python -m ruff format --check .` | 299 archivos ya formateados |
| `python -m mypy app` | sin errores (123 archivos) |
| `lint-imports` | 19 contratos cumplidos, 0 rotos |
| Frontend `npm run typecheck` | sin errores |
| Frontend `npm run lint` | 0 errores y 2 advertencias previas al change (`react-hooks/incompatible-library` en `ProductoFormScreen.tsx` y `CostosCargaScreen.tsx`), sin tocar |
| Frontend `npm run test` | **574 passed (574)** |
| Frontend `npm run build` | compila |

Prueba inestable conocida, no tocada: `test_identidad_commands_maestros.py::TestPinAutorizacionRotar::test_un_pin_invalido_por_longitud_nunca_aparece_en_claro_en_el_error` (elige un PIN de 2 dígitos al azar y falla si esos dígitos aparecen dentro de un UUID del mensaje). Falló una vez en la primera corrida completa del grupo (1132 passed, 1 failed) y pasa sola y en la corrida siguiente (1133 passed); no tiene relación con stock.

Hallazgos de código de producción por las pruebas nuevas: **ninguno** (no hubo defectos que corregir).

## 2.1 — Cobertura de escenarios por spec (`docs/04` §2.1 punto 2)

Las seis specs delta tienen 76 escenarios. Cada uno tiene al menos una prueba; la tabla nombra la prueba principal.

| Spec | Escenarios | Pruebas principales |
| --- | --- | --- |
| `stock/stock-inicial` | 18 | `test_stock_comandos.py` (bus: atomicidad, promedio, correcciones, costo, inactivos, `OFFLINE`, idempotencia), `test_stock_api.py::TestStockInicialRegistrar` (HTTP: `Operation-Id`, 403, 404, 409, 422), `test_stock_service.py`, `test_stock_domain.py` |
| `stock/ubicaciones` | 13 | `test_stock_comandos.py` y `test_stock_api.py::TestUbicacionCrear`/`TestUbicacionModificar`/`TestListarUbicaciones`, `test_stock_migracion.py` (vehículo sin toma en la base, nombre único) |
| `stock/libro-de-stock` | 15 | `test_stock_migracion.py` (datos del movimiento, cantidad cero, tipo, FK), `test_inv05_dos_roles.py`, `test_stock_libro_sin_rutas_de_edicion.py`, `test_inv04_cantidades_enteras.py`, `test_inv12_stock_dominio.py`, `test_inv12_stock_postgres.py`, `test_stock_concurrencia.py`, `test_inv02_aislamiento_esquema.py`, `test_inv21_aislamiento_endpoints_stock.py` |
| `stock/kardex` | 9 | `test_stock_service.py` (acumulado, período, orden, rango), `test_stock_api.py::TestKardex`/`TestSaldosDeUbicacion` (costos con y sin `VER_COSTOS`, 404, 403), `test_inv21_aislamiento_endpoints_stock.py` |
| `stock/administracion-de-stock` | 7 | `UbicacionesListScreen`, `UbicacionFormScreen`, `StockPorUbicacionScreen`, `KardexScreen`, `StockInicialScreen`, `rutas.test.tsx` y `cantidades.test.ts` (frontend, grupo 8) |
| `costeo/costo-promedio` | 14 | `test_costeo_domain.py`, `test_cst11_costo_promedio_fixtures.py` y `cst11.fixtures.test.ts` (casos compartidos en ambas suites), `test_costeo_service.py`, `test_stock_api.py::TestCostoPromedioDeProducto`, `test_stock_migracion.py` y `test_inv05_dos_roles.py` (la historia no se edita), `test_import_linter_stock_costeo.py` (límites de módulo) |

## 10.1 — ADR y `docs/` (aprobado y aplicado el 2026-09-30)

- `docs/adr/ADR-036-permisos-de-stock-y-lectura-del-costo-promedio.md` (D1, D2, D3 y la enmienda del 2026-09-30 más las aclaraciones: selector de productos con `GESTIONAR_CATALOGO`, respuestas con `producto_codigo`/`producto_nombre`, el Vendedor ve el menú "Stock"), `ADR-037-reglas-del-stock-inicial-y-su-correccion.md` (D4, D5, D6), `ADR-038-reglas-de-la-ubicacion-y-su-desactivacion.md` (D7, D8 y la modificación por `PUT` de reemplazo completo) y `ADR-039-reparto-entre-stock-y-costeo-bloqueo-y-promedio-nulo.md` (D9, D10 y `jornada_id` de D12). Los cuatro pasaron a *Vigente* el 2026-09-30 (ADR-002 quedó anotado como matizado por ADR-039).
- `openspec/changes/09-stock-y-costeo/propuesta-docs.md`: el texto exacto propuesto (antes/después) para `docs/01-dominio.md` (CST-12 en §6.2, STK-10 en §8.1, alcance de cuatro permisos en §19 y la fila de stock inicial de §21), `docs/02-arquitectura.md` §5.3 (`catalogo ──► costeo`), `docs/03-modelo-de-datos.md` (§2.3 con `stock_saldo` y `costo_producto`, §7, §9 y el índice del kardex de §16) y las notas de roadmap para los changes 10, 11, 15 y 18a.
- El 2026-09-30 se aplicó `propuesta-docs.md` §1 a §9 a `docs/01`, `docs/02` y `docs/03`; `docs/04` se actualizó al archivar (§11). 10.1 marcada.

## 10.2 — Definición de terminado (`docs/04-roadmap-changes.md` §2.1)

| # | Criterio | Estado |
| --- | --- | --- |
| 1 | Las pruebas que exige `02` §15 para su alcance pasan en CI | Cumple en local: unit y fixtures (1057), integration, properties y concurrency en verde (§9.8); frontend 574; `ruff check`, `ruff format`, `mypy` y `lint-imports` limpios. |
| 2 | Cada escenario de sus specs tiene al menos una prueba que lo cubre | Cumple: 76 escenarios, ver tabla de §2.1 (la auditoría del grupo 9 cerró las brechas listadas en §9, tarea 9.1). |
| 3 | Los invariantes que toca tienen prueba que los cita por ID | Cumple: INV-01 (falla inyectada en `test_inv12_stock_postgres.py` y concurrencia), INV-02 e INV-21 (esquema y endpoints), INV-03 (`test_inv03_sin_punto_flotante.py`, sin cambios), INV-04 (`test_inv04_cantidades_enteras.py`), INV-05 (libros de stock y de costo), INV-06 (doble envío) e INV-12 (Hypothesis de dominio y contra PostgreSQL). |
| 4 | La migración de Alembic sube y baja limpia sobre una base con datos | Cumple: `test_el_ciclo_de_migracion_con_datos_sube_baja_y_sube_sin_tocar_lo_ajeno` (9.7) y `test_downgrade_elimina_las_cinco_tablas_y_upgrade_las_recrea`. |
| 5 | Se probó a mano el flujo principal en el navegador | Cumple: lo ejecutó el usuario el 2026-09-30, sin desvíos (§10.3). |
| 6 | Las specs delta se archivaron en `openspec/specs/` y `04-roadmap-changes.md` quedó actualizado | Cumple: archivado el 2026-09-30 con las specs sincronizadas; las notas de roadmap para los changes 10, 11, 15 y 18a se incorporaron a `docs/04`. |
| 7 | Si se tomó una decisión nueva, quedó como ADR | Cumple: ADR-036 a ADR-039 aprobados por el usuario y *Vigente* desde el 2026-09-30 (§10.1). |

**Conclusión:** el trabajo de código y de pruebas está terminado. El change quedó aprobado (10.1) y verificado a mano (10.3) y se archivó el 2026-09-30.

### Notas de roadmap

Incorporadas a `docs/04-roadmap-changes.md` al archivar (texto completo en `propuesta-docs.md` §11):

- **Change 10 (`importacion-inicial`):** la importación de stock inicial reutiliza `stock/service.py::registrar_stock_inicial` fila por fila, con `IMPORTAR_DATOS` (ADR-036); hereda STK-10 y ADR-037 (`PRODUCTO_CON_OPERACIONES`, costo positivo con hasta 6 decimales, 404 para referencias ajenas, 409 para inactivas) y traduce cada rechazo a su número de fila. **Pregunta abierta:** fechar el stock inicial al día de corte reabre el momento del movimiento (hoy, el `occurred_at` del sobre).
- **Change 11 (`compras-y-deuda-proveedor`):** usa `registrar_movimientos` como único camino para cambiar stock; **queda sin decidir** qué historia de costo deja una `ANULACION_COMPRA` con `recalculado = false` (CMP-06).
- **Change 15 (`jornadas`):** agregar la FK de `stock_movimiento.jornada_id` a `jornada` y aplicar STK-09.
- **Change 18a (`venta-online-core`):** decide cómo costea una venta de un producto sin promedio (`costo_promedio` nulo hasta el primer ingreso, ADR-039).

## 10.3 — Recorrido manual en el navegador (ejecutado por el usuario el 2026-09-30)

### Preparación del entorno

1. Verificar que existe un `.env` en la raíz del repo con `APP_MIGRATIONS_DB_PASSWORD`, `APP_RUNTIME_DB_PASSWORD`, `JWT_SECRET` y `ADMIN_PASSWORD` (`CLAUDE.md` §4: ningún secreto por defecto).
2. Levantar el stack:
   ```bash
   docker compose up -d
   ```
3. Aplicar las migraciones (incluye `ubicacion`, `costo_producto`, `costo_producto_mov`, `stock_saldo` y `stock_movimiento` de este change):
   ```bash
   docker compose exec backend alembic upgrade head
   ```
4. Sembrar la organización inicial, los cinco roles y el usuario `admin` (idempotente):
   ```bash
   docker compose exec -e ADMIN_PASSWORD=<la contraseña de .env> backend python -m app.seed
   ```
   Organización: slug `organizacion-inicial`. Administrador: `admin`.
5. Abrir el frontend en `http://localhost:5173` (el API responde en `http://localhost:8000`; `docker compose ps` si el puerto es otro).
6. Hace falta un producto con presentación de referencia (por ejemplo una caja de 6): si no hay, crearlo en "Catálogo" con `admin` (nombre `Vino A`, unidad base `botella`, presentación de referencia `Caja x6` con 6 unidades).

### Crear un usuario Vendedor (`TRANSFERIR_STOCK`, sin `VER_COSTOS` ni `IMPORTAR_DATOS`)

No hay pantalla de usuarios todavía, así que se crea por API (mismo procedimiento que el change 08).

1. Buscar el `id` del rol:
   ```bash
   docker compose exec postgres psql -U distribuidora -d distribuidora -c \
     "SELECT id, nombre FROM rol WHERE nombre = 'Vendedor/Repartidor';"
   ```
   (si el nombre no coincide, `SELECT id, nombre FROM rol;` y elegir el del vendedor).
2. Login como `admin` y copiar el `access_token`:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"organizacion_slug":"organizacion-inicial","usuario":"admin","contrasena":"<ADMIN_PASSWORD>","dispositivo_id":"00000000-0000-0000-0000-000000000001","nombre_dispositivo":"Verificación 09"}'
   ```
3. Crear el usuario `vendedor`:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/identidad/usuarios \
     -H "Authorization: Bearer <access_token>" \
     -H "Operation-Id: 0193a000-0000-7000-8000-000000000901" \
     -H "Content-Type: application/json" \
     -d '{"usuario":"vendedor","nombre":"Vendedor de Prueba","email":null,"password":"una-contrasena-larga-123","rol_id":"<id del paso 1>"}'
   ```

### Flujo con `admin` (Administrador: tiene `ADMIN_CONFIGURACION`, `IMPORTAR_DATOS`, `TRANSFERIR_STOCK` y `VER_COSTOS`)

Entrar en el frontend como `admin` / `organizacion-inicial`. Importes en pesos con el formato de la interfaz.

| # | Paso | Resultado esperado |
| --- | --- | --- |
| 1 | Abrir "Stock" en el menú | Listado de ubicaciones vacío ("Todavía no hay ubicaciones") y el botón "Nueva ubicación" |
| 2 | "Nueva ubicación": nombre `Depósito central`, tipo Depósito, sin marcar "Requiere toma", guardar | Vuelve al listado con la ubicación "Activa" |
| 3 | "Nueva ubicación": nombre `Camioneta 1`, tipo Vehículo | "Requiere toma" se marca solo y no deja quitarla ("Un vehículo siempre requiere toma") |
| 4 | Si se logra enviar un vehículo sin toma (por ejemplo editando la petición en DevTools → Network → "Edit and resend" con `requiere_toma: false`) | El servidor lo rechaza con `VEHICULO_REQUIERE_TOMA` y el mensaje se muestra o, por API, responde 422 |
| 5 | Guardar el vehículo con toma | Aparece en el listado |
| 6 | Intentar crear otra ubicación llamada ` depósito CENTRAL ` | Se rechaza por nombre repetido y el mensaje se muestra junto al formulario |
| 7 | En `Depósito central` → "Cargar stock inicial": elegir `Vino A`, Ingreso, 10 cajas y 0 unidades (60 botellas si la caja es de 6), costo `1000` por unidad base, enviar | Vuelve al stock de la ubicación: `Vino A` con 10 cajas, costo promedio `$ 1.000,000000` (o el formato que muestre la interfaz). Antes de enviar, la pantalla mostraba "Promedio resultante: ... 1.000" |
| 8 | En `Camioneta 1` → "Cargar stock inicial": `Vino A`, Ingreso, 60 unidades (10 cajas), costo `1100` | La previsualización dice "Promedio resultante: ... 1.050" antes de enviar; al enviar, el stock de la camioneta muestra 10 cajas y el costo promedio de `Vino A` es `$ 1.050,000000` (es uno solo para todas las ubicaciones) |
| 9 | En `Depósito central` → "Cargar stock inicial": `Vino A`, **Corrección (egreso)**, 12 unidades, sin costo | El stock del depósito baja a 48 unidades (8 cajas) y el costo promedio sigue en `$ 1.050,000000` |
| 10 | Probar una corrección de 100 unidades en el depósito | Se rechaza (`STOCK_INSUFICIENTE`) con su mensaje y nada cambia |
| 11 | Desde el stock del depósito, "Ver kardex" de `Vino A` | Dos movimientos: Stock inicial +60 (acumulado 60, costo 1.000) y Corrección −12 (acumulado 48, costo 1.050, el promedio vigente); "Saldo actual" 48 |
| 12 | En el kardex, "Desde" = mañana y "Filtrar" | Sin movimientos y "Saldo anterior" 48 |
| 13 | "Desde" = hoy | Los dos movimientos con acumulado 60 y 48; fechas en la zona horaria de la organización |
| 14 | "Desde" posterior a "Hasta" | El formulario avisa el rango y no pide nada al servidor |
| 15 | "Quitar filtro" | Vuelve el kardex completo |
| 16 | Intentar cargar stock inicial con cantidad 0, `1.5` y `abc`, y costo `0` o `1.1234567` | Cada uno se rechaza junto al campo y no se envía nada |
| 17 | Enviar una carga y, sin recargar, repetir el envío con la red cortada (DevTools → Offline) | Avisa que se requiere conexión y que no se encola; al volver la red, el reintento del mismo dato no duplica el movimiento (mismo `operation_id`) |
| 18 | Editar `Depósito central` y desmarcar "Activa" | Se rechaza (`UBICACION_CON_STOCK`) con el mensaje del servidor; la ubicación sigue activa |
| 19 | Crear `Depósito vacío` y desactivarlo, luego reactivarlo | Se desactiva y se reactiva sin problema (no tiene stock) |
| 20 | Con la ubicación inactiva, ver su listado: el enlace "Cargar stock inicial" no aparece | Correcto (las inactivas no reciben movimientos) |
| 21 | Verificar la consistencia en la base: `docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT s.producto_id, s.ubicacion_id, s.cantidad_base, COALESCE(SUM(m.cantidad_base),0) AS suma FROM stock_saldo s LEFT JOIN stock_movimiento m USING (organizacion_id, producto_id, ubicacion_id) GROUP BY s.producto_id, s.ubicacion_id, s.cantidad_base;"` | En cada fila `cantidad_base` es igual a `suma` |
| 22 | Verificar el costo: `docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT costo_promedio, stock_total FROM costo_producto;"` y `SELECT origen_tipo, stock_anterior, promedio_anterior, stock_nuevo, promedio_nuevo FROM costo_producto_mov ORDER BY registered_at;` | Promedio `1050.000000` y `stock_total` 108; la historia tiene dos filas (60 → 120 con promedio 1000 → 1050; la corrección no deja fila) |

### Flujo con `vendedor` (rol Vendedor/Repartidor: lee stock y kardex, sin costos ni stock inicial)

Cerrar sesión y entrar como `vendedor` / `organizacion-inicial`.

| # | Paso | Resultado esperado |
| --- | --- | --- |
| 1 | Abrir "Stock" en el menú | La sección aparece (el menú depende de `TRANSFERIR_STOCK`); ve las ubicaciones y **no** ve "Nueva ubicación" ni "Editar" |
| 2 | "Ver stock" de `Depósito central` | Ve `Vino A` con su cantidad y **sin** columna de costo promedio; no aparece "Cargar stock inicial" |
| 3 | "Ver kardex" de `Vino A` | Ve los movimientos y el acumulado, sin columna de costo; el nombre y el código del producto aparecen aunque no tenga acceso al catálogo |
| 4 | Ir directo a `/admin/stock/ubicaciones/<id del depósito>/stock-inicial` | Avisa la falta de permiso y no muestra el formulario |
| 5 | Por API con el token del vendedor (login como `vendedor` para obtenerlo): `curl -s -X POST http://localhost:8000/api/v1/stock/iniciales -H "Authorization: Bearer <token>" -H "Operation-Id: 0193a000-0000-7000-8000-000000000902" -H "Content-Type: application/json" -d '{"ubicacion_id":"<id del depósito>","lineas":[{"producto_id":"<id de Vino A>","cantidad_base":6,"costo_unitario":"1000"}]}'` | `403` con código `PERMISO_REQUERIDO`; el stock no cambia |
| 6 | Por API: `curl -s http://localhost:8000/api/v1/catalogo/productos/<id de Vino A>/costo -H "Authorization: Bearer <token>"` | `403` (el vendedor no tiene `VER_COSTOS`) |
| 7 | Por API con el token de `admin`: el mismo `GET` del paso 6 | `200` con `costo_promedio` `"1050.000000"` y `stock_total` 108 |
| 8 | Por API con el token de `admin`: `GET /api/v1/catalogo/productos/00000000-0000-0000-0000-000000000000/costo` | `404` |

### Qué reportar

Para cada paso: ✅ si el resultado coincide, o el desvío observado (con captura si es posible). Si algo no coincide, no se marca 10.3 y se documenta acá antes de archivar.

### Resultado del recorrido (2026-09-30)

Ejecutado por el usuario con la aplicación levantada: flujo `admin` (pasos 1 a 22) y flujo `vendedor` (pasos 1 a 8), todos ✅. El usuario usó cantidades distintas a las del guion (corrección de −13 y un ingreso posterior de 7 unidades a `1000`); los controles cuadraron con esos datos: saldos por ubicación iguales a la suma de sus movimientos (60 y 54), `stock_total` 114 igual a la suma de ubicaciones, historia de costo con tres ingresos y la corrección sin fila, promedio `1046.929825` = redondeo a 6 decimales de (107 × 1050 + 7 × 1000) / 114. Por API: stock inicial del vendedor 403 `PERMISO_REQUERIDO` (falta `IMPORTAR_DATOS`), costo para el vendedor 403 (falta `VER_COSTOS`), costo para `admin` 200 con `costo_promedio` `"1046.929825"` y `stock_total` 114, producto inexistente 404 `RECURSO_NO_ENCONTRADO`. Sin desvíos.
