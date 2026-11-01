import { beforeEach, describe, expect, it, vi } from 'vitest'

import { enviarLote } from '../../../src/sync/clienteLote'
import { comandoDePrueba } from '../utils/colaDePrueba'

vi.mock('../../../src/lib/api/httpClient', () => ({ apiFetch: vi.fn() }))

import { apiFetch } from '../../../src/lib/api/httpClient'

/**
 * Change 22b, tarea 2.1 (spec `sync/motor-de-sincronizacion`, «Los cortes se reintentan con
 * espera exponencial»; `design.md` D5; cita SYN-04, SYN-06, `02` §6.3, §12.3): el cliente del
 * lote y la clasificación de cada desenlace.
 */
const apiFetchMock = vi.mocked(apiFetch)

function json(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

const lote = [comandoDePrueba(1), comandoDePrueba(2)]

describe('cliente del lote de sincronización (tarea 2.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('POST /sync/comandos con los sobres tal cual, y 200 devuelve los resultados por operation_id', async () => {
    const resultados = [
      { operation_id: 'op-1', estado: 'ACEPTADO', resultado: null, error_codigo: null },
      { operation_id: 'op-2', estado: 'RECHAZADO', resultado: null, error_codigo: 'JORNADA_INEXISTENTE' },
    ]
    apiFetchMock.mockResolvedValue(json(200, { resultados }))

    const respuesta = await enviarLote(lote)

    const [ruta, init] = apiFetchMock.mock.calls[0] ?? []
    expect(ruta).toBe('/sync/comandos')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ items: [lote[0]?.sobre, lote[1]?.sobre] })
    expect(respuesta).toEqual({ tipo: 'ok', resultados, corte: false })
  })

  it('un ítem ERROR_TRANSITORIO marca el corte (y los demás resultados se conservan)', async () => {
    const resultados = [
      { operation_id: 'op-1', estado: 'ACEPTADO', resultado: null, error_codigo: null },
      { operation_id: 'op-2', estado: 'ERROR_TRANSITORIO', resultado: null, error_codigo: null },
    ]
    apiFetchMock.mockResolvedValue(json(200, { resultados }))

    expect(await enviarLote(lote)).toEqual({ tipo: 'ok', resultados, corte: true })
  })

  it.each([500, 502, 503, 429])('%i es transitorio', async (estado) => {
    apiFetchMock.mockResolvedValue(json(estado, { codigo: 'X' }))

    expect(await enviarLote(lote)).toEqual({ tipo: 'transitorio' })
  })

  it('un fetch que falla (sin red) es transitorio', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    expect(await enviarLote(lote)).toEqual({ tipo: 'transitorio' })
  })

  it('401 (después de la renovación de apiFetch) es sesión vencida', async () => {
    apiFetchMock.mockResolvedValue(json(401, { codigo: 'NO_AUTENTICADO' }))

    expect(await enviarLote(lote)).toEqual({ tipo: 'sesion_vencida' })
  })

  it('403 COLA_AJENA y 422 son error del pedido, con su código', async () => {
    apiFetchMock.mockResolvedValueOnce(json(403, { codigo: 'COLA_AJENA' }))
    apiFetchMock.mockResolvedValueOnce(json(422, { detail: [] }))

    expect(await enviarLote(lote)).toEqual({ tipo: 'error_pedido', estado: 403, codigo: 'COLA_AJENA' })
    expect(await enviarLote(lote)).toEqual({ tipo: 'error_pedido', estado: 422, codigo: 'HTTP_422' })
  })

  it('un 200 que no es JSON válido no se aplica: se trata como transitorio', async () => {
    apiFetchMock.mockResolvedValue(new Response('<html>', { status: 200 }))

    expect(await enviarLote(lote)).toEqual({ tipo: 'transitorio' })
  })
})
