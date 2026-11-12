# Verificación — 11-compras-y-deuda-proveedor

Fecha de la verificación automática: 2026-10-02. La verificación manual en el navegador (tarea 16.2) la ejecuta el usuario y **no está marcada**.

## 1. Definición de terminado (`docs/04` §2.1)

| # | Criterio | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Las pruebas que exige `02` §15 pasan | Cumplido (local; CI no se ejecutó desde esta sesión) | Ver §2. |
| 2 | Cada escenario de las specs tiene una prueba | Cumplido | §3. |
| 3 | Los invariantes tocados tienen prueba que los cita por ID | Cumplido | §4. |
| 4 | La migración sube y baja limpia sobre una base con datos | Cumplido | `tests/integration/test_compras_migracion.py` (ciclo upgrade/downgrade y siembra idempotente de motivos). |
| 5 | Se probó a mano el flujo principal en el navegador | **Pendiente** (tarea 16.2, a cargo del usuario) | Guía en §6. |
| 6 | Las specs delta se archivaron y `04` quedó actualizado | **Pendiente** (al archivar) | Cambios propuestos a `docs/01` a `04` ya aplicados para revisión (ver el resumen del lote 3). |
| 7 | Las decisiones nuevas quedaron como ADR | Cumplido, a la espera de aprobación | ADR-043 y ADR-044, en estado *Propuesto*. |

## 2. Comandos y resultados (2026-10-02)

| Comando | Resultado |
| --- | --- |
| `python -m pytest tests/unit` | 1.456 pasaron |
| `python -m pytest tests/fixtures_compartidos` | 90 pasaron |
| `python -m pytest tests/properties` | 29 pasaron |
| `python -m pytest tests/integration` | 1.688 pasaron |
| `python -m pytest tests/concurrency` | 48 pasaron |
| `python -m ruff check .` / `ruff format --check .` | sin hallazgos / 382 archivos formateados |
| `python -m mypy app` | sin errores (158 archivos) |
| `lint-imports` | 22 contratos cumplidos, 0 rotos |
| `npm run test` | 729 pruebas pasaron |
| `npm run typecheck` | sin errores |
| `npm run lint` | 0 errores; 2 advertencias preexistentes (`react-hooks/incompatible-library`) |

Sin `skip` ni `xfail` en `backend/tests` (las pruebas de reversión que el lote 1 dejó como `xfail(strict)` ya están activas). Dependencias: ninguna agregada a `requirements*.txt`, `package.json` ni `package-lock.json` durante el change (tarea 16.1); `pyproject.toml` solo cambió la configuración de import-linter, por lo que no hace falta reconstruir las imágenes.

## 3. Cobertura por escenario (tarea 14.2)

Rutas relativas a `backend/tests/` salvo las de frontend (`frontend/tests/unit/`).

### `proveedores/compras`

