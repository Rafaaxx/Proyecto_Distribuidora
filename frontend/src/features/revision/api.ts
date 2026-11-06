import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import type { FiltrosDeObservaciones, FiltrosDeRechazos } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/observaciones/*` (change 25, D1, D3, D5, D7). Tipadas contra `schema.gen.ts`,
 * nunca `any`. El `Operation-Id` de cada escritura lo genera y conserva quien llama (INV-06).
 */

export type OperacionObservada = components['schemas']['OperacionObservadaResponse']
export type ObservacionDeBandeja = components['schemas']['ObservacionDeBandejaResponse']
export type PaginaDeObservaciones = components['schemas']['PaginaDeObservacionesResponse']
export type Rechazo = components['schemas']['RechazoResponse']
export type PaginaDeRechazos = components['schemas']['PaginaDeRechazosResponse']
export type ResumenDePendientes = components['schemas']['ResumenDePendientesResponse']
export type ResolverObservacionesDatos = components['schemas']['ResolverObservacionesRequest']
export type ResolverObservacionesResultado = components['schemas']['ResolucionResponse']
export type ResolverRechazoDatos = components['schemas']['ResolverRechazoRequest']
export type ResolverRechazoResultado = components['schemas']['ResolucionDeRechazoResponse']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

/** Inicio del día local de `fecha` (`aaaa-mm-dd`), más `dias` días, en ISO: el filtro de llegada es por momento. */
function inicioDeDia(fecha: string, dias = 0): string {
  const momento = new Date(`${fecha}T00:00:00`)
  momento.setDate(momento.getDate() + dias)
  return momento.toISOString()
}

function paramsDeObservaciones(cursor: string | undefined, limite: number, filtros: FiltrosDeObservaciones): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  params.set('estado', filtros.estado ?? 'PENDIENTE')
  if (filtros.codigo) params.append('codigo', filtros.codigo)
  if (filtros.tipo) params.append('tipo', filtros.tipo)
  if (filtros.usuarioId) params.set('usuario_id', filtros.usuarioId)
  if (filtros.jornadaId) params.set('jornada_id', filtros.jornadaId)
  if (filtros.desde) params.set('desde', inicioDeDia(filtros.desde))
  // `hasta` excluye: el día elegido entra completo.
  if (filtros.hasta) params.set('hasta', inicioDeDia(filtros.hasta, 1))
  return params.toString()
}

function paramsDeRechazos(cursor: string | undefined, limite: number, filtros: FiltrosDeRechazos): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  params.set('estado', filtros.estado ?? 'PENDIENTE')
  if (filtros.origen) params.set('origen', filtros.origen)
  if (filtros.tipo) params.append('tipo', filtros.tipo)
  if (filtros.usuarioId) params.set('usuario_id', filtros.usuarioId)
  if (filtros.jornadaId) params.set('jornada_id', filtros.jornadaId)
  return params.toString()
}

export async function listarObservaciones(
  filtros: FiltrosDeObservaciones = {},
  cursor?: string,
  limite = 30,
): Promise<PaginaDeObservaciones> {
  const respuesta = await apiFetch(`/observaciones?${paramsDeObservaciones(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function listarRechazos(
  filtros: FiltrosDeRechazos = {},
  cursor?: string,
  limite = 30,
): Promise<PaginaDeRechazos> {
  const respuesta = await apiFetch(`/observaciones/rechazos?${paramsDeRechazos(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

/** El detalle de un rechazo, con lo que envió el teléfono sin traducir (`contenido`). */
export async function obtenerRechazo(rechazoId: string): Promise<Rechazo> {
  const respuesta = await apiFetch(`/observaciones/rechazos/${rechazoId}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerResumenDePendientes(): Promise<ResumenDePendientes> {
  const respuesta = await apiFetch('/observaciones/resumen')
  return leerJsonOLanzar(respuesta)
}

export async function resolverObservaciones(
  datos: ResolverObservacionesDatos,
  operationId: string,
): Promise<ResolverObservacionesResultado> {
  const respuesta = await apiFetch('/observaciones/resolucion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function resolverRechazo(
  rechazoId: string,
  datos: ResolverRechazoDatos,
  operationId: string,
): Promise<ResolverRechazoResultado> {
  const respuesta = await apiFetch(`/observaciones/rechazos/${rechazoId}/resolucion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}
