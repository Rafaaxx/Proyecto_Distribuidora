import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import {
  ErrorDeStock,
  PermisoRequeridoStockError,
  mensajeDeErrorDeStock,
} from '../../../../src/features/stock/errores'
import {
  useAjuste,
  useAjustes,
  useAnularAjuste,
  useAnularTransferencia,
  useMotivosDeStock,
  useRegistrarAjuste,
  useRegistrarTransferencia,
  useSaldosCompletos,
  useTransferencia,
  useTransferencias,
} from '../../../../src/features/stock/hooks'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const ORIGEN = '11111111-1111-4111-8111-111111111111'
const DESTINO = '22222222-2222-4222-8222-222222222222'
const PRODUCTO = '33333333-3333-4333-8333-333333333333'
const MOTIVO = '44444444-4444-4444-8444-444444444444'
const OPERACION = '55555555-5555-4555-8555-555555555555'

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

function operationId(indice: number): string | null {
  return new Headers(opciones(indice).headers).get('Operation-Id')
}

const PAGINA_VACIA = { items: [], cursor_siguiente: null }

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('lecturas de transferencias y ajustes (tarea 12.2)', () => {
  it('useTransferencias manda ubicación y fechas, y sigue con el cursor', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'a' }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'b' }], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(
      () => useTransferencias({ ubicacionId: ORIGEN, desde: '2026-04-01', hasta: '2026-04-30' }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe('/stock/transferencias')
    expect(url(0).searchParams.get('ubicacion_id')).toBe(ORIGEN)
    expect(url(0).searchParams.get('desde')).toBe('2026-04-01')
    expect(url(0).searchParams.get('hasta')).toBe('2026-04-30')
    expect(url(1).searchParams.get('cursor')).toBe('c1')
  })

  it('useTransferencias sin filtros no manda ninguno', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, PAGINA_VACIA))
    const { wrapper } = envoltorio()

    renderHook(() => useTransferencias({}), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(url(0).searchParams.has('ubicacion_id')).toBe(false)
    expect(url(0).searchParams.has('desde')).toBe(false)
  })

  it('useAjustes suma el filtro de motivo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, PAGINA_VACIA))
    const { wrapper } = envoltorio()

    renderHook(() => useAjustes({ ubicacionId: ORIGEN, motivoId: MOTIVO }), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(url(0).pathname).toBe('/stock/ajustes')
    expect(url(0).searchParams.get('motivo_id')).toBe(MOTIVO)
    expect(url(0).searchParams.get('ubicacion_id')).toBe(ORIGEN)
  })

  it('useTransferencia y useAjuste piden el detalle por id y no piden nada sin id', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { id: OPERACION }))
    const { wrapper } = envoltorio()

    renderHook(() => useTransferencia(OPERACION), { wrapper })
    renderHook(() => useAjuste(OPERACION), { wrapper })
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))
    expect(url(0).pathname).toBe(`/stock/transferencias/${OPERACION}`)
    expect(url(1).pathname).toBe(`/stock/ajustes/${OPERACION}`)

    apiFetchMock.mockClear()
    renderHook(() => useTransferencia(undefined), { wrapper })
    renderHook(() => useAjuste(undefined), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it.each(['AJUSTE_STOCK', 'ANULACION_TRANSFERENCIA', 'ANULACION_AJUSTE'] as const)(
    'useMotivosDeStock pide los motivos del ámbito %s',
    async (ambito) => {
      apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [{ id: MOTIVO, nombre: 'Rotura' }] }))
      const { wrapper } = envoltorio()

      const { result } = renderHook(() => useMotivosDeStock(ambito), { wrapper })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(url(0).pathname).toBe('/configuracion/motivos')
      expect(url(0).searchParams.get('ambito')).toBe(ambito)
    },
  )

  it('useSaldosCompletos recorre todas las páginas de saldos de la ubicación', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ producto_id: 'a', cantidad_base: 1 }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ producto_id: 'b', cantidad_base: 2 }], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useSaldosCompletos(ORIGEN), { wrapper })

    await waitFor(() => expect(result.current.completo).toBe(true))
    expect(result.current.lineas.map((l) => l.producto_id)).toEqual(['a', 'b'])
    expect(url(1).searchParams.get('cursor')).toBe('c1')
  })

  it('useSaldosCompletos sin ubicación no pide nada', () => {
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useSaldosCompletos(undefined), { wrapper })

    expect(apiFetchMock).not.toHaveBeenCalled()
    expect(result.current.lineas).toEqual([])
    expect(result.current.completo).toBe(false)
  })
})

