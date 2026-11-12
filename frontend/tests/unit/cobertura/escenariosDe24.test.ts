import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 24, tarea 21.1: trazabilidad de las specs delta. Cada escenario de las ocho specs
 * (`ruta/area-de-ruta`, `sistema/ayuda-contextual`, `stock/jornadas`, `stock/libro-de-stock`,
 * `stock/rendicion-de-jornada`, `stock/toma-de-ubicacion`, `sync/lote-de-comandos`,
 * `sync/observaciones`) se asocia con la prueba que lo ejercita (archivo y fragmento de su nombre o
 * título); los del servidor apuntan a su archivo de `backend/tests`. Varios nombres se repiten entre
 * specs («Doble sincronización de la entrega», «Sin permiso»...), por eso la clave lleva la
 * capacidad. Si una prueba se renombra o se borra, esta falla y obliga a revisar la cobertura.
 * Además comprueba que cada escenario de las specs tiene su entrada acá (y ninguna sobra) y que
 * INV-01, INV-03, INV-04, INV-05, INV-06, INV-12, INV-16, INV-17 e INV-21 los cita alguna prueba
 * por su ID (`04` §2.1 puntos 2 y 3).
 *
 * Las specs se leen de la carpeta del change mientras está activo y, una vez archivado, de la del
 * archivo (el nombre lleva la fecha del archivo).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const CAMBIOS = resolve(RAIZ, 'openspec', 'changes')

function carpetaDeSpecs(): string {
  const activa = resolve(CAMBIOS, '24-rendicion-de-jornada', 'specs')
  if (existsSync(activa)) return activa
  const archivados = resolve(CAMBIOS, 'archive')
  const nombre = readdirSync(archivados).find((n) => n.endsWith('-24-rendicion-de-jornada'))
  if (nombre === undefined) throw new Error('No se encontró el change 24 ni activo ni archivado')
  return resolve(archivados, nombre, 'specs')
}

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const TERMINAR = 'areas/ruta/TerminarDia.test.tsx'
const TERMINAR_COLA = 'sync/terminarDia.test.ts'
const ENTREGA_EN_PANTALLA = 'areas/ruta/EntregaEnSincronizacion.test.tsx'
const AYUDA = 'ayuda/textosRendicion.test.ts'

const ENTREGAR = 'integration/test_jornada_entregar.py'
const ENTREGA_POR_LOTE = 'integration/test_entrega_por_lote.py'
const RENDIR = 'integration/test_jornada_rendir_v2.py'
const RENDIR_Y_CERRAR = 'integration/test_jornadas_rendir_cerrar.py'
const CERRAR = 'integration/test_jornada_cerrar_v2.py'
const LIBRO = 'integration/test_libro_diferencia_rendicion.py'
const TOMA = 'integration/test_toma_rendicion.py'
const RESUMEN = 'integration/test_resumen_de_jornada.py'
const TARDIOS = 'integration/test_jornada_rendida_observacion.py'
const MIGRACION = 'integration/test_rendicion_migracion.py'
const CONCURRENCIA = 'concurrency/test_rendicion_concurrente.py'
const PROPIEDADES = 'properties/test_rendicion_propiedades.py'

