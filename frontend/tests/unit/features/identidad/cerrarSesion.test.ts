import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { cerrarSesionAdmin } from '../../../../src/features/identidad/cerrarSesion'
import { fijarAccessToken, obtenerAccessToken, sesionTerminada } from '../../../../src/lib/auth/tokenStore'

function respuesta(status: number) {
  return { ok: status >= 200 && status < 300, status }
}

/**
 * "Cerrar sesión" de `/admin`: revoca la sesión en el servidor (`POST /auth/logout`) y recién
 * entonces olvida el access token. A diferencia de `/ruta`, no toca datos locales de Dexie.
 */
describe('cerrarSesionAdmin', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    fijarAccessToken('token-vigente')
  })

  it('llama a POST /auth/logout, limpia el access token y marca la sesión como terminada', async () => {
    apiFetchMock.mockResolvedValue(respuesta(204))

    const resultado = await cerrarSesionAdmin()

    expect(resultado).toBe('cerrada')
    expect(apiFetchMock).toHaveBeenCalledWith('/auth/logout', { method: 'POST' })
    expect(obtenerAccessToken()).toBeNull()
    expect(sesionTerminada()).toBe(true)
  })

  it('un 401 se trata como sesión ya cerrada', async () => {
    apiFetchMock.mockResolvedValue(respuesta(401))

    expect(await cerrarSesionAdmin()).toBe('cerrada')
    expect(obtenerAccessToken()).toBeNull()
  })

  it('si falla la red no cierra: informa sin_conexion y conserva el token', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    expect(await cerrarSesionAdmin()).toBe('sin_conexion')
    expect(obtenerAccessToken()).toBe('token-vigente')
    expect(sesionTerminada()).toBe(false)
  })

  it('un error del servidor (500) no cierra: informa error y conserva el token', async () => {
    apiFetchMock.mockResolvedValue(respuesta(500))

    expect(await cerrarSesionAdmin()).toBe('error')
    expect(obtenerAccessToken()).toBe('token-vigente')
  })
})
