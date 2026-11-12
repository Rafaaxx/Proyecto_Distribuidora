import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeCuentasCorrientes } from '../../../../src/features/cuentas-corrientes/errores'
import {
  useEstadoDeCuenta,
  useRegistrarSaldoInicial,
  useSaldoActual,
} from '../../../../src/features/cuentas-corrientes/hooks'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const ID = '11111111-1111-4111-8111-111111111111'

function movimiento(id: string, saldoAcumulado: string) {
  return {
    id,
    tipo: 'SALDO_INICIAL',
    sentido: 'AUMENTA',
    importe: '100.00',
    origen_tipo: 'SALDO_INICIAL',
    origen_id: id,
    occurred_at: '2026-03-10T15:00:00Z',
    registered_at: '2026-03-10T15:00:00Z',
    usuario_id: id,
    operation_id: id,
    saldo_acumulado: saldoAcumulado,
  }
}

function pagina(items: ReturnType<typeof movimiento>[], cursor: string | null) {
  return {
    saldo_anterior: '0.00',
    saldo_actual: '200.00',
    zona_horaria: 'America/Argentina/Mendoza',
    items,
    cursor_siguiente: cursor,
  }
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

describe('useEstadoDeCuenta (tarea 7.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('pide la cuenta de un cliente con el período y sigue con el cursor de la página anterior', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, pagina([movimiento('a', '100.00')], 'cursor-1')))
      .mockResolvedValueOnce(respuesta(200, pagina([movimiento('b', '200.00')], null)))
    const { wrapper } = envoltorio()

    const { result } = renderHook(
      () => useEstadoDeCuenta('CLIENTE', ID, { desde: '2026-04-01', hasta: '2026-04-30' }),
      { wrapper },
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const primera = new URL(String(apiFetchMock.mock.calls[0]?.[0]), 'http://x')
    expect(primera.pathname).toBe(`/clientes/${ID}/cuenta-corriente`)
    expect(primera.searchParams.get('desde')).toBe('2026-04-01')
    expect(primera.searchParams.get('hasta')).toBe('2026-04-30')
    expect(primera.searchParams.get('cursor')).toBeNull()
    expect(result.current.hasNextPage).toBe(true)

    await act(async () => {
      await result.current.fetchNextPage()
    })

    const segunda = new URL(String(apiFetchMock.mock.calls[1]?.[0]), 'http://x')
    expect(segunda.searchParams.get('cursor')).toBe('cursor-1')
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
    expect(result.current.data?.pages.flatMap((p) => p.items.map((i) => i.saldo_acumulado))).toEqual([
      '100.00',
      '200.00',
    ])
    expect(result.current.hasNextPage).toBe(false)
  })

  it('la cuenta de un proveedor va a su propia ruta y sin filtros no manda desde ni hasta', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, pagina([], null)))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useEstadoDeCuenta('PROVEEDOR', ID, {}), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = new URL(String(apiFetchMock.mock.calls[0]?.[0]), 'http://x')
    expect(url.pathname).toBe(`/proveedores/${ID}/cuenta-corriente`)
    expect(url.searchParams.has('desde')).toBe(false)
    expect(url.searchParams.has('hasta')).toBe(false)
  })

  it('un 404 se expone como error de dominio con su código, no como datos', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(404, { title: 'No existe.', codigo: 'RECURSO_NO_ENCONTRADO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useEstadoDeCuenta('CLIENTE', ID, {}), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(ErrorDeCuentasCorrientes)
    expect((result.current.error as ErrorDeCuentasCorrientes).codigo).toBe('RECURSO_NO_ENCONTRADO')
  })
})

describe('useSaldoActual (tarea 7.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('pide una sola fila y devuelve el saldo actual como string', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, pagina([], null)))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useSaldoActual('CLIENTE', ID), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBe('200.00')
    const url = new URL(String(apiFetchMock.mock.calls[0]?.[0]), 'http://x')
    expect(url.searchParams.get('limite')).toBe('1')
  })
})

describe('useRegistrarSaldoInicial (tarea 7.1, INV-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  const DATOS = { cuenta_tipo: 'CLIENTE' as const, entidad_id: ID, importe: '150000.00', sentido: 'AUMENTA' as const }

  it('envía el comando con Operation-Id y reenvía el mismo tras un error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(201, { movimiento_id: ID, saldo: '150000.00' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarSaldoInicial(), { wrapper })

    result.current.mutate(DATOS)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    const [ruta, primeras] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    const [, segundas] = apiFetchMock.mock.calls[1] as [string, RequestInit]
    expect(ruta).toBe('/cuentas-corrientes/saldos-iniciales')
    expect(primeras.method).toBe('POST')
    expect(JSON.parse(String(primeras.body))).toEqual(DATOS)
    const primerId = new Headers(primeras.headers).get('Operation-Id')
    expect(primerId).toBeTruthy()
    expect(new Headers(segundas.headers).get('Operation-Id')).toBe(primerId)
  })

  it('usa el operationId que se le pasa y no lo manda en el cuerpo', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { movimiento_id: ID, saldo: '1.00' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarSaldoInicial(), { wrapper })

    result.current.mutate({ ...DATOS, operationId: 'operacion-fija' })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [, opciones] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(new Headers(opciones.headers).get('Operation-Id')).toBe('operacion-fija')
    expect(JSON.parse(String(opciones.body))).toEqual(DATOS)
  })

  it('un rechazo del servidor no se reintenta y conserva su código', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(409, { title: 'La cuenta ya tiene operaciones.', codigo: 'CUENTA_CON_OPERACIONES' }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useRegistrarSaldoInicial(), { wrapper })

    result.current.mutate(DATOS)

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect((result.current.error as ErrorDeCuentasCorrientes).codigo).toBe('CUENTA_CON_OPERACIONES')
    expect(result.current.error?.message).toBe('La cuenta ya tiene operaciones.')
  })

  it('al aceptarse invalida el estado de cuenta de esa entidad', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { movimiento_id: ID, saldo: '1.00' }))
    const { wrapper, queryClient } = envoltorio()
    queryClient.setQueryData(['cuentas-corrientes', 'CLIENTE', ID, 'saldo'], '0.00')
    const { result } = renderHook(() => useRegistrarSaldoInicial(), { wrapper })

    result.current.mutate(DATOS)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(queryClient.getQueryState(['cuentas-corrientes', 'CLIENTE', ID, 'saldo'])?.isInvalidated).toBe(true)
  })
})
