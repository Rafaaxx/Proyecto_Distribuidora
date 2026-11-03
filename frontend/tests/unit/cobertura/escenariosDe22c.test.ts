import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 22c, tarea 14.1: trazabilidad de las specs delta. Cada escenario de las siete specs
 * (`ruta/area-de-ruta`, `sistema/ayuda-contextual`, `sistema/logging-estructurado`,
 * `sync/bootstrap`, `sync/cola-local`, `sync/lote-de-comandos`, `sync/motor-de-sincronizacion`)
 * se asocia con la prueba que lo ejercita (archivo y fragmento de su título); los del servidor
 * apuntan a su archivo de `backend/tests`. Si una prueba se renombra o se borra, esta falla y
 * obliga a revisar la cobertura. Además comprueba que cada escenario de las specs tiene su entrada
 * acá (y ninguna sobra) y que INV-17, INV-01 e INV-06 los cita alguna prueba por su ID
 * (`04` §2.1 puntos 2 y 3).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const SPECS = resolve(RAIZ, 'openspec', 'changes', '22c-stock-credito-locales-y-conflictos', 'specs')

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const DISPONIBLES = 'domain/ruta/disponiblesLocales.test.ts'
const APLICAR = 'sync/aplicarResultados.test.ts'
const BOOTSTRAP = 'sync/aplicarBootstrap.test.ts'
const CICLO = 'sync/sincronizar.test.ts'
const CLIENTES = 'areas/ruta/ClientesScreen.test.tsx'
const PRODUCTOS = 'areas/ruta/ProductosYStock.test.tsx'
const PANTALLA = 'areas/ruta/SincronizacionScreen.test.tsx'
const GUARDADA = 'areas/ruta/ventas/VentaGuardadaScreen.test.tsx'
const AYUDA = 'ayuda/textosRuta.test.ts'
const BOOT_SRV = 'integration/test_bootstrap_secuencia_procesada.py'
const LOTE_SRV = 'integration/test_bus_lote_sincronizacion.py'
const OBS_SRV = 'integration/test_lote_resultado_con_observaciones.py'
const INV17_SRV = 'integration/test_inv17_operaciones_sin_conexion_no_se_rechazan.py'
const METRICAS = 'unit/test_sync_metricas_de_lote.py'

