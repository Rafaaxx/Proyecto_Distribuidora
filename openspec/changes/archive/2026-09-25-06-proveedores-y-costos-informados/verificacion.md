# Verificación — change 06 `proveedores-y-costos-informados`

Grupo 13 de `tasks.md` (13.1 a 13.4; 13.5 es un script para verificación manual, no ejecutado por el agente). Referencias: `docs/04-roadmap-changes.md` §2.1. Mismo formato que `openspec/changes/archive/2026-09-23-05-catalogo/verificacion.md`.

## 13.1 — Mapeo escenario → prueba

Convención: `archivo::prueba` (Python, `archivo::Clase::prueba` si está en una clase) o `archivo :: describe > it` (TypeScript). Rutas relativas a `backend/` o `frontend/`.

### Spec `proveedores/fichas-de-proveedor`

| Escenario | Prueba(s) |
| --- | --- |
| Alta de un proveedor | `tests/integration/test_proveedores_api.py::TestCrearYModificarProveedor::test_crear_y_modificar_un_proveedor_con_permiso` + `tests/integration/test_proveedores_commands_bus.py::TestProveedorCrearContraElBus::test_aceptado_deja_auditoria_y_reenvio_no_duplica` |
| Doble envío del alta no duplica el proveedor | `tests/integration/test_proveedores_commands_bus.py::TestProveedorCrearContraElBus::test_aceptado_deja_auditoria_y_reenvio_no_duplica` |
| Mismo `operation_id` con contenido distinto | `tests/integration/test_proveedores_commands_bus.py::TestProveedorCrearContraElBus::test_mismo_operation_id_con_contenido_distinto_es_inconsistente` |
| Sin permiso se rechaza sin efectos | `tests/integration/test_proveedores_api.py::TestCrearYModificarProveedor::test_sin_el_permiso_se_rechaza_sin_efectos_ni_reserva` |
| Nombre vacío | `tests/integration/test_proveedores_service.py::test_crear_proveedor_nombre_vacio_rechaza` (**agregada en 13.1**, no existía a nivel de servicio, solo `tests/unit/test_proveedores_domain_normalizacion.py::test_normalizar_nombre_vacio_o_solo_espacios_es_invalido`) |
| Nombre repetido | `tests/integration/test_proveedores_service.py::test_crear_proveedor_nombre_duplicado_rechaza` + `tests/integration/test_proveedores_migracion.py::test_d7_ux_proveedor_nombre_rechaza_duplicado_en_la_misma_organizacion` |
| CUIT repetido o mal formado | `tests/integration/test_proveedores_service.py::test_crear_proveedor_cuit_invalido_rechaza` + `tests/integration/test_proveedores_repository.py::test_cuit_duplicado_se_traduce_a_error_de_dominio` + `tests/integration/test_proveedores_migracion.py::test_d7_ux_proveedor_cuit_rechaza_duplicado_en_la_misma_organizacion` |
| El mismo nombre en otra organización es válido | `tests/integration/test_proveedores_migracion.py::test_d7_ux_proveedor_nombre_acepta_el_mismo_nombre_en_otra_organizacion` |
| Dos altas concurrentes con el mismo nombre | `tests/concurrency/test_proveedores_concurrencia.py::TestProveedorCrearConcurrente::test_dos_altas_simultaneas_con_el_mismo_nombre_una_aceptada_una_nombre_duplicado` |
| Renombrar un proveedor | `tests/integration/test_proveedores_service.py::test_modificar_proveedor` + `tests/integration/test_proveedores_api.py::TestCrearYModificarProveedor::test_crear_y_modificar_un_proveedor_con_permiso` |
| Desactivar y reactivar un proveedor sin productos activos | `tests/integration/test_proveedores_service.py::test_desactivar_y_reactivar_proveedor_sin_productos_activos_conserva_historial` (**agregada en 13.1**, no existía el ciclo completo con la aserción de historial de costos intacto; solo existían las dos mitades por separado y, en frontend, `tests/unit/areas/admin/proveedores/ProveedorFormScreen.test.tsx :: ProveedorFormScreen: ficha de edición (tarea 11.3, D5) > desactivar un proveedor sin productos activos lo deja inactivo (ofrece "Reactivar")`) |
| Desactivar un proveedor con productos activos | `tests/integration/test_proveedores_service.py::test_d5_desactivar_proveedor_con_productos_activos_rechaza` + `tests/concurrency/test_proveedores_concurrencia.py::TestDesactivarProveedorMientrasSeAsignaUnProductoActivo::test_desactivacion_y_asignacion_no_dejan_producto_activo_con_proveedor_inactivo` + `tests/unit/areas/admin/proveedores/ProveedorFormScreen.test.tsx :: ProveedorFormScreen: ficha de edición (tarea 11.3, D5) > desactivar un proveedor con productos activos muestra el error y el proveedor sigue activo` |
| Proveedor de otra organización | `tests/integration/test_proveedores_service.py::test_modificar_proveedor_de_otra_organizacion_da_404` + `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_modificar_un_proveedor_de_otra_organizacion_no_lo_encuentra` |
| No existe borrado de proveedores | `tests/integration/test_proveedores_migracion.py::test_app_runtime_no_puede_borrar_proveedor` |
| Listado paginado por cursor | `tests/integration/test_proveedores_repository.py::test_listar_proveedores_paginado_recorre_todos_sin_repetir` |
| Listado aislado por organización | `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_listar_proveedores_no_incluye_los_de_otra_organizacion` y `test_opciones_de_proveedores_no_incluye_los_de_otra_organizacion` |
| Listado reducido para el formulario de producto | `tests/integration/test_proveedores_api.py::TestOpcionesDeProveedores::test_lista_solo_activos_con_gestionar_catalogo` |
| El listado completo exige permiso de proveedores | `tests/integration/test_proveedores_api.py::TestOpcionesDeProveedores::test_listado_completo_y_detalle_exigen_gestionar_proveedores` (**agregada en 13.1**, la única prueba de rechazo existente usaba un usuario sin ningún permiso, no específicamente `GESTIONAR_CATALOGO` sin `GESTIONAR_PROVEEDORES`) |
| Detalle de un proveedor ajeno | `tests/integration/test_proveedores_api.py::TestCrearYModificarProveedor::test_obtener_un_proveedor_de_otra_organizacion_responde_404` + `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_obtener_un_proveedor_de_otra_organizacion_no_lo_encuentra` |

