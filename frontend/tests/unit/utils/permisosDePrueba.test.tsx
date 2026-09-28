import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { usePermisos } from '../../../src/features/identidad/usePermisos'
import { PERMISOS_POR_ROL, queryClientConYo, yoDePrueba } from './permisosDePrueba'

/**
 * Auxiliar compartido de prueba (tarea 6.7): arma un `QueryClient` con
 * `['yo']` ya sembrado para un rol de `01` §19, así los grupos 7 y 8 no
 * repiten el cuerpo de `/yo` en cada pantalla. Sembrar la caché en vez de
 * mockear `apiFetch` evita una petición real: `usePermisos()` nunca llama
 * a `obtenerYo()`.
 */
describe('permisosDePrueba (tarea 6.7)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('yoDePrueba(GES) trae exactamente los permisos de Administración de 01 §19', () => {
    const yo = yoDePrueba('GES')
    expect(yo.permisos).toEqual(PERMISOS_POR_ROL.GES)
    expect(yo.permisos).toContain('GESTIONAR_CATALOGO')
    expect(yo.permisos).toContain('GESTIONAR_PROVEEDORES')
    expect(yo.permisos).not.toContain('GESTIONAR_DISPOSITIVOS')
  })

  it('yoDePrueba(SUP) trae GESTIONAR_DISPOSITIVOS y no GESTIONAR_CATALOGO ni GESTIONAR_PROVEEDORES', () => {
    const yo = yoDePrueba('SUP')
    expect(yo.permisos).toContain('GESTIONAR_DISPOSITIVOS')
    expect(yo.permisos).not.toContain('GESTIONAR_CATALOGO')
    expect(yo.permisos).not.toContain('GESTIONAR_PROVEEDORES')
  })

  it('admite overrides parciales del cuerpo de /yo (por ejemplo el nombre del usuario)', () => {
    const yo = yoDePrueba('ADM', { usuario: { id: 'u-1', nombre: 'Otro nombre' } })
    expect(yo.usuario.nombre).toBe('Otro nombre')
    expect(yo.permisos).toEqual(PERMISOS_POR_ROL.ADM)
  })

  it('queryClientConYo(rol) deja usePermisos() en estado "listo" sin pedir /yo', async () => {
    const queryClient = queryClientConYo('VEN')
    const { result } = renderHook(() => usePermisos(), {
      wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>,
    })

    await waitFor(() => expect(result.current.estado).toBe('listo'))
    expect(result.current.tiene('VENDER')).toBe(true)
    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(false)
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
