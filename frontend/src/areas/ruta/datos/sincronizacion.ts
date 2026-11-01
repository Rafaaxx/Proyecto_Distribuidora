import { liveQuery } from 'dexie'
import { useEffect, useState, useSyncExternalStore } from 'react'

import { baseLocal, type VentaLocal } from '../../../lib/dispositivo/db'
import {
  estadoDeSincronizacion,
  suscribirEstadoDeSincronizacion,
  type EstadoDeSincronizacionDeLaPestana,
} from '../../../sync/disparadores'
import { APP_VERSION } from '../../../sync/appVersion'
import { CLAVE_ULTIMA_SINCRONIZACION, CLAVE_ULTIMO_ERROR_SYNC, type ErrorDeSincronizacion } from '../../../sync/sincronizar'
import { ventaBloqueadaPorVersion } from '../../../sync/versionMinima'
import { contarVentasSinEnviar } from '../../../sync/ventasPendientes'
import { leerUltimoError } from '../sincronizacion/presentacion'

/**
 * Lecturas del estado de la sincronización para las pantallas de `/ruta` (change 22b,
 * `design.md` D7, D8). Todo sale de Dexie con `liveQuery`: lo que escribe otra pestaña se ve acá
 * sin recargar.
 */
export interface ResumenDeSincronizacion {
  sinEnviar: number
  conObservaciones: number
  rechazadas: number
  ultimaSincronizacion: string | null
  ultimoError: ErrorDeSincronizacion | null
}

const RESUMEN_VACIO: ResumenDeSincronizacion = {
  sinEnviar: 0,
  conObservaciones: 0,
  rechazadas: 0,
  ultimaSincronizacion: null,
  ultimoError: null,
}

async function ventasDeLaJornada(): Promise<VentaLocal[]> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) return []
  return baseLocal.ventas.where('jornada_id').equals(sesion.jornada.id).toArray()
}

async function leerResumen(): Promise<ResumenDeSincronizacion> {
  const sesion = await baseLocal.sesion.get('actual')
  const [ventas, ultima, error] = await Promise.all([
    ventasDeLaJornada(),
    baseLocal.meta.get(CLAVE_ULTIMA_SINCRONIZACION),
    baseLocal.meta.get(CLAVE_ULTIMO_ERROR_SYNC),
  ])
  return {
    sinEnviar: sesion === undefined ? 0 : await contarVentasSinEnviar(sesion.usuario.id),
    conObservaciones: ventas.filter((v) => v.estado_envio === 'CON_OBSERVACIONES').length,
    rechazadas: ventas.filter((v) => v.estado_envio === 'RECHAZADA').length,
    ultimaSincronizacion: ultima?.valor ?? null,
    ultimoError: leerUltimoError(error?.valor),
  }
}

function useConsulta<T>(consulta: () => Promise<T>, inicial: T): T {
  const [valor, setValor] = useState<T>(inicial)
  useEffect(() => {
    const suscripcion = liveQuery(consulta).subscribe({ next: setValor, error: () => setValor(inicial) })
    return () => suscripcion.unsubscribe()
    // La consulta y el valor inicial son constantes del módulo que las llama.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return valor
}

export function useResumenDeSincronizacion(): ResumenDeSincronizacion {
  return useConsulta(leerResumen, RESUMEN_VACIO)
}

export interface VentaConProblema {
  venta: VentaLocal
  codigo: string | null
}

/** Ventas de la jornada que volvieron «Con observaciones» o «Rechazada», con el código del rechazo. */
export function useVentasConProblemas(): VentaConProblema[] {
  return useConsulta(async () => {
    const ventas = (await ventasDeLaJornada()).filter(
      (v) => v.estado_envio === 'CON_OBSERVACIONES' || v.estado_envio === 'RECHAZADA',
    )
    ventas.sort((a, b) => a.occurred_at.localeCompare(b.occurred_at) || a.numero.localeCompare(b.numero))
    return Promise.all(
      ventas.map(async (venta) => ({
        venta,
        codigo: (await baseLocal.cola.where('operation_id').equals(venta.operation_id).first())?.error_codigo ?? null,
      })),
    )
  }, [] as VentaConProblema[])
}

/** `true` si la aplicación está por debajo de la última versión mínima conocida (no se venden ventas nuevas). */
export function useVersionBloqueada(): boolean {
  return useConsulta(() => ventaBloqueadaPorVersion(APP_VERSION), false)
}

/** Estado de la sincronización de esta pestaña: enviando, otra pestaña, sin señal. */
export function useEstadoDeEnvio(): EstadoDeSincronizacionDeLaPestana {
  return useSyncExternalStore(suscribirEstadoDeSincronizacion, estadoDeSincronizacion)
}