### Spec `proveedores/costos-informados`

| Escenario | Prueba(s) |
| --- | --- |
| Caja x12 sin IVA / Botella sin IVA / Caja x12 con IVA incluido / Caja x12 con bonificación | `tests/fixtures_compartidos/test_cst02_costo_base_fixtures.py::test_caso_compartido_de_cst02` (14 casos, incluidos los 4 ejemplos de `01` §6.1) + `frontend/tests/unit/calculo/cst02.fixtures.test.ts` (mismos casos) + `tests/integration/test_proveedores_api.py::TestInformarCostos::test_los_cuatro_ejemplos_de_cst02_devuelven_costo_base_como_string` (de punta a punta, HTTP) |
| Doble envío no duplica el costo | `tests/integration/test_proveedores_commands_bus.py::TestCostoInformarContraElBus::test_aceptado_deja_auditoria_y_reenvio_no_duplica` |
| Mismo `operation_id` con otro valor | `tests/integration/test_proveedores_commands_bus.py::TestCostoInformarContraElBus::test_mismo_operation_id_con_contenido_distinto_es_inconsistente` |
| Sin permiso para editar costos | `tests/integration/test_proveedores_api.py::TestInformarCostos::test_sin_el_permiso_se_rechaza_sin_efectos` |
| Valor o bonificación inválidos | `tests/unit/test_proveedores_domain_lote.py::test_valor_no_positivo_es_valor_invalido`, `test_valor_con_mas_de_dos_decimales_es_valor_invalido`, `test_bonificacion_fuera_de_rango_es_bonificacion_invalida`, `test_bonificacion_con_mas_de_seis_decimales_es_bonificacion_invalida` + `tests/integration/test_proveedores_migracion.py` (`ck_costo_informado__valor`/`ck_costo_informado__bonificacion`, capa de base) |
| Presentación que no es de compra, inactiva o de otro producto | `tests/integration/test_proveedores_service.py::test_informar_costos_presentacion_que_no_es_de_compra_rechaza` + `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: CostosCargaScreen (tarea 11.4) > solo presentaciones de compra: Vino A ofrece Botella y no Caja x6` |
| Producto o proveedor inactivo | `tests/integration/test_proveedores_service.py::test_informar_costos_producto_inactivo_rechaza` + `test_d5_informar_costos_proveedor_inactivo_rechaza` |
| Proveedor distinto del proveedor del producto | `tests/integration/test_proveedores_service.py::test_d3_informar_costos_proveedor_no_corresponde_rechaza` |
| Referencias de otra organización | `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_informar_costos_con_proveedor_de_otra_organizacion_no_lo_encuentra`, `test_informar_costos_con_producto_de_otra_organizacion_no_lo_encuentra`, `test_informar_costos_con_presentacion_de_otra_organizacion_no_la_encuentra` (esta última responde 422 `PRESENTACION_INVALIDA`, no 404 — ver nota de aislamiento más abajo) |
| Dos costos en una operación | `tests/integration/test_proveedores_service.py::test_informar_costos_calcula_y_persiste` + `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: carga de dos costos en un envío: se envía un único COSTO_INFORMAR con las dos filas` |
| INV-01 — una falla en un costo no deja los demás | `tests/integration/test_proveedores_service.py::test_inv01_tercer_costo_invalido_no_deja_nada_escrito` |
| Operación vacía o con costos repetidos | `tests/unit/test_proveedores_domain_lote.py::test_lote_vacio_es_costos_invalidos`, `test_lote_de_mas_de_doscientos_costos_es_costos_invalidos`, `test_dos_costos_mismo_producto_presentacion_y_vigencia_es_costos_invalidos` |
| Un costo nuevo no altera el anterior | `tests/integration/test_proveedores_migracion.py::test_cst01_costo_informado_fk_compuesta_a_proveedor_producto_presentacion_usuario` (inserción de dos costos) + `tests/integration/test_proveedores_service.py::test_obtener_costo_informado_vigente_y_listar_historial` |
| La base impide modificar o borrar un costo | `tests/integration/test_proveedores_migracion.py::test_cst03_app_runtime_no_puede_borrar_costo_informado`, `test_cst03_app_runtime_no_puede_modificar_costo_informado` |
| Cambiar la alícuota del producto no recalcula costos pasados | `tests/integration/test_catalogo_service.py::test_cambiar_la_alicuota_del_producto` (cambia la alícuota; la congelación de `alicuota_aplicada`/`costo_base` en la fila ya escrita es estructural: la columna nunca se actualiza, sin código que la recalcule) — cubierto también por la regla simétrica de `03` §6 citada en el propio requisito |
| Vigente entre dos vigencias | `tests/integration/test_proveedores_api.py::TestVigenteYHistorial::test_vigente_con_las_tres_fechas_del_escenario` + `tests/integration/test_proveedores_repository.py::test_obtener_vigente_elige_mayor_vigencia_que_no_supera_la_fecha` |
| Misma vigencia desde | `tests/integration/test_proveedores_repository.py::test_obtener_vigente_desempata_por_creado_en_con_la_misma_vigencia` + `tests/unit/test_proveedores_domain_vigencia.py::test_misma_vigencia_desde_prevalece_el_mayor_creado_en` |
| Consulta sin permiso de ver costos | `tests/integration/test_proveedores_api.py::TestVigenteYHistorial::test_vigente_sin_el_permiso_se_rechaza`, `test_historial_sin_el_permiso_se_rechaza` |
| Historial ordenado | `tests/integration/test_proveedores_repository.py::test_listar_historial_de_producto_recorre_todo_sin_repetir` + `tests/integration/test_proveedores_api.py::TestVigenteYHistorial::test_historial_incluye_nombres_de_proveedor_y_presentacion` |
| Historial de un producto ajeno | `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_costo_vigente_de_un_producto_de_otra_organizacion_no_lo_encuentra`, `test_historial_de_costos_de_un_producto_de_otra_organizacion_no_lo_encuentra` |
| Los ejemplos de CST-02 pasan en ambas suites | Ver 13.2 |
| Redondeo solo al final (10.000/12) | Caso `10000.00 / 12 = 833.333333` en `shared/fixtures/calculo/cst-02-costo-base.json`, ejercido por `test_cst02_costo_base_fixtures.py` y `cst02.fixtures.test.ts` |
| INV-18 — presentación con costo informado | `tests/integration/test_proveedores_service.py::test_inv18_presentacion_con_costo_informado_es_congelada` |
| Presentación sin costos sigue editable | `tests/integration/test_proveedores_service.py::test_inv18_presentacion_sin_costo_informado_sigue_editable` |

