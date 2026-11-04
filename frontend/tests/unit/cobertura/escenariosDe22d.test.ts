import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Change 22d, tarea 19.1: trazabilidad de las specs delta. Cada escenario de las siete specs
 * (`ruta/area-de-ruta`, `sistema/ayuda-contextual`, `sync/base-local`, `sync/cola-local`,
 * `sync/lote-de-comandos`, `sync/motor-de-sincronizacion`, `ventas/anulacion-de-venta`) se asocia
 * con la prueba que lo ejercita (archivo y fragmento de su título); los del servidor apuntan a su
 * archivo de `backend/tests`. Varios nombres se repiten entre specs («Doble envío», «Doble
 * sincronización», «Anulación rechazada»...), por eso la clave lleva la capacidad. Si una prueba se
 * renombra o se borra, esta falla y obliga a revisar la cobertura. Además comprueba que cada
 * escenario de las specs tiene su entrada acá (y ninguna sobra) y que INV-19, INV-01, INV-05,
 * INV-06 e INV-21 los cita alguna prueba por su ID (`04` §2.1 puntos 2 y 3).
 */
const UNIT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const RAIZ = resolve(UNIT, '..', '..', '..')
const BACKEND = resolve(RAIZ, 'backend', 'tests')
const SPECS = resolve(RAIZ, 'openspec', 'changes', 'archive', '2026-11-03-22d-anulacion-sin-conexion', 'specs')

type Destino = readonly [archivo: string, fragmento: string]

const unit = (archivo: string, fragmento: string): Destino => [resolve(UNIT, archivo), fragmento]
const servidor = (archivo: string, fragmento: string): Destino => [resolve(BACKEND, archivo), fragmento]

const ANULAR = 'areas/ruta/AnularVentaScreen.test.tsx'
const JORNADA = 'areas/ruta/JornadaNoAbierta.test.tsx'
const GUARDADA = 'areas/ruta/ventas/VentaGuardadaScreen.test.tsx'
const DE_HOY = 'areas/ruta/ventas/VentasDeHoyScreen.test.tsx'
const PANTALLA = 'areas/ruta/SincronizacionScreen.test.tsx'
const NOTA = 'domain/ventas/notaDesdeLocal.test.ts'
const AYUDA = 'ayuda/textosRuta.test.ts'
const DB = 'lib/dispositivo/db.test.ts'
const BOOTSTRAP = 'sync/aplicarBootstrap.test.ts'
const ANULAR_LOCAL = 'sync/anularVentaLocal.test.ts'
const DISPONIBLES = 'domain/ruta/disponiblesLocales.test.ts'
const APLICAR = 'sync/aplicarResultados.test.ts'
const CICLO = 'sync/sincronizar.test.ts'
const ESTADO = 'sync/estadoDeJornada.test.ts'
const PENDIENTES = 'areas/ruta/SincronizacionScreen.test.tsx'

const OFFLINE = 'integration/test_venta_anular_offline.py'
const REGLAS = 'integration/test_venta_anular_offline_reglas.py'
const EFECTOS = 'integration/test_venta_anular_offline_efectos.py'
const REST = 'integration/test_venta_anular_offline_rest.py'
const CONCURRENCIA = 'concurrency/test_venta_anular_offline_concurrencia.py'

