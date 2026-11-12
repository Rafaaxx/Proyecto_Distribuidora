import { apiFetch } from '../../lib/api/httpClient'
import type { components } from '../../api/schema.gen'
import { errorDesdeRespuesta } from './errores'
import type { FiltrosProveedores } from './claves'

/**
 * Funciones de acceso a `/api/v1/proveedores/*` y `/api/v1/costos/*`
 * (tarea 11.2). Tipadas contra `schema.gen.ts` -- nunca `any`. El
 * `Operation-Id` de cada escritura lo genera y conserva quien llama (los
 * hooks de mutación, `useMutaciones.ts`) para que el reintento automático
 * de TanStack Query reenvíe exactamente el mismo valor (INV-06): estas
 * funciones solo lo pasan como encabezado explícito.
 */

export type Proveedor = components['schemas']['ProveedorResponse']
export type ProveedorOpcion = components['schemas']['ProveedorOpcionResponse']
export type PaginaProveedores = components['schemas']['PaginaProveedores']
export type PaginaProveedorOpciones = components['schemas']['PaginaProveedorOpciones']
export type ProveedorCrearDatos = components['schemas']['ProveedorCrearRequest']
export type ProveedorModificarDatos = components['schemas']['ProveedorModificarRequest']

export type CostoDelLote = components['schemas']['CostoDelLoteRequest']
export type CostoInformarDatos = components['schemas']['CostoInformarRequest']
export type CostoInformarResultado = components['schemas']['CostoInformarResponse']
export type CostoInformado = components['schemas']['CostoInformadoResponse']
export type CostoVigente = components['schemas']['CostoVigenteResponse']
export type PaginaCostosInformados = components['schemas']['PaginaCostosInformados']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsPagina(cursor: string | undefined, limite: number): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) {
    params.set('cursor', cursor)
  }
  return params.toString()
}

// --- Proveedores ---

function paramsProveedores(cursor: string | undefined, limite: number, filtros: FiltrosProveedores): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.texto) params.set('texto', filtros.texto)
  if (filtros.activo !== undefined) params.set('activo', String(filtros.activo))
  return params.toString()
}

export async function listarProveedores(
  filtros: FiltrosProveedores = {},
  cursor?: string,
  limite = 30,
): Promise<PaginaProveedores> {
  const respuesta = await apiFetch(`/proveedores?${paramsProveedores(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerProveedor(proveedorId: string): Promise<Proveedor> {
  const respuesta = await apiFetch(`/proveedores/${proveedorId}`)
  return leerJsonOLanzar(respuesta)
}

export async function crearProveedor(datos: ProveedorCrearDatos, operationId: string): Promise<Proveedor> {
  const respuesta = await apiFetch('/proveedores', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function modificarProveedor(
  proveedorId: string,
  datos: ProveedorModificarDatos,
  operationId: string,
): Promise<Proveedor> {
  const respuesta = await apiFetch(`/proveedores/${proveedorId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function listarOpcionesDeProveedores(cursor?: string, limite = 100): Promise<PaginaProveedorOpciones> {
  const respuesta = await apiFetch(`/proveedores/opciones?${paramsPagina(cursor, limite)}`)
  return leerJsonOLanzar(respuesta)
}

// --- Costos informados ---

export async function informarCostos(datos: CostoInformarDatos, operationId: string): Promise<CostoInformarResultado> {
  const respuesta = await apiFetch('/costos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function obtenerCostoVigente(productoId: string, fecha?: string): Promise<CostoVigente> {
  const params = new URLSearchParams()
  if (fecha) params.set('fecha', fecha)
  const query = params.toString()
  const respuesta = await apiFetch(`/costos/productos/${productoId}/vigente${query ? `?${query}` : ''}`)
  return leerJsonOLanzar(respuesta)
}

export async function listarHistorialDeCostos(
  productoId: string,
  cursor?: string,
  limite = 30,
): Promise<PaginaCostosInformados> {
  const respuesta = await apiFetch(`/costos/productos/${productoId}/historial?${paramsPagina(cursor, limite)}`)
  return leerJsonOLanzar(respuesta)
}
