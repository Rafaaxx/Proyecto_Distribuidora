import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeStock, PermisoRequeridoStockError } from '../../../../src/features/stock/errores'
import {
  useCostoPromedio,
  useCrearUbicacion,
  useKardex,
  useModificarUbicacion,
  useRegistrarStockInicial,
  useSaldos,
  useUbicaciones,
} from '../../../../src/features/stock/hooks'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const ID = '11111111-1111-4111-8111-111111111111'
const PRODUCTO = '22222222-2222-4222-8222-222222222222'

function envoltorio() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  }
}

function url(indice: number): URL {
  return new URL(String(apiFetchMock.mock.calls[indice]?.[0]), 'http://x')
}

function opciones(indice: number): RequestInit {
  return apiFetchMock.mock.calls[indice]?.[1] as RequestInit
}

describe('lecturas de stock (tarea 8.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('useUbicaciones pide el listado con el filtro de estado y sigue con el cursor', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'a' }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'b' }], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useUbicaciones(true), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe('/stock/ubicaciones')
    expect(url(0).searchParams.get('activo')).toBe('true')
    expect(url(1).searchParams.get('cursor')).toBe('c1')
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
  })

  it('useUbicaciones sin filtro no manda activo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    renderHook(() => useUbicaciones(undefined), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(url(0).searchParams.has('activo')).toBe(false)
  })

  it('useSaldos pide los saldos de la ubicación', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    renderHook(() => useSaldos(ID), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(url(0).pathname).toBe(`/stock/ubicaciones/${ID}/saldos`)
  })

  it('useKardex manda producto, ubicación y período', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, { saldo_anterior: 0, saldo_actual: 0, zona_horaria: 'UTC', items: [], cursor_siguiente: null }),
    )
    const { wrapper } = envoltorio()

    renderHook(() => useKardex(PRODUCTO, ID, { desde: '2026-04-01', hasta: '2026-04-30' }), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(url(0).pathname).toBe('/stock/kardex')
    expect(url(0).searchParams.get('producto_id')).toBe(PRODUCTO)
    expect(url(0).searchParams.get('ubicacion_id')).toBe(ID)
    expect(url(0).searchParams.get('desde')).toBe('2026-04-01')
    expect(url(0).searchParams.get('hasta')).toBe('2026-04-30')
  })

  it('useCostoPromedio lee la ruta de catalogo y no pide nada si está deshabilitado', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, { producto_id: PRODUCTO, costo_promedio: '1050.000000', stock_total: 120 }),
    )
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useCostoPromedio(PRODUCTO, true), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(`/catalogo/productos/${PRODUCTO}/costo`)
    expect(result.current.data?.costo_promedio).toBe('1050.000000')

    apiFetchMock.mockClear()
    renderHook(() => useCostoPromedio(PRODUCTO, false), { wrapper })
    await new Promise((r) => setTimeout(r, 20))
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('un 403 y un 404 se exponen como errores de dominio con su código', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Falta el permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useSaldos(ID), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(PermisoRequeridoStockError)

    apiFetchMock.mockResolvedValueOnce(respuesta(404, { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' }))
    const otro = renderHook(() => useSaldos('otro'), { wrapper })
    await waitFor(() => expect(otro.result.current.isError).toBe(true))
    expect((otro.result.current.error as ErrorDeStock).codigo).toBe('RECURSO_NO_ENCONTRADO')
  })
})

describe('escrituras de stock (tarea 8.1, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('useCrearUbicacion envía POST con Operation-Id e invalida el listado', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { id: ID }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useCrearUbicacion(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ nombre: 'Camión 1', tipo: 'VEHICULO', requiere_toma: true })
    })

    expect(url(0).pathname).toBe('/stock/ubicaciones')
    expect(opciones(0).method).toBe('POST')
    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual({
      nombre: 'Camión 1',
      tipo: 'VEHICULO',
      requiere_toma: true,
    })
    expect(invalidar).toHaveBeenCalled()
  })

  it('useModificarUbicacion envía PUT a la ubicación', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: ID }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useModificarUbicacion(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        ubicacionId: ID,
        nombre: 'N',
        tipo: 'DEPOSITO',
        requiere_toma: false,
        activo: false,
      })
    })

    expect(url(0).pathname).toBe(`/stock/ubicaciones/${ID}`)
    expect(opciones(0).method).toBe('PUT')
    expect(JSON.parse(String(opciones(0).body))).toEqual({
      nombre: 'N',
      tipo: 'DEPOSITO',
      requiere_toma: false,
      activo: false,
    })
  })

  it('useRegistrarStockInicial reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(201, { ubicacion_id: ID, lineas: [] }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarStockInicial(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ubicacion_id: ID, lineas: [] })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    const primero = new Headers(opciones(0).headers).get('Operation-Id')
    expect(primero).toBeTruthy()
    expect(new Headers(opciones(1).headers).get('Operation-Id')).toBe(primero)
    expect(url(0).pathname).toBe('/stock/iniciales')
  })

  it('usa el operationId que se le pasa y no lo manda en el cuerpo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { ubicacion_id: ID, lineas: [] }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarStockInicial(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ubicacion_id: ID, lineas: [], operationId: 'op-fijo' })
    })

    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBe('op-fijo')
    expect(JSON.parse(String(opciones(0).body))).toEqual({ ubicacion_id: ID, lineas: [] })
  })

  it('un rechazo del servidor no se reintenta y conserva su código', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(409, { title: 'Stock insuficiente', codigo: 'STOCK_INSUFICIENTE' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarStockInicial(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ ubicacion_id: ID, lineas: [] })).rejects.toMatchObject({
        codigo: 'STOCK_INSUFICIENTE',
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('al aceptarse un stock inicial invalida saldos, kardex y costos', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { ubicacion_id: ID, lineas: [] }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useRegistrarStockInicial(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ubicacion_id: ID, lineas: [] })
    })

    const claves = invalidar.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
    expect(claves.some((k) => k.includes('"stock"'))).toBe(true)
    expect(claves.some((k) => k.includes('costo'))).toBe(true)
  })
})
