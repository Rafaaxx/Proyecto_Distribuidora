import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fijarAccessToken,
  limpiarAccessToken,
  obtenerAccessToken,
  suscribirACambiosDeToken,
} from '../../../../src/lib/auth/tokenStore'

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

/**
 * `design.md` D2-A (tarea 5.3): la consulta `['yo']` se entera de cada
 * renovación a través del aviso de `tokenStore`, sin que `httpClient`
 * conozca React ni TanStack. Estas pruebas verifican que la renovación
 * dispara exactamente el aviso esperado, y que `apiFetch` no cambia de
 * comportamiento (misma suite de la línea base arriba).
 */
describe('httpClient: aviso de token en la renovación (D2-A, tarea 5.3)', () => {
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

  it('una renovación exitosa tras un 401 avisa exactamente una vez, con el token nuevo', async () => {
    fijarAccessToken('token-vencido')

    fetchMock
      .mockResolvedValueOnce(respuesta(401, { codigo: 'NO_AUTENTICADO' }))
      .mockResolvedValueOnce(respuesta(200, { access_token: 'token-nuevo' }))
      .mockResolvedValueOnce(respuesta(200, { ok: true }))

    const { apiFetch } = await import('../../../../src/lib/api/httpClient')

    const listener = vi.fn()
    suscribirACambiosDeToken(listener)

    await apiFetch('/identidad/dispositivos')

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith('token-nuevo')
  })

  it('una renovación rechazada avisa con null', async () => {
    fijarAccessToken('token-vencido')

    fetchMock
      .mockResolvedValueOnce(respuesta(401, { codigo: 'NO_AUTENTICADO' }))
      .mockResolvedValueOnce(respuesta(401, { codigo: 'NO_AUTENTICADO' }))

    const { apiFetch } = await import('../../../../src/lib/api/httpClient')

    const listener = vi.fn()
    suscribirACambiosDeToken(listener)

    await apiFetch('/identidad/dispositivos')

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(null)
  })

  it('varias peticiones concurrentes con 401 comparten una renovación y avisan una sola vez', async () => {
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

    const listener = vi.fn()
    suscribirACambiosDeToken(listener)

    await Promise.all([
      apiFetch('/identidad/dispositivos'),
      apiFetch('/identidad/usuarios'),
      apiFetch('/identidad/roles/x/permisos'),
    ])

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith('token-nuevo')
  })
})

/**
 * Corte determinístico de la sesión terminada (tarea 11.2, B1).
 *
 * Hay un solo camino que limpia el access token: un `/auth/refresh` que el
 * backend rechaza. Desde ese momento ya se sabe que la sesión terminó, así
 * que cada 401 posterior tiene que devolver el 401 tal cual, sin abrir
 * otra negociación con `/auth/refresh`. Sin este corte, una pantalla que
 * sigue pidiendo datos (o reintentando su propia consulta) se comería un
 * `POST /auth/refresh` por cada intento, todos rechazados y todos inútiles.
 */
describe('httpClient: la sesión terminada no vuelve a negociarse (tarea 11.2, B1)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    // Sesión viva: existe un token en memoria y la renovación todavía
    // podría tener éxito.
    fijarAccessToken('token-vigente')
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

  function responderSiempreCon401() {
    fetchMock.mockImplementation((input: unknown) => {
      const url = String(input)
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(respuesta(401, { codigo: 'IDENTIDAD_REFRESH_TOKEN_INVALIDO' }))
      }
      return Promise.resolve(respuesta(401, { codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }))
    })
  }

  function llamadasARefresh(): unknown[][] {
    return fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/refresh'))
  }

  it('la primera petición negocia una vez, deja el token vacío y devuelve el 401', async () => {
    responderSiempreCon401()
    const { apiFetch } = await import('../../../../src/lib/api/httpClient')

    const res = await apiFetch('/identidad/dispositivos')

    expect(res.status).toBe(401)
    expect(llamadasARefresh()).toHaveLength(1)
    expect(obtenerAccessToken()).toBeNull()
  })

  it('las peticiones siguientes devuelven el 401 sin volver a llamar a /auth/refresh', async () => {
    responderSiempreCon401()
    const { apiFetch } = await import('../../../../src/lib/api/httpClient')

    await apiFetch('/identidad/dispositivos')
    const despues = await Promise.all([apiFetch('/yo'), apiFetch('/catalogo/productos')])

    for (const res of despues) {
      expect(res.status).toBe(401)
    }
    expect(llamadasARefresh()).toHaveLength(1)
  })

  it('una renovación aceptada vuelve a dejar la sesión viva para las siguientes peticiones', async () => {
    // El token vuelve a servir (login o cookie de refresh todavía viva):
    // la negociación se reabre.
    fetchMock.mockImplementation((input: unknown) => {
      const url = String(input)
      if (url.includes('/auth/refresh')) {
        return Promise.resolve(respuesta(200, { access_token: 'token-nuevo' }))
      }
      if (obtenerAccessToken() === 'token-nuevo') {
        return Promise.resolve(respuesta(200, { ok: true }))
      }
      return Promise.resolve(respuesta(401, { codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }))
    })
    const { apiFetch } = await import('../../../../src/lib/api/httpClient')

    await apiFetch('/identidad/dispositivos')
    const res = await apiFetch('/identidad/dispositivos')

    expect(res.status).toBe(200)
    expect(obtenerAccessToken()).toBe('token-nuevo')
    // Solo la primera negocia; con el token nuevo en memoria la segunda no
    // llega a pedir 401 ni a tocar `/auth/refresh`.
    expect(llamadasARefresh()).toHaveLength(1)
  })
})
