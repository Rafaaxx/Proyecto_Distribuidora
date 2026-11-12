# Verificación — 11b-condicion-iva-organizacion

Fecha de la verificación automática y de la manual: 2026-10-03. La verificación manual en el navegador (tarea 12.2) la ejecutó el usuario.

## 1. Definición de terminado (`docs/04` §2.1)

| # | Criterio | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Las pruebas que exige `02` §15 pasan | Cumplido (local; CI no se ejecutó desde esta sesión) | Ver §2. |
| 2 | Cada escenario de las specs tiene una prueba | Cumplido | §3. |
| 3 | Los invariantes tocados tienen prueba que los cita por ID | Cumplido | TR-06, INV-01, INV-03, INV-05, INV-06 e INV-21, citados en el nombre de la prueba (§3). |
| 4 | La migración sube y baja limpia sobre una base con datos | Cumplido | `tests/integration/test_condicion_iva_migracion.py` (ciclo upgrade/downgrade/upgrade, TR-06). |
| 5 | Se probó a mano el flujo principal en el navegador | Cumplido | §4. |
| 6 | Las specs delta se archivaron y `04` quedó actualizado | **Pendiente** (al archivar) | Cambios a `docs/00`, `01`, `03` y `04` ya aplicados para revisión del usuario. |
| 7 | Las decisiones nuevas quedaron como ADR | Cumplido | ADR-045, aprobado por el usuario el 2026-10-03 (estado *Vigente*). |

## 2. Comandos y resultados (2026-10-03)

| Comando | Resultado |
| --- | --- |
| `python -m pytest tests/unit` | 1.517 pasaron |
| `python -m pytest tests/fixtures_compartidos` | 96 pasaron |
| `python -m pytest tests/properties` | 29 pasaron |
| `python -m pytest tests/integration` | 1.798 pasaron |
| `python -m pytest tests/concurrency` | 52 pasaron |
| `python -m ruff check .` / `ruff format --check .` | sin hallazgos / 390 archivos formateados |
| `python -m mypy app` | sin errores (158 archivos) |
| `lint-imports` | 22 contratos cumplidos, 0 rotos |
| `npm run test` | 813 pruebas pasaron (83 archivos) |
| `npm run typecheck` | sin errores |
| `npm run lint` | 0 errores; 2 advertencias preexistentes (`watch` de react-hook-form) |
| `npm run build` | correcto |

Notas:

- `python -m pytest` sobre todo el backend falla en la recolección porque los `conftest` de `tests/integration`, `tests/concurrency` y `tests/properties` chocan; cada carpeta se corrió por separado. Es anterior a este change.
- `app-routing.test.tsx` falla con el stack de Docker levantado y pasa con backend y frontend detenidos. Los 813 corresponden a la corrida con el stack detenido.
- Dependencias: ninguna agregada a `requirements*.txt` ni a `package.json` en los dos lotes (tarea 12.1); no hizo falta reconstruir las imágenes.

Desvíos del ciclo TDD estricto:

- Tareas 3.2 y 3.3: las pruebas de `obtener_condicion_iva` y de la siembra se escribieron junto con el código, sin verlas fallar antes.
- Corrección de códigos HTTP y tarea 9.1: las pruebas pasaron de entrada porque el código ya existía. En 9.1 se verificó por mutación (quitando una línea del contrato de import-linter, la prueba falla).
- Tarea 8.1: la prueba de compra simultánea con cambio de condición no detecta por sí sola la falta de bloqueo (la condición se lee una sola vez). La que lo detecta es la de dos cambios simultáneos: sin el `FOR UPDATE` falla 3 de 3.

## 3. Cobertura por escenario (tarea 10.1)

Rutas relativas a `backend/tests/` salvo las de frontend (`frontend/tests/unit/`).

### `importacion/importacion-de-maestros`

| Escenario | Prueba |
| --- | --- |
| Costo por caja sin IVA | `test_costo_por_caja_sin_iva_da_costo_base_1500` |
| Costo con IVA incluido | `test_costo_con_iva_incluido_da_costo_base_1239_669421` |
| Costo con bonificación | `test_costo_con_bonificacion_10_da_costo_base_1350` |
| Monotributista, columna vacía | `test_cst06_un_monotributista_importa_el_valor_pagado_con_la_columna_vacia_o_n` |
| Monotributista con `S` | `test_cst06_una_s_en_la_fila_7_de_40_rechaza_toda_la_planilla_adr040`, `test_cst06_un_exento_tambien_rechaza_la_s` |
| Inscripto con la columna vacía | `test_cst06_un_inscripto_con_la_columna_vacia_da_error_de_valor` (`VALOR_OBLIGATORIO`) |
| Presentación que no es de compra | `test_presentacion_que_no_es_de_compra_da_presentacion_invalida` |
| Presentación con costo congelada | `test_la_presentacion_con_costo_importado_queda_congelada` |

