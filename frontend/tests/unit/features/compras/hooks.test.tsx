import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeCompras, PermisoRequeridoComprasError } from '../../../../src/features/compras/errores'
import {
  useAnularCompra,
  useCompra,
  useCompras,
  useConfirmarCompra,
  useMediosPago,
  useMotivos,
} from '../../../../src/features/compras/hooks'
import { useOperationIdPorContenido } from '../../../../src/features/compras/useOperationIdPorContenido'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const COMPRA = '11111111-1111-4111-8111-111111111111'
const PROVEEDOR = '22222222-2222-4222-8222-222222222222'
const UBICACION = '33333333-3333-4333-8333-333333333333'
const PRODUCTO = '44444444-4444-4444-8444-444444444444'
const PRESENTACION = '55555555-5555-4555-8555-555555555555'
const MOTIVO = '66666666-6666-4666-8666-666666666666'

const CUERPO_COMPRA = {
  proveedor_id: PROVEEDOR,
  fecha: '2026-05-10',
  ubicacion_id: UBICACION,
  condicion: 'CREDITO',
  total_factura: '18000.00',
  lineas: [
    {
      producto_id: PRODUCTO,
      presentacion_id: PRESENTACION,
      cantidad: '1',
      valor: '18000.00',
      incluye_iva: false,
      bonificacion: '0',
    },
  ],
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

describe('lecturas de compras (tarea 11.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('useCompras manda los filtros y sigue con el cursor', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'a' }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'b' }], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(
      () =>
        useCompras({
          proveedorId: PROVEEDOR,
          estado: 'ANULADA',
          desde: '2026-05-01',
          hasta: '2026-05-31',
          numeroComprobante: 'A-0001',
        }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe('/compras')
    expect(url(0).searchParams.get('proveedor_id')).toBe(PROVEEDOR)
    expect(url(0).searchParams.get('estado')).toBe('ANULADA')
    expect(url(0).searchParams.get('desde')).toBe('2026-05-01')
    expect(url(0).searchParams.get('hasta')).toBe('2026-05-31')
    expect(url(0).searchParams.get('numero_comprobante')).toBe('A-0001')
    expect(url(1).searchParams.get('cursor')).toBe('c1')
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
  })

  it('useCompras sin filtros no manda ninguno', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    renderHook(() => useCompras(), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect([...url(0).searchParams.keys()]).toEqual(['limite'])
  })

  it('useCompra pide el detalle y no pide nada sin id', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: COMPRA }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useCompra(COMPRA), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(`/compras/${COMPRA}`)

    apiFetchMock.mockClear()
    renderHook(() => useCompra(undefined), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('useMediosPago y useMotivos leen la configuración; los motivos por ámbito', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'm', nombre: 'Efectivo', requiere_referencia: false }] }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: MOTIVO, nombre: 'Error de carga' }] }))
    const { wrapper } = envoltorio()

    const medios = renderHook(() => useMediosPago(), { wrapper })
    await waitFor(() => expect(medios.result.current.isSuccess).toBe(true))
    const motivos = renderHook(() => useMotivos('ANULACION_COMPRA'), { wrapper })
    await waitFor(() => expect(motivos.result.current.isSuccess).toBe(true))

    expect(url(0).pathname).toBe('/configuracion/medios-pago')
    expect(url(1).pathname).toBe('/configuracion/motivos')
    expect(url(1).searchParams.get('ambito')).toBe('ANULACION_COMPRA')
    expect(medios.result.current.data?.items[0]?.nombre).toBe('Efectivo')
  })

  it('un 403 de la lista se expone como falta de permiso', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useCompras(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(PermisoRequeridoComprasError)
  })
})

