import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'
import { errorDesdeRespuesta } from './errores'
import type { FiltrosCompras } from './claves'

/**
 * Funciones de acceso a `/api/v1/compras/*` y a los catálogos de configuración que usa su
 * pantalla (change 11, tarea 11.1). Tipadas contra `schema.gen.ts`, nunca `any`. El
 * `Operation-Id` de cada escritura lo genera y conserva quien llama (hooks, INV-06).
 */

export type CompraConfirmarDatos = components['schemas']['CompraConfirmarRequest']
export type CompraConfirmarResultado = components['schemas']['CompraConfirmarResponse']
export type CompraAnularDatos = components['schemas']['CompraAnularRequest']
export type CompraAnularResultado = components['schemas']['CompraAnularResponse']
export type CompraLineaDatos = components['schemas']['CompraLineaRequest']
export type CompraMedioDatos = components['schemas']['CompraMedioRequest']
export type CompraResumen = components['schemas']['CompraResumenResponse']
export type CompraDetalle = components['schemas']['CompraDetalleResponse']
export type CompraLinea = components['schemas']['CompraLineaResponse']
export type PaginaCompras = components['schemas']['PaginaCompras']
export type DiferenciaDeCosto = components['schemas']['DiferenciaDeCostoResponse']
export type MedioPago = components['schemas']['MedioPagoResponse']
export type Motivo = components['schemas']['MotivoResponse']
export type ListaMediosPago = components['schemas']['ListaMediosPago']
export type ListaMotivos = components['schemas']['ListaMotivos']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

function paramsCompras(cursor: string | undefined, limite: number, filtros: FiltrosCompras): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) params.set('cursor', cursor)
  if (filtros.proveedorId) params.set('proveedor_id', filtros.proveedorId)
  if (filtros.estado) params.set('estado', filtros.estado)
  if (filtros.desde) params.set('desde', filtros.desde)
  if (filtros.hasta) params.set('hasta', filtros.hasta)
  if (filtros.numeroComprobante) params.set('numero_comprobante', filtros.numeroComprobante)
  return params.toString()
}

export async function listarCompras(
  filtros: FiltrosCompras = {},
  cursor?: string,
  limite = 30,
): Promise<PaginaCompras> {
  const respuesta = await apiFetch(`/compras?${paramsCompras(cursor, limite, filtros)}`)
  return leerJsonOLanzar(respuesta)
}

export async function obtenerCompra(compraId: string): Promise<CompraDetalle> {
  const respuesta = await apiFetch(`/compras/${compraId}`)
  return leerJsonOLanzar(respuesta)
}

export async function confirmarCompra(
  datos: CompraConfirmarDatos,
  operationId: string,
): Promise<CompraConfirmarResultado> {
  const respuesta = await apiFetch('/compras', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function anularCompra(
  compraId: string,
  datos: CompraAnularDatos,
  operationId: string,
): Promise<CompraAnularResultado> {
  const respuesta = await apiFetch(`/compras/${compraId}/anulacion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerJsonOLanzar(respuesta)
}

export async function listarMediosPago(): Promise<ListaMediosPago> {
  const respuesta = await apiFetch('/configuracion/medios-pago')
  return leerJsonOLanzar(respuesta)
}

export async function listarMotivos(ambito: string): Promise<ListaMotivos> {
  const respuesta = await apiFetch(`/configuracion/motivos?${new URLSearchParams({ ambito }).toString()}`)
  return leerJsonOLanzar(respuesta)
}
