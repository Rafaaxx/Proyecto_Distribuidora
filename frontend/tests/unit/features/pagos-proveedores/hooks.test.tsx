import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDePagos, PermisoRequeridoPagosError } from '../../../../src/features/pagos-proveedores/errores'
import {
  useAnularPago,
  usePago,
  usePagos,
  useRegistrarPago,
  useSaldoDelProveedor,
} from '../../../../src/features/pagos-proveedores/hooks'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PAGO = '11111111-1111-4111-8111-111111111111'
const PROVEEDOR = '22222222-2222-4222-8222-222222222222'
const EFECTIVO = '33333333-3333-4333-8333-333333333333'
const MOTIVO = '66666666-6666-4666-8666-666666666666'

const CUERPO_PAGO = {
  proveedor_id: PROVEEDOR,
  fecha: '2026-10-05',
  importe: '100000.00',
  observacion: null,
  medios: [{ medio_pago_id: EFECTIVO, importe: '100000.00', referencia: null }],
}

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

function clavesInvalidadas(spy: ReturnType<typeof vi.spyOn>): string[] {
  return spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
}

describe('lecturas de pagos a proveedores (tarea 8.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('usePagos manda los filtros y sigue con el cursor', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ pago_id: 'a' }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ pago_id: 'b' }], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(
      () =>
        usePagos({
          proveedorId: PROVEEDOR,
          estado: 'ANULADA',
          origen: 'INDEPENDIENTE',
          desde: '2026-10-01',
          hasta: '2026-10-31',
        }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe('/pagos-proveedores')
    expect(url(0).searchParams.get('proveedor_id')).toBe(PROVEEDOR)
    expect(url(0).searchParams.get('estado')).toBe('ANULADA')
    expect(url(0).searchParams.get('origen')).toBe('INDEPENDIENTE')
    expect(url(0).searchParams.get('desde')).toBe('2026-10-01')
    expect(url(0).searchParams.get('hasta')).toBe('2026-10-31')
    expect(url(1).searchParams.get('cursor')).toBe('c1')
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
  })

  it('usePagos sin filtros solo manda el límite', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    renderHook(() => usePagos(), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect([...url(0).searchParams.keys()]).toEqual(['limite'])
  })

  it('usePago pide el detalle y no pide nada sin id', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { pago_id: PAGO }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => usePago(PAGO), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(`/pagos-proveedores/${PAGO}`)

    apiFetchMock.mockClear()
    renderHook(() => usePago(undefined), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('useSaldoDelProveedor devuelve el saldo como string y no pide nada sin proveedor', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { saldo: '153720.00' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useSaldoDelProveedor(PROVEEDOR), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(`/proveedores/${PROVEEDOR}/saldo`)
    expect(result.current.data).toBe('153720.00')

    apiFetchMock.mockClear()
    renderHook(() => useSaldoDelProveedor(undefined), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('un 403 del listado se expone como falta de permiso', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => usePagos(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(PermisoRequeridoPagosError)
  })
})

describe('registrar un pago (tarea 8.2, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('envía POST con Operation-Id y sin ese id en el cuerpo, e invalida pagos, cuentas corrientes y saldo del proveedor', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(201, { pago_id: PAGO, estado: 'CONFIRMADA', importe: '100000.00', saldo: '53720.00' }),
    )
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useRegistrarPago(), { wrapper })

    let resultado: unknown
    await act(async () => {
      resultado = await result.current.mutateAsync(CUERPO_PAGO)
    })

    expect(url(0).pathname).toBe('/pagos-proveedores')
    expect(opciones(0).method).toBe('POST')
    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual(CUERPO_PAGO)
    expect((resultado as { saldo: string }).saldo).toBe('53720.00')
    const claves = clavesInvalidadas(invalidar)
    expect(claves).toContain('["pagos-proveedores"]')
    expect(claves).toContain('["cuentas-corrientes"]')
    expect(claves).toContain('["saldo-proveedor"]')
  })

  it('reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(201, { pago_id: PAGO, estado: 'CONFIRMADA', importe: '100000.00', saldo: '0.00' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarPago(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(CUERPO_PAGO)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    const primero = new Headers(opciones(0).headers).get('Operation-Id')
    expect(primero).toBeTruthy()
    expect(new Headers(opciones(1).headers).get('Operation-Id')).toBe(primero)
  })

  it('usa el operationId recibido y, sin él, genera uno distinto en cada envío', async () => {
    apiFetchMock.mockResolvedValue(respuesta(201, { pago_id: PAGO, estado: 'CONFIRMADA', importe: '1.00', saldo: '0.00' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarPago(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...CUERPO_PAGO, operationId: 'op-fijo' })
    })
    await act(async () => {
      await result.current.mutateAsync(CUERPO_PAGO)
    })
    await act(async () => {
      await result.current.mutateAsync(CUERPO_PAGO)
    })

    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBe('op-fijo')
    expect(JSON.parse(String(opciones(0).body))).not.toHaveProperty('operationId')
    const segundo = new Headers(opciones(1).headers).get('Operation-Id')
    const tercero = new Headers(opciones(2).headers).get('Operation-Id')
    expect(segundo).toBeTruthy()
    expect(tercero).toBeTruthy()
    expect(tercero).not.toBe(segundo)
  })

  it('un rechazo de un medio no se reintenta y conserva código, índice del medio y mensaje', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(422, { title: 'Medio 1: el medio de pago está inactivo', codigo: 'MEDIO_PAGO_INACTIVO', medio: 1 }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarPago(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync(CUERPO_PAGO)).rejects.toMatchObject({
        codigo: 'MEDIO_PAGO_INACTIVO',
        medio: 1,
        message: 'Medio 1: el medio de pago está inactivo',
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('un rechazo sin medio deja el índice en null', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(422, { title: 'Los medios no suman', codigo: 'MEDIOS_NO_SUMAN_IMPORTE' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarPago(), { wrapper })

    let error: unknown
    await act(async () => {
      error = await result.current.mutateAsync(CUERPO_PAGO).catch((e: unknown) => e)
    })

    expect(error).toBeInstanceOf(ErrorDePagos)
    expect((error as ErrorDePagos).medio).toBeNull()
  })

  it('un 403 se expone como falta de permiso', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarPago(), { wrapper })

    let error: unknown
    await act(async () => {
      error = await result.current.mutateAsync(CUERPO_PAGO).catch((e: unknown) => e)
    })

    expect(error).toBeInstanceOf(PermisoRequeridoPagosError)
  })
})