| Escenario | Prueba principal |
| --- | --- |
| Compra a crédito de vino por caja y cerveza por unidad | `integration/test_compras_confirmar.py::test_compra_a_credito_de_vino_por_caja_y_cerveza_por_unidad`; `test_compras_api.py::test_confirmar_una_compra_a_credito_responde_201_con_importes_como_string` |
| INV-07 — compra sin líneas | `test_compras_confirmar.py::test_inv07_compra_sin_lineas_se_rechaza_sin_efectos`; `test_compras_api.py::test_inv07_una_compra_sin_lineas_responde_422_con_su_codigo` |
| Compras solo con conexión | `test_compras_confirmar.py::test_cmp08_el_lote_rechaza_la_compra_enviada_sin_conexion` |
| Doble envío del mismo comando | `test_compras_confirmar.py::test_inv06_el_doble_envio_devuelve_el_resultado_original_y_no_duplica`; `concurrency/test_compras_concurrencia.py::TestMismoOperationIdSimultaneo` |
| Mismo Operation-Id con contenido distinto | `test_compras_confirmar.py::test_inv06_el_mismo_operation_id_con_otro_contenido_es_inconsistente`; `test_compras_api.py::test_inv06_el_mismo_operation_id_con_otro_contenido_responde_409` |
| Caja x12 sin IVA / con IVA incluido / con bonificación del 10 % | `fixtures_compartidos/test_cmp02_compra_fixtures.py` (casos de `cmp-02-compra.json`); `unit/test_proveedores_domain_compras.py::test_linea_con_iva_incluido_y_bonificacion_usa_la_formula_de_cst02`; `frontend/domain/compras/formularioCompra.test.ts` |
| Cantidad fraccionaria que da unidades enteras | `test_compras_confirmar.py::test_cantidad_fraccionaria_valida_ingresa_unidades_enteras` |
| Cantidad fraccionaria que no da unidades enteras | `test_compras_confirmar.py::test_inv04_cantidad_que_no_da_unidades_enteras_se_rechaza_con_su_linea` |
| Valor cero o negativo | `test_compras_confirmar.py::test_valor_cero_se_rechaza_con_su_linea` |
| Unidades congeladas en la línea | `test_compras_confirmar.py::test_las_lineas_congelan_unidades_alicuota_y_derivados` |
| Presentación solo de venta | `test_compras_confirmar.py::test_presentacion_solo_de_venta_se_rechaza` |
| Producto de otro proveedor | `test_compras_confirmar.py::test_producto_de_otro_proveedor_se_rechaza`; `test_compras_api.py::test_la_compra_de_otro_proveedor_de_la_organizacion_responde_422_con_su_linea` |
| Proveedor inactivo | `test_compras_confirmar.py::test_proveedor_inactivo_se_rechaza` |
| Fecha futura | `test_compras_confirmar.py::test_fecha_posterior_a_hoy_se_rechaza` |
| Proveedor de otra organización | `test_compras_api.py::test_inv21_un_proveedor_de_otra_organizacion_responde_404_sin_efectos`; `test_compras_confirmar.py::test_inv21_una_referencia_de_otra_organizacion_responde_404` |
| Promedio con stock previo | `test_compras_confirmar.py::test_promedio_con_stock_previo_se_recalcula_con_cst11` |
| Dos líneas del mismo producto | `test_compras_confirmar.py::test_dos_lineas_del_mismo_producto_se_aplican_en_orden` |
| INV-01 — falla después del stock | `test_compras_confirmar.py::test_inv01_una_falla_despues_de_ingresar_el_stock_y_antes_de_la_cuenta_no_deja_nada`; `test_compras_contado.py::test_una_falla_despues_del_stock_no_deja_pago_ni_compra_inv_01` |
| Contado con efectivo y transferencia | `test_compras_contado.py::test_contado_con_efectivo_y_transferencia_registra_compra_y_pago_cc_05` |
| INV-08 — medios que no suman el importe | `test_compras_contado.py::test_medios_que_no_suman_el_total_se_rechazan_sin_efectos_inv_08` (y `..._suman_de_mas_...`) |
| Medio que exige referencia sin referencia | `test_compras_contado.py::test_un_medio_que_exige_referencia_sin_ella_se_rechaza_sin_efectos` |
| Crédito con medios | `test_compras_contado.py::test_credito_con_medios_se_rechaza_sin_efectos`; `test_compras_confirmar.py::test_credito_con_medios_de_pago_se_rechaza` |
| Total de factura distinto del sugerido | `test_compras_confirmar.py::test_el_total_de_factura_informado_es_la_deuda_y_no_cambia_los_promedios`; `test_compras_contado.py::test_el_pago_usa_el_total_de_factura_informado_y_no_el_sugerido` |
| Total de factura con tres decimales | `test_compras_confirmar.py::test_total_de_factura_con_tres_decimales_se_rechaza` |
| Costo distinto del vigente / igual al vigente | `test_compras_confirmar.py::test_el_resultado_informa_costos_distintos_del_vigente_sin_crear_costos`; `test_un_costo_igual_al_vigente_no_aparece_en_las_diferencias` |
| Filtro por proveedor (listado) | `test_compras_api.py::test_listar_compras_filtra_por_proveedor_y_cada_una_aparece_una_vez` |
| Compra de otra organización (lectura) | `test_compras_api.py::test_inv21_el_listado_no_devuelve_compras_de_otra_organizacion`, `test_inv21_el_detalle_de_una_compra_de_otra_organizacion_responde_404` |
| Sin permiso (lectura) | `test_compras_api.py::test_leer_compras_exige_registrar_o_anular_compra` |
| Sin permiso de compra (confirmar) | `test_compras_api.py::test_sin_registrar_compra_responde_403_sin_efectos_ni_reserva`; `test_compras_confirmar.py::test_sin_registrar_compra_se_rechaza_con_403_y_sin_reserva` |
| Auditoría de la compra | `test_compras_confirmar.py::test_adr022_la_compra_deja_una_sola_auditoria_con_su_operation_id` |