describe('escrituras de compras (tarea 11.1, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('useConfirmarCompra envía POST con Operation-Id, sin ese id en el cuerpo, e invalida compras y stock', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(201, {
        compra_id: COMPRA,
        total_neto: '18000.00',
        total_factura: '18000.00',
        pago_id: null,
        diferencias_de_costo: [],
      }),
    )
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useConfirmarCompra(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(CUERPO_COMPRA)
    })

    expect(url(0).pathname).toBe('/compras')
    expect(opciones(0).method).toBe('POST')
    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual(CUERPO_COMPRA)
    const claves = invalidar.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
    expect(claves.some((k) => k.includes('"compras"'))).toBe(true)
    expect(claves.some((k) => k.includes('"stock"'))).toBe(true)
  })

  it('reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(201, { compra_id: COMPRA, diferencias_de_costo: [] }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useConfirmarCompra(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(CUERPO_COMPRA)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    const primero = new Headers(opciones(0).headers).get('Operation-Id')
    expect(primero).toBeTruthy()
    expect(new Headers(opciones(1).headers).get('Operation-Id')).toBe(primero)
  })

  it('usa el operationId recibido', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { compra_id: COMPRA, diferencias_de_costo: [] }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useConfirmarCompra(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...CUERPO_COMPRA, operationId: 'op-fijo' })
    })

    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBe('op-fijo')
    expect(JSON.parse(String(opciones(0).body))).not.toHaveProperty('operationId')
  })

  it('un rechazo de línea no se reintenta y conserva código, línea y mensaje', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(422, { title: 'Cantidad inválida', codigo: 'CANTIDAD_INVALIDA', linea: 1 }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useConfirmarCompra(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync(CUERPO_COMPRA)).rejects.toMatchObject({
        codigo: 'CANTIDAD_INVALIDA',
        linea: 1,
        message: 'Cantidad inválida',
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('un rechazo sin línea deja la línea en null', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(409, { title: 'Proveedor inactivo', codigo: 'PROVEEDOR_INACTIVO' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useConfirmarCompra(), { wrapper })

    let error: unknown
    await act(async () => {
      error = await result.current.mutateAsync(CUERPO_COMPRA).catch((e: unknown) => e)
    })

    expect(error).toBeInstanceOf(ErrorDeCompras)
    expect((error as ErrorDeCompras).linea).toBeNull()
  })

  it('useAnularCompra envía POST a la anulación con motivo y devuelve_pago, y devuelve las observaciones', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, {
        compra_id: COMPRA,
        estado: 'ANULADA',
        pago_anulado: true,
        observaciones: ['ANULACION_COMPRA_SIN_RECALCULO'],
      }),
    )
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useAnularCompra(), { wrapper })

    let resultado: unknown
    await act(async () => {
      resultado = await result.current.mutateAsync({ compraId: COMPRA, motivo_id: MOTIVO, devuelve_pago: true })
    })

    expect(url(0).pathname).toBe(`/compras/${COMPRA}/anulacion`)
    expect(opciones(0).method).toBe('POST')
    expect(new Headers(opciones(0).headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual({ motivo_id: MOTIVO, devuelve_pago: true })
    expect((resultado as { observaciones: string[] }).observaciones).toEqual(['ANULACION_COMPRA_SIN_RECALCULO'])
    const claves = invalidar.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
    expect(claves.some((k) => k.includes('"compras"'))).toBe(true)
  })

  it('anular una compra a crédito no manda devuelve_pago', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, { compra_id: COMPRA, estado: 'ANULADA', pago_anulado: false, observaciones: [] }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAnularCompra(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ compraId: COMPRA, motivo_id: MOTIVO })
    })

    expect(JSON.parse(String(opciones(0).body))).toEqual({ motivo_id: MOTIVO })
  })
})

describe('useOperationIdPorContenido (INV-06: mismo id para el mismo contenido)', () => {
  it('conserva el id mientras el contenido no cambia, aunque cambie la referencia', () => {
    const { result, rerender } = renderHook(({ contenido }) => useOperationIdPorContenido(contenido), {
      initialProps: { contenido: { a: 1, lineas: [{ b: 2 }] } },
    })
    const primero = result.current

    rerender({ contenido: { a: 1, lineas: [{ b: 2 }] } })

    expect(result.current).toBe(primero)
  })

  it('genera un id nuevo cuando cambia el contenido y vuelve a conservarlo', () => {
    const { result, rerender } = renderHook(({ contenido }) => useOperationIdPorContenido(contenido), {
      initialProps: { contenido: { a: 1 } },
    })
    const primero = result.current

    rerender({ contenido: { a: 2 } })
    const segundo = result.current
    rerender({ contenido: { a: 2 } })

    expect(segundo).not.toBe(primero)
    expect(result.current).toBe(segundo)
  })
})
