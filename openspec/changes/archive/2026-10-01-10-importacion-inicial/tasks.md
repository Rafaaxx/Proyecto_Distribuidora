# Tareas — 10-importacion-inicial

> Modo TDD estricto: en cada tarea de los grupos 1 a 9, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). El grupo 10 completa la cobertura por escenario e invariante; no la reemplaza. Las tareas están escritas con la **opción A (recomendada)** de cada decisión de `design.md`; si la tarea 0.1 aprueba otra, se actualizan con `/opsx:update` antes de empezar.
>
> **Lotes de apply:** Lote 1 = grupos 0 a 4 (infraestructura y proveedores de punta a punta). Lote 2 = grupos 5 a 6 (productos, clientes y costos). Lote 3 = grupos 7 a 12 (el 12 se ejecuta antes del 11) (puesta en marcha, pantalla, cobertura, docs y verificación manual).

## 0. Aprobación (bloqueante)

- [x] 0.1 El usuario revisa y aprueba (o cambia) D0 a D14 de `design.md`, incluidas las dos contradicciones de documentos (D8: CST-05; D9: `PRECIOS`/`COSTOS` en `03` §13) y la pregunta heredada de la fecha de corte (D7). Se anota fecha y opción en cada decisión. Si alguna difiere de la recomendada, se actualizan proposal, specs y tareas con `/opsx:update`. Verificable: `design.md` sin decisiones "Pendiente".

## 1. Migración (Lote 1)

- [x] 1.1 RED: `tests/integration/test_importacion_migracion.py` que exige la tabla `importacion` (`03` §13 + columnas de operación, D14): `UNIQUE (organizacion_id, id)`, FK compuestas a `usuario` y `dispositivo`, `CHECK` de catálogo de `tipo` (D9) y de `estado`, `CHECK` de filas no negativas, índice del historial y privilegios `SELECT, INSERT` para `app_runtime`. GREEN: revisión de Alembic con `upgrade`/`downgrade` limpios. Verificable con esa prueba y `alembic upgrade head`/`downgrade -1`.

## 2. Módulo, modelo y límites (Lote 1)

- [x] 2.1 RED: contrato de import-linter `importacion` (solo `service.py` de `catalogo`, `proveedores`, `clientes`, `stock`, `cuentas_corrientes`, `configuracion`, `identidad`; `importacion.domain` sin infraestructura; nadie importa `importacion`, D10). GREEN: esqueleto `backend/app/modules/importacion/` (`domain/`, `models.py`, `repository.py`, `commands.py`, `queries.py`, `api.py`, `schemas.py`), modelo igual a la migración, registro en `alembic/env.py` y `app/main.py`. Verificable con `lint-imports` y `alembic revision --autogenerate` sin diferencias.

## 3. Dominio de planillas (Lote 1, funciones puras)

- [x] 3.1 Conversión exacta de texto a `Decimal` (D12: coma decimal, sin miles, punto rechazado) y a entero (INV-04), con `NUMERO_INVALIDO`/`CANTIDAD_INVALIDA`; booleanos `S/SI/SÍ/N/NO` (`VALOR_INVALIDO`); fechas `AAAA-MM-DD` y `DD/MM/AAAA` (`FECHA_INVALIDA`). RED en `tests/unit/test_importacion_domain_valores.py` con los ejemplos de la spec `importacion/planillas` (`18000,00`, `1.500`, `1.234,56`, `10,5`, `01/10/2026`, `quizás`) más una propiedad Hypothesis: todo decimal con hasta 6 decimales escrito con coma vuelve igual (cita INV-03).
- [x] 3.2 Encabezados y filas: columnas obligatorias, desconocidas y repetidas (`COLUMNAS_INVALIDAS` con los nombres), orden libre, filas vacías ignoradas, número de fila visible (encabezado = 1), límites (`ARCHIVO_SIN_FILAS`, `ARCHIVO_DEMASIADO_GRANDE`, D11) y definición de columnas por tipo (D5, D6, D13). RED en `tests/unit/test_importacion_domain_planilla.py`.
- [x] 3.3 Lector CSV (D2): UTF-8 con/sin BOM, alternativa Windows-1252, separador `,`/`;` detectado en el encabezado, comillas. RED en `tests/unit/test_importacion_lector_csv.py` con un CSV "guardado por Excel en español" (`;`, `Ñ`). Fuera de `domain/` (adaptador).
- [x] 3.4 Lector `.xlsx` (D2/D3) con `zipfile` + `xml.etree`: primera hoja, cadenas compartidas, celdas en línea, texto literal de celdas numéricas sin `float`, fechas solo con formato de fecha; `ARCHIVO_INVALIDO` ante archivo no xlsx. RED en `tests/unit/test_importacion_lector_xlsx.py` con planillas mínimas generadas en la prueba (celda `1239.669421` → `"1239.669421"`, celda `1239.6694214876034` se conserva literal). Verificable: ninguna ruta del lector produce `float` (prueba que lo comprueba sobre los valores devueltos, cita INV-03).
- [x] 3.5 Traducción de errores: `DomainError` de un servicio → `{fila, columna, codigo, mensaje}` con la tabla código→columna por tipo, incluida la `fila` de `extension` de `informar_costos`; agregado `IMPORTACION_CON_ERRORES` (422, `extension.errores`). RED en `tests/unit/test_importacion_domain_errores.py`.

