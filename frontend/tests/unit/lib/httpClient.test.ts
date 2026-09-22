import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../../../src/lib/api/httpClient'

/**
 * Tarea 13.1 (`openspec/changes/04-pipeline-comandos/tasks.md`): el cliente
 * HTTP de `/admin` debe agregar el encabezado `Operation-Id` en toda
 * escritura (`design.md` D7) para que las tres escrituras del change 03
 * (alta de usuario, revocación de dispositivo, rotación de PIN) no queden
 * rotas al exigir ese encabezado (D4).
 */
const PATRON_UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function respuestaOk(): Response {
  return new Response(null, { status: 200 })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiFetch — encabezado Operation-Id', () => {
  it('agrega Operation-Id con formato UUIDv7 en una escritura (POST)', async () => {
    const fetchSimulado = vi.fn().mockResolvedValue(respuestaOk())
    vi.stubGlobal('fetch', fetchSimulado)

    await apiFetch('/identidad/usuarios', { method: 'POST' })

    const [, opciones] = fetchSimulado.mock.calls[0] as [string, RequestInit]
    const headers = opciones.headers as Headers
    expect(headers.get('Operation-Id')).toMatch(PATRON_UUID_V7)
  })

  it('agrega Operation-Id en un DELETE (revocación de dispositivo)', async () => {
    const fetchSimulado = vi.fn().mockResolvedValue(respuestaOk())
    vi.stubGlobal('fetch', fetchSimulado)

    await apiFetch('/identidad/dispositivos/algun-id', { method: 'DELETE' })

    const [, opciones] = fetchSimulado.mock.calls[0] as [string, RequestInit]
    const headers = opciones.headers as Headers
    expect(headers.get('Operation-Id')).toMatch(PATRON_UUID_V7)
  })

  it('no agrega Operation-Id en una lectura (GET)', async () => {
    const fetchSimulado = vi.fn().mockResolvedValue(respuestaOk())
    vi.stubGlobal('fetch', fetchSimulado)

    await apiFetch('/identidad/dispositivos')

    const [, opciones] = fetchSimulado.mock.calls[0] as [string, RequestInit]
    const headers = opciones.headers as Headers
    expect(headers.has('Operation-Id')).toBe(false)
  })

  it('dos escrituras distintas no comparten Operation-Id (triangulación)', async () => {
    const fetchSimulado = vi.fn().mockResolvedValue(respuestaOk())
    vi.stubGlobal('fetch', fetchSimulado)

    await apiFetch('/identidad/usuarios', { method: 'POST' })
    await apiFetch('/identidad/dispositivos/otro-id', { method: 'DELETE' })

    const [, opcionesPrimera] = fetchSimulado.mock.calls[0] as [string, RequestInit]
    const [, opcionesSegunda] = fetchSimulado.mock.calls[1] as [string, RequestInit]
    const primero = (opcionesPrimera.headers as Headers).get('Operation-Id')
    const segundo = (opcionesSegunda.headers as Headers).get('Operation-Id')

    expect(primero).not.toBeNull()
    expect(segundo).not.toBeNull()
    expect(primero).not.toBe(segundo)
  })

  it('respeta un Operation-Id ya provisto por quien llama, sin sobrescribirlo', async () => {
    const fetchSimulado = vi.fn().mockResolvedValue(respuestaOk())
    vi.stubGlobal('fetch', fetchSimulado)

    await apiFetch('/identidad/usuarios', {
      method: 'POST',
      headers: { 'Operation-Id': 'fijado-por-quien-llama' },
    })

    const [, opciones] = fetchSimulado.mock.calls[0] as [string, RequestInit]
    const headers = opciones.headers as Headers
    expect(headers.get('Operation-Id')).toBe('fijado-por-quien-llama')
  })
})