describe('anular un pago (tarea 8.2, PAG-03)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('envía POST a la anulación con el motivo e invalida pagos, compras, cuentas corrientes y saldo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { pago_id: PAGO, estado: 'ANULADA', saldo: '152460.00' }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useAnularPago(), { wrapper })

    let resultado: unknown
    await act(async () => {
      resultado = await result.current.mutateAsync({ pagoId: PAGO, motivo_id: MOTIVO })
    })

    expect(url(0).pathname).toBe(`/pagos-proveedores/${PAGO}/anulacion`)
    expect(opciones(0).method).toBe('POST')
    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual({ motivo_id: MOTIVO })
    expect((resultado as { saldo: string }).saldo).toBe('152460.00')
    const claves = clavesInvalidadas(invalidar)
    expect(claves).toContain('["pagos-proveedores"]')
    expect(claves).toContain('["compras"]')
    expect(claves).toContain('["cuentas-corrientes"]')
    expect(claves).toContain('["saldo-proveedor"]')
  })

  it('reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(200, { pago_id: PAGO, estado: 'ANULADA', saldo: '0.00' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAnularPago(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ pagoId: PAGO, motivo_id: MOTIVO })
    })

    const primero = new Headers(opciones(0).headers).get('Operation-Id')
    expect(primero).toBeTruthy()
    expect(new Headers(opciones(1).headers).get('Operation-Id')).toBe(primero)
  })

  it('PAGO_YA_ANULADO no se reintenta y conserva su código', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(409, { title: 'El pago ya está anulado', codigo: 'PAGO_YA_ANULADO' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAnularPago(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ pagoId: PAGO, motivo_id: MOTIVO })).rejects.toMatchObject({
        codigo: 'PAGO_YA_ANULADO',
        message: 'El pago ya está anulado',
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })
})