## 4. Comando, todo o nada, historial y plantillas, con proveedores (Lote 1)

- [x] 4.1 RED: `tests/integration/test_importacion_comando.py` con proveedores: dos filas válidas crean dos proveedores y una fila de `importacion`; una fila con `CUIT_INVALIDO` y otra con `NOMBRE_DUPLICADO` dan 422 con **los dos** errores y ningún proveedor; `FILA_DUPLICADA` dentro del archivo; doble envío idempotente; `COMANDO_INCONSISTENTE`; `OFFLINE` rechazado por el bus; 403 sin `IMPORTAR_DATOS`; una sola auditoría. GREEN: handler `IMPORTACION_REGISTRAR` v1 con savepoint por fila (`begin_nested`), error agregado al final, inserción de `importacion` y resultado `{importacion_id, filas_total, filas_ok}` (D1, D14); importador de proveedores sobre `proveedores/service.py::crear_proveedor`.
- [x] 4.2 RED: falla inyectada después de escribir la fila 5 de 10 → ningún proveedor ni `importacion` (cita INV-01). GREEN si hace falta. Verificable con la prueba.
- [x] 4.3 RED: `tests/integration/test_importacion_api.py`: `POST /api/v1/importaciones/{tipo}` multipart con `Operation-Id` (400 `OPERATION_ID_REQUERIDO` sin él, igual que el resto de las escrituras; 422 `TIPO_IMPORTACION_INVALIDO` para `PRECIOS` y tipos desconocidos, D9), Problem Details con `errores`; `GET /api/v1/importaciones` (orden, cursor, límite 1 a 200, aislamiento); `GET /api/v1/importaciones/plantillas/{tipo}` (CSV con solo encabezado, 403 sin permiso). GREEN: rutas, esquemas y tipos de OpenAPI regenerados (`npm run generate:api-types`).
- [x] 4.4 RED: las rutas nuevas entran en el ratchet de aislamiento (INV-21) y en el de permisos. GREEN. Verificable con las pruebas de ratchet existentes.

## 5. Productos con presentaciones (Lote 2)

- [x] 5.1 RED en `tests/unit/test_importacion_domain_productos.py`: agrupación por `codigo` (D5), `PRODUCTO_INCONSISTENTE`, armado de presentaciones, resolución de claves (D4: categoría, marca, proveedor por nombre, alícuota por porcentaje, `REFERENCIA_NO_ENCONTRADA`, `REFERENCIA_AMBIGUA`). GREEN en `importacion/domain`.
- [x] 5.2 RED en `tests/integration/test_importacion_productos.py` con los escenarios de la spec (Vino A caja x6 + botella; sin referencia y referencia sin venta → `REFERENCIA_INVALIDA` en la fila de la presentación; `UNIDADES_INVALIDAS`; `CODIGO_DUPLICADO`; categoría inexistente sin crearla; proveedor de otra organización = no encontrado, cita INV-21; inactivos). GREEN: importador sobre `catalogo/service.py::crear_producto`, con lecturas de referencias por los `service.py` (agregar funciones de búsqueda por clave natural donde falten, con su prueba propia en el módulo dueño).

## 6. Clientes y costos (Lote 2)