const MAPA: Record<string, Destino> = {
  // ruta/area-de-ruta
  'Cartera primero': unit(CLIENTES, 'lista primero el consumidor final, luego la cartera'),
  'Ficha con saldo y crédito': unit(CLIENTES, 'muestra contacto, lista aplicable, saldo y disponible exactos'),
  'Ficha con ventas del teléfono': unit(CLIENTES, 'muestra saldo $ 150.000,00, disponible $ 50.000,00 y la leyenda'),
  'Cliente suspendido': unit(CLIENTES, 'el cliente suspendido lleva la marca'),
  'Precio por presentación': unit(PRODUCTOS, 'muestra el precio por presentación de la versión vigente'),
  'Versión programada que entra en vigencia': unit(PRODUCTOS, 'la versión programada se toma a su hora'),
  'Stock en cajas y unidades': unit(PRODUCTOS, 'lista el stock de la ubicación por producto en cajas y unidades'),
  'Stock con ventas del teléfono': unit(PRODUCTOS, 'Stock: 63 menos una venta local de 12 = 51'),
  'Stock después de actualizar': unit(PRODUCTOS, 'después de actualizar (bootstrap con 48 y marca 7)'),
  'Lista de ventas con problemas': unit(PANTALLA, 'la fila de una «Con observaciones» muestra la primera observación traducida y «1 más»'),
  'Código sin texto': unit(PANTALLA, 'una rechazada con un código que el teléfono no conoce'),
  'Sesión vencida': unit(PANTALLA, 'una sesión vencida pide iniciar sesión con señal'),
  'Sin problemas': unit(PANTALLA, 'con todo enviado dice «Todo enviado»'),
  'Observaciones con detalle': unit(GUARDADA, 'muestra todas las observaciones traducidas'),
  'Producto que ya no está en la base local': unit(GUARDADA, 'un producto que ya no está en la base local se nombra «un producto»'),
  'Motivo del rechazo': unit(GUARDADA, 'el motivo del rechazo trae el texto, el código y el aviso'),
  'Venta enviada antes de guardar observaciones': unit(GUARDADA, 'una «Con observaciones» sin la lista guardada dice'),
  'Venta enviada sin observaciones': unit(GUARDADA, 'una «Enviada» no muestra ninguna de las dos secciones'),
  // sistema/ayuda-contextual
  'Observaciones y rechazos': unit(AYUDA, 'ruta.observacionesYRechazos: qué anotó el sistema'),
  'Stock del vehículo': unit(AYUDA, 'ruta.stockDelVehiculo: el de la última'),
  'Crédito del cliente': unit(AYUDA, 'ruta.creditoSinSenal: deuda de la última'),
  Rechazada: unit(AYUDA, 'ruta.ventaRechazada: problema de datos'),
  Trazabilidad: unit('ayuda/trazabilidad.test.ts', 'cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS'),
  // sistema/logging-estructurado
  'El registro de un comando informa duración, resultado y reintentos': servidor(
    'unit/test_logging_contexto_comando.py',
    'test_un_comando_sin_reintentos_informa_reintentos_cero',
  ),
  'El registro de un lote informa su tamaño': servidor('integration/test_grupo12_logging_lote.py', 'test_un_lote_de_tres_comandos_informa_tamano_tres'),
  'El cierre del lote informa el reparto por resultado': servidor(METRICAS, 'test_02_17_el_cierre_informa_el_reparto_por_resultado'),
  'El cierre del lote informa el corte': servidor(METRICAS, 'test_02_17_el_cierre_informa_el_corte_por_un_error_transitorio'),
  'Reenvío del mismo lote': servidor(METRICAS, 'test_inv06_el_reenvio_del_mismo_lote_informa_los_mismos_resultados'),
  'El contenido del comando no llega a los registros': servidor(METRICAS, 'test_02_18_el_cierre_no_lleva_el_contenido_ni_el_detalle'),
  // sync/bootstrap
  'Ventas ya procesadas': servidor(BOOT_SRV, 'test_syn11_la_marca_es_la_mayor_secuencia_de_la_jornada'),
  'Jornada sin comandos': servidor(BOOT_SRV, 'test_syn11_sin_comandos_la_marca_es_nula'),
  'Lote cortado por un error transitorio': servidor(BOOT_SRV, 'test_syn03_un_lote_cortado_en_la_9_deja_la_marca_en_8'),
  'Comandos de otra jornada o de otro teléfono': servidor(BOOT_SRV, 'test_inv21_no_mira_otra_jornada_ni_otro_dispositivo'),
  'Doble envío antes del bootstrap': servidor(BOOT_SRV, 'test_inv06_un_doble_envio_deja_la_marca_en_7_y_el_stock_una_vez'),
  // sync/cola-local
  'Segunda venta al mismo cliente': unit(DISPONIBLES, 'suma débitos y resta cobranzas'),
  'Stock después de vender': unit(DISPONIBLES, '63 botellas del bootstrap menos una venta de 15 = 48'),
  'Ventas de otra jornada': unit(DISPONIBLES, 'no cuenta las operaciones de otra jornada'),
  'Venta ya enviada': unit(APLICAR, '«Venta ya enviada»'),
  'Venta ya enviada, después de actualizar los datos': unit(DISPONIBLES, 'con la marca 7 y la venta en la secuencia 5 el bootstrap ya la incluye'),
  'Respuesta del lote perdida': unit(DISPONIBLES, 'respuesta perdida: la marca cubre la venta'),
  'Venta posterior a la foto': unit(DISPONIBLES, 'con la marca 7 y operaciones 7 y 8 cuenta solo la 8'),
  'Venta rechazada': unit(DISPONIBLES, 'una venta rechazada sigue descontando aunque la marca la cubra'),
  'Bootstrap sin secuencia procesada': unit(DISPONIBLES, 'sin marca (bootstrap anterior al 22c) cuenta todo'),
  'Doble sincronización': unit(DISPONIBLES, 'doble sincronización: aplicar la misma conciliación dos veces'),
  'El bootstrap no toca los movimientos': unit(BOOTSTRAP, 'un bootstrap nuevo reemplaza la marca y deja iguales movimientos'),
  // sync/lote-de-comandos
  'Un rechazo no detiene el lote': servidor(LOTE_SRV, 'test_el_segundo_se_rechaza_y_el_tercero_se_procesa'),
  'Cada resultado se identifica por su comando': servidor(LOTE_SRV, 'test_cada_resultado_se_identifica_por_su_operation_id'),
  'Venta sin conexión con observaciones': servidor(OBS_SRV, 'test_syn07_una_venta_con_stock_negativo_y_medio_inactivo'),
  'Resultado sin observaciones': servidor(OBS_SRV, 'test_syn04_aceptada_sin_observaciones_y_rechazada'),
  'Reenvío de un comando con observaciones': servidor(OBS_SRV, 'test_syn02_el_reenvio_devuelve_las_mismas_observaciones'),
  'Cada regla por separado': servidor(INV17_SRV, 'test_inv17_una_venta_sin_conexion_que_incumple_una_regla_se_acepta'),
  'Todas a la vez': servidor(INV17_SRV, 'test_inv17_una_venta_que_incumple_todas_las_reglas_a_la_vez_se_acepta_con_todas'),
  'Cobranza sin conexión': servidor(INV17_SRV, 'test_inv17_la_cobranza_con_consumidor_final_medio_desactivado_y_sin_permiso'),
  'Un comando malformado sí se rechaza': servidor(INV17_SRV, 'test_syn06_un_comando_malformado_si_se_rechaza_con_totales_inconsistentes'),
  'Doble envío de una venta observada': servidor(INV17_SRV, 'test_inv06_el_doble_envio_de_una_venta_observada_baja_el_stock_una_sola_vez'),
  // sync/motor-de-sincronizacion
  'Venta aceptada': unit(APLICAR, 'por operation_id (no por posición)'),
  'Venta con observaciones': unit(APLICAR, '«Venta con observaciones»'),
  'Corte a mitad del lote': unit(CICLO, 'un ítem ERROR_TRANSITORIO en la respuesta aplica lo demás, corta'),
  'Falla al escribir los resultados': unit(APLICAR, '«Falla al escribir los resultados»'),
  'Respuesta sin observaciones': unit(APLICAR, '«Respuesta sin observaciones»'),
}

