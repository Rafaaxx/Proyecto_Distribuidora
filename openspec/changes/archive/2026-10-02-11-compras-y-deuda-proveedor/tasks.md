# Tareas — 11-compras-y-deuda-proveedor

> Modo TDD estricto: en cada tarea de los grupos 1 a 13, la prueba que falla se escribe **antes** que el código (RED → GREEN → TRIANGULATE con al menos dos casos por comportamiento → REFACTOR, con la suite en verde después de cada paso). Antes de tocar un archivo existente se corre su suite como red de seguridad. El grupo 14 completa la cobertura por escenario e invariante; no la reemplaza. Las tareas están escritas con la **opción A (recomendada)** de cada decisión de `design.md`; si la tarea 0.1 aprueba otra, se actualizan con `/opsx:update` antes de empezar.
>
> **Lotes de apply:** Lote 1 = grupos 0 a 5 (cálculo, migración y compra a crédito de punta a punta por API). Lote 2 = grupos 6 a 10 (costeo y stock ampliados, contado, anulación y consultas). Lote 3 = grupos 11 a 16 (pantallas, concurrencia, cobertura, docs y verificación manual).

## 0. Aprobación (bloqueante)

- [x] 0.1 (Aprobado 2026-10-02: D0 a D16, todas con la opción A; motivos de D8 "Error de carga", "Devolución al proveedor" y "Otro".) El usuario revisa y aprueba (o cambia) D0 a D16 de `design.md`, incluidas las contradicciones de documentos (D1: deuda con o sin IVA; D2/D3: pago de contado antes del change 12; D10: stock negativo contra ADR-039; D11: inactivos) y los nombres de los motivos de D8. Se anota fecha y opción en cada decisión. Si alguna difiere de la recomendada, se actualizan proposal, specs y tareas con `/opsx:update`. Verificable: `design.md` sin decisiones "Pendiente".

## 1. Fixtures compartidos (Lote 1, antes de cualquier cálculo)

- [x] 1.1 Agregar `shared/fixtures/calculo/cmp-02-compra.json` (D15) con los ejemplos de CST-02 de `01` §6.1 como líneas de compra (Caja x12 `18000.00` sin IVA → base 12, `"1500.000000"`, `"18000.00"`; con IVA 21% → `"1239.669421"`, `"14876.03"`; bonificación 10% → `"1350.000000"`, `"16200.00"`), cantidad fraccionaria válida (2,5 × 6 = 15) e inválida (2,3 × 6 → `CANTIDAD_INVALIDA`), total neto de la compra del criterio 2 (`"126000.00"`) e IVA sugerido (`"152460.00"`, D1). RED: casos ejecutados por pytest (`backend/tests/fixtures_compartidos/`) y Vitest (`frontend/tests/unit/calculo/cmp02.fixtures.test.ts`) fallan por falta de motor.
- [x] 1.2 Agregar a `cst-11-costo-promedio.json` la operación de reversión (D9) con los tres casos de la spec `costeo/costo-promedio` (120/`1050` − 60 a `1100` → `1000`, recalculado; 48 → −12, mantiene; 65/`1728.571429` − 60 a `2000` → mantiene). RED en ambas suites.

## 2. Migración (Lote 1)

- [x] 2.1 RED: `tests/integration/test_compras_migracion.py` que exige `compra`, `compra_linea`, `pago_proveedor` y `pago_proveedor_medio` según `03` §6 + D12: `UNIQUE (organizacion_id, id)`, FK compuestas (proveedor, ubicación, producto, presentación, medio de pago, motivo, usuario, dispositivo), `CHECK` de catálogo y de rangos, coherencia de anulación, `compra_id` único en `pago_proveedor`, índices de D12, privilegios de `app_runtime` (sin `DELETE` en ninguna; sin `UPDATE` en líneas ni medios, INV-05) y motivos de `ANULACION_COMPRA` sembrados una sola vez en organizaciones existentes (D8). GREEN: revisión de Alembic. Verificable con la prueba, `alembic upgrade head` y `downgrade -1` sobre una base con datos.
- [x] 2.2 RED: la prueba de catálogo de columnas (INV-03/INV-04) incluye las tablas nuevas (`numeric` en importes y costos, `integer` en cantidades base). GREEN si hace falta.

## 3. Módulo, modelos y límites (Lote 1)