### `proveedores/anulacion-de-compras`

| Escenario | Prueba principal |
| --- | --- |
| Anulación de una compra a crédito | `test_compras_anular.py::test_anular_una_compra_a_credito_revierte_stock_y_cuenta`; `test_compras_api.py::test_anular_una_compra_a_credito_responde_200_con_su_resultado` |
| Compra ya anulada | `test_compras_anular.py::test_anular_dos_veces_con_otro_operation_id_es_compra_ya_anulada`; `test_compras_api.py::test_anular_dos_veces_responde_409_compra_ya_anulada` |
| Doble envío de la anulación | `test_compras_anular.py::test_el_reenvio_con_el_mismo_operation_id_devuelve_el_resultado_original_inv_06`; `test_compras_api.py::test_inv06_el_reenvio_de_la_anulacion_devuelve_lo_mismo_y_no_duplica` |
| Motivo de otro ámbito | `test_compras_anular.py::test_motivo_de_otro_ambito_es_motivo_invalido`; `test_compras_api.py::test_la_anulacion_con_motivo_de_otro_ambito_responde_422` |
| Sin permiso de anulación | `test_compras_anular.py::test_sin_permiso_de_anulacion_responde_403_y_la_compra_sigue_confirmada` |
| Compra de otra organización | `test_compras_anular.py::test_anular_una_compra_de_otra_organizacion_responde_404_inv_21`; `test_compras_api.py::test_inv21_anular_la_compra_de_otra_organizacion_responde_404` |
| Dos anulaciones simultáneas | `concurrency/test_compras_concurrencia.py::TestDosAnulacionesSimultaneas` |
| Se recalcula / stock restante cero / promedio resultante no positivo | `test_compras_anular.py::test_se_recalcula_el_promedio_al_anular_la_segunda_compra`, `test_con_stock_restante_cero_mantiene_el_promedio_y_observa`, `test_con_promedio_resultante_no_positivo_mantiene_el_promedio_y_observa` |
| Sin permiso y sin stock suficiente | `test_compras_anular.py::test_sin_permiso_de_negativo_y_sin_stock_suficiente_se_rechaza` |
| Con permiso (stock negativo) | `test_compras_anular.py::test_con_permiso_de_negativo_deja_menos_doce_y_observa` |
| Se devuelve el pago / no se devuelve | `test_compras_anular.py::test_contado_devolviendo_el_pago_anula_el_pago_y_deja_el_saldo_en_cero`, `test_contado_sin_devolver_el_pago_deja_saldo_a_favor`; `test_compras_api.py::test_anular_una_compra_de_contado_devolviendo_el_pago` |
| Producto desactivado después de la compra | `test_compras_anular.py::test_se_puede_anular_con_el_producto_y_el_proveedor_desactivados_d11` |
| INV-01 — falla en la cuenta | `test_compras_anular.py::test_una_falla_despues_del_egreso_y_antes_de_la_cuenta_no_deja_efectos_inv_01` |
| Propiedad — confirmar y anular deja todo como estaba | `properties/test_compras_inv12_inv13.py::test_confirmar_y_anular_sin_movimientos_intermedios_devuelve_stock_y_saldo_exactos`; `test_compras_anular.py::test_confirmar_y_anular_deja_el_saldo_y_el_stock_como_estaban_inv_12_inv_13` |