const MAPA: Record<string, Destino> = {
  // ruta/area-de-ruta
  'ruta/area-de-ruta: Anular sin señal': unit(ANULAR, 'anular sin señal: motivo, confirmación «¿Anular la venta …?»'),
  'ruta/area-de-ruta: Sin el permiso': unit(ANULAR, 'sin ANULAR_VENTA no se ofrece (SEG-06)'),
  'ruta/area-de-ruta: Venta rechazada': unit(ANULAR, 'una venta rechazada no se ofrece'),
  'ruta/area-de-ruta: Venta de otra jornada': unit(ANULAR, 'una venta de una jornada anterior guardada en el teléfono no se ofrece'),
  'ruta/area-de-ruta: Venta con cobro en el acto': unit(ANULAR, 'una venta con cobro en el acto exige elegir si se devuelve'),
  'ruta/area-de-ruta: Consumidor final': unit(ANULAR, 'al consumidor final la devolución figura elegida y no se puede cambiar'),
  'ruta/area-de-ruta: Sin motivo': unit(ANULAR, 'sin motivo no se confirma y se indica qué falta'),
  'ruta/area-de-ruta: Doble toque': unit(ANULAR, 'doble toque en «Confirmar anulación»: una sola anulación y un solo comando'),
  'ruta/area-de-ruta: Ventas de hoy': unit(DE_HOY, 'tres ventas, una anulada: ve las tres y solo la anulada lleva «Anulada»'),
  'ruta/area-de-ruta: Anulación rechazada en Sincronización': unit(PANTALLA, 'una anulación rechazada con VENTA_YA_ANULADA se lista como «Anulación de {número}»'),
  'ruta/area-de-ruta: Anulación con observaciones': unit(PANTALLA, 'una anulación con observaciones muestra la primera traducida'),
  'ruta/area-de-ruta: Pendientes': unit(PENDIENTES, 'dos ventas y una anulación sin enviar: «2 ventas y 1 anulación sin enviar»'),
  'ruta/area-de-ruta: Nota de una venta anulada': unit(NOTA, 'con la anulación pasa estado ANULADA y sus datos'),
  'ruta/area-de-ruta: Doble sincronización': unit(GUARDADA, 'escribir dos veces el mismo resultado muestra lo mismo'),
  'ruta/area-de-ruta: Jornada liberada': unit(JORNADA, '«%s», que lo vendido se sigue enviando y deshabilita «Vender» (RUT-09)'),
  'ruta/area-de-ruta: Carrito abierto': unit(JORNADA, 'con el carrito abierto, si el teléfono se entera «Confirmar venta» no confirma'),
  'ruta/area-de-ruta: Jornada en rendición': unit(JORNADA, 'el aviso nombra el estado: en rendición'),
  'ruta/area-de-ruta: Sigue sin señal': unit(JORNADA, 'sigue igual sin señal y después de recargar la aplicación (RUT-09)'),
  'ruta/area-de-ruta: Sin dato guardado': unit(JORNADA, 'sin dato guardado «Vender» sigue disponible y no hay aviso (SYN-05)'),
  'ruta/area-de-ruta: Anular con la jornada liberada': unit(ANULAR, 'con la jornada liberada tampoco muestra el formulario (RUT-09)'),
  // sistema/ayuda-contextual
  'sistema/ayuda-contextual: Anular venta': unit(AYUDA, 'ruta.anularVenta: deja sin efecto una venta de la jornada'),
  'sistema/ayuda-contextual: Anulación rechazada': unit(AYUDA, 'ruta.anulacionRechazada: el motivo está en el detalle'),
  'sistema/ayuda-contextual: Jornada no abierta': unit(AYUDA, 'ruta.jornadaNoAbierta: no se puede vender ni anular'),
  'sistema/ayuda-contextual: Stock y crédito': unit(AYUDA, 'el stock y el crédito nombran lo anulado además de lo vendido'),
  'sistema/ayuda-contextual: Trazabilidad': unit('ayuda/trazabilidad.test.ts', 'cada clave de <Ayuda clave> y de ayuda= existe en AYUDAS'),
  // sync/base-local
  'sync/base-local: Actualización de la base con ventas guardadas': unit(DB, 'una base v3 con sesión, PIN, datos y dos ventas con su cola abre en v5'),
  'sync/base-local: Bootstrap con una anulación sin enviar': unit(BOOTSTRAP, 'un bootstrap con una anulación sin enviar la deja con sus movimientos y su comando'),
  'sync/base-local: Anulación rechazada': unit(BOOTSTRAP, 'cerrar la sesión local no borra una anulación rechazada (SYN-09)'),
  // sync/cola-local
  'sync/cola-local: Anulación local': unit(ANULAR_LOCAL, 'escribe anulación, ingreso de la mercadería, crédito del total y el comando VENTA_ANULAR OFFLINE'),
  'sync/cola-local: Falla a mitad de la anulación': unit(ANULAR_LOCAL, 'falla a mitad: no queda anulación, movimiento ni comando'),
  'sync/cola-local: Doble toque': unit(ANULAR_LOCAL, 'reconfirmar la misma venta devuelve la anulación existente'),
  'sync/cola-local: Anulación de una venta sin enviar': unit(ANULAR_LOCAL, 'la anulación de una venta «Sin enviar» queda detrás de ella'),
  'sync/cola-local: Stock después de anular': unit(DISPONIBLES, 'stock: 63 tras vender 15 y anular'),
  'sync/cola-local: Crédito después de anular con devolución': unit(DISPONIBLES, 'crédito con devolución: límite 200.000, saldo 100.000'),
  'sync/cola-local: Crédito después de anular sin devolución': unit(DISPONIBLES, 'crédito sin devolución: saldo 80.000'),
  'sync/cola-local: Venta incluida en el bootstrap y anulación pendiente': unit(DISPONIBLES, 'venta incluida en el bootstrap (marca 7, 48 botellas) y anulación pendiente'),
  'sync/cola-local: Anulación incluida en el bootstrap': unit(DISPONIBLES, 'anulación incluida en el bootstrap (marca 8, 63 botellas): 63 y no 78'),
  'sync/cola-local: Anulación rechazada': unit(DISPONIBLES, 'anulación rechazada: no cuenta'),
  'sync/cola-local: Venta y anulación rechazadas': unit(DISPONIBLES, 'venta y anulación rechazadas: cuentan las dos y se compensan'),
  'sync/cola-local: Doble sincronización': unit(DISPONIBLES, 'doble sincronización: el mismo resultado dos veces no cambia el saldo ni el stock'),
  // sync/lote-de-comandos
  'sync/lote-de-comandos: Anulación sin conexión por el lote': servidor(OFFLINE, 'test_vta24_una_anulacion_sin_conexion_de_la_jornada_se_acepta_por_el_lote'),
  'sync/lote-de-comandos: Por REST sigue siendo con conexión': servidor(REST, 'test_vta24_por_rest_la_anulacion_sigue_siendo_online'),
  'sync/lote-de-comandos: Sin jornada': servidor(OFFLINE, 'test_syn10_la_anulacion_sin_jornada_en_el_sobre_se_rechaza_con_jornada_requerida'),
  'sync/lote-de-comandos: Jornada de otro teléfono': servidor(OFFLINE, 'test_syn10_la_jornada_de_otro_usuario_se_rechaza_con_jornada_ajena'),
  'sync/lote-de-comandos: Un rechazo no corta el lote': servidor(OFFLINE, 'test_syn04_un_rechazo_no_corta_el_lote'),
  'sync/lote-de-comandos: Doble envío': servidor(OFFLINE, 'test_inv06_el_doble_envio_devuelve_el_resultado_original_sin_efectos_nuevos'),
  // sync/motor-de-sincronizacion
  'sync/motor-de-sincronizacion: Anulación aceptada': unit(APLICAR, 'aceptada: la anulación y su comando quedan «Enviada»'),
  'sync/motor-de-sincronizacion: Anulación con observaciones': unit(APLICAR, 'con observaciones: la anulación queda «Con observaciones»'),
  'sync/motor-de-sincronizacion: Anulación rechazada': unit(APLICAR, 'una anulación rechazada deja de contar y la venta sigue descontando'),
  'sync/motor-de-sincronizacion: Falla al escribir los resultados': unit(APLICAR, 'falla a mitad de la respuesta: ni la venta ni su anulación cambian'),
  'sync/motor-de-sincronizacion: Doble envío': unit(APLICAR, 'doble envío: el mismo resultado otra vez no cambia la anulación ni su comando'),
  'sync/motor-de-sincronizacion: Jornada liberada durante el día': unit(ESTADO, "se guarda con la jornada y el momento"),
  'sync/motor-de-sincronizacion: Actualizar datos sin jornada': unit(ESTADO, 'JORNADA_REQUERIDA de «Actualizar datos» guarda «desconocido»'),
  'sync/motor-de-sincronizacion: Resultado con jornada liberada': unit(ESTADO, 'guarda LIBERADA para la jornada del comando'),
  'sync/motor-de-sincronizacion: Sin señal': unit(ESTADO, 'sin red, 403, 404, 500 o respuesta ilegible no cambian nada'),
  'sync/motor-de-sincronizacion: Lo vendido se sigue enviando': unit(CICLO, 'con la jornada liberada la guarda y las dos ventas sin enviar se envían igual'),
  'sync/motor-de-sincronizacion: Jornada nueva': unit(ESTADO, 'al abrir la jornada J2 y aplicar su bootstrap, el teléfono ya no la considera no abierta'),
  'sync/motor-de-sincronizacion: Doble consulta': unit(CICLO, 'doble consulta con LIBERADA no cambia lo guardado'),
  // ventas/anulacion-de-venta
  'ventas/anulacion-de-venta: Anulación sin conexión de una venta de la jornada': servidor(OFFLINE, 'test_vta24_una_anulacion_sin_conexion_de_la_jornada_se_acepta_por_el_lote'),
  'ventas/anulacion-de-venta: La venta y su anulación en el mismo lote': servidor(OFFLINE, 'test_syn03_la_venta_y_su_anulacion_en_el_mismo_lote_se_procesan_en_orden'),
  'ventas/anulacion-de-venta: Venta de otra jornada': servidor(OFFLINE, 'test_vta24_la_venta_de_otra_jornada_se_rechaza_con_jornada_ajena'),
  'ventas/anulacion-de-venta: Venta inexistente': servidor(OFFLINE, 'test_syn06_la_venta_rechazada_antes_es_venta_inexistente'),
  'ventas/anulacion-de-venta: Venta de otra organización': servidor(OFFLINE, 'test_inv21_la_venta_de_otra_organizacion_es_venta_inexistente_y_no_se_toca'),
  'ventas/anulacion-de-venta: Doble envío': servidor(OFFLINE, 'test_inv06_el_doble_envio_devuelve_el_resultado_original_sin_efectos_nuevos'),
  'ventas/anulacion-de-venta: Venta ya anulada desde administración': servidor(REGLAS, 'test_vta20_la_venta_ya_anulada_desde_administracion_se_rechaza_y_queda_una_sola_anulacion'),
  'ventas/anulacion-de-venta: Motivo dado de baja después del bootstrap': servidor(REGLAS, 'test_vta24_motivo_dado_de_baja_despues_del_bootstrap_se_acepta_sin_observacion'),
  'ventas/anulacion-de-venta: Motivo de otro ámbito': servidor(REGLAS, 'test_vta24_el_motivo_de_otro_ambito_se_rechaza_con_motivo_invalido'),
  'ventas/anulacion-de-venta: Devolución que no corresponde': servidor(REGLAS, 'test_vta22_devolver_dinero_de_una_venta_sin_cobranza_es_devolucion_invalida'),
  'ventas/anulacion-de-venta: Permiso revocado': servidor(REGLAS, 'test_syn10_el_permiso_revocado_se_acepta_con_permiso_revocado_sobre_la_venta'),
  'ventas/anulacion-de-venta: Jornada liberada': servidor(REGLAS, 'test_rut09_la_jornada_liberada_se_acepta_con_jornada_liberada_sobre_la_venta'),
  'ventas/anulacion-de-venta: Camioneta tomada por otro vendedor al sincronizar': servidor(REGLAS, 'test_stk09_la_camioneta_tomada_por_otro_vendedor_se_acepta_con_dos_observaciones'),
  'ventas/anulacion-de-venta: Ubicación inactiva': servidor(REGLAS, 'test_stk02_la_ubicacion_inactiva_se_rechaza_con_ubicacion_inactiva'),
  'ventas/anulacion-de-venta: Reenvío de una anulación con observaciones': servidor(REGLAS, 'test_inv06_el_reenvio_de_una_anulacion_con_observaciones_no_registra_otra'),
  'ventas/anulacion-de-venta: Anulación con la jornada abierta': servidor(EFECTOS, 'test_inv19_con_la_jornada_abierta_la_anulacion_y_el_reingreso_llevan_la_jornada_del_sobre'),
  'ventas/anulacion-de-venta: Anulación con devolución': servidor(EFECTOS, 'test_inv19_con_devolucion_el_stock_y_el_saldo_quedan_como_antes_de_la_venta'),
  'ventas/anulacion-de-venta: Anulación sin devolución': servidor(EFECTOS, 'test_inv19_sin_devolucion_el_saldo_difiere_solo_en_lo_cobrado_a_favor_del_cliente'),
  'ventas/anulacion-de-venta: Anulación sin conexión contra una anulación con conexión': servidor(
    CONCURRENCIA,
    'test_inv06_en_carrera_libre_una_se_acepta_y_la_otra_responde_venta_ya_anulada',
  ),
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
  recorrer(SPECS, '')
  return [...nombres].sort()
}

