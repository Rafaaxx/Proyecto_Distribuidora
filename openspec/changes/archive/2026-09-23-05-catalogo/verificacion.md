# Verificación — change 05 `catalogo`

Grupo 13 de `tasks.md` (13.1 a 13.4; 13.5 es un script para verificación manual, no ejecutado por el agente). Referencias: `docs/04-roadmap-changes.md` §2.1.

## 13.1 — Mapeo escenario → prueba

Convención: `archivo::prueba` (Python) o `archivo :: describe > it` (TypeScript). Todas las rutas son relativas a `backend/` o `frontend/` según corresponda.

### Spec `administracion-de-catalogo`

| Escenario | Prueba(s) |
| --- | --- |
| Usuario con permiso | `tests/unit/areas/admin/catalogo/ProductosListScreen.test.tsx :: ProductosListScreen > lista los productos de la primera página` |
| Usuario sin permiso | `tests/unit/areas/admin/catalogo/ProductosListScreen.test.tsx :: ProductosListScreen > ante PERMISO_REQUERIDO muestra el mensaje de falta de permiso y no la tabla` |
| Equivalencia de presentaciones en el detalle | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — edición > muestra la equivalencia CAT-08 de cada presentación contra la referencia` |
| Buscar por código | `tests/unit/areas/admin/catalogo/ProductosListScreen.test.tsx :: ProductosListScreen > reenvía el texto de búsqueda como filtro` (envío del filtro) + `backend/tests/integration/test_catalogo_repository.py::test_listar_productos_paginado_filtra_por_texto_excluye_no_coincidentes` (**agregada en 13.1**, exclusión real VA-001/CB-001) |
| Alta de producto con presentaciones | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — alta > crea un producto con una presentación de referencia y navega al detalle` + `backend/tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_alta_completa_y_detalle` |
| El formulario impide dos referencias | `tests/unit/domain/catalogo/productoSchema.test.ts :: exactamente una referencia con venta (CAT-03) > rechaza cuando ninguna presentación es de referencia` y `> rechaza cuando hay más de una presentación de referencia` |
| Reintento tras error de red no duplica | `tests/unit/features/catalogo/useMutacionesCatalogo.test.tsx :: useCrearCategoria: Operation-Id en reintentos > reenvía el mismo Operation-Id cuando el primer intento falla por error de red` (mecanismo genérico) + `backend/tests/integration/test_catalogo_commands_bus.py::test_producto_crear_aceptado_deja_producto_y_presentaciones_con_una_auditoria` (reenvío idéntico, servidor) |
| Código duplicado informado por el servidor | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — alta > muestra CODIGO_DUPLICADO junto al campo código y conserva el resto de los datos cargados` |
| Unidades congeladas informadas por el servidor | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — edición > ante UNIDADES_CONGELADAS al editar una presentación usada, muestra el mensaje del servidor` (**agregada en 13.1**, no existía prueba de este escenario) |
| Una marca desactivada no se ofrece | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — solo categorías/marcas activas > no ofrece una marca desactivada en el selector` (**agregada en 13.1**, solo existía el caso simétrico de categoría) |
| Una alícuota desactivada no se ofrece | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — selector de alícuota > el selector ofrece las alícuotas activas y no una desactivada` |
| Las alícuotas de otra organización no se listan | `backend/tests/integration/test_configuracion_api.py::TestAislamientoInv21::test_cada_organizacion_lista_solo_sus_propias_alicuotas` + `backend/tests/integration/test_configuracion_repository.py::test_nunca_devuelve_alicuotas_de_otra_organizacion` |

### Spec `categorias-y-marcas`