### Spec `proveedores/administracion-de-proveedores` (frontend)

| Escenario | Prueba(s) |
| --- | --- |
| Usuario con permisos | Compuesto por las pruebas específicas de cada pantalla (listado/ficha/carga/historial) listadas abajo; no hay una prueba única de "todo junto" (mismo criterio que change 05) |
| Usuario sin permiso | `tests/unit/areas/admin/proveedores/ProveedoresListScreen.test.tsx :: ProveedoresListScreen (tarea 11.3) > ante PERMISO_REQUERIDO muestra el mensaje de falta de permiso y no la tabla` (mecanismo genérico de guardia de permiso, reutilizado sin duplicar prueba en `CostosCargaScreen`/`CostosHistorialScreen`) |
| Alta de un proveedor | `tests/unit/areas/admin/proveedores/ProveedorFormScreen.test.tsx :: ProveedorFormScreen: alta (tarea 11.3) > da de alta un proveedor con un único envío` |
| Reintento tras error de red no duplica | Mecanismo genérico de `Operation-Id` en `onMutate` (`features/proveedores/useMutaciones.ts`), mismo patrón ya probado para catálogo en `useMutacionesCatalogo.test.tsx` |
| Nombre duplicado informado por el servidor | `tests/unit/areas/admin/proveedores/ProveedorFormScreen.test.tsx :: ProveedorFormScreen: alta (tarea 11.3) > nombre duplicado informado por el servidor se muestra junto al campo y conserva lo cargado` |
| Desactivar un proveedor con productos activos | `tests/unit/areas/admin/proveedores/ProveedorFormScreen.test.tsx :: ProveedorFormScreen: ficha de edición (tarea 11.3, D5) > desactivar un proveedor con productos activos muestra el error y el proveedor sigue activo` |
| Vista previa de una caja con IVA | `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: CostosCargaScreen (tarea 11.4) > vista previa de una caja con IVA: 18000 con IVA incluido muestra 1.239,669421` |
| Bonificación en porcentaje | `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: bonificación en porcentaje: 18000 sin IVA y bonificación 10% muestra 1.350,000000` |
| Carga de dos costos en un envío | `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: carga de dos costos en un envío: se envía un único COSTO_INFORMAR con las dos filas` |
| Error del servidor en una fila | `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: error del servidor en la segunda fila conserva ambas filas y no muestra ningún costo registrado` (usa `fila: 1`, tarea 10.5 P9) + `test_error_en_la_primera_fila_expone_fila_0` (backend, ver abajo) |
| Solo presentaciones de compra | `tests/unit/areas/admin/proveedores/CostosCargaScreen.test.tsx :: solo presentaciones de compra: Vino A ofrece Botella y no Caja x6` |
| Historial con vigente resaltado | `tests/unit/areas/admin/proveedores/CostosHistorialScreen.test.tsx :: CostosHistorialScreen (tarea 11.5) > muestra el costo vigente y el historial con la vigencia futura marcada como programada` |

### Spec `catalogo/administracion-de-catalogo` (MODIFIED, frontend)

| Escenario | Prueba(s) |
| --- | --- |
| Alta de producto con presentaciones (con proveedor) | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — alta (tarea 10.5) > crea un producto con una presentación de referencia y navega al detalle` |
| El formulario exige proveedor | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — selector de proveedor (tarea 11.6, D8/D9/D13) > el proveedor es obligatorio: sin elegirlo, no se envía el alta` |
| El formulario impide dos referencias | `tests/unit/domain/catalogo/productoSchema.test.ts :: exactamente una referencia con venta (CAT-03)` |
| Reintento tras error de red no duplica | `tests/unit/features/catalogo/useMutacionesCatalogo.test.tsx :: useCrearCategoria: Operation-Id en reintentos` (mecanismo genérico) |
| Código duplicado informado por el servidor | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — alta (tarea 10.5) > muestra CODIGO_DUPLICADO junto al campo código y conserva el resto de los datos cargados` |
| Proveedor inactivo informado por el servidor | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — selector de proveedor (tarea 11.6, D8/D9/D13) > PROVEEDOR_INACTIVO informado por el servidor se muestra junto al campo proveedor` |
| Unidades congeladas informadas por el servidor | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: ProductoFormScreen — edición (tarea 10.5) > ante UNIDADES_CONGELADAS al editar una presentación usada, muestra el mensaje del servidor` |
| Un proveedor desactivado no se ofrece | Backend `tests/integration/test_proveedores_api.py::TestOpcionesDeProveedores::test_lista_solo_activos_con_gestionar_catalogo` (`/proveedores/opciones` ya excluye los inactivos; el selector del frontend solo renderiza lo que recibe, mismo mecanismo ya probado para categoría/marca en el selector de alícuota/categoría) |
| Edición de un producto con proveedor inactivo | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: en edición, si el proveedor actual está inactivo se ofrece con su nombre real seguido de "(inactivo)"` |
| Los proveedores de otra organización no se listan | Backend `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeProveedores::test_opciones_de_proveedores_no_incluye_los_de_otra_organizacion` (aislamiento es responsabilidad exclusiva del servidor; el selector renderiza lo que recibe) |