- [x] 6.1 RED en `tests/integration/test_importacion_clientes.py`: cliente con CUIT normalizado, `ACTIVO`, sin crédito ni lista; `DOCUMENTO_INVALIDO`; `FICHA_INCOMPLETA`; `codigo` obligatorio (D6); `CODIGO_DUPLICADO` y `DOCUMENTO_DUPLICADO`. GREEN: importador sobre `clientes/service.py::crear_cliente`.
- [x] 6.2 RED en `tests/integration/test_importacion_costos.py` con los ejemplos de CST-02 de `01` §6.1 (`18000` sin IVA → `"1500.000000"`; con IVA 21% → `"1239.669421"`; bonificación 10 → `"1350.000000"`), `PRESENTACION_INVALIDA`, `PROVEEDOR_INACTIVO`, error de `informar_costos` traducido a la fila correcta, y `UNIDADES_CONGELADAS` al modificar después la presentación (cita INV-18). GREEN: importador sobre `proveedores/service.py::informar_costos` (lote de una fila, proveedor actual del producto). Solo si D8 = A.

## 7. Puesta en marcha (Lote 3)

- [x] 7.1 RED en `tests/integration/test_importacion_stock_inicial.py` con los escenarios de la spec (dos ubicaciones → promedio `"1050.000000"`; corrección −12 en el mismo archivo; costo cero y con 7 decimales → `COSTO_INVALIDO`; `PRODUCTO_CON_OPERACIONES` insertando otro tipo por el servicio; `STOCK_INSUFICIENTE` aun con `PERMITIR_STOCK_NEGATIVO`; `UBICACION_INACTIVA`; `PRODUCTO_INACTIVO`). GREEN: importador sobre `stock/service.py::registrar_stock_inicial`, una línea por fila, orden estable por (producto, ubicación); momento según D7.
- [x] 7.2 RED en `tests/integration/test_importacion_saldos_iniciales.py` con los escenarios de la spec (`C001` 150.000 "Nos debe"; corrección 20.000 `REDUCE` → `"130000.00"`; proveedor "Le debemos"; `CONSUMIDOR_FINAL_SIN_CUENTA`; `CUENTA_CON_OPERACIONES`; `IMPORTE_INVALIDO` con 3 decimales; `SENTIDO_INVALIDO`; cliente inexistente). GREEN: importador sobre `cuentas_corrientes/service.py::registrar_saldo_inicial`, rótulos de ADR-034 punto 8, orden estable por (`cuenta_tipo`, entidad).
- [x] 7.3 RED: propiedad contra PostgreSQL real: tras importar stock y saldos aleatorios válidos, `stock_saldo` = suma del libro y `saldo_cuenta` = suma de `cuenta_movimiento` (cita INV-12 e INV-13). Verificable con `tests/properties/test_importacion_inv12_inv13.py`.

## 8. Pantalla `/admin` (Lote 3)

- [x] 8.1 RED en `frontend/tests/unit/areas/admin/importacion/ImportacionScreen.test.tsx`: entrada de menú y ruta solo con `IMPORTAR_DATOS` (`<SiTienePermiso>`); elegir tipo, descargar plantilla, subir archivo; éxito con "N filas importadas"; tabla de errores con fila/columna/código/mensaje y aviso "No se importó ninguna fila"; error de columnas como mensaje general; mismo `Operation-Id` al reintentar tras error de red y uno nuevo al cambiar de archivo. GREEN: `frontend/src/areas/admin/importacion/` (pantalla, hook con TanStack Query, sin lógica de negocio ni lectura del archivo en el cliente).
- [x] 8.2 RED: historial paginado con fecha en la zona de la organización. GREEN. Verificable con `npm run test`, `npm run typecheck` y `npm run lint`.

## 9. Concurrencia (Lote 3)

- [x] 9.1 RED en `tests/concurrency/test_importacion_concurrencia.py` (commits reales): importación de stock con productos en orden inverso a sus ids en paralelo con un `STOCK_INICIAL_REGISTRAR` por pantalla sobre los mismos productos → sin interbloqueo, stock y promedio de aplicar ambos; dos importaciones simultáneas con el mismo `Operation-Id` → un solo efecto (cita INV-06). GREEN si hace falta.

## 10. Cobertura por escenario e invariante (Lote 3)