### `proveedores/administracion-de-compras`

| Escenario | Prueba principal |
| --- | --- |
| Usuario con solo anulación | `frontend/areas/admin/compras/ComprasListScreen.test.tsx` ("un usuario con solo ANULAR_COMPRA ve el listado pero no Nueva compra"); `rutas.test.tsx` |
| Usuario sin permisos de compra | `ComprasListScreen.test.tsx`, `CompraFormScreen.test.tsx`, `CompraDetalleScreen.test.tsx`, `rutas.test.tsx` (aviso sin pedir datos) |
| Vista previa de una línea con IVA | `CompraFormScreen.test.tsx` ("vista previa de Caja x12 con IVA: costo base 1.239,669421 e importe neto 14.876,03") |
| Medios que no suman el total | `CompraFormScreen.test.tsx` ("de contado con medios que no suman el total: confirmar queda deshabilitado") |
| Error del servidor por línea | `CompraFormScreen.test.tsx` ("un error del servidor en la línea 2 se muestra junto a esa línea") |
| El usuario acepta registrar el costo / no hace nada | `CompraResultado.test.tsx` (envía `COSTO_INFORMAR` con la vigencia de la compra; sin acción no se envía nada) |
| Anulación con observación | `CompraDetalleScreen.test.tsx` ("una observación del servidor se muestra como aviso") |
| Cantidades en cajas y unidades | `CompraDetalleScreen.test.tsx` ("5 cajas + 1 un.") |

### `catalogo/productos-y-presentaciones` (delta)

| Escenario | Prueba principal |
| --- | --- |
| Listado paginado por cursor / Filtro por proveedor | `test_compras_api.py::test_listar_productos_filtra_por_proveedor_y_activo_con_paginacion`, `test_listar_productos_sin_filtro_devuelve_los_de_todos_los_proveedores` |
| Filtro por proveedor de otra organización | `test_compras_api.py::test_inv21_filtrar_por_el_proveedor_de_otra_organizacion_devuelve_lista_vacia` |
| Detalle con presentación de referencia | `test_catalogo_api.py::TestProductosYPresentaciones::test_alta_completa_y_detalle` |
| Detalle con proveedor inactivo muestra su nombre | `test_compras_api.py::test_el_detalle_de_un_producto_con_proveedor_inactivo_muestra_su_nombre` (agregada en el lote 3: no existía una prueba específica) |
| Producto de otra organización | `test_catalogo_api.py::TestProductosYPresentaciones::test_producto_de_otra_organizacion_responde_404` |
| INV-18 — presentación usada en una compra / la anulación no libera las unidades | `test_compras_confirmar.py::test_inv18_presentacion_usada_en_compra_es_congelada`, `test_inv18_la_compra_anulada_tampoco_libera_las_unidades` |

### `costeo/costo-promedio` (delta)

| Escenario | Prueba principal |
| --- | --- |
| Reversión que recalcula | `unit/test_costeo_domain_reversion.py::test_con_stock_restante_positivo_recalcula_el_promedio`; `fixtures_compartidos/test_cst11_reversion_fixtures.py`; `integration/test_costeo_service.py::test_revertir_recalcula_el_promedio_y_deja_la_fila_de_historia` |
| Stock restante no positivo / Promedio resultante no positivo | `test_costeo_domain_reversion.py::test_con_stock_restante_cero_mantiene_el_promedio`, `..._promedio_resultante_cero_...`, `..._negativo_...` |
| Historia sin recálculo | `test_costeo_service.py::test_revertir_sin_recalculo_mantiene_el_promedio_y_escribe_igual_la_historia`; `integration/test_stock_movimientos.py::test_el_egreso_anulacion_compra_sin_recalculo_deja_la_fila_de_historia` |
| El promedio se reconstruye con la historia | `test_costeo_service.py::test_la_historia_se_reconstruye_con_ingresos_y_reversiones`; `unit/test_costeo_domain_reversion.py::test_ingreso_seguido_de_reversion_devuelve_el_promedio_previo_cmp_06` (Hypothesis) |

