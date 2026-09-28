import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Spec `identidad/autenticacion-y-sesion`, escenario "El refresh token no
 * es legible desde la aplicación" (lado cliente, tarea 13.2): el access
 * token vive únicamente en una variable de módulo, nunca en
 * `localStorage`, `sessionStorage` ni en una cookie legible desde
 * JavaScript, y se pierde al recargar la página.
 */
describe('tokenStore: access token en memoria (tarea 13.2)', () => {
  const localStorageSetItem = vi.spyOn(Storage.prototype, 'setItem')

  beforeEach(() => {
    localStorageSetItem.mockClear()
  })

  afterEach(() => {
    vi.resetModules()
  })

  it('arranca sin ningún token', async () => {
    const { obtenerAccessToken } = await import('../../../../src/lib/auth/tokenStore')
    expect(obtenerAccessToken()).toBeNull()
  })

  it('devuelve el token fijado hasta que se limpia', async () => {
    const { fijarAccessToken, obtenerAccessToken, limpiarAccessToken } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    fijarAccessToken('token-de-prueba-1')
    expect(obtenerAccessToken()).toBe('token-de-prueba-1')

    limpiarAccessToken()
    expect(obtenerAccessToken()).toBeNull()
  })

  it('reemplazar el token no deja rastro del anterior', async () => {
    const { fijarAccessToken, obtenerAccessToken } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    fijarAccessToken('token-de-prueba-1')
    fijarAccessToken('token-de-prueba-2')
    expect(obtenerAccessToken()).toBe('token-de-prueba-2')
  })

  it('fijar el token nunca escribe en localStorage ni en sessionStorage', async () => {
    const sessionStorageSetItem = vi.spyOn(window.sessionStorage, 'setItem')
    const { fijarAccessToken } = await import('../../../../src/lib/auth/tokenStore')

    fijarAccessToken('token-secreto')

    expect(localStorageSetItem).not.toHaveBeenCalled()
    expect(sessionStorageSetItem).not.toHaveBeenCalled()
    sessionStorageSetItem.mockRestore()
  })

  it('fijar el token nunca escribe en document.cookie', async () => {
    const cookieDescriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
    const setCookie = vi.fn()
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get: () => '',
      set: setCookie,
    })

    try {
      const { fijarAccessToken } = await import('../../../../src/lib/auth/tokenStore')
      fijarAccessToken('token-secreto')
      expect(setCookie).not.toHaveBeenCalled()
    } finally {
      if (cookieDescriptor) {
        Object.defineProperty(document, 'cookie', cookieDescriptor)
      }
    }
  })

  it('se pierde al recargar la página (módulo reevaluado desde cero)', async () => {
    const primeraCarga = await import('../../../../src/lib/auth/tokenStore')
    primeraCarga.fijarAccessToken('token-antes-de-recargar')
    expect(primeraCarga.obtenerAccessToken()).toBe('token-antes-de-recargar')

    // `vi.resetModules()` + un import nuevo simula lo que pasa en un reload
    // real: el motor de JS vuelve a evaluar el módulo desde cero, así que
    // la variable de módulo arranca en su valor inicial otra vez.
    vi.resetModules()
    const segundaCarga = await import('../../../../src/lib/auth/tokenStore')
    expect(segundaCarga.obtenerAccessToken()).toBeNull()
  })
})

/**
 * `design.md` D2-A (tarea 5.1-5.2): `tokenStore` avisa de cada cambio de
 * token para que `AdminScreen` invalide o descarte la consulta `['yo']`
 * sin que `httpClient` conozca React ni TanStack.
 */
