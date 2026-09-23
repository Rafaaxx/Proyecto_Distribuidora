import { apiFetch } from '../../lib/api/httpClient'
import type { components } from '../../api/schema.gen'

/**
 * Funciones de acceso a `/api/v1/configuracion/*` (tarea 10.7, `design.md`
 * D12). Tipadas contra `schema.gen.ts` (generado del OpenAPI real, tarea
 * 9.8) -- nunca `any`. Mismo patrón que `features/catalogo/api.ts` (tarea
 * 10.2).
 */

export type Alicuota = components['schemas']['AlicuotaResponse']
export type PaginaAlicuotas = components['schemas']['PaginaAlicuotas']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw new Error('No se pudo obtener el listado de alícuotas.')
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

export async function listarAlicuotas(cursor?: string, limite = 30): Promise<PaginaAlicuotas> {
  const respuesta = await apiFetch(`/configuracion/alicuotas?${paramsPagina(cursor, limite)}`)
  return leerJsonOLanzar(respuesta)
}