### `organizacion/catalogos-configurables` (delta)

| Escenario | Prueba principal |
| --- | --- |
| Motivos de anulación de compra / Medios de pago de la organización / Ámbito inválido | `test_compras_api.py::test_motivos_devuelve_solo_los_activos_del_ambito_pedido_de_la_organizacion`, `test_medios_de_pago_devuelve_solo_los_activos_de_la_organizacion`, `test_motivos_con_un_ambito_fuera_de_la_lista_responde_422_ambito_invalido` |
| Organización nueva | `integration/test_seed.py::test_una_organizacion_nueva_tiene_los_tres_motivos_de_anulacion_de_compra`, `test_sembrar_dos_veces_no_duplica_los_motivos_de_anulacion_de_compra` |
| Organización existente | `integration/test_compras_migracion.py::test_la_migracion_siembra_los_motivos_una_sola_vez_en_organizaciones_existentes` |

### `stock/libro-de-stock` (delta)

| Escenario | Prueba principal |
| --- | --- |
| Egreso mayor que el saldo | `integration/test_stock_service.py::test_una_correccion_que_dejaria_negativo_se_rechaza_sin_efectos`; `test_stock_comandos.py::test_una_correccion_que_deja_negativo_el_saldo_se_rechaza` |
| Egreso de anulación de compra con permiso / sin permiso | `test_stock_movimientos.py::test_con_permiso_la_anulacion_deja_saldo_negativo_y_lo_marca`; `test_compras_anular.py::test_sin_permiso_de_negativo_y_sin_stock_suficiente_se_rechaza` |
| Costo del egreso en el kardex | `test_stock_movimientos.py::test_el_egreso_anulacion_compra_revierte_el_promedio_y_queda_con_su_costo` |
| Reversión con producto inactivo / Otro tipo con producto inactivo | `test_stock_movimientos.py::test_la_reversion_admite_un_producto_inactivo`, `test_otros_tipos_siguen_rechazando_un_producto_inactivo` |

## 4. Invariantes citados por ID

| Invariante | Pruebas que lo citan |
| --- | --- |
| INV-01 (atomicidad) | `test_compras_confirmar.py`, `test_compras_contado.py`, `test_compras_anular.py` (pruebas `..._inv_01`) |
| INV-05 (libros de solo inserción) | `test_compras_migracion.py::test_inv05_app_runtime_*`; `test_compras_anular.py::test_la_anulacion_no_borra_nada_y_deja_las_lineas_inv_05` |
| INV-06 (idempotencia) | `test_compras_confirmar.py`, `test_compras_anular.py`, `test_compras_api.py` (`test_inv06_*`), `concurrency/test_compras_concurrencia.py::TestMismoOperationIdSimultaneo` |
| INV-07 (al menos una línea) | `test_compras_confirmar.py::test_inv07_*`, `test_compras_api.py::test_inv07_*`, `unit/test_proveedores_domain_compras.py` |
| INV-08 (medios suman el importe) | `test_compras_contado.py::test_medios_*_inv_08`, `unit/test_proveedores_domain_compras.py` |
| INV-12 (stock = suma del libro) | `properties/test_compras_inv12_inv13.py`, `concurrency/test_compras_concurrencia.py`, `test_compras_confirmar.py::test_inv12_inv13_*`, `test_compras_anular.py::test_confirmar_y_anular_*_inv_12_inv_13` |
| INV-13 (saldo = suma de movimientos) | los mismos archivos que INV-12 |
| INV-18 (unidades congeladas) | `test_compras_confirmar.py::test_inv18_*` |
| INV-21 (aislamiento por organización) | `test_compras_api.py::test_inv21_*`, `test_compras_confirmar.py`, `test_compras_contado.py`, `test_compras_anular.py`, `test_compras_migracion.py::test_inv21_*`; ratchets `test_inv21_ratchet_rutas.py` y `test_ratchet_permiso_por_ruta.py` |