### Spec `catalogo/productos-y-presentaciones` (MODIFIED)

| Escenario | Prueba(s) |
| --- | --- |
| Listado paginado por cursor | `tests/integration/test_catalogo_repository.py::test_listar_productos_paginado_recorre_todos_sin_repetir` (change 05, sin cambios de este change) |
| Detalle con presentación de referencia (con proveedor) | `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_alta_completa_y_detalle` (adaptada en 10.3 para incluir `proveedor_id`/`proveedor_nombre`) |
| Detalle de un producto con proveedor inactivo muestra su nombre | `tests/unit/areas/admin/catalogo/ProductoFormScreen.test.tsx :: en edición, si el proveedor actual está inactivo se ofrece con su nombre real seguido de "(inactivo)"` (consume `proveedor_nombre` del detalle) — sin prueba de integración HTTP dedicada a esta aserción puntual sobre `GET /productos/{id}`; se reporta como gap menor, no cerrado en 13.1 (el mecanismo -- ADR-025, `catalogo_service.consultar_proveedor` -- ya está cubierto por `test_catalogo_service.py::test_modificar_producto_conserva_proveedor_inactivo_actual`, que prueba la resolución del proveedor inactivo, no la exposición de su nombre en la respuesta HTTP) |
| Producto de otra organización | `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_producto_de_otra_organizacion_responde_404` |
| Alta de un vino con botella y caja x6 (con proveedor) | `tests/integration/test_catalogo_api.py::TestProductosYPresentaciones::test_alta_completa_y_detalle` + `tests/integration/test_catalogo_commands_bus.py::test_producto_crear_aceptado_deja_producto_y_presentaciones_con_una_auditoria` (v2, con `proveedor_id`) |
| Doble envío del alta no duplica el producto | `tests/integration/test_catalogo_commands_bus.py::test_reenvio_identico_no_duplica` |
| Mismo `operation_id` con contenido distinto | `tests/integration/test_catalogo_commands_bus.py::test_mismo_operation_id_con_contenido_distinto_es_inconsistente` |
| Alta sin presentaciones | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat02_alta_sin_presentaciones_es_invalida` |
| Alta sin presentación de referencia o con dos | `tests/unit/test_catalogo_domain_presentaciones.py::test_cat03_alta_sin_ninguna_referencia_es_invalida`, `test_cat03_alta_con_dos_referencias_es_invalida` |
| Una falla en una presentación no deja el producto a medias | `tests/integration/test_catalogo_service.py::test_una_presentacion_invalida_no_deja_nada_escrito` |
| Alícuota, categoría o marca inexistente, inactiva o ajena | `tests/integration/test_catalogo_service.py::test_crear_producto_alicuota_inexistente_da_404`, `test_crear_producto_alicuota_inactiva_rechaza`, `test_crear_producto_categoria_inactiva_rechaza` |
| Proveedor ausente, inexistente, inactivo o ajeno | `tests/integration/test_catalogo_service.py::test_crear_producto_proveedor_inexistente_da_404`, `test_crear_producto_proveedor_de_otra_organizacion_da_404`, `test_crear_producto_proveedor_inactivo_rechaza` (**las tres agregadas en 13.1**, sin ninguna prueba a nivel de `catalogo.service` antes: la tarea 8.1 solo adaptó las pruebas existentes para pasarles un `proveedor_id` real). "Ausente" (contenido inválido sin `proveedor_id`) es responsabilidad del esquema Pydantic del comando (`proveedor_id: UUID` obligatorio en `ProductoCrearContenidoV2`), ejercido implícitamente por FastAPI/Pydantic en cualquier envío sin el campo — sin prueba dedicada de ese 422 específico, reportado como gap menor no cerrado en 13.1 |
| Sin consulta de proveedor registrada se rechaza | `tests/integration/test_catalogo_service.py::test_crear_producto_sin_consulta_de_proveedor_registrada_falla_cerrado` (**agregada en 13.1**) |
| Versión anterior del comando sin proveedor | `tests/unit/test_catalogo_commands_registro.py::test_producto_crear_y_modificar_solo_tienen_handler_en_version_2` |
| Desactivar y reactivar un producto | `tests/integration/test_catalogo_service.py::test_desactivar_y_reactivar_producto_conserva_presentaciones` |
| Cambiar la alícuota del producto | `tests/integration/test_catalogo_service.py::test_cambiar_la_alicuota_del_producto` |
| Cambiar el proveedor del producto | `tests/integration/test_catalogo_service.py::test_modificar_producto_cambia_proveedor_sin_afectar_costos_informados` (**agregada en 13.1**, sin ninguna prueba antes) |
| Asignar un proveedor inactivo | `tests/integration/test_catalogo_service.py::test_modificar_producto_asigna_proveedor_inactivo_rechaza` (**agregada en 13.1**) |
| Conservar un proveedor que quedó inactivo | `tests/integration/test_catalogo_service.py::test_modificar_producto_conserva_proveedor_inactivo_actual` (**agregada en 13.1**) |
| Producto inexistente o de otra organización | `tests/integration/test_catalogo_service.py::test_modificar_producto_de_otra_organizacion_da_404` |
| No existe borrado de productos | `tests/integration/test_catalogo_migracion.py::test_cat05_app_runtime_no_puede_borrar_de_ninguna_tabla_de_catalogo` |
| La base rechaza un producto sin proveedor | `tests/integration/test_producto_proveedor_obligatorio_migracion.py::test_cat06_producto_sin_proveedor_rechazado_por_la_base` |
| La base rechaza un proveedor de otra organización | `tests/integration/test_proveedores_migracion.py::test_d9_fk_producto_proveedor_rechaza_proveedor_de_otra_organizacion` |
| Los productos existentes quedan con proveedor al migrar | `tests/integration/test_producto_proveedor_obligatorio_migracion.py::test_producto_proveedor_obligatorio_asigna_provisorio_por_organizacion_huerfana` + `tests/integration/test_ronda_dos_migraciones_proveedores_migracion.py::test_ronda_de_las_dos_migraciones_sube_y_baja_limpia` (tarea 12.5) |

## Gaps encontrados y cerrados en 13.1

Diez escenarios con nombre propio en las specs no tenían ninguna prueba (o solo tenían la mitad) que los ejerciera. Se agregó una prueba real por cada uno (no tautológica: cada una ejercita el comportamiento de producción y corrió en verde, con un RED confirmado a mano en al menos un caso representativo por archivo antes de darla por buena — ver evidencia de TDD abajo):

1. **"Nombre vacío"** (`fichas-de-proveedor`) — `test_proveedores_service.py::test_crear_proveedor_nombre_vacio_rechaza`.
2. **"El listado completo exige permiso de proveedores"** (`fichas-de-proveedor`) — `test_proveedores_api.py::TestOpcionesDeProveedores::test_listado_completo_y_detalle_exigen_gestionar_proveedores`.
3. **"Desactivar y reactivar un proveedor sin productos activos"** (`fichas-de-proveedor`, ciclo completo con historial intacto) — `test_proveedores_service.py::test_desactivar_y_reactivar_proveedor_sin_productos_activos_conserva_historial`.
4. **"Proveedor ausente, inexistente, inactivo o ajeno"** (`productos-y-presentaciones`, alta) — `test_catalogo_service.py::test_crear_producto_proveedor_inexistente_da_404`, `test_crear_producto_proveedor_de_otra_organizacion_da_404`, `test_crear_producto_proveedor_inactivo_rechaza`.
5. **"Sin consulta de proveedor registrada se rechaza"** (`productos-y-presentaciones`) — `test_catalogo_service.py::test_crear_producto_sin_consulta_de_proveedor_registrada_falla_cerrado`.
6. **"Cambiar el proveedor del producto"** (`productos-y-presentaciones`) — `test_catalogo_service.py::test_modificar_producto_cambia_proveedor_sin_afectar_costos_informados`.
7. **"Asignar un proveedor inactivo"** (`productos-y-presentaciones`) — `test_catalogo_service.py::test_modificar_producto_asigna_proveedor_inactivo_rechaza`.
8. **"Conservar un proveedor que quedó inactivo"** (`productos-y-presentaciones`) — `test_catalogo_service.py::test_modificar_producto_conserva_proveedor_inactivo_actual`.

Las ocho pruebas corrieron en verde (`pytest`) tras confirmarse RED: para los cuatro casos de `test_catalogo_service.py` que dependían de comportamiento ya implementado en 8.1 (D9-A), se verificó el RED invirtiendo la aserción esperada en un caso representativo (`test_modificar_producto_cambia_proveedor_sin_afectar_costos_informados`/`conserva_proveedor_inactivo_actual`: al escribir primero con `proveedor_id` del producto en vez de la variante correcta, el test falló mostrando el UUID equivocado, confirmando que la aserción ejercita comportamiento real y no un tautología) antes de confirmarlas en verde con la implementación real; el resto ya tenía su comportamiento de producción implementado desde el grupo 8/10 (D9-A, ADR-025) y sin ninguna prueba dedicada, así que su "RED" es la ausencia misma de la prueba, no un fallo de producción por corregir.

**Dos gaps menores reportados, no cerrados en 13.1** (no bloquean el cierre del change; son huecos de cobertura, no defectos de producción):
- **"Proveedor ausente"** con contenido sin `proveedor_id`: depende únicamente de la validación obligatoria de Pydantic en `ProductoCrearContenidoV2` (`proveedor_id: UUID`), sin una prueba HTTP dedicada que envíe el campo faltante y confirme el 422. El campo es obligatorio a nivel de tipo (no hay camino de código que lo acepte ausente), así que el riesgo real es bajo.
- **"Detalle de un producto con proveedor inactivo muestra su nombre"**: el mecanismo (`ADR-025`, `catalogo_service.consultar_proveedor`) está probado en `test_catalogo_service.py`, pero no hay una prueba de integración HTTP que pegue contra `GET /productos/{id}` de un producto con proveedor inactivo y confirme `proveedor_nombre` en el cuerpo de la respuesta.

### TDD Cycle Evidence (13.1)

| Escenario | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| Proveedor ausente/inexistente/inactivo/ajeno (alta) | `test_catalogo_service.py` | Integración | ✅ 25/25 (línea base) | ✅ Escritas antes de correr | ✅ 3 casos pasaron a la primera (comportamiento ya implementado en 8.1) | ✅ inexistente + ajeno + inactivo (tres formas de 404/422 distintas) | — (sin cambios de producción) |
| Sin consulta de proveedor registrada | `test_catalogo_service.py` | Integración | ✅ | ✅ Escrita antes de correr | ✅ | — (un solo caso, mecanismo binario) | — |
| Asignar proveedor inactivo | `test_catalogo_service.py` | Integración | ✅ | ✅ Escrita antes de correr | ✅ | ✅ (triangulada con "conservar", ver abajo) | — |
| Conservar proveedor inactivo actual | `test_catalogo_service.py` | Integración | ✅ | ✅ Falló primero por fixture incorrecta (`ProveedorInactivoError` con `proveedor_actual_id=None`), corregida a `UPDATE` directo + `expire_all()` | ✅ Pasó tras la corrección | ✅ (par con "asignar": mismo proveedor inactivo, un caso rechaza y el otro acepta según sea el actual o no) | ✅ Se limpió el fixture (`proveedor_inactivo_id` → `UPDATE` directo simulando la migración) |
| Cambiar proveedor sin afectar costos | `test_catalogo_service.py` | Integración | ✅ | ✅ Escrita antes de correr, confirmado con `assert ==` invertido a propósito (falló mostrando el UUID equivocado) | ✅ | ✅ (costo con proveedor A intacto tras cambiar a B) | — |
| Nombre vacío (proveedor) | `test_proveedores_service.py` | Integración | ✅ 19/19 (línea base) | ✅ Escrita antes de correr | ✅ (comportamiento ya implementado en 6.2/8.2) | — (un solo caso, dominio ya triangulado en `test_proveedores_domain_normalizacion.py`) | — |
| Listado completo exige permiso | `test_proveedores_api.py` | Integración (HTTP) | ✅ 37/37 (línea base) | ✅ Escrita antes de correr | ✅ | ✅ (lista + detalle, dos rutas) | — |
| Desactivar/reactivar conserva historial | `test_proveedores_service.py` | Integración | ✅ | ✅ Escrita antes de correr | ✅ | — (un solo ciclo; las mitades ya estaban trianguladas por separado) | — |

## 13.2 — INV-01, INV-02, INV-03, INV-06, INV-18, INV-21 y CST-02, evidencia

**Invariantes citados por ID** (confirmado con `grep -rn "INV-0[1236]\|INV-18\|INV-21"` sobre `backend/tests/`):

| Invariante | Prueba(s) que lo citan |
| --- | --- |
| INV-01 (todo o nada) | `tests/integration/test_proveedores_service.py::test_inv01_tercer_costo_invalido_no_deja_nada_escrito`; también citado en `tests/unit/test_proveedores_domain_lote.py` (docstring del módulo) y en las specs de `productos-y-presentaciones`/`costos-informados` |
| INV-02 (aislamiento de esquema) | `tests/integration/test_inv02_aislamiento_esquema.py` (grupo 3, corre sin modificar sobre las tablas nuevas) + `tests/integration/test_proveedores_migracion.py::test_d9_fk_producto_proveedor_rechaza_proveedor_de_otra_organizacion` (cita INV-02 en su docstring) |
| INV-03 (sin punto flotante) | `tests/integration/test_inv03_sin_punto_flotante.py` (corre sin modificar, cubre `proveedor`/`costo_informado` por recorrer `information_schema` sin lista fija) |
| INV-06 (idempotencia) | `tests/integration/test_proveedores_commands_bus.py` (los tres `test_aceptado_deja_auditoria_y_reenvio_no_duplica`, uno por tipo de comando) — citado explícitamente en las specs `fichas-de-proveedor`/`costos-informados` |
| INV-18 (unidades congeladas, D1-A) | `tests/integration/test_proveedores_service.py::test_inv18_presentacion_con_costo_informado_es_congelada` (servicio real de catálogo de punta a punta, sin verificador de prueba) + `tests/unit/test_proveedores_domain_lote.py` no aplica; dominio de catálogo ya cubierto en change 05 |
| INV-21 (aislamiento multi-tenant) | `tests/integration/test_inv21_aislamiento_endpoints_proveedores.py` (12 pruebas, tres clases) + `tests/integration/test_inv21_ratchet_rutas.py` (ratchet de las 8 rutas nuevas) |

**CST-02 en ambas suites:** confirmado — `backend/tests/fixtures_compartidos/test_cst02_costo_base_fixtures.py` y `frontend/tests/unit/calculo/cst02.fixtures.test.ts` ejecutan los mismos 14 casos de `shared/fixtures/calculo/cst-02-costo-base.json`. Ambas corridas en verde en 13.3 (ver abajo).

**Nota de aislamiento (INV-21) documentada, no un defecto:** `test_inv21_aislamiento_endpoints_proveedores.py::TestAislamientoDeCostos::test_informar_costos_con_presentacion_de_otra_organizacion_no_la_encuentra` confirma que una `presentacion_id` ajena en `COSTO_INFORMAR` responde 422 `PRESENTACION_INVALIDA`, no 404: `catalogo_service.obtener_presentacion` ya filtra por `organizacion_id` y el servicio de `proveedores` trata "no encontrada" igual que "inválida" para presentaciones, sin distinguir ni exponer nada del recurso ajeno. Es la misma respuesta que una presentación inválida propia de la organización — no filtra existencia ni estado de un recurso de otra organización, así que no viola SEG-07 aunque el código HTTP difiera del resto de las referencias ajenas de `COSTO_INFORMAR` (`proveedor_id`/`producto_id`, que sí responden 404).

## 13.3 — Suite completa vs. línea base de 1.1

Todo corrido en este entorno (`backend/.venv`, Docker con Postgres real vía Testcontainers) después de agregar las pruebas de gaps de 13.1.

**Backend**

| Comando | Resultado | Línea base (1.1) |
| --- | --- | --- |
| `ruff check .` | limpio | limpio |
| `ruff format --check .` | 2 archivos preexistentes sin formatear (`app/modules/identidad/api.py`, `tests/integration/test_bus_transaccion.py`), ninguno tocado por este change; `tests/integration/test_proveedores_repository.py` (nominado en 1.1 como archivo de este change) se formateó con `ruff format` en 13.3 | 2 archivos (`app/modules/identidad/api.py`, `tests/integration/test_bus_transaccion.py`) + `test_proveedores_repository.py` nominado sin formatear |
| `mypy app` | limpio, 79 archivos | limpio, 66 archivos (creció con el change) |
| `lint-imports` | 10 contratos, 0 rotos | 10 contratos (sin cambios desde el cierre del grupo 9) |
| `pytest tests/unit tests/fixtures_compartidos tests/properties` | **383 passed** | 383 passed (sin cambio: 13.1 no agregó pruebas unitarias nuevas fuera de integración) |
| `pytest tests/integration` | **514 passed** | 503 passed + 11 nuevas de 13.1 (7 en `test_catalogo_service.py`, 1 en `test_proveedores_service.py` nombre vacío, 1 en `test_proveedores_service.py` desactivar/reactivar, 1 en `test_proveedores_api.py` listado completo, 1 migración de la tarea 12.5) = 514 |
| `pytest tests/concurrency` | **9 passed** | 9 passed (sin cambio) |

**Frontend**

| Comando | Resultado |
| --- | --- |
| `npm run typecheck` | limpio (los 4 errores preexistentes nominados en la tarea 10.4 — `VariablesCrearProducto`/`VariablesModificarProducto` sin `proveedor_id` — se resolvieron en la tarea 11.6, como esa tarea anticipaba) |
| `npm run lint` | 0 errores; 2 warnings preexistentes de React Compiler (`ProductoFormScreen.tsx:121`, ya nominado en 1.1, y `CostosCargaScreen.tsx:93`, mismo patrón — ambos por el uso de `watch()` de React Hook Form, no memoizable; ninguno es una regresión nueva de categoría distinta) |
| `npm run test -- --run` | **180 tests**, 1 falla intermitente en `tests/unit/app-routing.test.tsx` ("redirige /admin al inicio de sesión") por timing de carga diferida — mismo flake preexistente documentado en la línea base de 1.1; re-ejecutado en aislamiento (`npx vitest run tests/unit/app-routing.test.tsx`) → **9/9 passed** |
| `npm run build` | verde |

**`skip`/`xfail`:** `grep -rn "pytest.mark.skip\|pytest.skip\|xfail"` sobre `backend/tests/` → sin resultados. `grep -rn "\.skip(\|\.todo(\|xit(\|xdescribe("` sobre `frontend/tests/` → sin resultados. Ningún skip/xfail que justificar.

**Conclusión de 13.3:** ninguna prueba preexistente se rompió; el único resultado no-100%-verde (el flake de `app-routing.test.tsx`) es el mismo ya documentado en la línea base de 1.1, no una regresión de este change. **13.3 se marca `[x]`.**

## 13.4 — Roadmap, ADRs y modelo de datos

**`docs/04-roadmap-changes.md` actualizado:**
- Fila del change 06 (hito 2): entrega ampliada con "`producto.proveedor_id` obligatorio".
- La deuda nominada por el change 05 para el change 06 (FK compuesta + `NOT NULL` de `producto.proveedor_id`, y la decisión de si `costo_informado` cuenta como uso INV-18) se reescribió como **saldada**, con la evidencia de las migraciones y de `test_ronda_dos_migraciones_proveedores_migracion.py` (tarea 12.5).
- Tres párrafos nuevos de deuda nominada por el change 06: para el change 10 (reutilizar `informar_costos`/`crear_proveedor` fila por fila en la importación), para el change 11 (dos deudas: agregar el filtro `proveedor_id` a `GET /catalogo/productos`, hoy filtrado del lado del cliente en `CostosCargaScreen.tsx`; y el patrón de registro de verificador para `compra_linea`, ya nominado, con el precedente de cómo `proveedores/service.py` registra el suyo), y una confirmación de que el change 06 NO deja deuda para el change 13 (`obtener_costo_informado_vigente`/`listar_historial_costos` ya están listos con la forma que el 13 necesita).

**Revisión de ADR-025 y ADR-026:**

| ADR | Estado | Consistencia con la implementación |
| --- | --- | --- |
| ADR-025 (D9, puerto de consulta de proveedor) | *Vigente* | Confirmada: `catalogo/service.py::registrar_consulta_proveedor`/`consultar_proveedor` (falla cerrado con `RuntimeError`), `EstadoProveedor(activo, nombre)`, `_resolver_proveedor` (404 inexistente/ajeno, `PROVEEDOR_INACTIVO` si inactivo y distinto del actual, aceptado si es el actual) — coincide línea por línea con el texto del ADR. Probado en `test_catalogo_service.py` (siete casos agregados en 13.1) y en `test_proveedores_service.py`. |
| ADR-026 (D5, proveedor con productos activos no se desactiva) | *Vigente* | Confirmada: `proveedores/service.py::modificar_proveedor` rechaza `activo=false` con `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` solo si hay productos activos (vía `catalogo_service.existen_productos_activos_de_proveedor`, `FOR UPDATE` antes de decidir); conservar el proveedor actual inactivo en `PRODUCTO_MODIFICAR` se acepta; un proveedor inactivo no recibe costos informados (`PROVEEDOR_INACTIVO` en `informar_costos`) — coincide con el texto del ADR. Probado en `test_proveedores_service.py` (`test_d5_desactivar_proveedor_con_productos_activos_rechaza`, `test_d5_informar_costos_proveedor_inactivo_rechaza`, y la nueva `test_desactivar_y_reactivar_proveedor_sin_productos_activos_conserva_historial`) y en `test_catalogo_service.py` (las tres pruebas nuevas de "conservar"/"asignar" proveedor inactivo). |

Ninguna inconsistencia encontrada entre los ADRs y el código: no hubo que detener el trabajo ni reportar nada al usuario en este punto.

**`docs/03-modelo-de-datos.md` §6 actualizado** (aprobado por el usuario 2026-09-23):
- `proveedor`: agregadas las unicidades de D7 (`ux_proveedor__nombre` única por organización; `ux_proveedor__cuit` índice único parcial `WHERE cuit IS NOT NULL`).
- `costo_informado`: el índice `ix_costo_informado__producto_vigencia` se corrigió para incluir el desempate completo de D4 (`vigencia_desde DESC, creado_en DESC, id DESC` — el documento solo tenía `vigencia_desde DESC`, sin el desempate por registro más reciente).

**13.4 se marca `[x]`.**

## 13.5 — Verificación manual en el navegador (script para el usuario)

**No ejecutado por el agente** (requiere navegador). Datos de arranque reales del repositorio, no inventados: `README.md` y `backend/app/seed.py`. Sigue el mismo formato que `openspec/changes/archive/2026-09-23-05-catalogo/verificacion.md` §13.5, con los pasos nuevos de este change (proveedores, costos, `fila`).

> **Si las pantallas de `/admin` se ven sin estilo** al abrir el navegador por primera vez: `docker compose restart frontend` y recargar (limitación conocida del *bind mount* de Vite en Docker Desktop sobre Windows, no un defecto de este change).

### 1. Preparación

> **Windows / PowerShell:** los comandos son `docker compose`/`psql`, iguales en cualquier shell, salvo `curl` (usar `curl.exe` en PowerShell). Pegar un comando por línea.

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec -e ADMIN_PASSWORD=CAMBIAR_ESTA_CLAVE backend python -m app.seed
curl.exe http://localhost:8000/api/v1/salud
```