### `organizacion/parametros-de-organizacion`

| Escenario | Prueba |
| --- | --- |
| Organización inicial con valores por defecto | `integration/test_seed.py::test_la_organizacion_inicial_nace_monotributista_en_modo_a_sin_modalidad` |
| Parámetro sin valor definido | `test_los_parametros_a_definir_al_configurar_quedan_explicitamente_nulos` |
| Valor fuera del dominio | `test_condicion_iva_migracion.py::test_una_condicion_fuera_del_dominio_se_rechaza`, `test_identidad_service.py::test_el_alta_rechaza_una_condicion_desconocida` |
| Parámetros monetarios sin float (INV-03) | `integration/test_inv03_sin_punto_flotante.py` |
| Organizaciones existentes al migrar (TR-06) | `test_tr06_el_ciclo_upgrade_downgrade_upgrade_conserva_los_datos_existentes` |
| El inscripto computa crédito fiscal | `unit/test_identidad_valores.py::test_el_responsable_inscripto_computa` |
| Monotributista y exento no computan | `test_monotributo_y_exento_no_computan` |
| No inscripta con modalidad se rechaza | `test_d2_una_organizacion_no_inscripta_exige_modo_a_y_modalidad_nula`, `test_pasar_a_no_inscripto_con_modalidad_de_iva_se_rechaza` |
| Monotributista pasa a inscripto | `test_condicion_iva_cambiar.py::test_monotributista_pasa_a_responsable_inscripto_con_una_auditoria`, `test_tr06_el_cambio_no_toca_costos_ni_compras_previos` |
| Sin permiso (403) | `test_sin_admin_configuracion_se_rechaza_con_permiso_requerido` |
| Mismo valor (409) | `test_cambiar_al_mismo_valor_se_rechaza_y_no_audita`, `test_el_mismo_valor_responde_409_con_su_codigo` |
| Modo incompatible (409) | `test_pasar_a_no_inscripto_con_modo_distinto_de_a_se_rechaza` |
| Doble envío (INV-06) | `test_inv06_el_reenvio_devuelve_el_resultado_original_con_una_sola_auditoria` |
| Valor desconocido (422) | `test_un_valor_desconocido_responde_422_y_no_cambia` |
| Lectura de la propia organización | `test_cst06_cualquier_usuario_lee_la_configuracion_fiscal_de_su_organizacion` |
| Aislamiento entre organizaciones (INV-21) | `test_inv21_cada_organizacion_lee_solo_su_propia_configuracion_fiscal` |
| Cambio con confirmación | `areas/admin/configuracion/ConfiguracionFiscalScreen.test.tsx` |
| Usuario sin permiso, solo lectura | `areas/admin/configuracion/ConfiguracionFiscalScreen.test.tsx` |
| Concurrencia: compra y cambio; dos cambios | `concurrency/test_condicion_iva_concurrencia.py` |

### `proveedores/administracion-de-compras`

| Escenario | Prueba |
| --- | --- |
| Vista previa con IVA | `areas/admin/compras/CompraFormScreen.test.tsx` ("vista previa de Caja x12 con IVA") |
| Vista previa de monotributista | `CompraFormScreen.test.tsx` ("Caja x12 a 21.780: costo base 1.815,000000", "un monotributista no ve Incluye IVA") |
| Medios que no suman el total | `CompraFormScreen.test.tsx` ("de contado con medios que no suman el total") |
| Error del servidor por línea | `CompraFormScreen.test.tsx` ("INCLUYE_IVA_NO_APLICA del servidor se muestra junto a la línea") |
| Detalle con la regla congelada | `areas/admin/compras/CompraDetalleScreen.test.tsx` |

### `proveedores/administracion-de-proveedores`

| Escenario | Prueba |
| --- | --- |
| Vista previa de una caja con IVA | `areas/admin/proveedores/CostosCargaScreen.test.tsx` |
| Vista previa de monotributista | `CostosCargaScreen.test.tsx` ("21780 como valor pagado muestra costo base 1.815,000000 y envía incluye_iva = false") |
| Bonificación en porcentaje | `CostosCargaScreen.test.tsx` |
| Carga de dos costos | `CostosCargaScreen.test.tsx` |
| Error en una fila | `CostosCargaScreen.test.tsx` ("INCLUYE_IVA_NO_APLICA del servidor señala la fila") |
| Solo presentaciones de compra | `CostosCargaScreen.test.tsx` |
| Volver a la ficha | `CostosCargaScreen.test.tsx` |
| Historial con vigente resaltado y costos de las dos reglas | `areas/admin/proveedores/CostosHistorialScreen.test.tsx` |