## 5. Hallazgos de concurrencia y propiedades (lote 3)

Las 14 pruebas de `concurrency/test_compras_concurrencia.py` y las 3 de `properties/test_compras_inv12_inv13.py` pasaron en la primera ejecución contra el código de los lotes 1 y 2: verifican el orden global de bloqueo y la atomicidad ya implementados, no los impulsaron. No se encontró ningún error de producción.

## 6. Guía de verificación manual (tarea 16.2, a cargo del usuario)

### Preparación

1. `docker compose up` con la migración al día (`alembic upgrade head`; el seed de desarrollo siembra los motivos de anulación de compra).
2. Entrar a `/admin` con un Administrador. Tener al menos un proveedor con dos productos (por ejemplo `Vino A` con `Caja x6` y `Cerveza B` con `Botella`), un depósito activo y medios de pago `Efectivo` y `Transferencia` (esta con referencia obligatoria).
3. Ver el costo promedio requiere `VER_COSTOS`; registrar un costo informado, `EDITAR_COSTOS`; anular, `ANULAR_COMPRA`.

### Flujos

| # | Flujo | Resultado esperado | Resultado obtenido | OK |
| --- | --- | --- | --- | --- |
| 1 | Compra a crédito (criterio 2): 10 cajas de Vino A x6 a $6.000 sin IVA y 60 botellas de Cerveza B a $1.100 sin IVA, depósito, condición "A crédito" | Vista previa de importes; total de factura sugerido $152.460,00; tras confirmar, stock 60 y 60, promedios $1.000 y $1.100 (ficha del producto, con `VER_COSTOS`) y deuda de $152.460,00 en la cuenta del proveedor | | |
| 2 | Misma compra con total de factura corregido a $153.720,00 | La deuda es $153.720,00 y los promedios no cambian | | |
| 3 | Compra de contado con dos medios: $100.000 en Efectivo y el resto en Transferencia con referencia | El botón de confirmar se habilita solo cuando los medios suman el total; la deuda del proveedor no cambia y el detalle muestra el pago con sus dos medios | | |
| 4 | Oferta de costo informado: comprar Vino A a un costo distinto del vigente | El resultado lista la diferencia y ofrece "Registrar como costo informado" (con `EDITAR_COSTOS`); al aceptar, el costo queda vigente desde la fecha de la compra | | |
| 5 | Anular una compra a crédito cuando el promedio se recalcula (hay otra compra posterior del mismo producto) | Stock y deuda se revierten; el promedio se recalcula; sin aviso | | |
| 6 | Anular una compra a crédito cuando no se puede recalcular (el producto queda sin stock) | La anulación se acepta y se muestra el aviso de que el promedio no se recalculó | | |
| 7 | Anular una compra de contado devolviendo el pago | La pantalla obliga a elegir; el pago queda anulado y el saldo del proveedor vuelve a como estaba | | |
| 8 | Anular una compra de contado sin devolver el pago | El pago se mantiene y la cuenta muestra "Saldo a nuestro favor" | | |
| 9 | Anular una compra cuyo stock ya se vendió o transfirió, con y sin `PERMITIR_STOCK_NEGATIVO` | Sin permiso: rechazo por stock insuficiente; con permiso: stock negativo y aviso | | |
| 10 | Anular una compra ya anulada (dos pestañas) | La segunda muestra "ya anulada" sin duplicar movimientos | | |
| 11 | Carga de costos de un proveedor (`/admin/proveedores/.../costos`) | El selector muestra solo los productos de ese proveedor, sin traer la página completa de productos | | |
| 12 | Usuario con solo `REGISTRAR_COMPRA`: abrir "Nueva compra" | El formulario carga proveedores, ubicaciones, productos y alícuotas sin errores 403 (D17, D18); `/admin/proveedores`, `/admin/stock` y catálogo siguen sin acceso | | |
| 13 | Usuario con solo `ANULAR_COMPRA` | Ve el listado y el detalle, puede anular y no ve "Nueva compra" | | |
| 14 | Listado: filtros por proveedor, estado, fechas y número de comprobante; "Cargar más" | Los filtros acotan y la paginación no repite ni omite compras | | |