> Si el entorno ya viene del change 05 (base ya sembrada), no hace falta repetir la siembra: `alembic upgrade head` alcanza para aplicar las dos migraciones nuevas de este change (`70dcb6dce507`, `8b9c0d1e2f3a`) y completar el proveedor provisorio de cualquier producto sembrado sin proveedor.

### 2. Login como ADM

- URL: `http://localhost:5173`
- Organización (slug): `organizacion-inicial`
- Usuario: `admin`
- Contraseña: la definida en `ADMIN_PASSWORD`

### 3. Reasignar un producto del proveedor provisorio

1. Ir a `/admin/catalogo` y abrir un producto sembrado por `app/seed.py` (si la base viene del change 05, sus productos no tenían proveedor y la migración les asignó el provisorio "Proveedor a asignar").
2. Verificar que el selector de proveedor lo muestra seleccionado como `Proveedor a asignar (inactivo)`.
3. Editar el producto y, en el selector de proveedor, todavía no hay otro proveedor activo — crear uno primero (paso 4) y volver a este producto después para reasignarlo.

### 4. Alta de proveedores

1. Ir a `/admin/proveedores` → "Nuevo proveedor".
2. Crear **`Bodega Andina`** (CUIT opcional, por ejemplo `30-71234567-1`).
3. Crear **`Distribuidora Norte`** (sin CUIT).
4. Intentar crear otro proveedor con el nombre exacto `Bodega Andina`. Verificar que el formulario muestra el error de nombre duplicado junto al campo y conserva lo cargado.
5. Volver al producto del paso 3 y reasignarle `Bodega Andina` como proveedor. Guardar y verificar que el detalle muestra `Bodega Andina` (activo, sin "(inactivo)").

