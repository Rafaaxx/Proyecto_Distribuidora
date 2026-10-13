import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../../src/features/stock/errores'
import {
  useAbrirJornada,
  useCerrarJornada,
  useJornada,
  useJornadaActual,
  useJornadas,
  useLiberarJornada,
  useMotivosDeStock,
  useRendirJornada,
} from '../../../../src/features/stock/hooks'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const UBICACION = '11111111-1111-4111-8111-111111111111'
const USUARIO = '22222222-2222-4222-8222-222222222222'
const JORNADA = '33333333-3333-4333-8333-333333333333'
const MOTIVO = '44444444-4444-4444-8444-444444444444'
const PAGINA_VACIA = { items: [], cursor_siguiente: null }

function envoltorio() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  }
}

const url = (i: number) => new URL(String(apiFetchMock.mock.calls[i]?.[0]), 'http://x')
const opciones = (i: number) => apiFetchMock.mock.calls[i]?.[1] as RequestInit
const operationId = (i: number) => new Headers(opciones(i).headers).get('Operation-Id')

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('lecturas de jornadas (tarea 13.2)', () => {
  it('useJornadas manda los filtros y sigue con el cursor', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'a' }], cursor_siguiente: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'b' }], cursor_siguiente: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(
      () =>
        useJornadas({
          ubicacionId: UBICACION,
          usuarioId: USUARIO,
          estado: 'EN_RENDICION',
          desde: '2026-04-01',
          hasta: '2026-04-30',
        }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe('/stock/jornadas')
    expect(url(0).searchParams.get('ubicacion_id')).toBe(UBICACION)
    expect(url(0).searchParams.get('usuario_id')).toBe(USUARIO)
    expect(url(0).searchParams.get('estado')).toBe('EN_RENDICION')
    expect(url(0).searchParams.get('desde')).toBe('2026-04-01')
    expect(url(0).searchParams.get('hasta')).toBe('2026-04-30')
    expect(url(1).searchParams.get('cursor')).toBe('c1')
  })

  it('useJornadas sin filtros no manda ninguno', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, PAGINA_VACIA))
    const { wrapper } = envoltorio()

    renderHook(() => useJornadas({}), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    for (const campo of ['ubicacion_id', 'usuario_id', 'estado', 'desde', 'hasta']) {
      expect(url(0).searchParams.has(campo)).toBe(false)
    }
  })

  it('useJornada pide el detalle y sin id no pide nada', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: JORNADA, estado: 'ABIERTA' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useJornada(JORNADA), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(`/stock/jornadas/${JORNADA}`)

    apiFetchMock.mockClear()
    renderHook(() => useJornada(undefined), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('useJornadaActual devuelve la jornada no cerrada del token', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: JORNADA, estado: 'ABIERTA' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useJornadaActual(true), { wrapper })

    await waitFor(() => expect(result.current.data).toMatchObject({ id: JORNADA }))
    expect(url(0).pathname).toBe('/stock/jornadas/actual')
  })

  it('useJornadaActual toma el 404 como "no tengo jornada" (data null) y no lo trata como error', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(404, { title: 'No hay', codigo: 'RECURSO_NO_ENCONTRADO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useJornadaActual(true), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })

  it('useJornadaActual deshabilitado no pide nada (sin ABRIR_JORNADA no se consulta)', () => {
    const { wrapper } = envoltorio()
    renderHook(() => useJornadaActual(false), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('los motivos de liberación son del ámbito LIBERACION_JORNADA', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [] }))
    const { wrapper } = envoltorio()

    renderHook(() => useMotivosDeStock('LIBERACION_JORNADA'), { wrapper })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(url(0).searchParams.get('ambito')).toBe('LIBERACION_JORNADA')
  })
})

