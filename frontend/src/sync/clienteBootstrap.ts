import { apiFetch } from '../lib/api/httpClient'
import type { BootstrapRespuesta } from './aplicarBootstrap'

/**
 * Pide `GET /api/v1/sync/bootstrap` (change 21, `design.md` D9, D11; RUT-03). No toca la base
 * local: informa cada desenlace como un resultado distinto para que quien llama decida
 * (reintentar, avisar, pedir otra jornada). Aplicarlo es `aplicarBootstrap`.
 */
export type ResultadoBootstrap =
  | { tipo: 'ok'; bootstrap: BootstrapRespuesta }
  | { tipo: 'jornada_requerida' }
  | { tipo: 'sin_sesion' }
  | { tipo: 'sin_red' }
  | { tipo: 'error'; estado: number }

const CODIGO_JORNADA_REQUERIDA = 'JORNADA_REQUERIDA'

async function codigoDe(respuesta: Response): Promise<string | undefined> {
  try {
    const problema = (await respuesta.json()) as { codigo?: string }
    return problema.codigo
  } catch {
    return undefined
  }
}

export async function pedirBootstrap(): Promise<ResultadoBootstrap> {
  let respuesta: Response
  try {
    respuesta = await apiFetch('/sync/bootstrap')
  } catch {
    return { tipo: 'sin_red' }
  }

  if (respuesta.ok) {
    return { tipo: 'ok', bootstrap: (await respuesta.json()) as BootstrapRespuesta }
  }
  if (respuesta.status === 401) {
    return { tipo: 'sin_sesion' }
  }
  if (respuesta.status === 409 && (await codigoDe(respuesta)) === CODIGO_JORNADA_REQUERIDA) {
    return { tipo: 'jornada_requerida' }
  }
  return { tipo: 'error', estado: respuesta.status }
}