| Escenario | Prueba(s) |
| --- | --- |
| Alta de una categoría | `tests/integration/test_catalogo_api.py::TestCrearCategoria::test_un_usuario_con_gestionar_catalogo_crea_una_categoria` + `tests/integration/test_catalogo_commands_bus.py::test_categoria_crear_aceptado_deja_una_sola_fila_de_auditoria` |
| Alta de una marca | `tests/integration/test_catalogo_api.py::TestMarcas::test_crear_y_modificar_una_marca` |
| Doble envío del mismo alta no duplica | `tests/integration/test_catalogo_commands_bus.py::test_reenvio_identico_no_duplica` + `tests/integration/test_catalogo_api.py::TestCrearCategoria::test_reenvio_del_mismo_operation_id_devuelve_la_misma_categoria` |
| Sin permiso se rechaza sin efectos | `tests/integration/test_catalogo_api.py::TestCrearCategoria::test_sin_el_permiso_se_rechaza_sin_efectos_ni_reserva` |
| Nombre repetido en la misma organización | `tests/integration/test_catalogo_repository.py::test_nombre_duplicado_de_categoria_se_traduce_a_error_de_dominio` + `tests/integration/test_catalogo_service.py::test_crear_categoria_nombre_duplicado_rechaza` + `tests/integration/test_catalogo_migracion.py::test_cat01_ux_categoria_nombre_rechaza_duplicado_en_la_misma_organizacion` |
| El mismo nombre en otra organización es válido | `tests/integration/test_catalogo_api.py::TestCrearCategoria::test_el_mismo_nombre_en_otra_organizacion_es_valido` (**agregada en 13.1**, no existía) |
| Nombre vacío o solo espacios | `tests/integration/test_catalogo_service.py::test_crear_marca_nombre_vacio_rechaza` + `tests/unit/test_catalogo_domain_nombres.py::test_normalizar_nombre_vacio_o_solo_espacios_es_invalido` |
| Renombrar una marca | `tests/integration/test_catalogo_api.py::TestMarcas::test_crear_y_modificar_una_marca` |
| Desactivar una categoría con productos activos | `tests/integration/test_catalogo_service.py::test_d11_desactivar_categoria_con_productos_activos_rechaza` |
| Una categoría inactiva no se asigna a productos nuevos | `tests/integration/test_catalogo_service.py::test_crear_producto_categoria_inactiva_rechaza` |
| Categoría de otra organización | `tests/integration/test_catalogo_api.py::TestModificarCategoria::test_modificar_una_categoria_de_otra_organizacion_responde_404` + `tests/integration/test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeCategorias::test_modificar_una_categoria_de_otra_organizacion_no_la_encuentra` |
| Listado filtrado por activas | `tests/integration/test_catalogo_repository.py::test_listar_categorias_paginado_solo_activas_excluye_inactivas` y `test_listar_marcas_paginado_solo_activas_excluye_inactivas` (**agregadas en 13.1**; el parámetro `solo_activas` de la API no tenía ninguna prueba) |
| Listado aislado por organización | `tests/integration/test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeCategorias::test_listar_categorias_no_incluye_las_de_otra_organizacion` + `TestAislamientoDeMarcas::test_listar_marcas_no_incluye_las_de_otra_organizacion` |

### Spec `productos-y-presentaciones`

