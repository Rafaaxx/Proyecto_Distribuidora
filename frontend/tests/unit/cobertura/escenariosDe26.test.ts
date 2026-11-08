import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 26, tarea 17.1: trazabilidad de las specs delta. Cada escenario de las siete specs
 * (`reportes/ajustes-por-motivo`, `reportes/area-de-reportes`, `reportes/observaciones-por-vendedor`,
 * `reportes/rendicion-por-vendedor`, `reportes/saldos-de-cuentas`, `reportes/ventas-por-periodo`,
 * `sistema/ayuda-contextual`) se asocia con la prueba que lo ejercita (archivo y fragmento de su
 * nombre o título); los del servidor apuntan a su archivo de `backend/tests`. Si una prueba se
 * renombra o se borra, esta falla y obliga a revisar la cobertura. Además comprueba que cada
 * escenario de las specs tiene su entrada acá (y ninguna sobra) y que REP-01 a REP-05, INV-02,
 * INV-03, INV-10, INV-13, INV-14 e INV-21 los cita alguna prueba por su ID (`04` §2.1 puntos 2 y 3).
 *
 * No hay pruebas de concurrencia (los reportes son de solo lectura y no toman bloqueos) ni
 * migración (el change no cambia el esquema): `04` §2.1 punto 4 no aplica.
 *
 * Las specs se leen de la carpeta del change mientras está activo y, una vez archivado, de la del
 * archivo (el nombre lleva la fecha del archivo).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const CAMBIOS = resolve(RAIZ, 'openspec', 'changes')

function carpetaDeSpecs(): string {
  const activa = resolve(CAMBIOS, '26-reportes-etapa-1', 'specs')
  if (existsSync(activa)) return activa
  const archivados = resolve(CAMBIOS, 'archive')
  const nombre = readdirSync(archivados).find((n) => n.endsWith('-26-reportes-etapa-1'))
  if (nombre === undefined) throw new Error('No se encontró el change 26 ni activo ni archivado')
  return resolve(archivados, nombre, 'specs')
}

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const VENTAS = 'integration/reportes/test_reporte_ventas.py'
const CANTIDADES = 'integration/reportes/test_reporte_ventas_cantidades.py'
const UTILIDAD = 'integration/reportes/test_reporte_ventas_utilidad.py'
const CONCILIA = 'integration/reportes/test_reporte_ventas_concilia.py'
const RENDICIONES = 'integration/reportes/test_reporte_rendiciones.py'
const OBSERVACIONES = 'integration/reportes/test_reporte_observaciones.py'
const AJUSTES = 'integration/reportes/test_reporte_ajustes.py'
const SALDOS = 'integration/reportes/test_reporte_saldos.py'
const VENTAS_PAGINADAS = 'integration/reportes/test_reporte_ventas_paginacion.py'
const RENDICIONES_PAGINADAS = 'integration/reportes/test_reporte_rendiciones_paginacion.py'
const SALDOS_PAGINADOS = 'integration/reportes/test_reporte_saldos_paginacion.py'
const SOLO_LECTURA = 'integration/reportes/test_reportes_solo_lectura.py'
const PROPIEDADES = 'properties/test_reportes_propiedades.py'

const VENTAS_UI = 'areas/admin/reportes/VentasReporte.test.tsx'
const RENDICIONES_UI = 'areas/admin/reportes/RendicionesReporte.test.tsx'
const SALDOS_UI = 'areas/admin/reportes/SaldosReporte.test.tsx'
const OBSERVACIONES_UI = 'areas/admin/reportes/ObservacionesPorVendedorReporte.test.tsx'
const AREA_UI = 'areas/admin/reportes/ReportesArea.test.tsx'

