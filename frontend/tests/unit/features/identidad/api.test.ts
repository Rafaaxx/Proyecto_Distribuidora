import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeIdentidad, obtenerYo } from '../../../../src/features/identidad/api'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const YO_ADMINISTRACION = {
  usuario: { id: '11111111-1111-1111-1111-111111111111', nombre: 'Ana Administración' },
  organizacion: { id: '22222222-2222-2222-2222-222222222222', nombre: 'Organización inicial' },
  rol: { id: '33333333-3333-3333-3333-333333333333', nombre: 'Administración' },
  permisos: ['EDITAR_COSTOS', 'GESTIONAR_CATALOGO', 'GESTIONAR_PROVEEDORES', 'VER_COSTOS'],
}

/**
 * `design.md` D1-A / D8-A (tarea 6.2): `obtenerYo()` pide `GET /yo` con
 * `apiFetch` y tipa la respuesta con `schema.gen.ts` (`YoResponse`).
 */
describe('obtenerYo (tarea 6.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('pide GET /yo y devuelve el cuerpo parseado ante un 200', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))

    const yo = await obtenerYo()

    expect(apiFetchMock).toHaveBeenCalledWith('/yo')
    expect(yo).toEqual(YO_ADMINISTRACION)
  })

  it('propaga un error con el estado de la respuesta ante un 401', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(401, { title: 'El access token no es válido.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }),
    )

    await expect(obtenerYo()).rejects.toMatchObject({ status: 401 })
  })

  it('el error propagado es un ErrorDeIdentidad con el código del servidor', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(401, { title: 'El access token no es válido.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }),
    )

    await expect(obtenerYo()).rejects.toBeInstanceOf(ErrorDeIdentidad)
    apiFetchMock.mockResolvedValueOnce(
      respuesta(401, { title: 'El access token no es válido.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }),
    )
    await expect(obtenerYo()).rejects.toMatchObject({ codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' })
  })
})

/**
 * Corte determinístico de la sesión terminada (tarea 11.2, B1).
 *
 * Cuando la renovación ya fue rechazada, `/yo` no puede volver a tener
 * éxito: `obtenerYo()` lo dice en el acto, sin volver a pegarle al
 * servidor. Importa por dos razones concretas:
 *
 * 1. `AdminScreen` reinicia `['yo']` cuando se limpia el token, así que
 *    cada intento de la consulta vuelve a ejecutar `obtenerYo()`. Si este
 *    fuera a la red, ese reinicio dispararía otra renovación, que sería
 *    rechazada, que limpiaría el token otra vez: un bucle de
 *    `/auth/refresh` sin fin en lugar del aviso "Iniciar sesión".
 * 2. El error tiene que ser un `ErrorDeIdentidad` con `status` 401, que es
 *    lo que `AdminLayout` mira para ofrecer iniciar sesión en vez de
 *    reintentar (`design.md` D3-A).
 *
 * El caso simétrico queda fijado acá: sin token pero con la sesión viva
 * (página recién recargada, cookie `HttpOnly` del refresh vigente,
 * ADR-017) `obtenerYo()` sí va a la red, porque el 401 del primer intento
 * es justamente lo que dispara la renovación.
 */
describe('obtenerYo: fallo rápido con la sesión terminada (tarea 11.2, B1)', () => {
  afterEach(() => {
    vi.resetModules()
  })

  it('con la sesión terminada, rechaza con 401 sin llamar a apiFetch', async () => {
    // Importaciones frescas: el estado de la sesión vive en el módulo
    // `tokenStore`, así que tiene que ser la misma generación que usa la
    // `obtenerYo` que se prueba.
    const { limpiarAccessToken } = await import('../../../../src/lib/auth/tokenStore')
    const { obtenerYo: obtenerYoConSesionMuerta } = await import('../../../../src/features/identidad/api')
    limpiarAccessToken()
    apiFetchMock.mockReset()

    await expect(obtenerYoConSesionMuerta()).rejects.toMatchObject({ status: 401 })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('sin token pero con la sesión viva, sí va a la red (recarga de página)', async () => {
    const { obtenerYo: obtenerYoSinToken } = await import('../../../../src/features/identidad/api')
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))

    await expect(obtenerYoSinToken()).resolves.toEqual(YO_ADMINISTRACION)
    expect(apiFetchMock).toHaveBeenCalledWith('/yo')
  })
})
