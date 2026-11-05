import { liveQuery } from 'dexie'
import { useEffect, useState, useSyncExternalStore } from 'react'

import {
  explicarEnvio,
  TIPO_DE_ENTREGA,
  type ExplicacionDeEnvio,
  type NombresLocales,
} from '../../../domain/ruta/textosDeSincronizacion'
import {
  baseLocal,
  type AnulacionLocal,
  type CobranzaLocal,
  type EstadoDeComando,
  type EstadoDeEnvio,
  type VentaLocal,
} from '../../../lib/dispositivo/db'
import {
  estadoDeSincronizacion,
  suscribirEstadoDeSincronizacion,
  type EstadoDeSincronizacionDeLaPestana,
} from '../../../sync/disparadores'
import { APP_VERSION } from '../../../sync/appVersion'
import { CLAVE_ULTIMA_SINCRONIZACION, CLAVE_ULTIMO_ERROR_SYNC, type ErrorDeSincronizacion } from '../../../sync/sincronizar'
import { ventaBloqueadaPorVersion } from '../../../sync/versionMinima'
import { contarPendientes } from '../../../sync/ventasPendientes'
import { leerUltimoError } from '../sincronizacion/presentacion'

/**
 * Lecturas del estado de la sincronización para las pantallas de `/ruta` (change 22b,
 * `design.md` D7, D8). Todo sale de Dexie con `liveQuery`: lo que escribe otra pestaña se ve acá
 * sin recargar.
 */
export interface ResumenDeSincronizacion {
  /** Ventas sin enviar (change 22d: las anulaciones se cuentan aparte). */
  sinEnviar: number
  anulacionesSinEnviar: number
  /** Change 23: cobranzas independientes sin enviar. */
  cobranzasSinEnviar: number
  conObservaciones: number
  rechazadas: number
  ultimaSincronizacion: string | null
  ultimoError: ErrorDeSincronizacion | null
}

const RESUMEN_VACIO: ResumenDeSincronizacion = {
  sinEnviar: 0,
  anulacionesSinEnviar: 0,
  cobranzasSinEnviar: 0,
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

async function anulacionesDeLaJornada(): Promise<AnulacionLocal[]> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) return []
  return baseLocal.anulaciones.where('jornada_id').equals(sesion.jornada.id).toArray()
}

/** Las cobranzas independientes de la jornada de la sesión (las filas sin `origen` son cobros de una venta). */
export async function cobranzasDeLaJornada(): Promise<CobranzaLocal[]> {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) return []
  const filas = await baseLocal.cobranzas.where('jornada_id').equals(sesion.jornada.id).toArray()
  return filas.filter((c) => c.origen === 'INDEPENDIENTE')
}

