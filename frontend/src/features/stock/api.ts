import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import type { FiltrosKardex } from './claves'
import { errorDesdeRespuesta } from './errores'

/**
 * Acceso a la API de stock (change 09, grupo 8, tarea 8.1). Tipado contra
 * `schema.gen.ts` -- nunca `any`.
 *
 * Escrituras (`ONLINE`, sin cola): `POST /stock/ubicaciones`,
 * `PUT /stock/ubicaciones/{id}` y `POST /stock/iniciales`. El `Operation-Id` lo
 * genera y conserva quien llama para que el reintento reenvíe el mismo valor
 * (INV-06). Lecturas: ubicaciones, saldos y kardex de `/stock`, y el costo
 * promedio de `/catalogo/productos/{id}/costo` (enmienda a D3, solo `VER_COSTOS`).
 * Los costos viajan y vuelven como string (INV-03); las cantidades, como enteros
 * en unidad base (INV-04).
 */

export type Ubicacion = components['schemas']['UbicacionResponse']
export type PaginaUbicaciones = components['schemas']['PaginaUbicaciones']
export type UbicacionCrearDatos = components['schemas']['UbicacionCrearRequest']
export type UbicacionModificarDatos = components['schemas']['UbicacionModificarRequest']
export type StockDeUbicacion = components['schemas']['StockDeUbicacionResponse']
export type LineaDeStock = components['schemas']['LineaDeStockResponse']
export type Kardex = components['schemas']['KardexResponse']
export type LineaDeKardex = components['schemas']['LineaDeKardexResponse']
export type StockInicialDatos = components['schemas']['StockInicialRegistrarRequest']
export type StockInicialResultado = components['schemas']['StockInicialResponse']
export type CostoPromedio = components['schemas']['CostoPromedioResponse']

/** Tamaño de página por defecto (ADR-034 punto 6). */
export const LIMITE_POR_DEFECTO = 50

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function conOperationId(operationId: string): HeadersInit {
  return { 'Content-Type': 'application/json', 'Operation-Id': operationId }
}

// --- ubicaciones ------------------------------------------------------------

export async function listarUbicaciones(
  activo?: boolean,
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<PaginaUbicaciones> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (activo !== undefined) params.set('activo', String(activo))
  const respuesta = await apiFetch(`/stock/ubicaciones?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function crearUbicacion(datos: UbicacionCrearDatos, operationId: string): Promise<Ubicacion> {
  const respuesta = await apiFetch('/stock/ubicaciones', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarUbicacion(
  ubicacionId: string,
  datos: UbicacionModificarDatos,
  operationId: string,
): Promise<Ubicacion> {
  const respuesta = await apiFetch(`/stock/ubicaciones/${ubicacionId}`, {
    method: 'PUT',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- stock inicial ----------------------------------------------------------

export async function registrarStockInicial(
  datos: StockInicialDatos,
  operationId: string,
): Promise<StockInicialResultado> {
  const respuesta = await apiFetch('/stock/iniciales', {
    method: 'POST',
    headers: conOperationId(operationId),
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

// --- lecturas ---------------------------------------------------------------

export async function obtenerSaldos(
  ubicacionId: string,
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<StockDeUbicacion> {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  const respuesta = await apiFetch(`/stock/ubicaciones/${ubicacionId}/saldos?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerKardex(
  productoId: string,
  ubicacionId: string,
  filtros: FiltrosKardex = {},
  cursor?: string,
  limite: number = LIMITE_POR_DEFECTO,
): Promise<Kardex> {
  const params = new URLSearchParams()
  params.set('producto_id', productoId)
  params.set('ubicacion_id', ubicacionId)
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  const respuesta = await apiFetch(`/stock/kardex?${params.toString()}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerCostoPromedio(productoId: string): Promise<CostoPromedio> {
  const respuesta = await apiFetch(`/catalogo/productos/${productoId}/costo`)
  return leerJsonOLanzar(respuesta)
}