- [x] 10.1 Repasar que cada escenario de las cinco specs tiene una prueba que lo cubre y agregar las faltantes (planillas, maestros, puesta en marcha, registro, pantalla).
- [x] 10.2 Invariantes citados por ID: INV-01 (4.2), INV-03 (3.1, 3.4 y `test_inv03_sin_punto_flotante.py` sobre `importacion`), INV-04 (3.1, 7.1), INV-05 (`importacion` sin `UPDATE`/`DELETE` si D14 = A), INV-06 (4.1, 9.1), INV-12/INV-13 (7.3), INV-18 (6.2), INV-21 (4.4, 5.2). Verificable con `grep` de cada ID en `backend/tests`.
- [x] 10.3 Integración con 2.000 filas de proveedores dentro del límite de tiempo razonable (medición anotada en `verificacion.md`, riesgo de savepoints).
- [x] 10.4 Suite completa: `python -m pytest -q --ignore=tests/concurrency`, `python -m pytest tests/concurrency`, `ruff check`, `ruff format --check`, `mypy app`, `lint-imports`, `python -m pytest tests/fixtures_compartidos/`, y en el frontend `npm run test`, `npm run typecheck`, `npm run lint`, `npm run check:api-types`; todo en verde. Ciclo de migración con datos (`upgrade head → downgrade -1 → upgrade head`).

## 11. ADRs, documentación y cierre (Lote 3)

- [x] 11.1 Registrar en `docs/adr/` (desde ADR-040), en estado *Propuesto*, las decisiones aprobadas que lo requieren (D1 atomicidad y savepoints; D2/D3 lectura y exactitud de planillas, incluida la dependencia nueva `python-multipart` aprobada por el usuario el 2026-10-01; D10 módulo y dependencias; D7 si se eligió B) y redactar en `propuesta-docs.md` el texto para `01` CST-05 (D8), `02` §5.1/§5.3 (D10), §6.5 (`IMPORTACION_REGISTRAR`) y `03` §13 (`importacion` con `COSTOS` y columnas de operación, D9/D14). No editar `docs/` hasta que el usuario apruebe el texto.
- [x] 11.2 Repasar la definición de terminado de `04` §2.1 en `verificacion.md` y nominar la deuda para el change 13 (importación de `PRECIOS`).
- [x] 11.3 Verificación manual en el navegador (último paso, la ejecuta el usuario): con un Administrador, descargar las plantillas; importar proveedores, productos (Vino A caja x6 + botella), clientes y costos; importar un archivo de clientes con dos filas malas y ver el informe sin ningún cliente creado; corregirlo y reimportarlo; importar stock inicial en depósito y vehículo y ver promedio `"1050.000000"` en el kardex; importar saldos iniciales y ver "Nos debe" en el estado de cuenta; ver el historial; con un Vendedor, comprobar que no ve la importación y recibe 403 por API. Pasos en `verificacion.md`.

## 12. Validaciones faltantes en el alta por pantalla (Lote 3, agregado 2026-10-01; ejecutar antes del grupo 11)

- [x] 12.1 RED (safety net previo sobre las pruebas de catálogo): `PRODUCTO_CREAR` con nombre, unidad base o nombre de presentación vacíos o solo espacios → error de dominio con código estable (reusar el existente si lo hay; si no, `VALOR_OBLIGATORIO` o el que defina `01`), sin escribir nada. GREEN en el dominio/servicio de catálogo, de modo que la importación de productos herede la misma regla sin duplicarla. TRIANGULATE: cada campo, vacío y solo espacios, y alta válida sin cambios.
- [x] 12.2 RED (safety net previo sobre las pruebas de clientes): `CLIENTE_CREAR` (y la modificación de cliente si acepta el mismo campo) con `estado_facturacion_default` fuera de `NO_REQUIERE`/`PENDIENTE` → 422 con error de dominio, nunca 500. GREEN en el dominio de clientes; la validación del importador de clientes pasa a apoyarse en esa regla. TRIANGULATE con valores válidos e inválidos. Si el frontend de `/admin` ofrece esos campos, verificar que sus formularios ya impiden los valores inválidos (sin cambiarlos salvo que falte).
- [x] 12.3 Agregar `VALOR_OBLIGATORIO` (nuevo en el lote 2, celdas obligatorias vacías) a la lista de códigos de `specs/importacion/` y anotar las dos validaciones de 12.1 y 12.2 en `propuesta-docs.md` para `01` (reglas de catálogo y clientes) en el grupo 11.
