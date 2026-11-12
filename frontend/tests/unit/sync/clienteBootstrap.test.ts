import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { baseLocal } from '../../../src/lib/dispositivo/db'
import { pedirBootstrap } from '../../../src/sync/clienteBootstrap'

vi.mock('../../../src/lib/api/httpClient', () => ({ apiFetch: vi.fn() }))

import { apiFetch } from '../../../src/lib/api/httpClient'

/**
 * Change 21, tarea 6.2 (spec `sync/base-local`, "El bootstrap se ejecuta al abrir la jornada y
 * a pedido"; RUT-03, INV-01): cada fallo se informa como un resultado distinto y no toca la
 * base local.
 */
const apiFetchMock = vi.mocked(apiFetch)

function json(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('pedir el bootstrap (change 21, tarea 6.2)', () => {
  beforeEach(async () => {
    apiFetchMock.mockReset()
    await Promise.all(baseLocal.tables.map((t) => t.clear()))
    await baseLocal.meta.put({ clave: 'fecha_bootstrap', valor: 'ayer' })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('200: devuelve el bootstrap tal como llegó y pide GET /sync/bootstrap', async () => {
    const cuerpo = { generado_en: '2026-10-30T10:00:00Z' }
    apiFetchMock.mockResolvedValue(json(200, cuerpo))

    const resultado = await pedirBootstrap()

    expect(apiFetchMock).toHaveBeenCalledWith('/sync/bootstrap')
    expect(resultado).toEqual({ tipo: 'ok', bootstrap: cuerpo })
  })

  it('409 JORNADA_REQUERIDA: resultado propio, sin tocar la base', async () => {
    apiFetchMock.mockResolvedValue(json(409, { codigo: 'JORNADA_REQUERIDA', title: 'Sin jornada' }))

    expect(await pedirBootstrap()).toEqual({ tipo: 'jornada_requerida' })
    expect((await baseLocal.meta.get('fecha_bootstrap'))?.valor).toBe('ayer')
  })

  it('un 409 con otro código no es "jornada requerida": es error del servidor/otro', async () => {
    apiFetchMock.mockResolvedValue(json(409, { codigo: 'OTRO', title: 'Otro' }))

    expect((await pedirBootstrap()).tipo).toBe('error')
  })

  it('error de red (fetch rechaza): resultado "sin_red"', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    expect(await pedirBootstrap()).toEqual({ tipo: 'sin_red' })
    expect((await baseLocal.meta.get('fecha_bootstrap'))?.valor).toBe('ayer')
  })

  it('5xx: resultado "error" con el estado', async () => {
    apiFetchMock.mockResolvedValue(json(503, { title: 'Caído' }))

    expect(await pedirBootstrap()).toEqual({ tipo: 'error', estado: 503 })
    expect((await baseLocal.meta.get('fecha_bootstrap'))?.valor).toBe('ayer')
  })

  it('401 sin sesión: resultado "sin_sesion"', async () => {
    apiFetchMock.mockResolvedValue(json(401, {}))

    expect(await pedirBootstrap()).toEqual({ tipo: 'sin_sesion' })
  })
})