- [x] 3.1 RED: contrato de import-linter: `proveedores` usa `stock`, `costeo`, `cuentas_corrientes`, `configuracion` y `catalogo` solo por `service.py`; `proveedores.domain` sin infraestructura. GREEN: modelos SQLAlchemy de compras y pagos iguales a la migración (`alembic revision --autogenerate` sin diferencias), registro en `alembic/env.py`. Verificable con `lint-imports`.
- [x] 3.2 RED: `tests/unit/test_seed.py` (o el existente) exige los motivos de `ANULACION_COMPRA` de D8 en una organización nueva. GREEN en `app/seed.py`.

## 4. Dominio de compras (Lote 1, funciones puras)

- [x] 4.1 RED en `tests/unit/test_proveedores_domain_compras.py`: cálculo de línea y totales sobre `calcular_costo_base` (CMP-02, D5) consumiendo `cmp-02-compra.json`; `CANTIDAD_INVALIDA`, `VALOR_INVALIDO`, `BONIFICACION_INVALIDA`, más de 3 decimales en cantidad, más de 200 líneas, `COMPRA_SIN_LINEAS` (cita INV-07); propiedad Hypothesis: `total_neto` = suma de importes de línea y cantidad base entera (cita INV-04). GREEN en `proveedores/domain/compras.py`; motor TS en `frontend/src/domain/compras/` que pasa 1.1.
- [x] 4.2 RED: validación de condición y medios (D2): crédito sin medios, contado con medios que suman `total_factura` (`MEDIOS_NO_SUMAN_IMPORTE`, propiedad Hypothesis que cita INV-08), referencia obligatoria (`REFERENCIA_OBLIGATORIA`), `total_factura` con 2 decimales y > 0 (`IMPORTE_INVALIDO`), fecha no futura (`FECHA_INVALIDA`, D6). GREEN.
- [x] 4.3 RED: comparación CMP-04 (D7): lista de líneas con costo distinto del vigente o sin vigente; igual no aparece. GREEN.

## 5. Compra a crédito de punta a punta (Lote 1)

- [x] 5.1 RED en `tests/integration/test_compras_confirmar.py`: escenario del criterio 2 (Vino A por caja + Cerveza B por botella, crédito): compra `CONFIRMADA`, movimientos `COMPRA` con costo base, promedios `"1000.000000"`/`"1100.000000"`, `COMPRA` en la cuenta por `total_factura`; promedio con stock previo (`"1050.000000"`, CST-11); dos líneas del mismo producto; validaciones de referencias (`PRESENTACION_INVALIDA`, `PROVEEDOR_NO_CORRESPONDE`, `PROVEEDOR_INACTIVO`, `PRODUCTO_INACTIVO`, `UBICACION_INACTIVA`, 404 ajeno, cita INV-21); idempotencia y `COMANDO_INCONSISTENTE` (cita INV-06); `OFFLINE` rechazado (CMP-08); 403 sin `REGISTRAR_COMPRA`; una auditoría (ADR-022); `diferencias_de_costo` en el resultado sin crear costos (CMP-04). GREEN: `proveedores/service.py::confirmar_compra` con el orden de bloqueo de `design.md` y handler `COMPRA_CONFIRMAR` v1.
- [x] 5.2 RED: falla inyectada después de `registrar_movimientos` y antes de la cuenta → ningún efecto (cita INV-01). GREEN si hace falta.
- [x] 5.3 RED: `tests/integration/test_compras_api.py` para `POST /api/v1/compras` (Operation-Id obligatorio, Problem Details con la línea en errores de línea, importes como string). GREEN: ruta, esquemas Pydantic y tipos de OpenAPI regenerados (`npm run generate:api-types`).
- [x] 5.4 RED: `test_inv18_presentacion_usada_en_compra_es_congelada` (compra confirmada y anulada después). GREEN: `_presentacion_tiene_compra` registrado en `catalogo/service.py::registrar_verificador_uso` al importar `proveedores/service.py`.

## 6. Reversión del promedio en `costeo` (Lote 2)

