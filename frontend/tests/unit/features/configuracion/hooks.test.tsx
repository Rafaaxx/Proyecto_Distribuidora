import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeConfiguracion } from '../../../../src/features/configuracion/errores'
import {
  useCambiarCondicionIva,
  useConfiguracionFiscal,
  useResumenReglaIva,
} from '../../../../src/features/configuracion/useConfiguracionFiscal'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const MONOTRIBUTO = {
  condicion_iva: 'MONOTRIBUTO',
  computa_credito_fiscal: false,
  modo_impositivo: 'A',
  modalidad_iva_default: null,
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

function opciones(indice: number): RequestInit {
  return apiFetchMock.mock.calls[indice]?.[1] as RequestInit
}

function cabecera(indice: number, nombre: string): string | undefined {
  return (opciones(indice).headers as Record<string, string>)[nombre]
}

describe('useConfiguracionFiscal (11b, tarea 7.1, CST-06)', () => {
  beforeEach(() => apiFetchMock.mockReset())

  it('lee la condición y si computa crédito fiscal de GET /configuracion/fiscal', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, MONOTRIBUTO))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useConfiguracionFiscal(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiFetchMock.mock.calls[0]?.[0]).toBe('/configuracion/fiscal')
    expect(result.current.data).toEqual(MONOTRIBUTO)
  })

  it('un error del servidor deja la consulta en error sin datos', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(500, { title: 'Falló' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useConfiguracionFiscal(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })
})

describe('useResumenReglaIva (11b, tarea 7.1, D10)', () => {
  beforeEach(() => apiFetchMock.mockReset())

  it('lee los conteos y no consulta si está deshabilitado', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, { fecha: '2026-10-03', con_credito_fiscal: 3, sin_credito_fiscal: 12 }),
    )
    const { wrapper } = envoltorio()

    const habilitado = renderHook(() => useResumenReglaIva(true), { wrapper })
    await waitFor(() => expect(habilitado.result.current.isSuccess).toBe(true))
    expect(apiFetchMock.mock.calls[0]?.[0]).toBe('/costos/resumen-regla-iva')
    expect(habilitado.result.current.data?.sin_credito_fiscal).toBe(12)

    apiFetchMock.mockClear()
    const apagado = renderHook(() => useResumenReglaIva(false), { wrapper: envoltorio().wrapper })
    expect(apagado.result.current.fetchStatus).toBe('idle')
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('useCambiarCondicionIva (11b, tarea 7.1, INV-06)', () => {
  beforeEach(() => apiFetchMock.mockReset())

  it('envía la condición con un Operation-Id y refresca la configuración fiscal', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { ...MONOTRIBUTO, condicion_iva: 'EXENTO' }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useCambiarCondicionIva(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ condicion_iva: 'EXENTO' })
    })

    expect(apiFetchMock.mock.calls[0]?.[0]).toBe('/configuracion/fiscal/condicion-iva')
    expect(opciones(0).method).toBe('POST')
    expect(JSON.parse(String(opciones(0).body))).toEqual({ condicion_iva: 'EXENTO' })
    expect(cabecera(0, 'Operation-Id')).toMatch(/^[0-9a-f-]{36}$/)
    expect(invalidar).toHaveBeenCalledWith({ queryKey: ['configuracion', 'fiscal'] })
  })

  it('el reintento tras un error de red reenvía el mismo Operation-Id', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(200, MONOTRIBUTO))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCambiarCondicionIva(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ condicion_iva: 'MONOTRIBUTO' })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(cabecera(0, 'Operation-Id')).toBe(cabecera(1, 'Operation-Id'))
  })

  it('un rechazo de dominio llega con su código y su estado, y no se reintenta', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(409, { title: 'Ya es monotributista', codigo: 'CONDICION_IVA_SIN_CAMBIO' }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCambiarCondicionIva(), { wrapper })

    let error: unknown
    await act(async () => {
      error = await result.current.mutateAsync({ condicion_iva: 'MONOTRIBUTO' }).catch((e: unknown) => e)
    })

    expect(error).toBeInstanceOf(ErrorDeConfiguracion)
    expect((error as ErrorDeConfiguracion).codigo).toBe('CONDICION_IVA_SIN_CAMBIO')
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('dos envíos manuales distintos usan Operation-Id distintos', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, MONOTRIBUTO))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCambiarCondicionIva(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ condicion_iva: 'MONOTRIBUTO' })
    })
    await act(async () => {
      await result.current.mutateAsync({ condicion_iva: 'EXENTO' })
    })

    expect(cabecera(0, 'Operation-Id')).not.toBe(cabecera(1, 'Operation-Id'))
  })
})