describe('trazabilidad de las specs delta del 22d (tarea 19.1; INV-19, INV-01, INV-05, INV-06, INV-21)', () => {
  it.each(Object.entries(MAPA))('%s tiene una prueba que lo ejercita', (_nombre, [archivo, fragmento]) => {
    expect(existsSync(archivo), `falta ${archivo}`).toBe(true)
    expect(readFileSync(archivo, 'utf-8')).toContain(fragmento)
  })

  it('cada escenario de las siete specs está en el mapa y el mapa no tiene escenarios inexistentes', () => {
    const reales = escenariosDeLasSpecs()
    expect(reales.length).toBeGreaterThan(75)
    expect(reales.filter((nombre) => !(nombre in MAPA))).toEqual([])
    expect(Object.keys(MAPA).filter((nombre) => !reales.includes(nombre))).toEqual([])
  })

  it('INV-19, INV-01, INV-05, INV-06 e INV-21 los cita alguna prueba por su ID (04 §2.1 puntos 2 y 3)', () => {
    const texto = (ruta: string): string => readFileSync(ruta, 'utf-8')
    expect(texto(resolve(BACKEND, EFECTOS))).toContain('INV-19')
    expect(texto(resolve(UNIT, ANULAR_LOCAL))).toContain('INV-01')
    expect(texto(resolve(UNIT, DB))).toContain('INV-05')
    expect(texto(resolve(UNIT, 'areas/ruta/FlujoAnulacionSinConexion.test.tsx'))).toContain('INV-06')
    expect(texto(resolve(BACKEND, CONCURRENCIA))).toContain('INV-06')
    expect(texto(resolve(BACKEND, OFFLINE))).toContain('INV-21')
  })
})