- [x] 6.1 Red de seguridad: suite de `costeo` y de `stock` en verde. RED en `tests/unit/test_costeo_domain_reversion.py`: `calcular_reversion` (CMP-06) con los casos de 1.2 y una propiedad Hypothesis: ingreso seguido de reversión devuelve el promedio previo dentro de `0.000001 × (S+q)/S` cuando `S > 0`. GREEN en `costeo/domain/costo_promedio.py` y en el motor TS de CST-11, de modo que los casos de 1.2 pasan en las dos suites.
- [x] 6.2 RED en `tests/integration/test_costeo_service.py`: `revertir_ingreso` actualiza `costo_producto` y escribe siempre `costo_producto_mov` con `ANULACION_COMPRA`, cantidad negativa, costo de la línea y `recalculado` (D9; cita CST-13 y la deuda del 09); reconstrucción de la historia. GREEN en `costeo/service.py`.

## 7. Ampliación de `stock` (Lote 2)

- [x] 7.1 Red de seguridad: suite completa de `stock` y `importacion` en verde. RED en `tests/integration/test_stock_movimientos.py`: egreso `ANULACION_COMPRA` con costo delega en `costeo.revertir_ingreso` y queda en el kardex con ese costo; sin costo → `COSTO_INVALIDO`; producto inactivo admitido solo para `ANULACION_COMPRA` (D11); `permitir_negativo` solo para `ANULACION_COMPRA`, con marca de saldo negativo en el resultado; sin él, `STOCK_INSUFICIENTE` (D10). GREEN en `stock/domain/movimientos.py` y `stock/service.py` con parámetros por defecto que conservan el comportamiento del 09.

## 8. Compra de contado (Lote 2)

- [x] 8.1 RED en `tests/integration/test_compras_contado.py`: efectivo + transferencia con referencia → `pago_proveedor` (`origen = COMPRA`, `compra_id`) con dos medios, `COMPRA` y `PAGO` en la cuenta, saldo sin cambio (CC-05, PAG-01, cita INV-08); medios que no suman; medio inactivo o de otra organización; referencia faltante; crédito con medios → `CONDICION_INVALIDA`. GREEN.

## 9. Anulación (Lote 2)

- [x] 9.1 RED en `tests/integration/test_compras_anular.py` con los escenarios de la spec `proveedores/anulacion-de-compras`: crédito; recalcula (`"1000.000000"`); stock restante cero y promedio no positivo con `ANULACION_COMPRA_SIN_RECALCULO`; sin permiso de negativo → `STOCK_INSUFICIENTE`; con permiso → −12 y `STOCK_NEGATIVO`; contado con `devuelve_pago` true/false; `COMPRA_YA_ANULADA`; idempotencia; `MOTIVO_INVALIDO`; 403 sin `ANULAR_COMPRA`; 404 ajeno; producto desactivado después (D11). GREEN: `proveedores/service.py::anular_compra` (compra `FOR UPDATE`, luego el orden global, líneas en orden inverso) y handler `COMPRA_ANULAR` v1 con observaciones.
- [x] 9.2 RED: falla inyectada después del egreso y antes de la cuenta → la compra sigue `CONFIRMADA` sin efectos (cita INV-01). GREEN si hace falta.
- [x] 9.3 RED: `POST /api/v1/compras/{id}/anulacion` en `test_compras_api.py`. GREEN y tipos regenerados.

## 10. Consultas (Lote 2)

- [x] 10.1 RED: `GET /api/v1/compras` (filtros proveedor, estado, fechas en la zona de la organización, cursor, límite 1 a 200 con 422 fuera de rango, 403 sin permiso, aislamiento) y `GET /api/v1/compras/{id}` (líneas, pago, anulación). GREEN en `proveedores/queries.py` y `api.py`.
- [x] 10.2 RED: filtro `proveedor_id` en `GET /api/v1/catalogo/productos` (spec `catalogo/productos-y-presentaciones`, proveedor ajeno → lista vacía). GREEN en `catalogo/queries.py`/`api.py`.
- [x] 10.3 RED: `GET /api/v1/configuracion/medios-pago` y `GET /api/v1/configuracion/motivos?ambito=` (`AMBITO_INVALIDO`, aislamiento). GREEN.
- [x] 10.4 RED: las rutas nuevas entran en los ratchets de aislamiento (INV-21) y de permisos. GREEN.

## 11. Frontend: datos y dominio (Lote 3)

- [x] 11.1 RED en `frontend/tests/unit/features/compras/`: hooks de TanStack Query para listar, detallar, confirmar y anular (mismo `Operation-Id` al reintentar tras error de red, nuevo al cambiar el contenido), medios y motivos. GREEN en `frontend/src/features/compras/`.
- [x] 11.2 RED: `CostosCargaScreen.test.tsx` exige que pida productos con `proveedor_id` al servidor (deuda del 06). GREEN en `CostosCargaScreen.tsx`.

