import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { useProductosDelProveedor } from '../../../../src/features/catalogo/useListados'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PROVEEDOR = '22222222-2222-4222-8222-222222222222'

function envoltorio() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

function url(indice: number): URL {
  return new URL(String(apiFetchMock.mock.calls[indice]?.[0]), 'http://x')
}

describe('useProductosDelProveedor (change 11, D17 / tarea 11.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('pide los activos del proveedor y recorre todas las páginas hasta el final', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'a', nombre: 'A' }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'b', nombre: 'B' }], cursor_siguiente: 'c2' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'c', nombre: 'C' }], cursor_siguiente: null }))

    const { result } = renderHook(() => useProductosDelProveedor(PROVEEDOR), { wrapper: envoltorio() })

    await waitFor(() => expect(result.current.cargando).toBe(false))
    expect(result.current.productos.map((p) => p.id)).toEqual(['a', 'b', 'c'])
    expect(apiFetchMock).toHaveBeenCalledTimes(3)
    expect(url(0).pathname).toBe('/catalogo/productos')
    expect(url(0).searchParams.get('proveedor_id')).toBe(PROVEEDOR)
    expect(url(0).searchParams.get('activo')).toBe('true')
    expect(url(2).searchParams.get('cursor')).toBe('c2')
  })

  it('sin proveedor no pide nada y devuelve una lista vacía', () => {
    const { result } = renderHook(() => useProductosDelProveedor(undefined), { wrapper: envoltorio() })

    expect(apiFetchMock).not.toHaveBeenCalled()
    expect(result.current.productos).toEqual([])
    expect(result.current.cargando).toBe(false)
  })
})
