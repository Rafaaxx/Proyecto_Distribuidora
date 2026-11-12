import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { usePermisos } from '../../../../src/features/identidad/usePermisos'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const YO_ADMINISTRACION = {
  usuario: { id: '1', nombre: 'Ana' },
  organizacion: { id: '2', nombre: 'Organización inicial' },
  rol: { id: '3', nombre: 'Administración' },
  permisos: ['GESTIONAR_CATALOGO', 'GESTIONAR_PROVEEDORES'],
}

function envolvedor(queryClient: QueryClient) {
  return function Envolvedor({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

/**
 * `design.md` D2-A / D3-A (tarea 6.3): `usePermisos()` es la única fuente
 * de permisos de `/admin`. `tiene()` falla cerrada mientras carga y ante
 * un error, nunca falla abierta (fail-closed, B1).
 */
describe('usePermisos (tarea 6.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('estado "cargando" y tiene() falso en falso mientras la consulta está pendiente', () => {
    apiFetchMock.mockReturnValue(new Promise(() => {})) // nunca resuelve
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    expect(result.current.estado).toBe('cargando')
    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(false)
  })

  it('estado "listo" y tiene() según los permisos de la respuesta', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    await waitFor(() => expect(result.current.estado).toBe('listo'))

    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(true)
    expect(result.current.tiene('GESTIONAR_DISPOSITIVOS')).toBe(false)
    expect(result.current.yo).toEqual(YO_ADMINISTRACION)
  })

  it('estado "error" y tiene() falso (falla cerrada) cuando la consulta falla', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(500, { title: 'Error del servidor.' }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    await waitFor(() => expect(result.current.estado).toBe('error'))

    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(false)
  })

  it('reintentar() vuelve a pedir /yo tras un error', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(500, { title: 'Error del servidor.' }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    await waitFor(() => expect(result.current.estado).toBe('error'))

    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))
    result.current.reintentar()

    await waitFor(() => expect(result.current.estado).toBe('listo'))
    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(true)
  })

  /**
   * `design.md`, Risks ("Doble pedido de `/yo` al recargar la página"),
   * tarea 6.5: al recargar, la consulta `['yo']` puede recibir un 401 que
   * dispara la renovación del token; `AdminScreen` invalida `['yo']` con
   * `cancelRefetch: false` justo cuando esa misma consulta todavía está
   * en vuelo (fue ella la que causó la renovación). El resultado debe ser
   * un solo pedido exitoso, no dos.
   */
  it('invalidar ["yo"] con cancelRefetch: false mientras la consulta está en vuelo no duplica el pedido', async () => {
    let resolverPedido: ((valor: unknown) => void) | undefined
    apiFetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolverPedido = resolve
        }),
    )
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    expect(result.current.estado).toBe('cargando')
    expect(apiFetchMock).toHaveBeenCalledTimes(1)

    // Simula lo que hace `AdminScreen` al renovarse el token mientras el
    // pedido original de `/yo` todavía no resolvió.
    void queryClient.invalidateQueries({ queryKey: ['yo'] }, { cancelRefetch: false })

    resolverPedido?.(respuesta(200, YO_ADMINISTRACION))

    await waitFor(() => expect(result.current.estado).toBe('listo'))
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(true)
  })

  /**
   * Spec `identidad/permisos-efectivos`, escenario "Los permisos no
   * quedan en el almacenamiento del navegador" (tarea 6.6): la respuesta
   * de `/yo` vive solo en la caché en memoria de TanStack Query, igual
   * que el access token (ADR-027, ADR-017).
   */
  it('tras cargar /yo, ninguna clave de localStorage ni sessionStorage contiene la respuesta', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, YO_ADMINISTRACION))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    await waitFor(() => expect(result.current.estado).toBe('listo'))

    for (const almacen of [window.localStorage, window.sessionStorage]) {
      for (let i = 0; i < almacen.length; i += 1) {
        const clave = almacen.key(i) as string
        const valor = almacen.getItem(clave) ?? ''
        expect(valor).not.toContain('GESTIONAR_CATALOGO')
        expect(valor).not.toContain(YO_ADMINISTRACION.usuario.id)
      }
    }
  })
})

/**
 * Corte determinístico de la sesión terminada (tarea 11.2, B1).
 *
 * Los tests de arriba arman su `QueryClient` con `retry: false`, así que
 * ninguno ejercita el valor por defecto de TanStack Query. Este bloque usa
 * un `QueryClient` pelado a propósito: sin `retry: false` explícito, un 401
 * de `/yo` queda reintentándose con el backoff por defecto (1 s + 2 s + 4 s
 * en `QueryClient` de TanStack Query v5) y el aviso "Iniciar sesión" --que
 * solo se muestra con `estado === 'error'`-- tarda 7 segundos en aparecer,
 * o nunca aparece si otra renovación vuelve a fallar mientras tanto. El
 * error de una consulta de sesión no se reintenta solo: reintentar es
 * explícito, con el botón **Reintentar** del encabezado.
 */
describe('usePermisos: sin reintentos automáticos (tarea 11.2, B1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('ante un 401, la consulta falla en el primer intento y no reintenta', async () => {
    apiFetchMock.mockResolvedValue(respuesta(401, { title: 'No autenticado.', codigo: 'IDENTIDAD_ACCESS_TOKEN_INVALIDO' }))
    const queryClient = new QueryClient() // sin `defaultOptions`: valores de producción
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    await waitFor(() => expect(result.current.estado).toBe('error'))

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(result.current.error?.status).toBe(401)
    expect(result.current.tiene('GESTIONAR_CATALOGO')).toBe(false)
  })

  it('ante un error de red sin estado HTTP, tampoco reintenta', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const queryClient = new QueryClient()
    const { result } = renderHook(() => usePermisos(), { wrapper: envolvedor(queryClient) })

    await waitFor(() => expect(result.current.estado).toBe('error'))

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    // Sin `status` no hay forma de saber si la sesión terminó: el
    // encabezado ofrece Reintentar, no iniciar sesión.
    expect(result.current.error).toBeUndefined()
  })
})
