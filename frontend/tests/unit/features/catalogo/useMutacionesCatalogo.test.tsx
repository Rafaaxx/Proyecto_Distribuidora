import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { useCrearCategoria, useModificarCategoria } from '../../../../src/features/catalogo/useMutacionesCatalogo'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const CATEGORIA = {
  id: '11111111-1111-1111-1111-111111111111',
  nombre: 'Bebidas',
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

function envoltorio() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
    queryClient,
  }
}

/**
 * Tarea 10.2: el `Operation-Id` de un envío se conserva en el reintento
 * (INV-06). El bus de comandos trata un reenvío con el mismo
 * `Operation-Id` como la MISMA operación (`04-pipeline-comandos` D4/D7):
 * si el reintento generara uno nuevo, un error de red duplicaría la
 * categoría en vez de deduplicarse.
 */
describe('useCrearCategoria: Operation-Id en reintentos (tarea 10.2, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('reenvía el mismo Operation-Id cuando el primer intento falla por error de red', async () => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(respuesta(201, CATEGORIA))

    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearCategoria(), { wrapper })

    result.current.mutate({ nombre: 'Bebidas' })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(2)

    const [, primerasOpciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    const [, segundasOpciones] = apiFetchMock.mock.calls[1] as [string, RequestInit]
    const primerId = new Headers(primerasOpciones.headers).get('Operation-Id')
    const segundoId = new Headers(segundasOpciones.headers).get('Operation-Id')

    expect(primerId).toBeTruthy()
    expect(segundoId).toBe(primerId)
  })

  it('dos envíos distintos (dos llamadas a mutate) usan Operation-Id distintos', async () => {
    apiFetchMock.mockResolvedValue(respuesta(201, CATEGORIA))

    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearCategoria(), { wrapper })

    result.current.mutate({ nombre: 'Bebidas' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [, primerasOpciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    const primerId = new Headers(primerasOpciones.headers).get('Operation-Id')

    result.current.mutate({ nombre: 'Gaseosas' })
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))
    const [, segundasOpciones] = apiFetchMock.mock.calls[1] as [string, RequestInit]
    const segundoId = new Headers(segundasOpciones.headers).get('Operation-Id')

    expect(segundoId).not.toBe(primerId)
  })

  it('al aceptarse, invalida la clave de categorías', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, CATEGORIA))
    const { wrapper, queryClient } = envoltorio()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useCrearCategoria(), { wrapper })
    result.current.mutate({ nombre: 'Bebidas' })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['catalogo', 'categorias'] })
  })
})

describe('useModificarCategoria (tarea 10.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('envía PUT con el id de la categoría en la ruta', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { ...CATEGORIA, nombre: 'Bebidas sin alcohol' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useModificarCategoria(), { wrapper })

    result.current.mutate({ categoriaId: CATEGORIA.id, nombre: 'Bebidas sin alcohol', activo: true })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [ruta, opciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(ruta).toBe(`/catalogo/categorias/${CATEGORIA.id}`)
    expect(opciones.method).toBe('PUT')
  })
})