| Escenario | Prueba(s) |
| --- | --- |
| Alta de un vino con botella y caja x6 | `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_alta_completa_y_detalle` + `tests/integration/test_catalogo_commands_bus.py::test_producto_crear_aceptado_deja_producto_y_presentaciones_con_una_auditoria` |
| Doble envío del alta no duplica el producto | `tests/integration/test_catalogo_commands_bus.py::test_reenvio_identico_no_duplica` |
| Mismo `operation_id` con contenido distinto | `tests/integration/test_catalogo_commands_bus.py::test_mismo_operation_id_con_contenido_distinto_es_inconsistente` |
| Alta sin presentaciones | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat02_alta_sin_presentaciones_es_invalida` + `tests/integration/test_catalogo_service.py::test_crear_producto_sin_presentaciones_rechaza` |
| Alta sin presentación de referencia o con dos | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat03_alta_sin_ninguna_referencia_es_invalida` y `test_cat03_alta_con_dos_referencias_es_invalida` |
| Una falla en una presentación no deja el producto a medias | `tests/unit/test_catalogo_domain_presentaciones.py::test_una_falla_de_unidades_en_una_presentacion_no_referencia_se_reporta` + `tests/integration/test_catalogo_service.py::test_una_presentacion_invalida_no_deja_nada_escrito` |
| Alícuota, categoría o marca inexistente, inactiva o ajena | `tests/integration/test_catalogo_service.py::test_crear_producto_alicuota_inexistente_da_404`, `test_crear_producto_alicuota_inactiva_rechaza`, `test_crear_producto_categoria_inactiva_rechaza` + `tests/integration/test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_crear_producto_con_categoria_de_otra_organizacion_no_la_encuentra`, `test_crear_producto_con_marca_de_otra_organizacion_no_la_encuentra`, `test_crear_producto_con_alicuota_de_otra_organizacion_no_la_encuentra` |
| El código del producto es único (código repetido) | `tests/integration/test_catalogo_repository.py::test_codigo_duplicado_de_producto_se_traduce_a_error_de_dominio` + `tests/integration/test_catalogo_service.py::test_crear_producto_codigo_duplicado_rechaza` + `tests/integration/test_catalogo_migracion.py::test_cat01_ux_producto_codigo_rechaza_duplicado` |
| Dos altas concurrentes con el mismo código | `tests/concurrency/test_catalogo_concurrencia.py::test_dos_altas_simultaneas_con_el_mismo_codigo_una_aceptada_una_codigo_duplicado` |
| El alta no exige proveedor antes del change 06 | Cubierto implícitamente por toda alta de producto en `test_catalogo_service.py` (`proveedor_id=None` en cada llamada, p. ej. `test_crear_producto_con_presentaciones_en_una_sola_unidad`) — no hay ningún camino de código que exija `proveedor_id` todavía |
| Desactivar y reactivar un producto | `tests/integration/test_catalogo_service.py::test_desactivar_y_reactivar_producto_conserva_presentaciones` |
| Cambiar la alícuota del producto | `tests/integration/test_catalogo_service.py::test_cambiar_la_alicuota_del_producto` (**agregada en 13.1**, no existía) |
| Producto inexistente o de otra organización | `tests/integration/test_catalogo_service.py::test_modificar_producto_de_otra_organizacion_da_404` + `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_producto_de_otra_organizacion_responde_404` + `tests/integration/test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_modificar_un_producto_de_otra_organizacion_no_lo_encuentra` |
| No existe borrado de productos | `tests/integration/test_catalogo_migracion.py::test_cat05_app_runtime_no_puede_borrar_de_ninguna_tabla_de_catalogo` |
| Agregar una presentación de compra | `tests/integration/test_catalogo_service.py::test_agregar_presentacion_de_compra` + `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_agregar_modificar_y_cambiar_referencia_de_presentacion` |
| Unidades no enteras o menores a 1 | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat02_unidades_base_menor_a_uno_es_invalida`, `test_inv04_unidades_no_enteras_son_invalidas`, `test_unidades_base_booleana_es_invalida` + `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_agregar_presentacion_con_unidades_invalidas_responde_error_de_dominio` |
| Desactivar la presentación de referencia | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat03_referencia_no_puede_desactivarse`, `test_cat03_referencia_no_puede_dejar_de_usarse_en_venta` + `tests/integration/test_catalogo_service.py::test_desactivar_referencia_directamente_rechaza` |
| Presentación de otra organización | `tests/integration/test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDePresentaciones::test_modificar_una_presentacion_de_otra_organizacion_no_la_encuentra` |
| Cambiar la referencia | `tests/integration/test_catalogo_service.py::test_cambiar_referencia` + `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_agregar_modificar_y_cambiar_referencia_de_presentacion` |
| La nueva referencia no se usa en venta o está inactiva | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat03_nueva_referencia_inactiva_o_sin_venta_es_invalida` + `tests/integration/test_catalogo_service.py::test_cambiar_referencia_hacia_inactiva_conserva_la_anterior` |
| La base rechaza una segunda referencia escrita por fuera del servicio | `tests/integration/test_catalogo_migracion.py::test_cat03_ux_presentacion_referencia_rechaza_segunda_referencia_directa` + `tests/integration/test_catalogo_repository.py::test_segunda_referencia_directa_se_traduce_a_referencia_invalida` |
| Dos cambios de referencia concurrentes | `tests/concurrency/test_catalogo_concurrencia.py::test_dos_cambios_de_referencia_simultaneos_dejan_exactamente_una_referencia` |
| La base rechaza una referencia que no se usa en venta | `tests/integration/test_catalogo_migracion.py::test_cat03_ck_referencia_venta_rechaza_referencia_sin_venta` |
| Cambiar las unidades de una presentación sin uso | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat04_cambiar_unidades_sin_uso_es_valido` + `tests/integration/test_catalogo_service.py::test_cambiar_unidades_de_presentacion_sin_uso_es_permitido` |
| INV-18 — cambiar las unidades de una presentación usada | `tests/unit/test_catalogo_domain_presentaciones.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado` + `tests/integration/test_catalogo_service.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado` |
| Una presentación usada sí puede renombrarse o desactivarse | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat04_presentacion_usada_puede_renombrarse_o_desactivarse_sin_cambiar_unidades` + `tests/integration/test_catalogo_service.py::test_cat04_presentacion_usada_puede_renombrarse_y_desactivarse` |
| Listado paginado por cursor | `tests/integration/test_catalogo_repository.py::test_listar_productos_paginado_recorre_todos_sin_repetir` |
| Detalle con presentación de referencia | `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_alta_completa_y_detalle` + `tests/integration/test_catalogo_service.py::test_lecturas_publicas_de_producto_y_referencia` |
| Producto de otra organización (detalle) | `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_producto_de_otra_organizacion_responde_404` + `tests/integration/test_inv21_aislamiento_endpoints_catalogo.py::TestAislamientoDeProductos::test_obtener_un_producto_de_otra_organizacion_no_lo_encuentra` |

### Spec `visualizacion-de-cantidades`

| Escenario | Prueba(s) |
| --- | --- |
| Vino A, caja x6, 31 unidades / Cerveza B, caja x12, 31 unidades / Cantidad negativa / Cantidad cero y referencia de una unidad | `backend/tests/fixtures_compartidos/test_cat08_visualizacion_fixtures.py::test_caso_compartido_de_cat08` (recorre `shared/fixtures/calculo/cat-08-visualizacion.json`, 7 casos) + `frontend/tests/unit/calculo/cat08.fixtures.test.ts` (mismos casos) |
| Unidades de referencia inválidas | Casos `u=0` y `u=-6` del mismo fixture compartido (inválidos, ambas suites) |
| Los ejemplos de CAT-08 corren en ambas suites | Confirmado por la ejecución conjunta de `pytest tests/fixtures_compartidos` y `npm run test -- tests/unit/calculo`: ambas 100% verdes sobre el mismo archivo `shared/fixtures/calculo/cat-08-visualizacion.json` |
| Propiedad de reconstrucción | `backend/tests/properties/test_cat08_reconstruccion.py::test_cat08_inv04_reconstruccion_exacta` (Hypothesis) |

## Gaps encontrados y cerrados en 13.1

Seis escenarios con nombre propio en las specs no tenían ninguna prueba que los ejerciera. Se agregó una prueba real por cada uno (no tautológica: cada una ejercita el comportamiento y se corrió en verde antes de darla por buena):

1. **"Buscar por código"** (administracion-de-catalogo) — `backend/tests/integration/test_catalogo_repository.py::test_listar_productos_paginado_filtra_por_texto_excluye_no_coincidentes`. Antes solo había una prueba de paginación que usaba `texto` como prefijo compartido por todos los códigos creados (no probaba exclusión).
2. **"Unidades congeladas informadas por el servidor"** (administracion-de-catalogo) — `frontend/tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx`, nueva prueba en el describe de edición. El mecanismo de despliegue del error (`errors.root`) ya existía y funcionaba (la prueba pasó sin tocar código de producción), pero no estaba ejercitado.
3. **"Una marca desactivada no se ofrece"** (administracion-de-catalogo) — `frontend/tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx`, simétrica a la prueba ya existente de categoría inactiva.
4. **"El mismo nombre en otra organización es válido"** (categorias-y-marcas) — `backend/tests/integration/test_catalogo_api.py::TestCrearCategoria::test_el_mismo_nombre_en_otra_organizacion_es_valido`.
5. **"Listado filtrado por activas"** (categorias-y-marcas) — `backend/tests/integration/test_catalogo_repository.py::test_listar_categorias_paginado_solo_activas_excluye_inactivas` y la simétrica de marcas. El parámetro `solo_activas` existe de punta a punta (`api.py` → `queries.py` → `repository.py`) pero no tenía ninguna prueba en ningún nivel.
6. **"Cambiar la alícuota del producto"** (productos-y-presentaciones) — `backend/tests/integration/test_catalogo_service.py::test_cambiar_la_alicuota_del_producto`.

Las seis pruebas corrieron en verde (`pytest` / `vitest`) sin necesidad de tocar código de producción: el comportamiento ya estaba implementado, solo no estaba verificado por un escenario con ese nombre. Ningún gap requirió cambiar código de producción ni reveló un defecto.

## 13.2 — CAT-03, INV-18 e INV-21, evidencia

**CAT-03 (exactamente una presentación de referencia, activa y usada en venta), tres capas:**
- Servicio: `backend/tests/unit/test_catalogo_domain_presentaciones.py` (múltiples `test_cat03_*`, incluida la propiedad Hypothesis `test_propiedad_todo_conjunto_aceptado_tiene_exactamente_una_referencia_de_venta`).
- Índice único parcial `ux_presentacion__referencia`: `backend/tests/integration/test_catalogo_migracion.py::test_cat03_ux_presentacion_referencia_rechaza_segunda_referencia_directa`.
- `CHECK ck_presentacion__referencia_venta`: `backend/tests/integration/test_catalogo_migracion.py::test_cat03_ck_referencia_venta_rechaza_referencia_sin_venta`.
- Concurrencia (dos transacciones, commits reales): `backend/tests/concurrency/test_catalogo_concurrencia.py::test_dos_cambios_de_referencia_simultaneos_dejan_exactamente_una_referencia`.

**INV-18 (unidades congeladas una vez usada la presentación):**
- Dominio: `backend/tests/unit/test_catalogo_domain_presentaciones.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado`.
- Servicio (verificador de uso, `design.md` D2): `backend/tests/integration/test_catalogo_service.py::test_inv18_cambiar_unidades_de_presentacion_usada_es_congelado`, apoyado en `test_sin_verificadores_ninguna_presentacion_esta_usada` y `test_con_un_verificador_que_responde_true_la_presentacion_esta_usada`.
- Pantalla: `frontend/tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx` (nueva, ver gap 2 arriba).
- No hay prueba de concurrencia dedicada a INV-18 en este change: la ventana de carrera se cierra por diseño (`venta_linea` congela `unidades_presentacion` al momento de la operación, INV-18/PRC-23), no por un lock en `catalogo`; ese cierre lo ejercitará el change 18a cuando `venta_linea` exista. Confirmado que no es un gap de este change: no existe ningún módulo de operaciones todavía (06, 11, 18a nacen después).

**CAT-08 en ambas suites:** confirmado — `backend/tests/fixtures_compartidos/test_cat08_visualizacion_fixtures.py` y `frontend/tests/unit/calculo/cat08.fixtures.test.ts` ejecutan los mismos 7 casos de `shared/fixtures/calculo/cat-08-visualizacion.json` con su `id` visible (formato `02` §10.4). Corridas en verde en 13.3.

## 13.3 — Suite completa vs. línea base de 1.1

Todo corrido en este entorno (`backend/.venv`, Docker con Postgres real vía Testcontainers).

**Backend**
| Comando | Resultado | Línea base (1.1) |
| --- | --- | --- |
| `ruff check .` | limpio | limpio |
| `ruff format --check .` | 2 archivos preexistentes sin formatear (`identidad/api.py`, `test_bus_transaccion.py`), ninguno tocado por este change | mismos 2 archivos |
| `mypy app` | limpio, 66 archivos | limpio, 50 archivos (creció con el change) |
| `lint-imports` | 8 contratos en verde | 6 contratos (creció: D2 agregó "catalogo domain no importa..." y "catalogo solo alcanza..."), sin contratos rotos |
| `pytest tests/unit tests/fixtures_compartidos tests/properties` | **303 passed** | 242 passed |
| `pytest tests/integration` | **394 passed** | 289 passed (con 1 falla espuria documentada en 1.1, no real) |
| `pytest tests/concurrency` | **6 passed** | incluido en los 289 de integración+concurrencia de 1.1 |

El crecimiento de 242→303 y 289→394 corresponde al propio change 05 (grupos 1 a 12) más las 8 pruebas agregadas en 13.1 (2 en `test_catalogo_repository.py` de texto, 2 de `solo_activas`, 1 de "mismo nombre otra organización", 1 de "cambiar alícuota", 2 en frontend). Ningún test preexistente se rompió.

**Frontend**
| Comando | Resultado |
| --- | --- |
| `npm run typecheck` | limpio |
| `npm run lint` | 0 errores; 1 warning preexistente de React Compiler en `ProductoFormScreen.tsx:116` (uso de `watch()` de React Hook Form, ninguna línea tocada por este grupo) — no es una regresión de 13.1 |
| `npm run test` (Vitest) | **121 passed**, 19 archivos, sin skips |
| `npm run test -- tests/unit/calculo` | 41 passed (fixtures compartidos, 4 archivos) |
| `npm run build` | build de producción exitoso |

**`skip`/`xfail`:** `grep -rn "@pytest.mark.skip\|pytest.skip\|xfail"` sobre `backend/tests/` → **sin resultados**. `grep -rn "\.skip(\|\.todo(\|xit(\|xdescribe("` sobre `frontend/tests/` → **sin resultados**. No hay ningún skip/xfail que justificar en la suite de este change.

## 13.4 — Roadmap y ADRs

**`docs/04-roadmap-changes.md` actualizado:**
- Fila del change 05 (hito 2): `INV-18 (cerrado por completo), CAT-03 (cerrado por completo)`, siguiendo el estilo de las filas 03/04.
- Párrafo nuevo "**CAT-03 e INV-18 cerrados por el change 05...**" (mismo formato que el párrafo "INV-06 cerrado por el change 04"), con la evidencia de 13.2 resumida y referencia a `ADR-023` (propuesta).
- Deuda del grupo 12 (change 06: FK de `proveedor_id`, verificador de `costo_informado`; change 11: verificador de `compra_linea`; change 13: ADR sobre cambio de referencia con precios) ya estaba escrita — verificada, sin cambios necesarios.

**Revisión de decisiones nuevas (`design.md` D1–D12) contra §2.1 punto 7:**

| Decisión | ¿Necesita ADR? | Razón |
| --- | --- | --- |
| D1 — `producto.proveedor_id` nulable antes del change 06 | No | El propio `design.md` lo resuelve explícitamente: "sin ADR: es una decisión de secuencia, como D3 del `02`", con precedente ya establecido en el proyecto. |
| D2 — Puerto de verificadores de uso (CAT-04/INV-18) | **Sí — ADR-023 (Vigente)** | Establece un mecanismo de extensión reutilizable por tres changes futuros (06, 11, 18a) para resolver una dependencia entre módulos que `01`/`02`/`03` no anticipan; es arquitectura, no solo una decisión de este change, y es del mismo tipo que ADR-016 (motor de cálculo compartido). Aprobado por el usuario 2026-09-23 — ver `docs/adr/ADR-023-verificador-de-uso-de-presentaciones.md`. |
| D3 — Firma de los handlers de catálogo (sigue la plantilla D7 del change 04) | No | Sigue un patrón ya establecido en un ADR/change anterior; no introduce nada nuevo, solo lo reaplica. Deuda de corrección nominada al change 17, sin decisión nueva. |
| D4 — Granularidad de los comandos | No | Aplica el patrón ya usado por `identidad` (estado completo deseado en `*_MODIFICAR`); no es una decisión de arquitectura nueva. |
| D5 — Concurrencia (`SELECT FOR UPDATE` sobre `producto`) | No | Aplica el patrón de bloqueo ya documentado en `02` §7.3; no agrega un nivel nuevo al orden de bloqueo, solo lo usa. |
| D6 — Errores de dominio y unicidades | No | Seguimiento directo de `02` §6.3, ya establecido para todo el proyecto. |
| D7 — Auditoría | No | Aplica AUD-01/ADR-022 tal cual, sin variación. |
| D8 — CAT-08 como cálculo compartido | No | Aplica ADR-016 (motor de cálculo compartido) tal cual a un caso nuevo; no es una decisión nueva, es su aplicación. |
| D9 — Permiso de las lecturas (`GESTIONAR_CATALOGO`, sin permiso nuevo) | No | El propio `design.md` lo resuelve sin crear un permiso nuevo; no hay nada que anotar en `01` §19. |
| D10 — Primera pantalla de `/admin` | No | Decisión de implementación de UI (tokens, componentes, capas de datos), no de arquitectura de negocio o de datos. |
| D11 — Categoría con productos activos no se desactiva | **Sí — ADR-024 (Vigente)** | Es una interpretación de una regla que `01` deja abierta ("supuesto a confirmar"), aprobada por el usuario el 2026-09-22 dentro del propio `design.md`. Promovida a ADR en esta verificación (13.4) porque fija una regla de negocio releíble por changes futuros sin depender de un change ya archivado, y documenta explícitamente la asimetría con `marca` — ver `docs/adr/ADR-024-categoria-con-productos-activos-no-se-desactiva.md`, referenciado desde `design.md` D11. |
| D12 — Listado de alícuotas (`GET /configuracion/alicuotas`, permiso `GESTIONAR_CATALOGO`) | No | Sigue el mismo razonamiento que D9 (ya resuelto sin ADR) y el mismo contrato de paginación/forma de respuesta que `catalogo`; es una decisión de forma de API, no de arquitectura. |
| Import-linter: `allow_indirect_imports` en el contrato "configuracion no importa modelos ni repositorio de identidad" | No | La tarea 9.6 documenta que es "el mismo caso ya resuelto para `sync-solo-service`/`catalogo-solo-por-service-ajeno`": aplica una solución ya usada, no introduce un mecanismo nuevo. Revisado y aceptado por el usuario 2026-09-23. |

**Hallazgo adicional de 13.4 (import-linter):** `ignore_imports` del contrato `catalogo-solo-por-service-ajeno` traía `catalogo.api -> sync.models`, agregada solo porque `catalogo/api.py` importaba `Comando` de `sync.models` para anotar el tipo de `_resultado_de`. `identidad/api.py` nunca necesitó esa ruta porque no anota ese tipo. Se corrigió: `sync/service.py` re-exporta `Comando` explícitamente (`Comando as Comando`, requerido por `mypy strict`/`implicit_reexport = False`) y `catalogo/api.py` anota con `sync_service.Comando` (atributo del módulo `service.py` ya importado, sin importar `sync.models` directamente). Se retiró la ruta de `ignore_imports`; el contrato queda con una sola ruta ignorada (`sync.service`). Verificado: `lint-imports` 8/8, `ruff check .`, `mypy app`, `pytest tests/integration/test_catalogo_api.py tests/integration/test_catalogo_commands_bus.py tests/unit` (291 passed).

**Conclusión de 13.4:** `ADR-023` (D2) y `ADR-024` (D11) redactados y aprobados por el usuario 2026-09-23, ambos en estado `Vigente`. El hallazgo de import-linter (`catalogo.api -> sync.models`) se corrigió en el código, no solo se documentó. El resto de la tarea 13.4 (actualización del roadmap, verificación de la deuda del grupo 12) ya estaba terminado. **13.4 se marca `[x]`.**

## 13.5 — Verificación manual en el navegador (script para el usuario)

**No ejecutado por el agente** (requiere navegador). Datos de arranque reales del repositorio, no inventados: `README.md` y `backend/app/seed.py`.

> **Si las pantallas de `/admin` se ven sin estilo** (sin tarjetas, sin colores, como HTML sin CSS) al abrir el navegador por primera vez tras levantar el entorno: el servidor de desarrollo de Vite corriendo dentro del contenedor `frontend` a veces no detecta los cambios de archivos montados desde Windows por Docker Desktop (limitación conocida del *bind mount*, no un defecto de este change). Solución: `docker compose restart frontend` y recargar la página.

### 1. Preparación

> **Windows / PowerShell:** todos los comandos de este script son de `docker compose`/`psql`, iguales en cualquier shell. La única excepción es `curl`: en PowerShell `curl` es un alias de `Invoke-WebRequest` (otra sintaxis) — usar `curl.exe` en su lugar. Pegar **un comando por línea** (no dos comandos separados por espacio en la misma línea): PowerShell no corta silenciosamente, pero un bloque copiado con varios comandos en una sola línea puede ejecutarse distinto a lo esperado.

```bash
# Desde la raíz del repo. Si no existe, copiar .env.example a .env y completar
# APP_MIGRATIONS_DB_PASSWORD, APP_RUNTIME_DB_PASSWORD, JWT_SECRET
# (ninguno tiene valor por defecto, CLAUDE.md §4). ADMIN_PASSWORD NO va en
# este .env para este paso: `docker-compose.yml` no lo declara en
# `environment:` del servicio `backend` (solo lo usan `${}` las variables
# que sí están ahí), así que ponerlo en `.env` no lo hace llegar al
# contenedor. Se pasa explícitamente al correr la siembra, más abajo.
docker compose up -d