## 12. Pantallas `/admin` (Lote 3)

- [x] 12.1 RED en `frontend/tests/unit/areas/admin/compras/`: menú y rutas por permiso (spec `proveedores/administracion-de-compras`); formulario con proveedor activo, productos del proveedor, presentaciones de compra, vista previa de línea y totales (Caja x12 con IVA → `1.239,669421` / `14.876,03`), total de factura prellenado y editable, medios de contado con faltante; error del servidor junto a su línea. GREEN en `frontend/src/areas/admin/compras/` (sin lógica de negocio en componentes).
- [x] 12.2 RED: resultado con oferta "Registrar como costo informado" solo con `EDITAR_COSTOS`, que envía `COSTO_INFORMAR` con vigencia = fecha de la compra (D7); sin acción no se envía nada. GREEN.
- [x] 12.3 RED: listado paginado con filtros, detalle con cajas + unidades (CAT-08), anulación con motivo y `devuelve_pago` en contado, aviso de observaciones. GREEN. Verificable con `npm run test`, `npm run typecheck` y `npm run lint`.

## 13. Concurrencia (Lote 3)

- [x] 13.1 RED en `tests/concurrency/test_compras_concurrencia.py` (commits reales): dos compras simultáneas al mismo proveedor con productos en orden inverso → sin interbloqueo, stock, promedio y saldo de aplicar ambas; compra en paralelo con `STOCK_INICIAL_REGISTRAR` del mismo producto; dos anulaciones simultáneas de la misma compra → una `COMPRA_YA_ANULADA` y un solo egreso por línea; mismo `Operation-Id` en paralelo → un solo efecto (cita INV-06). GREEN si hace falta.

## 14. Cobertura por escenario e invariante (Lote 3)

- [x] 14.1 Propiedad contra PostgreSQL real (`tests/properties/test_compras_inv12_inv13.py`): compras y anulaciones aleatorias válidas dejan `stock_saldo` = suma del libro, `stock_total` = suma de saldos y `saldo_cuenta` = suma de `cuenta_movimiento` (cita INV-12 e INV-13); confirmar y anular sin movimientos intermedios devuelve stock y saldo exactos.
- [x] 14.2 Pruebas de integración finales: cada escenario de las seis specs delta tiene al menos una prueba que lo cubre (tabla escenario → prueba en el resumen del lote); INV-01, INV-05, INV-06, INV-07, INV-08, INV-12, INV-13, INV-18 e INV-21 citados por ID. Suite completa de backend (`pytest`, `ruff`, `mypy`, `lint-imports`) y frontend en verde, sin `skip`/`xfail` injustificados.

## 15. ADRs, documentación y cierre (Lote 3)

- [x] 15.1 Redactar ADR-043 (deuda, pago de contado y anulación de compras: D1, D2, D3, D4, D5, D6, D7, D11, D13, D14, D16) y ADR-044 (reversión y stock negativo en `stock`/`costeo`, enmienda ADR-039: D9, D10), en estado *Propuesto* hasta la aprobación del usuario.
- [x] 15.2 Propuesta de cambios a `docs/` para revisión del usuario: `01` (CMP-01/02/03/05/06 con las reglas aprobadas, SYN-07 sin cambios), `02` §5.3/§6.5 (dependencias y comandos), `03` §4 y §6 (D8, D12), `04` (deudas del 05, 06 y 09 saldadas, deudas nuevas para el 12).

## 16. Verificación manual (Lote 3, último paso)

- [x] 16.1 Si algún lote agregó una dependencia a `requirements.txt` o `package.json`, reconstruir antes las imágenes (`docker compose up -d --build backend`, y `frontend` si corresponde); si no se agregó ninguna, anotarlo.
- [x] 16.2 El usuario prueba en el navegador el flujo principal: compra a crédito del criterio 2 (stock, promedio en la ficha del producto con `VER_COSTOS`, deuda en la cuenta del proveedor), compra de contado con dos medios, oferta de costo informado, anulación con y sin recálculo, anulación de contado devolviendo y sin devolver el pago, y el selector de productos filtrado en la carga de costos. Se registra el resultado en `verificacion.md`.
