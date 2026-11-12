import { liveQuery } from 'dexie'

import { baseLocal } from '../lib/dispositivo/db'
import {
  CLAVE_ULTIMA_SINCRONIZACION,
  sincronizadorDeLaPestana,
  type OrigenDeSincronizacion,
  type ResultadoDeSincronizacion,
  type Sincronizador,
} from './sincronizar'

/**
 * Disparadores de la sincronización (change 22b, `design.md` D6 = B, D2, D5; `02` §13.3, SEG-03,
 * ADR-064). Existen SOLO mientras la sesión local está desbloqueada: `SesionRuta` los inicia al
 * quedar activa y los detiene al bloquearse o cerrar la sesión (con la sesión bloqueada o sin
 * usuario local no se sincroniza, así el motor siempre sabe de quién es la cola).
 *
 * Disparan: al empezar (desbloquear o terminar el login), el evento `online`, la vuelta a primer
 * plano (`visibilitychange` con la aplicación visible), cada 2 minutos, después de cada venta
 * confirmada si hay conexión y «Sincronizar». Todos pasan por el mismo sincronizador de la
 * pestaña (candado único y «repetir al terminar»); `online`, primer plano y «Sincronizar» vuelven
 * la espera exponencial a cero y envían en el momento, el resto respeta la espera vigente.
 *
 * Además guarda el estado de la sincronización de esta pestaña (`enviando`, `otra_pestana`,
 * `sin_senal`) para que la interfaz lo muestre.
 */
export const INTERVALO_PERIODICO_MS = 120_000

export type FaseDeSincronizacion = 'ocioso' | 'enviando' | 'otra_pestana' | 'sin_senal'

export interface EstadoDeSincronizacionDeLaPestana {
  fase: FaseDeSincronizacion
}

export type ResultadoDeSincronizarAPedido = ResultadoDeSincronizacion | { tipo: 'sin_sesion' } | { tipo: 'sin_senal' }

export interface OpcionesDeDisparadores {
  usuarioId: string
  dispositivoId: string
  sincronizador?: Sincronizador
  intervaloMs?: number
}

export interface Disparadores {
  detener: () => void
}

interface Activo {
  usuarioId: string
  dispositivoId: string
  sincronizador: Sincronizador
}

let activo: Activo | null = null
let estado: EstadoDeSincronizacionDeLaPestana = { fase: 'ocioso' }
const oyentes = new Set<() => void>()

function fijarFase(fase: FaseDeSincronizacion): void {
  if (estado.fase === fase) return
  estado = { fase }
  oyentes.forEach((oyente) => oyente())
}

export function estadoDeSincronizacion(): EstadoDeSincronizacionDeLaPestana {
  return estado
}

export function suscribirEstadoDeSincronizacion(oyente: () => void): () => void {
  oyentes.add(oyente)
  return () => {
    oyentes.delete(oyente)
  }
}

async function ejecutar(origen: OrigenDeSincronizacion): Promise<ResultadoDeSincronizacion | null> {
  const propio = activo
  if (propio === null) return null
  fijarFase('enviando')
  const resultado = await propio.sincronizador.sincronizar({
    usuarioId: propio.usuarioId,
    dispositivoId: propio.dispositivoId,
    origen,
  })
  // «repetira»: esta pestaña ya está enviando; quien lleva el ciclo cierra el estado.
  if (resultado.tipo === 'repetira') return resultado
  if (activo === propio) fijarFase(resultado.tipo === 'otra_pestana' ? 'otra_pestana' : 'ocioso')
  return resultado
}

export function iniciarDisparadores(opciones: OpcionesDeDisparadores): Disparadores {
  const propio: Activo = {
    usuarioId: opciones.usuarioId,
    dispositivoId: opciones.dispositivoId,
    sincronizador: opciones.sincronizador ?? sincronizadorDeLaPestana,
  }
  activo = propio

  const alVolverLaSenal = () => void ejecutar('online')
  const alCambiarLaVisibilidad = () => {
    if (document.visibilityState === 'visible') void ejecutar('primer_plano')
  }
  window.addEventListener('online', alVolverLaSenal)
  document.addEventListener('visibilitychange', alCambiarLaVisibilidad)
  const temporizador = setInterval(() => void ejecutar('periodico'), opciones.intervaloMs ?? INTERVALO_PERIODICO_MS)

  // «Sincronizando en otra pestaña» se apaga cuando esa pestaña termina y escribe su éxito.
  // La primera lectura es el valor de partida, no un cambio.
  let primera = true
  let anterior: string | undefined
  const suscripcion = liveQuery(() => baseLocal.meta.get(CLAVE_ULTIMA_SINCRONIZACION)).subscribe({
    next: (fila) => {
      const cambio = !primera && fila?.valor !== anterior
      primera = false
      anterior = fila?.valor
      if (cambio && estado.fase === 'otra_pestana') fijarFase('ocioso')
    },
    error: () => undefined,
  })

  void ejecutar('arranque')

  return {
    detener: () => {
      window.removeEventListener('online', alVolverLaSenal)
      document.removeEventListener('visibilitychange', alCambiarLaVisibilidad)
      clearInterval(temporizador)
      suscripcion.unsubscribe()
      if (activo === propio) {
        activo = null
        fijarFase('ocioso')
      }
    },
  }
}

/** Después de confirmar una venta: sincroniza si hay conexión (respeta la espera vigente). */
export function dispararTrasVenta(): void {
  if (activo === null || !navigator.onLine) return
  void ejecutar('venta')
}

/** «Sincronizar»: prueba en el momento. Sin conexión informa y no toca la última sincronización. */
export async function sincronizarAPedido(): Promise<ResultadoDeSincronizarAPedido> {
  if (activo === null) return { tipo: 'sin_sesion' }
  if (!navigator.onLine) {
    fijarFase('sin_senal')
    return { tipo: 'sin_senal' }
  }
  return (await ejecutar('manual')) ?? { tipo: 'sin_sesion' }
}