# Aplicar migraciones (rol app_migrations, nunca app_runtime):
docker compose exec backend alembic upgrade head

# Puesta en marcha (organización inicial + 5 roles + usuario admin + 3 alícuotas).
# ADMIN_PASSWORD se pasa acá con `-e` (elegir cualquier contraseña):
docker compose exec -e ADMIN_PASSWORD=CAMBIAR_ESTA_CLAVE backend python -m app.seed
```

> **La siembra nunca pisa la contraseña de un admin que ya existe** (`backend/app/seed.py`): si ya se corrió antes contra este volumen de Postgres, correrla de nuevo no cambia la contraseña ya fijada — solo importa el `ADMIN_PASSWORD` de la primera vez. Para reiniciar con una contraseña nueva (por ejemplo, si no se recuerda la anterior): `docker compose down -v` (borra el volumen de Postgres) y repetir este paso 1 completo (`up -d` → `alembic upgrade head` → `seed`).

Confirmar que el backend responde (en PowerShell, `curl.exe`; en bash, `curl`):

```bash
curl.exe http://localhost:8000/api/v1/salud
```

### 2. Login como ADM

- URL: `http://localhost:5173`
- Organización (slug): `organizacion-inicial`
- Usuario: `admin`
- Contraseña: la que se definió en `ADMIN_PASSWORD` al preparar el entorno