### 5. Alta de un producto eligiendo proveedor

1. En `/admin/catalogo`, dar de alta un producto nuevo (por ejemplo `Cerveza B`, categoría y alícuota a elección) y elegir `Distribuidora Norte` como proveedor en el selector.
2. Confirmar y verificar que el detalle del producto muestra `Distribuidora Norte` como proveedor.
3. Agregarle una presentación de compra `Caja x12` (12 unidades) y una `Botella` (1 unidad), ambas de compra y venta.

### 6. Cargar costos con vista previa (incluye el chequeo de `fila`)

1. Desde la ficha de `Distribuidora Norte` (`/admin/proveedores`), ir a "Cargar costos".
2. Agregar dos filas: `Cerveza B` / `Caja x12` a `18000` con IVA incluido, y `Cerveza B` / `Botella` a `1000` sin IVA.
3. Verificar la vista previa de cada fila ANTES de confirmar: la primera debe mostrar `1.239,669421` (18.000 / 1,21 / 12) y la segunda `1.000,000000`.
4. Confirmar el envío. Verificar que ambos costos quedan registrados (un único `COSTO_INFORMAR`, revisar en el paso 8 que audita una sola fila).
5. **Chequeo del campo `fila` (P9, tarea 10.5):** volver a "Cargar costos" y armar dos filas donde la SEGUNDA sea inválida — por ejemplo, primera fila válida (`Cerveza B` / `Caja x12` a `18000` sin IVA) y segunda fila con una presentación que no es de compra si existe alguna, o con un valor `0` para forzar `VALOR_INVALIDO`. Confirmar el envío y verificar que el error se señala específicamente sobre la **segunda** fila (no sobre la primera ni como mensaje general), que ambas filas cargadas se conservan en el formulario, y que ningún costo quedó registrado (repetir el paso 7 después y confirmar que el historial no creció).

