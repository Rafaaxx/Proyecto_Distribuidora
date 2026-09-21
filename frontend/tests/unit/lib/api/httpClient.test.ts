import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fijarAccessToken, limpiarAccessToken, obtenerAccessToken } from '../../../../src/lib/auth/tokenStore'

vi.mock('../../../../src/lib/dispositivo/dispositivoId', () => ({
  obtenerOGenerarDispositivoId: vi.fn(async () => 'dispositivo-de-prueba'),
}))

/**
 * Spec `identidad/autenticacion-y-sesion`: el access token vence a los 15
 * minutos y debe renovarse solo; ADR-017 exige que la renovación sea una
 * sola en vuelo aunque varias peticiones fallen a la vez (tarea 13.3).
 */
describe('httpClient: renovación automática del access token (tarea 13.3)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    limpiarAccessToken()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function respuesta(status: number, cuerpo: unknown): Response {
    return new Response(JSON.stringify(cuerpo), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  it('ante un 401, renueva el access token y reintenta la petición original una vez', async () => {
    fijarAccessToken('token-vencido')

    fetchMock
      .mockResolvedValueOnce(respuesta(401, { codigo: 'NO_AUTENTICADO' })) // primer intento con el token vencido
      .mockResolvedValueOnce(respuesta(200, { access_token: 'token-nuevo' })) // /auth/refresh
      .mockResolvedValueOnce(respuesta(200, { ok: true })) // reintento con el token nuevo

    const { apiFetch } = await import('../../../../src/lib/api/httpClient')
    const res = await apiFetch('/identidad/dispositivos')

    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ ok: true })
    expect(obtenerAccessToken()).toBe('token-nuevo')
    expect(fetchMock).toHaveBeenCalledTimes(3)

    const [, refreshInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(refreshInit.credentials).toBe('include')

    const [tercerUrl, tercerInit] = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(tercerUrl).toContain('/identidad/dispositivos')
    expect(new Headers(tercerInit.headers).get('Authorization')).toBe('Bearer token-nuevo')
  })

  it('varias peticiones que reciben 401 a la vez disparan una sola renovación', async () => {
    fijarAccessToken('token-vencido')

    fetchMock.mockImplementation((input: string) => {
      const url = String(input)
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(respuesta(200, { access_token: 'token-nuevo' }))
      }
      const token = obtenerAccessToken()
      if (token === 'token-nuevo') {
        return Promise.resolve(respuesta(200, { ok: true, url }))
      }
      return Promise.resolve(respuesta(401, { codigo: 'NO_AUTENTICADO' }))
    })

    const { apiFetch } = await import('../../../../src/lib/api/httpClient')

    const [r1, r2, r3] = await Promise.all([
      apiFetch('/identidad/dispositivos'),
      apiFetch('/identidad/usuarios'),
      apiFetch('/identidad/roles/x/permisos'),
    ])

    expect(r1.status).toBe(200)
    expect(r2.status).toBe(200)
    expect(r3.status).toBe(200)

    const llamadasARefresh = fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'))
    expect(llamadasARefresh).toHaveLength(1)
  })

  it('si la renovación falla, no reintenta la petición y limpia el access token', async () => {
    fijarAccessToken('token-vencido')

    fetchMock
      .mockResolvedValueOnce(respuesta(401, { codigo: 'NO_AUTENTICADO' }))
      .mockResolvedValueOnce(respuesta(401, { codigo: 'NO_AUTENTICADO' })) // /auth/refresh también rechaza

    const { apiFetch } = await import('../../../../src/lib/api/httpClient')
    const res = await apiFetch('/identidad/dispositivos')

    expect(res.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(obtenerAccessToken()).toBeNull()
  })
})