describe('tokenStore: aviso de cambios de token (D2-A, tarea 5.1)', () => {
  afterEach(() => {
    vi.resetModules()
  })

  it('avisa con el token nuevo al fijarAccessToken', async () => {
    const { fijarAccessToken, suscribirACambiosDeToken } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    const listener = vi.fn()
    suscribirACambiosDeToken(listener)
    fijarAccessToken('token-de-prueba-1')

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith('token-de-prueba-1')
  })

  it('avisa con null al limpiarAccessToken', async () => {
    const { fijarAccessToken, limpiarAccessToken, suscribirACambiosDeToken } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    fijarAccessToken('token-de-prueba-1')
    const listener = vi.fn()
    suscribirACambiosDeToken(listener)
    limpiarAccessToken()

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(null)
  })

  it('desuscribir corta los avisos', async () => {
    const { fijarAccessToken, suscribirACambiosDeToken } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    const listener = vi.fn()
    const desuscribir = suscribirACambiosDeToken(listener)
    desuscribir()
    fijarAccessToken('token-de-prueba-2')

    expect(listener).not.toHaveBeenCalled()
  })

  it('avisa a dos suscriptores, y una suscripción dada de baja durante el aviso no rompe a las demás', async () => {
    const { fijarAccessToken, suscribirACambiosDeToken } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    const listener1 = vi.fn()
    const listener2 = vi.fn()

    // listener1 se da de baja a sí mismo apenas es avisado.
    const referenciaADesuscribir1: { actual: () => void } = { actual: () => {} }
    listener1.mockImplementation(() => {
      referenciaADesuscribir1.actual()
    })
    referenciaADesuscribir1.actual = suscribirACambiosDeToken(listener1)
    suscribirACambiosDeToken(listener2)

    fijarAccessToken('token-de-prueba-3')

    expect(listener1).toHaveBeenCalledTimes(1)
    expect(listener2).toHaveBeenCalledTimes(1)
    expect(listener2).toHaveBeenCalledWith('token-de-prueba-3')

    // Un segundo aviso confirma que la baja de listener1 surtió efecto y
    // que listener2 sigue recibiendo avisos.
    fijarAccessToken('token-de-prueba-4')
    expect(listener1).toHaveBeenCalledTimes(1)
    expect(listener2).toHaveBeenCalledTimes(2)
  })
})

/**
 * Corte determinístico de la sesión terminada (tarea 11.2, B1, `design.md`
 * D3-A).
 *
 * `tokenStore` tiene que distinguir dos estados que antes se confundían en
 * el mismo `accessToken === null`:
 *
 * - **no hay token todavía**: página recién cargada o recién iniciada
 *   sesión. La cookie `HttpOnly` del refresh token sigue vigente (ADR-017),
 *   así que la primera petición da 401, dispara la renovación y el reintento
 *   con el token nuevo trae los permisos. Ofrecer "Iniciar sesión" en este
 *   estado dejaría al usuario fuera de `/admin` en cada recarga.
 * - **la sesión terminó**: el backend rechazó la renovación. Volver a
 *   intentarlo solo vuelve a fallar, así que hay que cortar y ofrecer
 *   "Iniciar sesión".
 *
 * El paso de un estado al otro es exactamente `limpiarAccessToken` (la
 * renovación fue rechazada) y `fijarAccessToken` (hubo un token nuevo:
 * login o renovación aceptada).
 */
describe('tokenStore: sesión terminada (tarea 11.2, B1)', () => {
  afterEach(() => {
    vi.resetModules()
  })

  it('arranca con la sesión viva: sin token, pero sin sesión terminada', async () => {
    const { obtenerAccessToken, sesionTerminada } = await import('../../../../src/lib/auth/tokenStore')

    expect(obtenerAccessToken()).toBeNull()
    expect(sesionTerminada()).toBe(false)
  })

  it('limpiarAccessToken marca la sesión como terminada', async () => {
    const { fijarAccessToken, limpiarAccessToken, sesionTerminada } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    fijarAccessToken('token-de-prueba-1')
    expect(sesionTerminada()).toBe(false)

    limpiarAccessToken()

    expect(sesionTerminada()).toBe(true)
  })

  it('fijarAccessToken deja la sesión viva otra vez (renovación aceptada)', async () => {
    const { fijarAccessToken, limpiarAccessToken, sesionTerminada } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    limpiarAccessToken()
    expect(sesionTerminada()).toBe(true)

    fijarAccessToken('token-renovado')

    expect(sesionTerminada()).toBe(false)
  })

  it('fijar un token después del corte deja la sesión viva (login posterior a un rechazo)', async () => {
    const { fijarAccessToken, limpiarAccessToken, sesionTerminada } = await import(
      '../../../../src/lib/auth/tokenStore'
    )

    fijarAccessToken('token-1')
    limpiarAccessToken()
    fijarAccessToken('token-2')

    expect(sesionTerminada()).toBe(false)
  })
})
