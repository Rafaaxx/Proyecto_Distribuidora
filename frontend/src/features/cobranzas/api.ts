import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import type { FiltrosCobranzas } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/cobranzas/*` y a las lecturas de apoyo de quien cobra
 * (`/clientes/opciones`, `/clientes/{id}/saldo`; change 17, tarea 14.1). Tipadas contra
 * `schema.gen.ts`, nunca `any`. El `Operation-Id` de cada escritura lo genera y conserva quien
 * llama (hooks, INV-06).
 */

export type CobranzaRegistrarDatos = components['schemas']['CobranzaRegistrarRequest']
export type CobranzaRegistrarResultado = components['schemas']['CobranzaRegistrarResponse']
export type CobranzaAnularDatos = components['schemas']['CobranzaAnularRequest']
export type CobranzaAnularResultado = components['schemas']['CobranzaAnularResponse']
export type CobranzaResumen = components['schemas']['CobranzaResumenResponse']
export type CobranzaDetalle = components['schemas']['CobranzaDetalleResponse']
export type CobranzaMedio = components['schemas']['CobranzaMedioResponse']
export type PaginaCobranzas = components['schemas']['PaginaCobranzas']
export type ClienteOpcion = components['schemas']['ClienteOpcionResponse']
export type PaginaOpcionesDeClientes = components['schemas']['PaginaOpcionesDeClientes']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsCobranzas(cursor: string | undefined, limite: number, filtros: FiltrosCobranzas): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.clienteId) params.set('cliente_id', filtros.clienteId)
  if (filtros.estado) params.set('estado', filtros.estado)
  if (filtros.usuarioId) params.set('usuario_id', filtros.usuarioId)
  if (filtros.jornadaId) params.set('jornada_id', filtros.jornadaId)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  return params.toString()
}

export async function listarCobranzas(
  filtros: FiltrosCobranzas = {},
  cursor?: string,
  limite = 30,
): Promise<PaginaCobranzas> {
  const respuesta = await apiFetch(`/cobranzas?${paramsCobranzas(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerCobranza(cobranzaId: string): Promise<CobranzaDetalle> {
  const respuesta = await apiFetch(`/cobranzas/${cobranzaId}`)
  return leerJsonOLanzar(respuesta)
}

/** Selector de clientes de quien cobra (D14): ACTIVO y SUSPENDIDO, sin crédito ni documento. */
export async function listarOpcionesDeClientes(texto: string, cursor?: string, limite = 50): Promise<PaginaOpcionesDeClientes> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (texto.trim() !== '') params.set('texto', texto.trim())
  if (cursor) params.set('cursor', cursor)
  const respuesta = await apiFetch(`/clientes/opciones?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

/** Saldo actual del cliente como string (CC-04, INV-03). */
export async function obtenerSaldoDelCliente(clienteId: string): Promise<string> {
  const respuesta = await apiFetch(`/clientes/${clienteId}/saldo`)
  return (await leerJsonOLanzar<{ saldo: string }>(respuesta)).saldo
}

export async function registrarCobranza(
  datos: CobranzaRegistrarDatos,
  operationId: string,
): Promise<CobranzaRegistrarResultado> {
  const respuesta = await apiFetch('/cobranzas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function anularCobranza(
  cobranzaId: string,
  datos: CobranzaAnularDatos,
  operationId: string,
): Promise<CobranzaAnularResultado> {
  const respuesta = await apiFetch(`/cobranzas/${cobranzaId}/anulacion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}