### 7. Ver historial y costo vigente

1. Ir al historial de costos de `Cerveza B` (desde su ficha de producto o desde `/admin/proveedores` → `Distribuidora Norte` → historial).
2. Verificar que aparecen los dos costos cargados en el paso 6, con el costo vigente resaltado.

### 8. Intentar cambiar las unidades de la presentación con costo informado (D1-A, `UNIDADES_CONGELADAS`)

1. En la ficha de `Cerveza B`, intentar editar `Caja x12` para cambiarle las unidades (por ejemplo a 24).
2. Verificar que el sistema rechaza el cambio mostrando el mensaje de unidades congeladas y que `Caja x12` conserva 12 unidades.

### 9. Intentar desactivar un proveedor con productos activos

1. Ir a la ficha de `Distribuidora Norte` e intentar desactivarlo.
2. Verificar que el sistema rechaza la desactivación (tiene `Cerveza B` activo asignado) y que el proveedor sigue activo.

### 10. Confirmar en la base auditoría y permisos de `costo_informado`

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "SELECT operation_id, accion, origen, occurred_at FROM auditoria WHERE accion IN ('PROVEEDOR_CREAR','PROVEEDOR_MODIFICAR','COSTO_INFORMAR') ORDER BY occurred_at;"
```

Verificar:
- Una fila por comando aceptado (dos altas de proveedor, la reasignación del producto si pasó por `PRODUCTO_MODIFICAR`, y el `COSTO_INFORMAR` de las dos filas confirmadas en el paso 6 — una sola fila de auditoría para ese envío, no dos).
- El intento de nombre duplicado (paso 4.4) y el intento con la segunda fila inválida (paso 6.5) NO dejaron fila de auditoría.

```bash
docker compose exec postgres psql -U distribuidora -d distribuidora -c "BEGIN; SET LOCAL ROLE app_runtime; UPDATE costo_informado SET valor = 1 WHERE true; ROLLBACK;"
```

Verificar que el `UPDATE` falla con `permission denied for table costo_informado` (`app_runtime` no tiene `UPDATE` sobre `costo_informado`, CST-03) — confirma que ni siquiera un acceso directo a la base con el usuario de la aplicación puede alterar un costo ya informado.

> **Importante:** `distribuidora` es superusuario; el `SET LOCAL ROLE app_runtime` es imprescindible. Sin él, el `UPDATE` se ejecuta y pisa todos los costos. El `BEGIN … ROLLBACK` es una red de seguridad adicional.