describe('escrituras de transferencias y ajustes (tarea 12.2)', () => {
  const CUERPO_TRANSFERENCIA = {
    ubicacion_origen_id: ORIGEN,
    ubicacion_destino_id: DESTINO,
    lineas: [{ producto_id: PRODUCTO, cantidad_base: 48 }],
  }
  const CUERPO_AJUSTE = { ubicacion_id: ORIGEN, motivo_id: MOTIVO, lineas: [{ producto_id: PRODUCTO, cantidad_base: -6 }] }

  it('registrar una transferencia hace POST con Operation-Id, sin mandarlo en el cuerpo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { id: OPERACION }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarTransferencia(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...CUERPO_TRANSFERENCIA, operationId: 'op-fijo' })
    })

    expect(url(0).pathname).toBe('/stock/transferencias')
    expect(opciones(0).method).toBe('POST')
    expect(operationId(0)).toBe('op-fijo')
    expect(JSON.parse(String(opciones(0).body))).toEqual(CUERPO_TRANSFERENCIA)
  })

  it('registrar un ajuste hace POST a /stock/ajustes', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { id: OPERACION }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarAjuste(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...CUERPO_AJUSTE })
    })

    expect(url(0).pathname).toBe('/stock/ajustes')
    expect(opciones(0).method).toBe('POST')
    expect(JSON.parse(String(opciones(0).body))).toEqual(CUERPO_AJUSTE)
  })

  it.each([
    ['transferencia', () => useRegistrarTransferencia(), CUERPO_TRANSFERENCIA],
    ['ajuste', () => useRegistrarAjuste(), CUERPO_AJUSTE],
  ] as const)('el reintento tras un error de red de un %s reenvía el mismo Operation-Id', async (_nombre, usar, cuerpo) => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(respuesta(201, { id: OPERACION }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => usar() as ReturnType<typeof useRegistrarAjuste>, { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...(cuerpo as typeof CUERPO_AJUSTE) })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(operationId(0)).toBeTruthy()
    expect(operationId(1)).toBe(operationId(0))
  })

  it('dos envíos distintos sin operationId explícito usan Operation-Id distintos', async () => {
    apiFetchMock.mockResolvedValue(respuesta(201, { id: OPERACION }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarTransferencia(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...CUERPO_TRANSFERENCIA })
    })
    await act(async () => {
      await result.current.mutateAsync({ ...CUERPO_TRANSFERENCIA })
    })

    expect(operationId(1)).not.toBe(operationId(0))
  })

  it('anular una transferencia hace POST a su anulación con el motivo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: OPERACION, estado: 'ANULADA' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAnularTransferencia(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: OPERACION, motivo_id: MOTIVO, operationId: 'op-anular' })
    })

    expect(url(0).pathname).toBe(`/stock/transferencias/${OPERACION}/anulacion`)
    expect(opciones(0).method).toBe('POST')
    expect(operationId(0)).toBe('op-anular')
    expect(JSON.parse(String(opciones(0).body))).toEqual({ motivo_id: MOTIVO })
  })

  it('anular un ajuste hace POST a su anulación con el motivo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: OPERACION, estado: 'ANULADA' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAnularAjuste(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: OPERACION, motivo_id: MOTIVO })
    })

    expect(url(0).pathname).toBe(`/stock/ajustes/${OPERACION}/anulacion`)
    expect(JSON.parse(String(opciones(0).body))).toEqual({ motivo_id: MOTIVO })
  })

  it.each([
    ['registrar una transferencia', () => useRegistrarTransferencia(), { ...CUERPO_TRANSFERENCIA }],
    ['registrar un ajuste', () => useRegistrarAjuste(), { ...CUERPO_AJUSTE }],
    ['anular una transferencia', () => useAnularTransferencia(), { id: OPERACION, motivo_id: MOTIVO }],
    ['anular un ajuste', () => useAnularAjuste(), { id: OPERACION, motivo_id: MOTIVO }],
  ] as const)('al aceptarse %s invalida stock (saldos, kardex, listados, detalle) y costos', async (_nombre, usar, variables) => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: OPERACION }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => usar() as unknown as ReturnType<typeof useAnularAjuste>, { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...(variables as { id: string; motivo_id: string }) })
    })

    const claves = invalidar.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
    expect(claves).toContain('["stock"]')
    expect(claves).toContain('["costo-promedio"]')
  })

  it('un rechazo del servidor no se reintenta y conserva código y línea', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(409, { title: 'El saldo es 10', codigo: 'STOCK_INSUFICIENTE', linea: 2 }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarAjuste(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ ...CUERPO_AJUSTE })).rejects.toMatchObject({
        codigo: 'STOCK_INSUFICIENTE',
        linea: 2,
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('mensajeDeErrorDeStock (tarea 12.2)', () => {
  const error = (codigo: string) => new ErrorDeStock(codigo, 'mensaje del servidor')

  it('STOCK_INSUFICIENTE es distinto en el ajuste, la transferencia y la anulación', () => {
    const transferencia = mensajeDeErrorDeStock(error('STOCK_INSUFICIENTE'), 'transferencia')
    const ajuste = mensajeDeErrorDeStock(error('STOCK_INSUFICIENTE'), 'ajuste')
    const anulacion = mensajeDeErrorDeStock(error('STOCK_INSUFICIENTE'), 'anulacion')

    expect(ajuste).toBe('Un ajuste no puede dejar stock negativo.')
    expect(transferencia).toContain('origen')
    expect(anulacion).toContain('anular')
    expect(new Set([transferencia, ajuste, anulacion]).size).toBe(3)
  })

  it.each([
    ['UBICACIONES_IGUALES', 'El origen y el destino tienen que ser distintos.'],
    ['MOTIVO_INVALIDO', 'El motivo elegido no es válido. Elegí otro.'],
    ['PRODUCTO_INACTIVO', 'inactivo'],
    ['UBICACION_INACTIVA', 'inactiva'],
    ['TRANSFERENCIA_YA_ANULADA', 'ya fue anulada'],
    ['AJUSTE_YA_ANULADO', 'ya fue anulado'],
    ['PRODUCTO_SIN_COSTO', 'stock inicial'],
  ])('%s tiene un mensaje propio', (codigo, fragmento) => {
    expect(mensajeDeErrorDeStock(error(codigo), 'ajuste')).toContain(fragmento)
  })

  it('PRODUCTO_SIN_COSTO explica que ese stock se carga con stock inicial o con una compra', () => {
    const mensaje = mensajeDeErrorDeStock(error('PRODUCTO_SIN_COSTO'), 'ajuste')
    expect(mensaje).toContain('stock inicial')
    expect(mensaje).toContain('compra')
  })

  it('un 403 al anular explica que la transferencia es de otro usuario', () => {
    const mensaje = mensajeDeErrorDeStock(new PermisoRequeridoStockError('x'), 'anulacion')
    expect(mensaje).toContain('otro usuario')
  })

  it('un 403 fuera de la anulación usa el mensaje de permiso', () => {
    expect(mensajeDeErrorDeStock(new PermisoRequeridoStockError('x'), 'transferencia')).toBe(
      'No tenés permiso para hacer esta operación.',
    )
  })

  it('un código sin mensaje propio muestra el del servidor', () => {
    expect(mensajeDeErrorDeStock(error('LINEAS_INVALIDAS'), 'transferencia')).toBe('mensaje del servidor')
  })

  it('un corte de red avisa que se necesita conexión', () => {
    expect(mensajeDeErrorDeStock(new TypeError('Failed to fetch'), 'transferencia')).toContain('conexión')
  })

  it('un error ajeno al dominio usa el mensaje genérico', () => {
    const ajeno = Object.assign(new Error('interno'), { codigo: 'OTRO_MODULO' })
    expect(mensajeDeErrorDeStock(ajeno, 'ajuste')).toBe('No se pudo completar la operación.')
  })
})