const MAPA: Record<string, Destino> = {
  // reportes/ajustes-por-motivo
  'reportes/ajustes-por-motivo: Pérdidas por rotura': servidor(AJUSTES, 'test_las_perdidas_por_rotura_suman_ajustes_unidades_y_valor'),
  'reportes/ajustes-por-motivo: Ajuste anulado': servidor(AJUSTES, 'test_un_ajuste_anulado_no_suma_y_se_cuenta_aparte'),
  'reportes/ajustes-por-motivo: Diferencias de rendición': servidor(AJUSTES, 'test_las_diferencias_de_rendicion_van_en_su_propia_fila'),
  'reportes/ajustes-por-motivo: Sin permiso de costos': servidor(AJUSTES, 'test_sin_ver_costos_las_unidades_se_informan_y_los_valores_van_en_null'),
  'reportes/ajustes-por-motivo: Período sin ajustes': servidor(AJUSTES, 'test_un_periodo_sin_ajustes_devuelve_todo_en_cero'),
  // reportes/area-de-reportes
  'reportes/area-de-reportes: Sin permiso de reportes': servidor(VENTAS, 'test_sin_ver_reportes_responde_403_permiso_requerido'),
  'reportes/area-de-reportes: Consulta/Dirección entra a los reportes': unit('areas/admin/AdminInicio.test.tsx', 'el usuario de Consulta aterriza en «Reportes»'),
  'reportes/area-de-reportes: Consultar un reporte no cambia nada': servidor(SOLO_LECTURA, 'test_pedir_todos_los_reportes_no_cambia_ninguna_tabla'),
  'reportes/area-de-reportes: Mes en curso por defecto': servidor(VENTAS, 'test_sin_fechas_el_periodo_es_el_mes_en_curso_segun_el_reloj_inyectable'),
  'reportes/area-de-reportes: Venta cerca de la medianoche': servidor(VENTAS, 'test_una_venta_cerca_de_la_medianoche_entra_en_el_mes_de_la_zona_de_la_organizacion'),
  'reportes/area-de-reportes: Rango invertido': servidor(VENTAS, 'test_un_rango_invertido_responde_422_rango_de_fechas_invalido'),
  'reportes/area-de-reportes: Período demasiado largo': servidor(VENTAS, 'test_367_dias_responden_422_y_366_se_aceptan'),
  'reportes/area-de-reportes: Datos de otra organización': servidor(VENTAS, 'test_inv21_el_reporte_no_incluye_ventas_de_otra_organizacion'),
  'reportes/area-de-reportes: Filtro con un vendedor ajeno': servidor(VENTAS, 'test_inv21_filtrar_por_un_vendedor_de_otra_organizacion_devuelve_el_reporte_vacio'),
  'reportes/area-de-reportes: Más de una página': servidor(SALDOS_PAGINADOS, 'test_los_clientes_se_paginan_de_a_cincuenta_con_totales_de_todo_lo_filtrado'),
  'reportes/area-de-reportes: Las páginas no repiten ni pierden filas': servidor(RENDICIONES_PAGINADAS, 'test_las_jornadas_van_en_paginas_de_cincuenta_con_la_mas_reciente_primero'),
  'reportes/area-de-reportes: Página fuera de rango': servidor(VENTAS_PAGINADAS, 'test_una_pagina_fuera_de_rango_trae_filas_vacias_con_los_totales_reales'),
  'reportes/area-de-reportes: Cada lista del reporte de ventas se pagina por su lado': servidor(VENTAS_PAGINADAS, 'test_cada_lista_se_pagina_por_su_lado'),
  'reportes/area-de-reportes: Recorrer las páginas': unit(VENTAS_UI, '«Siguiente» en «Por día» pide solo la página 2 de esa lista y deja las otras en la 1'),
  'reportes/area-de-reportes: Una sola página': unit('areas/admin/reportes/Paginacion.test.tsx', 'con una sola página o sin filas no muestra nada'),
  'reportes/area-de-reportes: Cambiar un filtro vuelve a la primera página': unit(VENTAS_UI, 'cambiar el vendedor vuelve todas las listas a la página 1'),
  'reportes/area-de-reportes: Menú con y sin permiso': unit('areas/admin/AdminLayout.test.tsx', 'Consulta/Dirección ve solo «Reportes»'),
  'reportes/area-de-reportes: Cambiar el período': unit(VENTAS_UI, 'al elegir otras fechas vuelve a pedir el reporte con ellas'),
  'reportes/area-de-reportes: Error del servidor': unit(VENTAS_UI, 'un error cualquiera muestra el texto de error de carga'),
  // reportes/observaciones-por-vendedor
  'reportes/observaciones-por-vendedor: Vendedor con avisos y rechazos': servidor(OBSERVACIONES, 'test_el_vendedor_con_avisos_y_rechazos_se_cuenta_en_su_fila'),
  'reportes/observaciones-por-vendedor: Fuera del período': servidor(OBSERVACIONES, 'test_lo_que_cae_fuera_del_periodo_no_se_cuenta'),
  'reportes/observaciones-por-vendedor: Otra organización': servidor(OBSERVACIONES, 'test_inv21_no_cuenta_observaciones_ni_rechazos_de_otra_organizacion'),
  'reportes/observaciones-por-vendedor: Acceso a la bandeja según permiso': unit(OBSERVACIONES_UI, '«Ver en Revisión» solo con REVISAR_OBSERVACIONES, a la bandeja filtrada por ese vendedor'),
  // reportes/rendicion-por-vendedor
  'reportes/rendicion-por-vendedor: Jornada rendida': servidor(RENDICIONES, 'test_la_jornada_rendida_informa_ventas_anuladas_cobrado_y_diferencias'),
  'reportes/rendicion-por-vendedor: Lo registrado después de la rendición': servidor(RENDICIONES, 'test_lo_registrado_despues_de_la_rendicion_va_aparte'),
  'reportes/rendicion-por-vendedor: Jornada liberada sin conteo': servidor(RENDICIONES, 'test_la_jornada_liberada_sale_sin_conteo'),
  'reportes/rendicion-por-vendedor: Valor de las diferencias según permiso': servidor(RENDICIONES, 'test_el_valor_de_las_diferencias_solo_lo_ve_quien_tiene_ver_costos'),
  'reportes/rendicion-por-vendedor: La jornada más reciente primero, en páginas': servidor(RENDICIONES_PAGINADAS, 'test_las_jornadas_van_en_paginas_de_cincuenta_con_la_mas_reciente_primero'),
  'reportes/rendicion-por-vendedor: Filtros por vendedor y estado': servidor(RENDICIONES, 'test_los_filtros_de_vendedor_y_estado'),
  'reportes/rendicion-por-vendedor: Dos jornadas del mismo vendedor': servidor(RENDICIONES, 'test_los_totales_por_vendedor_suman_sus_jornadas'),
  'reportes/rendicion-por-vendedor: Detalle sin permisos de jornadas': servidor(RENDICIONES, 'test_el_detalle_es_el_resumen_de_rut07_sin_el_valor_para_quien_no_ve_costos'),
  'reportes/rendicion-por-vendedor: Jornada de otra organización': servidor(RENDICIONES, 'test_inv21_el_detalle_de_una_jornada_ajena_o_inexistente_es_404'),
  'reportes/rendicion-por-vendedor: Ver el detalle': unit(RENDICIONES_UI, '«Ver detalle» abre el resumen de la jornada pedido al reporte, sin valores de costo (RUT-07)'),
  'reportes/rendicion-por-vendedor: Sin jornadas': unit(RENDICIONES_UI, 'un período sin jornadas muestra «Sin jornadas en el período.»'),
  // reportes/saldos-de-cuentas
  'reportes/saldos-de-cuentas: Vendedores del filtro': servidor(SALDOS, 'test_la_lista_de_vendedores_es_completa_y_no_depende_de_la_pagina_ni_del_filtro'),
  'reportes/saldos-de-cuentas: El saldo es la suma de los movimientos': servidor(SALDOS, 'test_el_saldo_es_la_suma_de_los_movimientos_del_libro'),
  'reportes/saldos-de-cuentas: Deudores y saldo a favor': servidor(SALDOS, 'test_deudores_a_favor_con_saldo_y_todos_con_sus_totales'),
  'reportes/saldos-de-cuentas: Límite y disponible': servidor(SALDOS, 'test_limite_y_disponible_con_y_sin_limite'),
  'reportes/saldos-de-cuentas: Filtro por vendedor asignado': servidor(SALDOS, 'test_filtra_por_vendedor_asignado_y_muestra_su_nombre'),
  'reportes/saldos-de-cuentas: Deuda con un proveedor': servidor(SALDOS, 'test_deuda_con_un_proveedor_es_la_suma_de_sus_movimientos'),
  'reportes/saldos-de-cuentas: Supervisor con la plantilla actual': servidor(SALDOS, 'test_supervisor_con_la_plantilla_actual_ve_clientes_y_no_proveedores'),
  'reportes/saldos-de-cuentas: Consulta/Dirección entra por `VER_UTILIDAD`': servidor(SALDOS, 'test_consulta_direccion_entra_a_proveedores_por_ver_utilidad'),
  'reportes/saldos-de-cuentas: Solo `VER_REPORTES` no alcanza': servidor(SALDOS, 'test_solo_ver_reportes_no_alcanza_para_proveedores_y_cada_permiso_extra_si'),
  'reportes/saldos-de-cuentas: Enlace al estado de cuenta según permiso': unit(SALDOS_UI, '«Ver estado de cuenta» solo con GESTIONAR_CLIENTES, hacia la cuenta corriente del cliente'),
  'reportes/saldos-de-cuentas: Sin resultados': unit(SALDOS_UI, 'sin clientes muestra «Sin clientes para mostrar.»'),
  'reportes/saldos-de-cuentas: Pestaña de proveedores según la regla compuesta': unit(AREA_UI, 'el Supervisor ve cinco: sin «Saldos de proveedores» (SEG-06)'),
  // reportes/ventas-por-periodo
  'reportes/ventas-por-periodo: Totales del período': servidor(VENTAS, 'test_el_resumen_suma_las_ventas_confirmadas_del_periodo'),
  'reportes/ventas-por-periodo: Valores congelados': servidor(VENTAS, 'test_rep05_las_cifras_pasadas_no_cambian_con_precios_posteriores'),
  'reportes/ventas-por-periodo: Concilia con las ventas registradas': servidor(CONCILIA, 'test_rep01_el_reporte_concilia_con_el_listado_de_ventas_confirmadas'),
  'reportes/ventas-por-periodo: Por día, el más reciente primero': servidor(VENTAS_PAGINADAS, 'test_por_dia_trae_cincuenta_filas_con_el_sobre_y_la_fecha_mas_reciente_primero'),
  'reportes/ventas-por-periodo: Filtro por vendedor': servidor(VENTAS, 'test_el_filtro_de_vendedor_acota_el_resumen_y_los_desgloses'),
  'reportes/ventas-por-periodo: Período sin ventas': servidor(VENTAS, 'test_un_periodo_sin_ventas_trae_ceros_y_desgloses_vacios'),
  'reportes/ventas-por-periodo: Anulada dentro del período': servidor(VENTAS, 'test_las_anuladas_no_suman_en_el_periodo_y_se_informan_aparte'),
  'reportes/ventas-por-periodo: Anulada después del período': servidor(VENTAS, 'test_una_anulada_despues_del_periodo_queda_en_el_periodo_de_la_venta'),
  'reportes/ventas-por-periodo: Anuladas en páginas, la más reciente primero': servidor(VENTAS_PAGINADAS, 'test_las_anuladas_se_paginan_con_la_mas_reciente_primero_y_desempate_por_id'),
  'reportes/ventas-por-periodo: Cajas equivalentes del glosario': servidor(CANTIDADES, 'test_15_botellas_de_un_vino_x6_son_2_con_50_cajas_equivalentes'),
  'reportes/ventas-por-periodo: Detalle por presentación': servidor(CANTIDADES, 'test_el_detalle_por_presentacion_separa_cajas_y_botellas'),
  'reportes/ventas-por-periodo: La referencia cambió entre ventas': servidor(CANTIDADES, 'test_la_referencia_congelada_de_cada_linea_manda_aunque_cambie_despues'),
  'reportes/ventas-por-periodo: Redondeo una sola vez': servidor(CANTIDADES, 'test_el_redondeo_se_hace_una_sola_vez_sobre_la_suma_exacta'),
  'reportes/ventas-por-periodo: Utilidad con permiso': servidor(UTILIDAD, 'test_con_ver_utilidad_el_resumen_informa_costo_vendido_y_utilidad'),
  'reportes/ventas-por-periodo: Sin permiso de utilidad': servidor(UTILIDAD, 'test_sin_ver_utilidad_costo_utilidad_y_lineas_sin_costo_vienen_en_null'),
  'reportes/ventas-por-periodo: Línea vendida sin costo': servidor(UTILIDAD, 'test_una_linea_sin_costo_queda_fuera_del_costo_y_de_la_utilidad_y_se_informa_aparte'),
  'reportes/ventas-por-periodo: Las anuladas no suman utilidad': servidor(UTILIDAD, 'test_las_anuladas_no_suman_costo_ni_utilidad'),
  'reportes/ventas-por-periodo: Con utilidad y líneas sin costo': unit(VENTAS_UI, 'la nota de líneas sin costo aparece con su texto aprobado y el costo y la utilidad en cada desglose'),
  'reportes/ventas-por-periodo: Período vacío': unit(VENTAS_UI, 'muestra los dos textos de vacío y ninguna nota de líneas sin costo'),
  // sistema/ayuda-contextual
  'sistema/ayuda-contextual: Ayuda de las anuladas': unit(VENTAS_UI, 'la ayuda de las anuladas explica que no suman en el período en que se hicieron, sin ejemplo'),
  'sistema/ayuda-contextual: Ayuda de la utilidad': unit(VENTAS_UI, 'con utilidad ofrece las cinco ayudas: período, cajas equivalentes, utilidad, líneas sin costo y anuladas'),
  'sistema/ayuda-contextual: Ayuda de las cajas equivalentes': unit(VENTAS_UI, 'con utilidad ofrece las cinco ayudas: período, cajas equivalentes, utilidad, líneas sin costo y anuladas'),
  'sistema/ayuda-contextual: Clave o ID inexistente': unit('ayuda/trazabilidad.test.ts', 'cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS'),
}