// `Venta rechazada` está en dos specs (cola-local y motor): el nombre vale para ambas y cada una
// tiene su propia prueba.
const EXTRAS: Record<string, Destino> = {
  'Venta rechazada (motor)': unit(APLICAR, 'un rechazo conserva su código y no inventa observaciones'),
}

function escenariosDeLasSpecs(): string[] {
  const nombres = new Set<string>()
  const recorrer = (dir: string): void => {
    for (const entrada of readdirSync(dir)) {
      const ruta = resolve(dir, entrada)
      if (entrada.endsWith('.md')) {
        for (const linea of readFileSync(ruta, 'utf-8').split(/\r?\n/)) {
          const m = /^#### Scenario: (.+)$/.exec(linea)
          if (m?.[1] !== undefined) nombres.add(m[1].trim())
        }
      } else if (!entrada.includes('.')) recorrer(ruta)
    }
  }
  recorrer(SPECS)
  return [...nombres].sort()
}

describe('trazabilidad de las specs delta del 22c (tarea 14.1; INV-17, INV-01, INV-06)', () => {
  it.each(Object.entries({ ...MAPA, ...EXTRAS }))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las siete specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(55)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('INV-17, INV-01 e INV-06 los cita alguna prueba por su ID (04 §2.1 puntos 2 y 3)', () => {
    const texto = (ruta: string): string => readFileSync(ruta, 'utf-8')
    expect(texto(resolve(BACKEND, INV17_SRV))).toContain('INV-17')
    expect(texto(resolve(UNIT, APLICAR))).toContain('INV-01')
    expect(texto(resolve(BACKEND, BOOT_SRV))).toContain('INV-06')
    expect(texto(resolve(UNIT, 'areas/ruta/FlujoConciliacion.test.tsx'))).toContain('INV-06')
  })
})