La alícuota **`21%`** ya existe en la siembra (`ALICUOTAS_INICIALES` en `backend/app/seed.py`: `21%`, `10,5%`, `0%`) — no hace falta crearla. Si por algún motivo no apareciera en el selector (por ejemplo, una base reseteada sin volver a sembrar), crearla a mano requiere un endpoint de alta de alícuotas que **no existe todavía** en este change (`configuracion/api.py` solo expone el listado, D12); en ese caso, volver a correr `python -m app.seed` contra una base recién migrada.

### 3. Categoría y marca

1. Ir a `/admin/catalogo` → pestaña de categorías/marcas.
2. Crear la categoría **`Vinos`**.
3. Crear la marca (a elección, por ejemplo `Bodega Norte`).

### 4. Alta de `Vino A`

1. Ir a "Nuevo producto".
2. Código `VA-001`, nombre `Vino A`, categoría `Vinos`, marca la creada en el paso 3.
3. Alícuota: elegirla del selector desplegable (no pegar un `uuid` a mano) — elegir **`21%`**.
4. Presentaciones:
   - `Botella`, 1 unidad, uso en venta (marcarla o no como referencia según se decida en el paso siguiente).
   - `Caja x6`, 6 unidades, uso en venta, marcada como **referencia**.
5. Confirmar. Verificar que navega al detalle de `Vino A` sin recargar la página y que `Caja x6` figura como la única referencia.

