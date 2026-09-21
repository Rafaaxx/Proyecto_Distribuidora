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
