import { baseLocal } from '../lib/dispositivo/db'
import { conCandadoSiLibre } from '../lib/locks'
import { aplicarResultados } from './aplicarResultados'
import { enviarLote } from './clienteLote'
import {
  debeEsperar,
  ESPERA_INICIAL,
  registrarFallo,
  reiniciarEspera,
  type EstadoDeEspera,
} from './espera'
import { partirEnLotes, seleccionarCola } from './seleccionDeCola'
import { actualizarVersionMinima } from './versionMinima'

/**
 * Ciclo de sincronización del teléfono (change 22b, `design.md` D1, D2, D3, D5, D6; SYN-03,
 * SYN-04, `02` §6.4, §13.3). Una sola sincronización a la vez: Web Lock `distribuidora:sync` con
 * `ifAvailable` (si otra pestaña lo tiene, esta no espera). Si un disparador llega con la propia
 * pestaña sincronizando, solo se anota «repetir al terminar»: una marca, no un contador, así que
 * a lo sumo hay UNA vuelta más.
 *
 * El estado vive en `meta` para que lo vean todas las pestañas: `ultima_sincronizacion` (ISO del
 * último ciclo sin cortes) y `ultimo_error_sync` (JSON con tipo, código y momento). La espera
 * exponencial vive en memoria de la pestaña.
 */
export const NOMBRE_DEL_CANDADO = 'distribuidora:sync'
export const CLAVE_ULTIMA_SINCRONIZACION = 'ultima_sincronizacion'
export const CLAVE_ULTIMO_ERROR_SYNC = 'ultimo_error_sync'

export type OrigenDeSincronizacion = 'arranque' | 'manual' | 'online' | 'primer_plano' | 'venta' | 'periodico'

/** Los que prueban en el momento y vuelven la espera a cero (D5, D6 = B). */
const ORIGENES_QUE_REINICIAN_LA_ESPERA: ReadonlySet<OrigenDeSincronizacion> = new Set([
  'manual',
  'online',
  'primer_plano',
])

export interface EntradaDeSincronizacion {
  usuarioId: string
  dispositivoId: string
  origen: OrigenDeSincronizacion
}

export type ResultadoDeSincronizacion =
  | { tipo: 'completa'; enviadas: number }
  | { tipo: 'transitorio' }
  | { tipo: 'sesion_vencida' }
  | { tipo: 'error_pedido'; estado: number; codigo: string }
  | { tipo: 'otra_pestana' }
  | { tipo: 'en_espera' }
  | { tipo: 'repetira' }

export type TipoDeErrorDeSincronizacion = 'transitorio' | 'sesion_vencida' | 'error_pedido'

export interface ErrorDeSincronizacion {
  tipo: TipoDeErrorDeSincronizacion
  codigo: string | null
  en: string
}

type ResultadoDelCiclo = Exclude<ResultadoDeSincronizacion, { tipo: 'otra_pestana' | 'en_espera' | 'repetira' }>

export interface DependenciasDelSincronizador {
  ahora?: () => Date
  azar?: () => number
}

export interface Sincronizador {
  sincronizar: (entrada: EntradaDeSincronizacion) => Promise<ResultadoDeSincronizacion>
  /** Vuelve la espera exponencial a cero (la usan «Sincronizar», `online` y primer plano). */
  reiniciarEspera: () => void
  estadoDeEspera: () => EstadoDeEspera
}

export function crearSincronizador(dependencias: DependenciasDelSincronizador = {}): Sincronizador {
  const ahora = dependencias.ahora ?? (() => new Date())
  const azar = dependencias.azar ?? Math.random
  let espera: EstadoDeEspera = ESPERA_INICIAL
  let enCurso = false
  let repetir = false

  async function guardarError(tipo: TipoDeErrorDeSincronizacion, codigo: string | null): Promise<void> {
    const error: ErrorDeSincronizacion = { tipo, codigo, en: ahora().toISOString() }
    await baseLocal.meta.put({ clave: CLAVE_ULTIMO_ERROR_SYNC, valor: JSON.stringify(error) })
  }

  async function unaVuelta(entrada: EntradaDeSincronizacion): Promise<ResultadoDelCiclo> {
    const lotes = partirEnLotes(await seleccionarCola(entrada.usuarioId, entrada.dispositivoId))
    let enviadas = 0
    for (const lote of lotes) {
      const respuesta = await enviarLote(lote)
      if (respuesta.tipo === 'ok') {
        await aplicarResultados(respuesta.resultados, ahora())
        enviadas += respuesta.resultados.filter((r) => r.estado !== 'ERROR_TRANSITORIO').length
        // Un ítem sin resultado quedó sin procesar: también corta (sigue PENDIENTE).
        if (respuesta.corte || respuesta.resultados.length < lote.length) {
          espera = registrarFallo(espera, ahora().getTime(), azar)
          await guardarError('transitorio', null)
          return { tipo: 'transitorio' }
        }
        continue
      }
      if (respuesta.tipo === 'transitorio') {
        espera = registrarFallo(espera, ahora().getTime(), azar)
        await guardarError('transitorio', null)
        return { tipo: 'transitorio' }
      }
      if (respuesta.tipo === 'sesion_vencida') {
        await guardarError('sesion_vencida', null)
        return { tipo: 'sesion_vencida' }
      }
      await guardarError('error_pedido', respuesta.codigo)
      return respuesta
    }
    espera = reiniciarEspera()
    await baseLocal.meta.bulkDelete([CLAVE_ULTIMO_ERROR_SYNC])
    await baseLocal.meta.put({ clave: CLAVE_ULTIMA_SINCRONIZACION, valor: ahora().toISOString() })
    return { tipo: 'completa', enviadas }
  }

  async function ciclo(entrada: EntradaDeSincronizacion): Promise<ResultadoDelCiclo> {
    let total = 0
    let resultado: ResultadoDelCiclo
    // D7: al empezar cada ciclo se pide la mínima (sin señal vale la última); la cola se envía igual.
    await actualizarVersionMinima()
    do {
      repetir = false
      resultado = await unaVuelta(entrada)
      if (resultado.tipo === 'completa') total += resultado.enviadas
      // Una vuelta más solo si la anterior terminó sin corte: tras un error no se martilla.
    } while (repetir && resultado.tipo === 'completa')
    return resultado.tipo === 'completa' ? { tipo: 'completa', enviadas: total } : resultado
  }

  async function sincronizar(entrada: EntradaDeSincronizacion): Promise<ResultadoDeSincronizacion> {
    if (ORIGENES_QUE_REINICIAN_LA_ESPERA.has(entrada.origen)) espera = reiniciarEspera()

    if (enCurso) {
      repetir = true
      return { tipo: 'repetira' }
    }
    if (debeEsperar(espera, ahora().getTime())) return { tipo: 'en_espera' }

    enCurso = true
    try {
      const resultado = await conCandadoSiLibre(NOMBRE_DEL_CANDADO, () => ciclo(entrada))
      return resultado.obtenido ? resultado.valor : { tipo: 'otra_pestana' }
    } finally {
      enCurso = false
      repetir = false
    }
  }

  return {
    sincronizar,
    reiniciarEspera: () => {
      espera = reiniciarEspera()
    },
    estadoDeEspera: () => espera,
  }
}

/** Sincronizador de la pestaña: lo comparten los disparadores y la pantalla (Lote 3). */
export const sincronizadorDeLaPestana = crearSincronizador()