> **Cómo leer la columna "Equivalencia" (CAT-08):** cada presentación se muestra en términos de la referencia vigente, no al revés. Con `Caja x6` como referencia, la fila de `Botella` (1 unidad) muestra "0 Caja x6(s) + 1 unidad(es)" (una botella es una fracción de la caja de referencia, no la contiene ni una vez entera); la fila de la propia `Caja x6` (la referencia) muestra "—", porque no tiene sentido expresarla en términos de sí misma. Si en cambio se buscara cuántas veces entra `Botella` en `Caja x6`, ese cálculo (6 botellas por caja) no es lo que esta columna muestra.

### 5. `Caja x12` y cambio de referencia

1. En el detalle de `Vino A`, "Agregar presentación": `Caja x12`, 12 unidades, uso en venta.
2. Click en "Usar como referencia" sobre `Caja x12`. Verificar que pasa a ser la referencia y `Caja x6` deja de serlo (sin momento visible con cero o dos referencias — no hay forma de observar esto en la UI más allá de que el resultado final sea consistente).
3. Cambiar la referencia de nuevo si se quiere confirmar el camino inverso.

### 6. Código duplicado

1. Intentar dar de alta otro producto con código `VA-001`.
2. Verificar que el formulario muestra el error junto al campo código (`CODIGO_DUPLICADO`) y conserva los datos cargados.

