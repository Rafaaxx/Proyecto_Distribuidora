import { apiFetch } from '../../lib/api/httpClient'
import type { components } from '../../api/schema.gen'
import { errorDesdeRespuesta } from './errores'

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

export type ConfiguracionFiscal = components['schemas']['ConfiguracionFiscalResponse']
export type CondicionIva = components['schemas']['CondicionIvaCambiarRequest']['condicion_iva']
export type CondicionIvaCambiarDatos = components['schemas']['CondicionIvaCambiarRequest']
export type ResumenReglaIva = components['schemas']['ResumenReglaIvaResponse']

async function leerFiscalOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

/** `GET /configuracion/fiscal` (11b, D8): la condición de la organización del token. */
export async function obtenerConfiguracionFiscal(): Promise<ConfiguracionFiscal> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/fiscal'))
}

/** `GET /costos/resumen-regla-iva` (11b, D10): costos vigentes por regla de IVA. */
export async function obtenerResumenReglaIva(): Promise<ResumenReglaIva> {
  return leerFiscalOLanzar(await apiFetch('/costos/resumen-regla-iva'))
}

/** `POST /configuracion/fiscal/condicion-iva` (11b, D7). El `Operation-Id` lo conserva quien llama. */
export async function cambiarCondicionIva(
  datos: CondicionIvaCambiarDatos,
  operationId: string,
): Promise<ConfiguracionFiscal> {
  const respuesta = await apiFetch('/configuracion/fiscal/condicion-iva', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerFiscalOLanzar(respuesta)
}