### Hallazgos de la verificación manual

Sesión del 2026-10-02 (usuario):

- Flujos 2, 3, 4, 5, 8 y 14 probados por el usuario: OK.
- H1 — Vista previa de cantidad: un producto con referencia `Botella` (1 unidad) muestra "Cantidad base: 24 cajas" para 2 × Caja x12. `formatearCantidad` (`domain/stock/cantidades.ts`, compartido con stock) dice siempre "cajas" en lugar del nombre de la presentación de referencia. Pendiente de corregir. CORREGIDO (2026-10-02): `formatearCantidad` toma la referencia `{ unidades, nombre }` y muestra "61 unidades (10 Caja x6 + 1 un.)", "24 unidades" si la referencia es de 1 unidad o no hay; archivos: `domain/stock/cantidades.ts`, CompraFormScreen, CompraDetalleScreen, KardexScreen, StockPorUbicacionScreen. Limitación: las respuestas de stock/kardex/compra solo mandan `unidades_referencia`, así que ahí el paréntesis dice "Presentación x6" (el nombre real solo aparece en el formulario de compra); mostrar el nombre ahí requiere un campo nuevo en el backend. LIMITACIÓN DEL NOMBRE RESUELTA (2026-10-02): el backend agrega `nombre_referencia` junto a `unidades_referencia` en stock por ubicación (`GET /stock/ubicaciones/{id}/stock`), kardex y detalle de compra (`GET /compras/{id}`); `null` si no hay referencia. Las tres pantallas muestran ahora "60 unidades (10 Caja x6)" y la pantalla de Stock inicial rotula la cantidad en presentaciones con el nombre de la referencia ("Caja x6", pista "Una Caja x6 tiene 6 unidades.", mensaje de validación con el nombre). Se retiró `referenciaDesdeUnidades` (reemplazada por `referenciaDeRespuesta(unidades, nombre)`).
- H2 — En el historial de costos de "Vino A", el costo vigente pasó de Proveedor1 $1.000 (vigencia 2026-10-02) a Bodega Sur $3.000 (2026-10-01) después de otra compra. Según el orden de CST-03 eso no puede pasar en el mismo producto. Resuelto: el usuario confirmó que había dos productos "Vino A" (uno de Bodega Sur, de pruebas anteriores). No es un bug.
- Flujos 1, 6, 7, 10 y 11 probados por el usuario: OK. H1 también aparece en la pantalla de stock ("+24 cajas").
- Flujo 6 (consulta del usuario): anular una compra no revierte un costo informado aceptado en la oferta. Es lo esperado: el costo informado es un registro aparte y no se sobrescribe (CST-03, CMP-04, CMP-05).
- Flujo 9: no se puede probar desde la interfaz, porque las transferencias y los ajustes son del change 14 y ningún egreso disponible deja la ubicación sin stock suficiente. Lo cubren las pruebas de integración y concurrencia de `STOCK_NEGATIVO` y `STOCK_INSUFICIENTE`.
- Flujos 12 y 13 (usuarios con un solo permiso): no se pueden probar desde la interfaz porque no hay alta de roles ni de usuarios. Lo cubren las pruebas de D17 y D18.
- Nota de negocio (fuera del change): la distribuidora no es responsable inscripta; ver engram `dominio/condicion-iva-organizacion`.

### Resultado

2026-10-02: el usuario dio por buena la verificación manual y pidió archivar el change. Tarea 16.2 marcada [x]. ADR-043 y ADR-044 pasan a *Vigente*. También se corrigió una prueba intermitente de antes del change (`test_token_con_firma_alterada_da_401_invalido`: alteraba el último carácter de la firma base64url, que tiene bits de relleno).