### 7. Desactivar y reactivar

1. En el detalle de `Vino A`, editar el producto y desmarcar "Activo". Guardar.
2. Verificar que queda inactivo y que sus presentaciones conservan su estado (no se desactivan solas).
3. Volver a marcar "Activo" y guardar. Verificar que vuelve a activarse.

### 8. Auditoría — una fila por comando

Para cada comando confirmado arriba (alta de categoría, alta de marca, alta de producto, agregar presentación, cambiar referencia, código duplicado rechazado — este último NO debería dejar fila si el rechazo revierte la reserva, confirmar que efectivamente no aparece, `02` §6.3 — desactivar, reactivar), confirmar en la base:

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT operation_id, accion, origen, occurred_at FROM auditoria WHERE organizacion_id = (SELECT id FROM organizacion WHERE slug = 'organizacion-inicial') ORDER BY occurred_at;"
```

> Nota: el servicio de Postgres en `docker-compose.yml` se llama `postgres`, no `db` — usar `docker compose exec postgres psql -U distribuidora -d distribuidora -c "..."` (ajustar `-U`/`-d` si se cambiaron `POSTGRES_USER`/`POSTGRES_DB` en `.env`).

Verificar:
- Exactamente una fila por `operation_id` de los comandos aceptados (alta de categoría, de marca, de producto, `PRESENTACION_AGREGAR`, `PRESENTACION_REFERENCIA_CAMBIAR`, dos `PRODUCTO_MODIFICAR` de desactivar/reactivar).
- `origen = 'COMANDO'` en todas.
- El intento de código duplicado (rechazado) **no** dejó fila (la reserva se revierte, `02` §6.3).
- Si se reintentó alguna operación con el mismo `Operation-Id` (por ejemplo recargando la página tras un corte de red simulado), sigue habiendo una sola fila para ese `operation_id`, no dos.

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT operation_id, count(*) FROM auditoria WHERE operation_id IS NOT NULL GROUP BY operation_id HAVING count(*) > 1;"
```

Esta segunda consulta debe devolver **cero filas**: ningún `operation_id` audita más de una vez.