const MAPA: Record<string, Destino> = {
  // ruta/area-de-ruta
  'ruta/area-de-ruta: Terminar el día sin señal': unit(TERMINAR, 'sin señal: confirma, encola la entrega, dispara la sincronización y corta «Vender» y «Cobrar» con el aviso (RUT-05, SYN-03)'),
  'ruta/area-de-ruta: La marca sobrevive a la recarga': unit(TERMINAR, 'la marca sobrevive a la recarga: el inicio sigue cortado y sin «Terminar el día» (RUT-05)'),
  'ruta/area-de-ruta: Falla al terminar el día': unit(TERMINAR_COLA, 'INV-01: una falla al escribir la cola no deja marca, ni comando, ni avance de la secuencia'),
  'ruta/area-de-ruta: Doble toque': unit(TERMINAR_COLA, 'doble toque: reconfirmar no encola otra entrega y devuelve la existente (INV-06)'),
  'ruta/area-de-ruta: Sin permiso': unit(TERMINAR, 'sin ABRIR_JORNADA en el bootstrap no se ofrece (SEG-06)'),
  'ruta/area-de-ruta: Entrega rechazada': unit(ENTREGA_EN_PANTALLA, 'rechazada con %s: «Rechazada», sin el código crudo, «%s» y «Avisá a tu supervisor.» (SYN-06)'),
  'ruta/area-de-ruta: Doble sincronización de la entrega': unit(ENTREGA_EN_PANTALLA, 'aplicar dos veces el mismo resultado no cambia lo mostrado (INV-06)'),
  // sistema/ayuda-contextual
  'sistema/ayuda-contextual: Ayuda del conteo': unit(AYUDA, '%s lleva el texto aprobado, cita sus reglas, sin ejemplo ni «Ver más»'),
  'sistema/ayuda-contextual: Ayuda de «Terminar el día»': unit(AYUDA, "'ruta.terminarDia',"),
  'sistema/ayuda-contextual: Textos revisados': unit(AYUDA, '%s, revisada, lleva el texto aprobado y sin ejemplo'),
  'sistema/ayuda-contextual: Clave o ID inexistente': unit('ayuda/trazabilidad.test.ts', 'cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS'),
  // stock/jornadas
  'stock/jornadas: Rendir una jornada abierta': servidor(RENDIR, 'test_rendicion_sin_diferencias_deja_la_jornada_en_rendicion_y_no_escribe_movimientos'),
  'stock/jornadas: Rendir una jornada sin entrega': servidor(RENDIR, 'test_la_rendicion_exige_la_entrega'),
  'stock/jornadas: Cerrar una jornada en rendición libera la ubicación': servidor(RENDIR_Y_CERRAR, 'test_cerrar_deja_la_jornada_cerrada_y_libera_la_ubicacion'),
  'stock/jornadas: Cerrar una jornada que no se rindió': servidor(RENDIR_Y_CERRAR, 'test_cerrar_una_jornada_que_no_se_rindio_se_rechaza'),
  'stock/jornadas: Rendir dos veces': servidor(RENDIR_Y_CERRAR, 'test_rendir_dos_veces_se_rechaza_y_no_cambia_la_jornada'),
  'stock/jornadas: Transición sobre una jornada terminada': servidor(RENDIR_Y_CERRAR, 'test_una_jornada_terminada_no_admite_transiciones'),
  'stock/jornadas: El vendedor no rinde su propia jornada': servidor(RENDIR_Y_CERRAR, 'test_el_vendedor_no_rinde_ni_cierra_su_propia_jornada'),
  'stock/jornadas: Jornada de otra organización': servidor(RENDIR_Y_CERRAR, 'test_inv21_una_jornada_de_otra_organizacion_o_inexistente_responde_404'),
  'stock/jornadas: Doble envío del cierre': servidor(RENDIR_Y_CERRAR, 'test_inv06_el_reenvio_del_cierre_devuelve_el_resultado_original'),
  // stock/libro-de-stock
  'stock/libro-de-stock: Sobrante al promedio vigente': servidor(LIBRO, 'test_sobrante_se_valoriza_al_promedio_vigente_sin_recalcularlo'),
  'stock/libro-de-stock: Faltante que dejaría negativo': servidor(LIBRO, 'test_faltante_que_dejaria_negativo_se_rechaza_aun_con_permiso'),
  'stock/libro-de-stock: Diferencia con otro origen': servidor(LIBRO, 'test_diferencia_con_otro_origen_es_tipo_invalido'),
  // stock/rendicion-de-jornada
  'stock/rendicion-de-jornada: Entrega aceptada': servidor(ENTREGAR, 'test_rut05_la_entrega_guarda_momento_origen_y_secuencia_sin_cambiar_el_estado'),
  'stock/rendicion-de-jornada: Entrega de una jornada liberada': servidor(ENTREGAR, 'test_rut09_una_jornada_que_no_esta_abierta_se_rechaza_sin_cambios'),
  'stock/rendicion-de-jornada: Segunda entrega con otro identificador': servidor(ENTREGAR, 'test_rut05_una_segunda_entrega_con_otro_identificador_se_rechaza'),
  'stock/rendicion-de-jornada: Entrega de la jornada de otro': servidor(ENTREGAR, 'test_inv21_la_jornada_de_otro_se_rechaza_con_jornada_ajena'),
  'stock/rendicion-de-jornada: Entrega sin permiso': servidor(ENTREGAR, 'test_seg06_sin_abrir_jornada_se_rechaza_con_permiso_requerido'),
  'stock/rendicion-de-jornada: Doble envío de la entrega': servidor(ENTREGAR, 'test_inv06_el_doble_envio_devuelve_el_resultado_original_sin_cambiar_la_entrega'),
  'stock/rendicion-de-jornada: Rendición sin diferencias': servidor(RENDIR, 'test_rendicion_sin_diferencias_deja_la_jornada_en_rendicion_y_no_escribe_movimientos'),
  'stock/rendicion-de-jornada: Rendición sin la entrega': servidor(RENDIR, 'test_la_rendicion_exige_la_entrega'),
  'stock/rendicion-de-jornada: Falta contar un producto': servidor(RENDIR, 'test_falta_contar_un_producto'),
  'stock/rendicion-de-jornada: Un producto vendido hasta cero también se cuenta': servidor(RENDIR, 'test_un_producto_vendido_hasta_cero_tambien_se_cuenta'),
  'stock/rendicion-de-jornada: Sobrante de un producto no esperado': servidor(RENDIR, 'test_sobrante_de_un_producto_no_esperado'),
  'stock/rendicion-de-jornada: El esperado cambió mientras se contaba': servidor(RENDIR, 'test_el_esperado_cambio_mientras_se_contaba'),
  'stock/rendicion-de-jornada: Cantidad contada inválida': servidor(RENDIR, 'test_cantidad_negativa_es_cantidad_invalida'),
  'stock/rendicion-de-jornada: El vendedor no rinde': servidor(RENDIR, 'test_el_vendedor_no_rinde'),
  'stock/rendicion-de-jornada: Rendición de otra organización': servidor(RENDIR, 'test_rendir_la_jornada_de_otra_organizacion_es_404'),
  'stock/rendicion-de-jornada: La versión sin conteo ya no se acepta': servidor(RENDIR, 'test_la_version_sin_conteo_ya_no_se_acepta'),
  'stock/rendicion-de-jornada: Reenvío de una rendición v1 ya aceptada': servidor(RENDIR, 'ni un v1 nuevo ni el reenvío de uno ya aceptado llegan al handler'),
  'stock/rendicion-de-jornada: Doble envío de la rendición': servidor(RENDIR, 'test_el_doble_envio_devuelve_el_resultado_original'),
  'stock/rendicion-de-jornada: Faltante': servidor(RENDIR, 'test_el_faltante_escribe_la_diferencia_al_promedio_con_la_jornada'),
  'stock/rendicion-de-jornada: Sobrante sin promedio': servidor(RENDIR, 'test_sobrante_sin_promedio_se_acepta_con_costo_nulo'),
  'stock/rendicion-de-jornada: Sobrante de un producto inactivo': servidor(RENDIR, 'test_sobrante_de_un_producto_inactivo_exige_reactivar'),
  'stock/rendicion-de-jornada: Faltante de un producto inactivo': servidor(RENDIR, 'test_faltante_de_un_producto_inactivo_se_acepta'),
  'stock/rendicion-de-jornada: Producto inactivo sin diferencia': servidor(RENDIR, 'test_inactivo_sin_diferencia_se_acepta_sin_movimiento'),
  'stock/rendicion-de-jornada: Falla a mitad de la rendición': servidor(RENDIR, 'test_una_falla_a_mitad_de_la_rendicion_no_deja_nada'),
  'stock/rendicion-de-jornada: La rendición no se modifica ni se borra': servidor(MIGRACION, 'test_inv05_app_runtime_no_modifica_ni_borra_una_rendicion'),
  'stock/rendicion-de-jornada: El stock cuadra con lo contado': servidor(PROPIEDADES, 'test_inv12_rut07_inv05_el_stock_es_lo_contado_el_resumen_cuadra_y_los_libros_solo_crecen'),
  'stock/rendicion-de-jornada: El resumen cuadra': servidor(RESUMEN, 'test_el_resumen_cuadra_al_abrir_mas_movimientos_es_el_esperado'),
  'stock/rendicion-de-jornada: Cobranzas por medio de pago': servidor(RESUMEN, 'test_las_cobranzas_se_suman_por_medio_de_pago'),
  'stock/rendicion-de-jornada: Anulación de una jornada liberada': servidor(RESUMEN, 'test_la_anulacion_de_una_jornada_liberada_figura_entre_las_anuladas'),
  'stock/rendicion-de-jornada: Cobranza anulada aparte': servidor(RESUMEN, 'test_una_cobranza_anulada_no_suma_en_su_medio_y_figura_entre_las_anuladas'),
  'stock/rendicion-de-jornada: Lo tardío no cambia el resumen rendido': servidor(RESUMEN, 'test_las_ventas_de_despues_de_la_rendicion_figuran_aparte'),
  'stock/rendicion-de-jornada: Sin permiso de costos': servidor(RESUMEN, 'test_el_valor_de_las_diferencias_solo_con_ver_costos'),
  'stock/rendicion-de-jornada: Jornada sin conteo': servidor(RESUMEN, 'test_una_jornada_cerrada_antes_del_change_informa_stock_y_dinero_sin_conteo'),
  'stock/rendicion-de-jornada: Resumen de otra organización': servidor(RESUMEN, 'test_inv21_una_jornada_de_otra_organizacion_o_inexistente_es_404'),
  'stock/rendicion-de-jornada: Cerrar devolviendo al depósito': servidor(CERRAR, 'test_cerrar_devolviendo_al_deposito_escribe_la_transferencia_y_libera'),
  'stock/rendicion-de-jornada: Devolver más de lo que hay': servidor(CERRAR, 'test_devolver_mas_de_lo_que_hay_es_stock_insuficiente_sin_efectos'),
  'stock/rendicion-de-jornada: Destino con toma': servidor(CERRAR, 'test_destino_con_toma_es_ubicacion_con_toma'),
  'stock/rendicion-de-jornada: Devolución sin permiso de transferir': servidor(CERRAR, 'test_devolucion_sin_transferir_stock_es_403_sin_cambios'),
  'stock/rendicion-de-jornada: Cerrar sin devolver': servidor(CERRAR, 'test_cerrar_sin_devolver_libera_y_deja_el_stock'),
  'stock/rendicion-de-jornada: Doble envío del cierre con devolución': servidor(CERRAR, 'test_doble_envio_del_cierre_con_devolucion_devuelve_lo_mismo_con_una_transferencia'),
  'stock/rendicion-de-jornada: Rendición y venta tardía a la vez': servidor(CONCURRENCIA, 'class TestRendicionContraVentaSinConexion'),
  'stock/rendicion-de-jornada: Rendición y liberación a la vez': servidor(CONCURRENCIA, 'class TestRendicionContraLiberacion'),
  // stock/toma-de-ubicacion
  'stock/toma-de-ubicacion: La rendición escribe sobre el vehículo tomado': servidor(TOMA, 'test_la_rendicion_escribe_sobre_el_vehiculo_tomado_con_la_jornada'),
  'stock/toma-de-ubicacion: La excepción no alcanza a una transferencia común': servidor(TOMA, 'test_la_excepcion_no_alcanza_a_una_transferencia_comun'),
  'stock/toma-de-ubicacion: La devolución del cierre sale del vehículo tomado': servidor(TOMA, 'test_la_devolucion_del_cierre_sale_del_vehiculo_tomado'),
  // sync/lote-de-comandos
  'sync/lote-de-comandos: Entrega detrás de ventas y cobranzas': servidor(ENTREGA_POR_LOTE, 'test_rut05_la_entrega_se_procesa_detras_de_las_ventas_y_la_cobranza'),
  'sync/lote-de-comandos: Error transitorio antes de la entrega': servidor(ENTREGA_POR_LOTE, 'test_syn03_un_error_transitorio_anterior_deja_la_entrega_sin_procesar'),
  'sync/lote-de-comandos: Un rechazo anterior no impide la entrega': servidor(ENTREGA_POR_LOTE, 'test_syn06_un_rechazo_anterior_no_impide_la_entrega'),
  'sync/lote-de-comandos: Entrega en modo ONLINE': servidor(ENTREGA_POR_LOTE, 'test_syn06_la_entrega_en_modo_online_se_rechaza_sin_cambios'),
  'sync/lote-de-comandos: Doble sincronización de la entrega': servidor(ENTREGA_POR_LOTE, 'test_inv06_la_doble_sincronizacion_devuelve_los_resultados_originales'),
  // sync/observaciones
  'sync/observaciones: Venta tardía': servidor(TARDIOS, 'test_una_venta_tardia_de_una_jornada_en_rendicion_lleva_las_dos_observaciones'),
  'sync/observaciones: Cobranza tardía con la jornada cerrada': servidor(TARDIOS, 'test_una_cobranza_tardia_se_acepta_con_jornada_rendida_y_baja_el_saldo'),
  'sync/observaciones: Anulación tardía': servidor(TARDIOS, 'test_una_anulacion_tardia_se_acepta_con_jornada_rendida'),
  'sync/observaciones: Doble envío de la operación tardía': servidor(TARDIOS, 'test_el_doble_envio_de_la_venta_tardia_no_duplica_la_observacion'),
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

describe('trazabilidad de las specs delta del 24 (tarea 21.1; INV-01, INV-03, INV-04, INV-05, INV-06, INV-12, INV-16, INV-17, INV-21)', () => {
  it.each(Object.entries(MAPA))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las ocho specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(65)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('INV-01, INV-03, INV-04, INV-05, INV-06, INV-12, INV-16, INV-17 e INV-21 los cita alguna prueba por su ID (04 §2.1 puntos 2 y 3)', () => {
    const texto = (ruta: string): string => readFileSync(ruta, 'utf-8')
    const citas: Record<string, readonly string[]> = {
      'INV-01': [resolve(UNIT, TERMINAR_COLA), resolve(BACKEND, RENDIR), resolve(BACKEND, CERRAR)],
      'INV-03': [resolve(BACKEND, RESUMEN), resolve(BACKEND, MIGRACION), resolve(BACKEND, LIBRO)],
      'INV-04': [resolve(BACKEND, RENDIR), resolve(BACKEND, 'fixtures_compartidos/test_rut06_rendicion.py'), resolve(UNIT, 'calculo/rendicion.test.ts')],
      'INV-05': [resolve(BACKEND, MIGRACION), resolve(BACKEND, PROPIEDADES)],
      'INV-06': [resolve(BACKEND, ENTREGAR), resolve(BACKEND, ENTREGA_POR_LOTE), resolve(BACKEND, CONCURRENCIA)],
      'INV-12': [resolve(BACKEND, PROPIEDADES), resolve(BACKEND, CONCURRENCIA), resolve(BACKEND, RENDIR)],
      'INV-16': [resolve(BACKEND, CONCURRENCIA), resolve(BACKEND, CERRAR), resolve(BACKEND, TOMA)],
      'INV-17': [resolve(BACKEND, TARDIOS), resolve(BACKEND, CONCURRENCIA)],
      'INV-21': [resolve(BACKEND, ENTREGAR), resolve(BACKEND, RENDIR), resolve(BACKEND, RESUMEN)],
    }
    for (const [id, archivos] of Object.entries(citas)) {
      for (const archivo of archivos) {
        expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
        expect(texto(archivo), `${archivo} no cita ${id}`).toContain(id)
      }
    }
  })
})