function escenariosDeLasSpecs(): string[] {
  const nombres = new Set<string>()
  const recorrer = (dir: string, capacidad: string): void => {
    for (const entrada of readdirSync(dir, { withFileTypes: true })) {
      const ruta = resolve(dir, entrada.name)
      if (entrada.isDirectory()) {
        recorrer(ruta, capacidad === '' ? entrada.name : `${capacidad}/${entrada.name}`)
      } else if (entrada.name.endsWith('.md')) {
        for (const linea of readFileSync(ruta, 'utf-8').split(/\r?\n/)) {
          const m = /^#### Scenario: (.+)$/.exec(linea)
          if (m?.[1] !== undefined) nombres.add(`${capacidad}: ${m[1].trim()}`)
        }
      }
    }
  }
  recorrer(carpetaDeSpecs(), '')
  return [...nombres].sort()
}

describe('trazabilidad de las specs delta del 26 (tarea 17.1; REP-01 a REP-05, INV-02, INV-03, INV-10, INV-13, INV-14, INV-21)', () => {
  it.each(Object.entries(MAPA))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las siete specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(60)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('REP-01 a REP-05, INV-02, INV-03, INV-10, INV-13, INV-14 e INV-21 los cita alguna prueba por su ID (04 §2.1 puntos 2 y 3)', () => {
    const citas: Record<string, readonly string[]> = {
      'REP-01': [VENTAS, CONCILIA, PROPIEDADES, SOLO_LECTURA],
      'REP-02': [VENTAS, UTILIDAD, PROPIEDADES],
      'REP-03': [CANTIDADES],
      'REP-04': [UTILIDAD],
      'REP-05': [VENTAS, CANTIDADES, PROPIEDADES],
      'INV-02': [VENTAS],
      'INV-03': [VENTAS, RENDICIONES, PROPIEDADES],
      'INV-10': [PROPIEDADES],
      'INV-13': [SALDOS, PROPIEDADES],
      'INV-14': [VENTAS, PROPIEDADES],
      'INV-21': [VENTAS, CANTIDADES, RENDICIONES, OBSERVACIONES, AJUSTES, SALDOS],
    }
    for (const [id, archivos] of Object.entries(citas)) {
      for (const archivo of archivos) {
        const ruta = resolve(BACKEND, archivo)
        expect(existsSync(ruta), `falta ${ruta}`).toBe(true)
        expect(readFileSync(ruta, 'utf-8'), `${ruta} no cita ${id}`).toContain(id)
      }
    }
  })
})
