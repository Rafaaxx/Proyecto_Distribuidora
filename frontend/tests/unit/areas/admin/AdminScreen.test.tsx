import { QueryClient } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * `design.md` D2-A (tarea 6.5): `AdminScreen` se suscribe una sola vez a
 * `tokenStore` para mantener la consulta `['yo']` sincronizada con cada
 * cambio de token, sin que `httpClient` conozca React ni TanStack.
 *
 * Cada test reimporta `AdminScreen` y `tokenStore` tras `vi.resetModules()`
 * para partir de un `QueryClient` de módulo limpio y de una suscripción
 * nueva (mismo criterio que `tokenStore.test.ts`).
 */
describe('AdminScreen: suscripción a cambios de token (tarea 6.5)', () => {
  let invalidateQueriesSpy: ReturnType<typeof vi.spyOn>
  let resetQueriesSpy: ReturnType<typeof vi.spyOn>
  let removeQueriesSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    invalidateQueriesSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries')
    resetQueriesSpy = vi.spyOn(QueryClient.prototype, 'resetQueries')
    removeQueriesSpy = vi.spyOn(QueryClient.prototype, 'removeQueries')
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  async function montar() {
    const tokenStore = await import('../../../../src/lib/auth/tokenStore')
    const { AdminScreen } = await import('../../../../src/areas/admin/AdminScreen')
    const resultado = render(
      <MemoryRouter initialEntries={['/login']}>
        <AdminScreen />
      </MemoryRouter>,
    )
    return { ...resultado, ...tokenStore }
  }

  it('al fijarse un token, invalida ["yo"] con cancelRefetch: false', async () => {
    const { fijarAccessToken } = await montar()

    fijarAccessToken('token-nuevo')

    expect(invalidateQueriesSpy).toHaveBeenCalledWith({ queryKey: ['yo'] }, { cancelRefetch: false })
  })

  it('al limpiarse el token, reinicia ["yo"] para que el observer vuelva a consultar', async () => {
    const { limpiarAccessToken } = await montar()

    limpiarAccessToken()

    expect(resetQueriesSpy).toHaveBeenCalledWith({ queryKey: ['yo'] })
  })

  /**
   * Tarea 11.2: `removeQueries` destruye la consulta y deja al observer de
   * `usePermisos()` suscrito a un objeto que ya no existe, así que nunca
   * vuelve a pasar por `estado: 'error'` y el aviso "Iniciar sesión" (B1)
   * no aparece. El comportamiento observable está en
   * `AdminScreenSesionTerminada.test.tsx`; acá se fija que la operación
   * elegida sea la que deja vivo al observer.
   */
  it('al limpiarse el token, no elimina ["yo"] de la caché', async () => {
    const { limpiarAccessToken } = await montar()

    limpiarAccessToken()

    expect(removeQueriesSpy).not.toHaveBeenCalled()
  })

  it('se da de baja al desmontar: un cambio de token posterior no toca la consulta', async () => {
    const { fijarAccessToken, unmount } = await montar()

    unmount()
    invalidateQueriesSpy.mockClear()
    resetQueriesSpy.mockClear()
    removeQueriesSpy.mockClear()
    fijarAccessToken('token-tras-desmontar')

    expect(invalidateQueriesSpy).not.toHaveBeenCalled()
    expect(resetQueriesSpy).not.toHaveBeenCalled()
    expect(removeQueriesSpy).not.toHaveBeenCalled()
  })
})
