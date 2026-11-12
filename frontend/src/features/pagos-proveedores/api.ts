import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import type { FiltrosPagos } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/pagos-proveedores/*` y al saldo del proveedor (change 12,
 * tarea 8.2). Tipadas contra `schema.gen.ts`, nunca `any`. El `Operation-Id` de cada
 * escritura lo genera y conserva quien llama (hooks, INV-06).
 */

export type PagoRegistrarDatos = components['schemas']['PagoProveedorRegistrarRequest']
export type PagoRegistrarResultado = components['schemas']['PagoProveedorRegistrarResponse']
export type PagoAnularDatos = components['schemas']['PagoProveedorAnularRequest']
export type PagoAnularResultado = components['schemas']['PagoProveedorAnularResponse']
export type PagoResumen = components['schemas']['PagoResumenResponse']
export type PagoDetalle = components['schemas']['PagoDetalleResponse']
export type PagoMedio = components['schemas']['PagoMedioResponse']
export type PaginaPagos = components['schemas']['PaginaPagos']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsPagos(cursor: string | undefined, limite: number, filtros: FiltrosPagos): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.proveedorId) params.set('proveedor_id', filtros.proveedorId)
  if (filtros.estado) params.set('estado', filtros.estado)
  if (filtros.origen) params.set('origen', filtros.origen)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  return params.toString()
}

export async function listarPagos(filtros: FiltrosPagos = {}, cursor?: string, limite = 30): Promise<PaginaPagos> {
  const respuesta = await apiFetch(`/pagos-proveedores?${paramsPagos(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerPago(pagoId: string): Promise<PagoDetalle> {
  const respuesta = await apiFetch(`/pagos-proveedores/${pagoId}`)
  return leerJsonOLanzar(respuesta)
}

/** Saldo actual del proveedor como string (CC-04, INV-03). */
export async function obtenerSaldoDelProveedor(proveedorId: string): Promise<string> {
  const respuesta = await apiFetch(`/proveedores/${proveedorId}/saldo`)
  return (await leerJsonOLanzar<components['schemas']['SaldoProveedorResponse']>(respuesta)).saldo
}

export async function registrarPago(datos: PagoRegistrarDatos, operationId: string): Promise<PagoRegistrarResultado> {
  const respuesta = await apiFetch('/pagos-proveedores', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function anularPago(
  pagoId: string,
  datos: PagoAnularDatos,
  operationId: string,
): Promise<PagoAnularResultado> {
  const respuesta = await apiFetch(`/pagos-proveedores/${pagoId}/anulacion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}