### `proveedores/compras`

| Escenario | Prueba |
| --- | --- |
| Caja x12 sin IVA, con IVA y con bonificación | `unit/test_proveedores_domain_compras.py`, fixtures `CMP02-linea-*` |
| Línea de monotributista | `test_cst06_linea_sin_credito_fiscal_toma_el_valor_pagado_como_costo` |
| Incluye IVA en una organización no inscripta | `test_d4_incluye_iva_sin_credito_fiscal_se_rechaza`, `test_compras_confirmar.py::test_d4_una_linea_con_incluye_iva_en_una_organizacion_no_inscripta_se_rechaza` |
| Cantidad fraccionaria válida e inválida | `test_cantidad_fraccionaria_que_da_unidades_enteras_es_valida`, `test_cantidad_invalida_se_rechaza` |
| Valor cero o negativo | `test_valor_invalido_se_rechaza`, `test_valor_cero_se_rechaza_con_su_linea` |
| Unidades congeladas | `test_las_lineas_congelan_unidades_alicuota_y_derivados` |
| El cambio de condición no toca compras (TR-06) | `test_tr06_cambiar_la_condicion_no_toca_la_compra_y_su_anulacion_egresa_al_mismo_costo` |
| Total distinto del sugerido | `test_el_total_de_factura_informado_es_la_deuda_y_no_cambia_los_promedios` |
| Total sugerido de monotributista | `test_d5_compra_del_criterio_2_de_un_monotributista_suma_valores_pagados` |
| Total con tres decimales | `test_total_de_factura_con_tres_decimales_se_rechaza` |

### `proveedores/costos-informados`

| Escenario | Prueba |
| --- | --- |
| Caja x12 sin IVA, botella, con IVA y con bonificación | fixtures `CST02-*` (pytest y Vitest) |
| Monotributista informa el valor pagado | `test_cst06_una_organizacion_no_inscripta_informa_el_valor_pagado` |
| Monotributista con bonificación | `test_cst06_con_bonificacion_el_monotributista_descuenta_solo_la_bonificacion` |
| Incluye IVA en una organización no inscripta | `test_d4_incluye_iva_en_una_organizacion_no_inscripta_se_rechaza_sin_registrar_nada` |
| El cambio de condición no toca costos (TR-06) | `test_tr06_cambiar_la_condicion_no_toca_los_costos_registrados` |
| Doble envío (INV-06) | `test_proveedores_commands_bus.py::TestCostoInformarContraElBus::test_aceptado_deja_auditoria_y_reenvio_no_duplica` |
| Mismo `operation_id` con otro valor | `test_mismo_operation_id_con_contenido_distinto_es_inconsistente` |
| Sin permiso para editar costos | `test_proveedores_api.py::TestInformarCostos::test_sin_el_permiso_se_rechaza_sin_efectos` |
| Valor o bonificación inválidos | fixtures `CST02-valor-*` y `CST02-bonificacion-*`, `unit/test_proveedores_domain_costo_base.py` |
| Resumen tras cambiar la condición | `test_cst06_el_resumen_cuenta_los_costos_vigentes_por_regla`, `test_cst03_el_resumen_cuenta_solo_el_ultimo_costo_de_cada_presentacion` |
| Resumen sin permiso | `test_el_resumen_sin_permiso_responde_403` |

## 4. Verificación manual (tarea 12.2)

Ejecutada por el usuario el 2026-10-03 en `http://localhost:5173`, con la migración `a9c0d1e2f3a4` aplicada en la base de desarrollo. Resultado informado por el usuario: todos los pasos correctos.

| # | Paso | Resultado |
| --- | --- | --- |
| 1 | Pasar la organización a `MONOTRIBUTO` desde `/admin/configuracion/fiscal` (confirmación y resumen de costos vigentes) | Correcto |
| 2 | Cargar un costo de Caja x12 a $21.780 sin la casilla de IVA (`1.815,000000`) | Correcto |
| 3 | Registrar una compra de monotributista (total sugerido igual a la suma de las líneas) | Correcto |
| 4 | Ver una compra y un costo previos intactos, con "IVA descontado: Sí" | Correcto |
| 5 | Importar una planilla de costos con la columna vacía (entra) y otra con `S` (rechazada) | Correcto |
| 6 | Volver a `RESPONSABLE_INSCRIPTO` y comprobar que reaparece la casilla | Correcto |
