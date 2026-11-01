import type { components } from '../api/schema.gen'
import { apiFetch } from '../lib/api/httpClient'
import type { ComandoEnCola } from '../lib/dispositivo/db'

/**
 * Cliente de `POST /api/v1/sync/comandos` (change 22b, `design.md` D5; SYN-04, SYN-06, `02` §6.3,
 * §12.3). No toca la base local: informa cada desenlace como un resultado distinto para que el
 * ciclo decida (aplicar, esperar, cortar). La renovación del access token la hace `apiFetch`;
 * un 401 que llega hasta acá es sesión vencida.
 */
export type ResultadoDeItem = components['schemas']['ResultadoItemLoteResponse']

export type ResultadoDeLote =
  | { tipo: 'ok'; resultados: ResultadoDeItem[]; corte: boolean }
  | { tipo: 'transitorio' }
  | { tipo: 'sesion_vencida' }
  | { tipo: 'error_pedido'; estado: number; codigo: string }

const ESTADO_TRANSITORIO_DE_ITEM = 'ERROR_TRANSITORIO'

async function codigoDe(respuesta: Response): Promise<string | undefined> {
  try {
    return ((await respuesta.json()) as { codigo?: string }).codigo
  } catch {
    return undefined
  }
}

export async function enviarLote(comandos: ComandoEnCola[]): Promise<ResultadoDeLote> {
  let respuesta: Response
  try {
    respuesta = await apiFetch('/sync/comandos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: comandos.map((c) => c.sobre) }),
    })
  } catch {
    return { tipo: 'transitorio' }
  }

  if (respuesta.ok) {
    try {
      const cuerpo = (await respuesta.json()) as components['schemas']['LoteComandosResponse']
      const resultados = cuerpo.resultados
      return { tipo: 'ok', resultados, corte: resultados.some((r) => r.estado === ESTADO_TRANSITORIO_DE_ITEM) }
    } catch {
      return { tipo: 'transitorio' }
    }
  }
  if (respuesta.status >= 500 || respuesta.status === 429) return { tipo: 'transitorio' }
  if (respuesta.status === 401) return { tipo: 'sesion_vencida' }
  return {
    tipo: 'error_pedido',
    estado: respuesta.status,
    codigo: (await codigoDe(respuesta)) ?? `HTTP_${respuesta.status}`,
  }
}