describe('escrituras de jornadas (tarea 13.2)', () => {
  const ESCRITURAS = [
    ['abrir', () => useAbrirJornada(), { ubicacion_id: UBICACION }, '/stock/jornadas', { ubicacion_id: UBICACION }],
    ['rendir', () => useRendirJornada(), { id: JORNADA }, `/stock/jornadas/${JORNADA}/rendicion`, {}],
    ['cerrar', () => useCerrarJornada(), { id: JORNADA }, `/stock/jornadas/${JORNADA}/cierre`, {}],
    [
      'liberar',
      () => useLiberarJornada(),
      { id: JORNADA, motivo_id: MOTIVO, observacion: 'Se enfermó' },
      `/stock/jornadas/${JORNADA}/liberacion`,
      { motivo_id: MOTIVO, observacion: 'Se enfermó' },
    ],
  ] as const

  it.each(ESCRITURAS)('%s hace POST con Operation-Id y el cuerpo esperado', async (_n, usar, variables, ruta, cuerpo) => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: JORNADA }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => usar() as unknown as ReturnType<typeof useLiberarJornada>, { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...(variables as { id: string; motivo_id: string }), operationId: 'op-fijo' })
    })

    expect(url(0).pathname).toBe(ruta)
    expect(opciones(0).method).toBe('POST')
    expect(operationId(0)).toBe('op-fijo')
    expect(JSON.parse(String(opciones(0).body))).toEqual(cuerpo)
  })

  it('liberar sin observación no la manda', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: JORNADA }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useLiberarJornada(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: JORNADA, motivo_id: MOTIVO })
    })

    expect(JSON.parse(String(opciones(0).body))).toEqual({ motivo_id: MOTIVO })
  })

  it.each(ESCRITURAS)('el reintento tras un error de red de %s reenvía el mismo Operation-Id', async (_n, usar, variables) => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(respuesta(200, { id: JORNADA }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => usar() as unknown as ReturnType<typeof useLiberarJornada>, { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...(variables as { id: string; motivo_id: string }) })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(operationId(1)).toBe(operationId(0))
  })

  it('dos aperturas distintas sin operationId explícito usan Operation-Id distintos', async () => {
    apiFetchMock.mockResolvedValue(respuesta(201, { id: JORNADA }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAbrirJornada(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ubicacion_id: UBICACION })
    })
    await act(async () => {
      await result.current.mutateAsync({ ubicacion_id: UBICACION })
    })

    expect(operationId(1)).not.toBe(operationId(0))
  })

  it.each(ESCRITURAS)('al aceptarse %s invalida stock (jornadas, ubicaciones y saldos)', async (_n, usar, variables) => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: JORNADA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => usar() as unknown as ReturnType<typeof useLiberarJornada>, { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ...(variables as { id: string; motivo_id: string }) })
    })

    const claves = invalidar.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
    expect(claves).toContain('["stock"]')
  })

  it('un rechazo de dominio no se reintenta y conserva el código', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(409, { title: 'Tomada', codigo: 'UBICACION_TOMADA' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAbrirJornada(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ ubicacion_id: UBICACION })).rejects.toMatchObject({
        codigo: 'UBICACION_TOMADA',
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('mensajes de error de jornadas (tarea 13.2)', () => {
  const error = (codigo: string) => new ErrorDeStock(codigo, 'mensaje del servidor')

  it('UBICACION_TOMADA tiene un texto al abrir, otro al mover stock y otro al modificar la ubicación', () => {
    const apertura = mensajeDeErrorDeStock(error('UBICACION_TOMADA'), 'apertura')
    const transferencia = mensajeDeErrorDeStock(error('UBICACION_TOMADA'), 'transferencia')
    const ajuste = mensajeDeErrorDeStock(error('UBICACION_TOMADA'), 'ajuste')
    const anulacion = mensajeDeErrorDeStock(error('UBICACION_TOMADA'), 'anulacion')
    const ubicacion = mensajeDeErrorDeStock(error('UBICACION_TOMADA'), 'ubicacion')

    expect(apertura).toContain('Elegí otra')
    expect(transferencia).toContain('jornada')
    expect(ajuste).toBe(transferencia)
    expect(anulacion).toBe(transferencia)
    expect(ubicacion).toContain('desactivar')
    expect(new Set([apertura, transferencia, ubicacion]).size).toBe(3)
  })

  it.each([
    ['UBICACION_SIN_TOMA', 'no requiere toma'],
    ['USUARIO_CON_JORNADA', 'tenés una jornada'],
    ['DISPOSITIVO_CON_JORNADA', 'este dispositivo'],
    ['JORNADA_ESTADO_INVALIDO', 'ya cambió'],
    ['MOTIVO_INVALIDO', 'motivo'],
    ['OBSERVACION_INVALIDA', '500'],
  ])('%s tiene un mensaje propio', (codigo, fragmento) => {
    expect(mensajeDeErrorDeStock(error(codigo), 'apertura')).toContain(fragmento)
  })

  it('JORNADA_ESTADO_INVALIDO y MOTIVO_INVALIDO se muestran también en el contexto "jornada"', () => {
    expect(mensajeDeErrorDeStock(error('JORNADA_ESTADO_INVALIDO'), 'jornada')).toContain('ya cambió')
    expect(mensajeDeErrorDeStock(error('MOTIVO_INVALIDO'), 'jornada')).toContain('motivo')
  })

  it('un corte de red en una jornada avisa que se necesita conexión', () => {
    expect(mensajeDeErrorDeStock(new TypeError('Failed to fetch'), 'apertura')).toContain('conexión')
  })
})