async function leerResumen(): Promise<ResumenDeSincronizacion> {
  const sesion = await baseLocal.sesion.get('actual')
  const [ventas, anulaciones, cobranzas, ultima, error] = await Promise.all([
    ventasDeLaJornada(),
    anulacionesDeLaJornada(),
    cobranzasDeLaJornada(),
    baseLocal.meta.get(CLAVE_ULTIMA_SINCRONIZACION),
    baseLocal.meta.get(CLAVE_ULTIMO_ERROR_SYNC),
  ])
  const pendientes = sesion === undefined ? { ventas: 0, anulaciones: 0, cobranzas: 0 } : await contarPendientes(sesion.usuario.id)
  const conEstado = (estado: EstadoDeEnvio) =>
    ventas.filter((v) => v.estado_envio === estado).length +
    anulaciones.filter((a) => a.estado_envio === estado).length +
    cobranzas.filter((c) => c.estado_envio === estado).length
  return {
    sinEnviar: pendientes.ventas,
    anulacionesSinEnviar: pendientes.anulaciones,
    cobranzasSinEnviar: pendientes.cobranzas,
    conObservaciones: conEstado('CON_OBSERVACIONES'),
    rechazadas: conEstado('RECHAZADA'),
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

/** Los nombres que la base local todavía conoce, para armar los textos de las observaciones (22c, D5). */
async function leerNombresLocales(): Promise<NombresLocales> {
  const [productos, catalogoDeMedios, autorizadores] = await Promise.all([
    baseLocal.productos.toArray(),
    baseLocal.catalogos.get('medios_pago'),
    baseLocal.autorizadores.toArray(),
  ])
  return {
    productos: new Map(productos.map((p) => [p.id, p.nombre])),
    medios: new Map(catalogoDeMedios?.clave === 'medios_pago' ? catalogoDeMedios.items.map((m) => [m.id, m.nombre]) : []),
    autorizadores: new Map(autorizadores.map((a) => [a.id, a.nombre])),
  }
}

/** Lo que explica el estado de envío de una venta, leído de la fila de `cola` de su operación. */
async function leerExplicacion(
  operationId: string,
  estado: EstadoDeEnvio,
  nombres: NombresLocales,
): Promise<ExplicacionDeEnvio | null> {
  const comando = await baseLocal.cola.where('operation_id').equals(operationId).first()
  return explicarEnvio(estado, comando, nombres, comando?.sobre.tipo)
}

export interface VentaConProblema {
  venta: VentaLocal
  codigo: string | null
  explicacion: ExplicacionDeEnvio | null
}

/** Ventas de la jornada que volvieron «Con observaciones» o «Rechazada», con su explicación traducida. */
export function useVentasConProblemas(): VentaConProblema[] {
  return useConsulta(async () => {
    const ventas = (await ventasDeLaJornada()).filter(
      (v) => v.estado_envio === 'CON_OBSERVACIONES' || v.estado_envio === 'RECHAZADA',
    )
    ventas.sort((a, b) => a.occurred_at.localeCompare(b.occurred_at) || a.numero.localeCompare(b.numero))
    const nombres = await leerNombresLocales()
    return Promise.all(
      ventas.map(async (venta) => {
        const explicacion = await leerExplicacion(venta.operation_id, venta.estado_envio, nombres)
        return { venta, codigo: explicacion?.tipo === 'rechazo' ? explicacion.codigo : null, explicacion }
      }),
    )
  }, [] as VentaConProblema[])
}

export interface AnulacionConProblema {
  anulacion: AnulacionLocal
  /** La venta anulada (para el número y el cliente); `undefined` si ya no está en el teléfono. */
  venta: VentaLocal | undefined
  codigo: string | null
  explicacion: ExplicacionDeEnvio | null
}

/** Anulaciones de la jornada «Con observaciones» o «Rechazadas», con su explicación traducida (22d, D10). */
export function useAnulacionesConProblemas(): AnulacionConProblema[] {
  return useConsulta(async () => {
    const anulaciones = (await anulacionesDeLaJornada()).filter(
      (a) => a.estado_envio === 'CON_OBSERVACIONES' || a.estado_envio === 'RECHAZADA',
    )
    anulaciones.sort((a, b) => a.occurred_at.localeCompare(b.occurred_at))
    const nombres = await leerNombresLocales()
    return Promise.all(
      anulaciones.map(async (anulacion) => {
        const explicacion = await leerExplicacion(anulacion.operation_id, anulacion.estado_envio, nombres)
        return {
          anulacion,
          venta: await baseLocal.ventas.get(anulacion.venta_id),
          codigo: explicacion?.tipo === 'rechazo' ? explicacion.codigo : null,
          explicacion,
        }
      }),
    )
  }, [] as AnulacionConProblema[])
}

export interface CobranzaConProblema {
  cobranza: CobranzaLocal
  codigo: string | null
  explicacion: ExplicacionDeEnvio | null
}

/** Cobranzas de la jornada «Con observaciones» o «Rechazadas», con su explicación traducida (change 23, D10). */
export function useCobranzasConProblemas(): CobranzaConProblema[] {
  return useConsulta(async () => {
    const cobranzas = (await cobranzasDeLaJornada()).filter(
      (c) => c.estado_envio === 'CON_OBSERVACIONES' || c.estado_envio === 'RECHAZADA',
    )
    cobranzas.sort((a, b) => (a.occurred_at ?? '').localeCompare(b.occurred_at ?? ''))
    const nombres = await leerNombresLocales()
    return Promise.all(
      cobranzas.map(async (cobranza) => {
        const explicacion = await leerExplicacion(cobranza.operation_id, cobranza.estado_envio ?? 'PENDIENTE', nombres)
        return { cobranza, codigo: explicacion?.tipo === 'rechazo' ? explicacion.codigo : null, explicacion }
      }),
    )
  }, [] as CobranzaConProblema[])
}

export interface EntregaDelDia {
  estado: EstadoDeEnvio
  codigo: string | null
  explicacion: ExplicacionDeEnvio | null
}

const ESTADO_DE_ENVIO_DE_LA_ENTREGA: Record<EstadoDeComando, EstadoDeEnvio> = {
  PENDIENTE: 'PENDIENTE',
  ACEPTADO: 'ACEPTADA',
  ACEPTADO_CON_OBSERVACIONES: 'ACEPTADA',
  RECHAZADO: 'RECHAZADA',
}

/**
 * La entrega del día de la jornada de la sesión, con su estado y, si el servidor la rechazó, su
 * explicación traducida (change 24, D10, D11); `null` si el vendedor todavía no terminó el día.
 */
export function useEntregaDelDia(): EntregaDelDia | null {
  return useConsulta(async () => {
    const sesion = await baseLocal.sesion.get('actual')
    if (sesion === undefined) return null
    const comando = (await baseLocal.cola.toArray()).find(
      (c) => c.sobre.tipo === TIPO_DE_ENTREGA && c.sobre.jornada_id === sesion.jornada.id,
    )
    if (comando === undefined) return null
    const estado = ESTADO_DE_ENVIO_DE_LA_ENTREGA[comando.estado]
    const explicacion = explicarEnvio(estado, comando, await leerNombresLocales(), TIPO_DE_ENTREGA)
    return { estado, codigo: explicacion?.tipo === 'rechazo' ? explicacion.codigo : null, explicacion }
  }, null as EntregaDelDia | null)
}

/** Explicación de las observaciones o del rechazo de una venta, sin conexión (22c, D4). `undefined` mientras carga. */
export function useExplicacionDeEnvio(venta: VentaLocal): ExplicacionDeEnvio | null | undefined {
  return useExplicacionDeOperacion(venta.operation_id, venta.estado_envio)
}

/** Lo mismo para cualquier operación de la cola, por ejemplo la anulación de una venta (22d, D10). */
export function useExplicacionDeOperacion(
  operacionId: string,
  estado: EstadoDeEnvio,
): ExplicacionDeEnvio | null | undefined {
  const [explicacion, setExplicacion] = useState<ExplicacionDeEnvio | null | undefined>(undefined)
  useEffect(() => {
    const suscripcion = liveQuery(async () => leerExplicacion(operacionId, estado, await leerNombresLocales())).subscribe({
      next: setExplicacion,
      error: () => setExplicacion(null),
    })
    return () => suscripcion.unsubscribe()
  }, [operacionId, estado])
  return explicacion
}

/** `true` si la aplicación está por debajo de la última versión mínima conocida (no se venden ventas nuevas). */
export function useVersionBloqueada(): boolean {
  return useConsulta(() => ventaBloqueadaPorVersion(APP_VERSION), false)
}

/** Estado de la sincronización de esta pestaña: enviando, otra pestaña, sin señal. */
export function useEstadoDeEnvio(): EstadoDeSincronizacionDeLaPestana {
  return useSyncExternalStore(suscribirEstadoDeSincronizacion, estadoDeSincronizacion)
}
