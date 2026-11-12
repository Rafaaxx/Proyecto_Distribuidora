import type { components } from '../../api/schema.gen'
import { apiFetch } from '../../lib/api/httpClient'

/**
 * Acceso a `GET /api/v1/sistema/consistencia` (change 28, D5): el último resultado de la verificación de
 * consistencia de la organización. Tipado contra `schema.gen.ts`, nunca `any`.
 */

export type DiferenciaDeConsistencia = components['schemas']['DiferenciaDeConsistenciaResponse']
export type Consistencia = components['schemas']['ConsistenciaResponse']

export async function obtenerConsistencia(): Promise<Consistencia> {
  const respuesta = await apiFetch('/sistema/consistencia')
  if (!respuesta.ok) {
    throw new Error(`La consulta de consistencia respondió ${String(respuesta.status)}`)
  }
  return (await respuesta.json()) as Consistencia
}
