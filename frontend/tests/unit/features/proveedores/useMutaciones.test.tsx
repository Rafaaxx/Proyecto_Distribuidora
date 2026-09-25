import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { useCrearProveedor, useInformarCostos } from '../../../../src/features/proveedores/useMutaciones'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PROVEEDOR = {
  id: '11111111-1111-1111-1111-111111111111',
  nombre: 'Bodega Andina',
  cuit: null,
  contacto: null,
  telefono: null,
  email: null,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const COSTO_RESULTADO = {
  costos: [{ id: '22222222-2222-2222-2222-222222222222', costo_base: '1500.000000' }],
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
 * Tarea 11.2: el `Operation-Id` de un envío se conserva en el reintento
 * (INV-06), mismo criterio que `useMutacionesCatalogo.test.tsx`.
 */
describe('useCrearProveedor: Operation-Id en reintentos (tarea 11.2, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('reenvía el mismo Operation-Id cuando el primer intento falla por error de red', async () => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(respuesta(201, PROVEEDOR))

    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearProveedor(), { wrapper })

    result.current.mutate({ nombre: 'Bodega Andina' })

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
    apiFetchMock.mockResolvedValue(respuesta(201, PROVEEDOR))

    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearProveedor(), { wrapper })

    result.current.mutate({ nombre: 'Bodega Andina' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [, primerasOpciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    const primerId = new Headers(primerasOpciones.headers).get('Operation-Id')

    result.current.mutate({ nombre: 'Bodega Sur' })
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))
    const [, segundasOpciones] = apiFetchMock.mock.calls[1] as [string, RequestInit]
    const segundoId = new Headers(segundasOpciones.headers).get('Operation-Id')

    expect(segundoId).not.toBe(primerId)
  })

  it('un rechazo de dominio (409 NOMBRE_DUPLICADO) NO se reintenta (tarea 14.2, bug 13.5)', async () => {
    apiFetchMock.mockResolvedValue(respuesta(409, { title: 'El nombre ya está en uso.', codigo: 'NOMBRE_DUPLICADO' }))

    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearProveedor(), { wrapper })

    result.current.mutate({ nombre: 'Bodega Andina' })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('al aceptarse, invalida el listado y las opciones de proveedores', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, PROVEEDOR))
    const { wrapper, queryClient } = envoltorio()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { result } = renderHook(() => useCrearProveedor(), { wrapper })
    result.current.mutate({ nombre: 'Bodega Andina' })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['proveedores', 'listado', {}] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['proveedores', 'opciones'] })
  })
})

describe('useInformarCostos (tarea 11.2, CST-05)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('reenvía el mismo Operation-Id cuando el primer intento falla por error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(201, COSTO_RESULTADO))

    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useInformarCostos(), { wrapper })

    result.current.mutate({
      proveedor_id: PROVEEDOR.id,
      costos: [
        {
          producto_id: '33333333-3333-3333-3333-333333333333',
          presentacion_id: '44444444-4444-4444-4444-444444444444',
          valor: '18000.00',
          incluye_iva: false,
          bonificacion: '0',
          vigencia_desde: '2026-09-24',
        },
      ],
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    const [, primerasOpciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    const [, segundasOpciones] = apiFetchMock.mock.calls[1] as [string, RequestInit]
    expect(new Headers(segundasOpciones.headers).get('Operation-Id')).toBe(
      new Headers(primerasOpciones.headers).get('Operation-Id'),
    )
  })

  it('al aceptarse, invalida el historial del producto informado', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, COSTO_RESULTADO))
    const { wrapper, queryClient } = envoltorio()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const productoId = '33333333-3333-3333-3333-333333333333'

    const { result } = renderHook(() => useInformarCostos(), { wrapper })
    result.current.mutate({
      proveedor_id: PROVEEDOR.id,
      costos: [
        {
          producto_id: productoId,
          presentacion_id: '44444444-4444-4444-4444-444444444444',
          valor: '18000.00',
          incluye_iva: false,
          bonificacion: '0',
          vigencia_desde: '2026-09-24',
        },
      ],
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['proveedores', 'costos', 'historial', productoId],
    })
  })
})
