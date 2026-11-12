/**
 * Change 16, tarea 14.2: lecturas y escrituras de reglas de descuento y de topes por rol
 * (DSC-01, DSC-06; INV-06, TR-10; `design.md` D13, D15, D16, D18). Cada escritura lleva
 * `Operation-Id`; el reintento tras un error de RED reenvía el mismo valor y un rechazo de
 * dominio no se reintenta. Las rutas de los topes cuelgan de `/identidad/roles`.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ErrorDeApiDescuentos, PermisoRequeridoDescuentosError } from '../../../../src/features/descuentos/errores'
import {
  useActivarReglaDescuento,
  useCrearReglaDescuento,
  useDefinirTopeDeRol,
  useModificarReglaDescuento,
  usePausarReglaDescuento,
  useReglaDescuento,
  useReglasDescuento,
  useRolesConTope,
} from '../../../../src/features/descuentos/hooks'
import {
  campoDeReglaDeDescuentoParaCodigo,
  campoDeTopeParaCodigo,
  mensajeDeErrorDeDescuentos,
} from '../../../../src/features/descuentos/mapaErrorACampo'

const REGLA = '11111111-1111-4111-8111-111111111111'
const ROL = '22222222-2222-4222-8222-222222222222'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
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

function operationId(indice: number): string | null {
  return new Headers(opciones(indice).headers).get('Operation-Id')
}

function clavesInvalidadas(spy: ReturnType<typeof vi.spyOn>): string[] {
  return spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))
}

const ALTA = {
  nombre: 'Mayorista',
  tipo: 'VOLUMEN_OPERACION',
  medida: 'CAJAS_EQUIVALENTES',
  operador: 'GTE',
  umbral: '20',
  accion_tipo: 'PORCENTAJE',
  accion_valor: '0.050000',
  prioridad: 10,
  acumulable: false,
  alcances: [],
  vigencia_desde: null,
  vigencia_hasta: null,
} as const

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('lecturas de descuentos (tarea 14.2)', () => {
  it('useReglasDescuento pide el listado, con el estado como filtro y el cursor', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'a' }], siguiente_cursor: 'c1' }))
      .mockResolvedValueOnce(respuesta(200, { items: [{ id: 'b' }], siguiente_cursor: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useReglasDescuento('VENCIDA'), { wrapper })
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe('/descuentos/reglas')
    expect(url(0).searchParams.get('estado')).toBe('VENCIDA')
    expect(url(0).searchParams.has('cursor')).toBe(false)
    expect(url(1).searchParams.get('cursor')).toBe('c1')
    await waitFor(() => expect(result.current.data?.pages).toHaveLength(2))
  })

  it('sin filtro no manda el parámetro estado', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [], siguiente_cursor: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useReglasDescuento(undefined), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).searchParams.has('estado')).toBe(false)
  })

  it('useReglaDescuento pide el detalle y no pide nada sin id', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: REGLA }))
    const { wrapper } = envoltorio()

    const detalle = renderHook(() => useReglaDescuento(REGLA), { wrapper })
    renderHook(() => useReglaDescuento(undefined), { wrapper })

    await waitFor(() => expect(detalle.result.current.isSuccess).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    expect(url(0).pathname).toBe(`/descuentos/reglas/${REGLA}`)
  })

  it('useRolesConTope pide GET /identidad/roles', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, [{ id: ROL, nombre: 'Vendedor', activo: true, tope_descuento: '0.050000' }]))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useRolesConTope(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe('/identidad/roles')
    expect(result.current.data?.[0]?.tope_descuento).toBe('0.050000')
  })

  it('un 403 de una lectura es PermisoRequeridoDescuentosError', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Sin permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useReglasDescuento(undefined), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(PermisoRequeridoDescuentosError)
  })
})

describe('escrituras de descuentos (tarea 14.2)', () => {
  it('crear envía POST /descuentos/reglas con Operation-Id e invalida el listado', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { id: REGLA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useCrearReglaDescuento(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(ALTA)
    })

    expect(url(0).pathname).toBe('/descuentos/reglas')
    expect(opciones(0).method).toBe('POST')
    expect(operationId(0)).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual(ALTA)
    expect(clavesInvalidadas(invalidar)).toContain('["descuentos","reglas"]')
  })

  it('modificar envía PUT sin el id ni el operationId en el cuerpo e invalida listado y detalle', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: REGLA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useModificarReglaDescuento(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ reglaId: REGLA, vigencia_hasta: '2026-12-31T23:00:00.000Z', operationId: 'op-1' })
    })

    expect(url(0).pathname).toBe(`/descuentos/reglas/${REGLA}`)
    expect(opciones(0).method).toBe('PUT')
    expect(operationId(0)).toBe('op-1')
    expect(JSON.parse(String(opciones(0).body))).toEqual({ vigencia_hasta: '2026-12-31T23:00:00.000Z' })
    const claves = clavesInvalidadas(invalidar)
    expect(claves).toContain('["descuentos","reglas"]')
    expect(claves).toContain(`["descuentos","regla","${REGLA}"]`)
  })

  it.each([
    ['activar', () => useActivarReglaDescuento(), `/descuentos/reglas/${REGLA}/activacion`],
    ['pausar', () => usePausarReglaDescuento(), `/descuentos/reglas/${REGLA}/pausa`],
  ] as const)('%s envía POST sin cuerpo e invalida el listado y el detalle', async (_nombre, hook, ruta) => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: REGLA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(hook as () => ReturnType<typeof useActivarReglaDescuento>, { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ reglaId: REGLA })
    })

    expect(url(0).pathname).toBe(ruta)
    expect(opciones(0).method).toBe('POST')
    expect(opciones(0).body).toBeUndefined()
    expect(operationId(0)).toBeTruthy()
    const claves = clavesInvalidadas(invalidar)
    expect(claves).toContain('["descuentos","reglas"]')
    expect(claves).toContain(`["descuentos","regla","${REGLA}"]`)
  })

  it('definir el tope envía PUT /identidad/roles/{id}/tope-descuento con el tope como cadena e invalida los roles', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: ROL, nombre: 'Vendedor', activo: true, tope_descuento: '0.050000' }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useDefinirTopeDeRol(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ rolId: ROL, tope_descuento: '0.050000' })
    })

    expect(url(0).pathname).toBe(`/identidad/roles/${ROL}/tope-descuento`)
    expect(opciones(0).method).toBe('PUT')
    expect(operationId(0)).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual({ tope_descuento: '0.050000' })
    expect(clavesInvalidadas(invalidar)).toContain('["descuentos","roles"]')
  })
})

describe('Operation-Id de las escrituras de descuentos (INV-06)', () => {
  it('reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(respuesta(201, { id: REGLA }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearReglaDescuento(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(ALTA)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(operationId(0)).toBeTruthy()
    expect(operationId(1)).toBe(operationId(0))
  })

  it('el tope también reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(respuesta(200, {}))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useDefinirTopeDeRol(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ rolId: ROL, tope_descuento: '0.100000' })
    })

    expect(operationId(1)).toBe(operationId(0))
  })

  it('con el operationId recibido (reintento manual del mismo contenido) reenvía el mismo; sin él, uno nuevo por envío', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { id: REGLA }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => usePausarReglaDescuento(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ reglaId: REGLA, operationId: 'op-fijo' })
      await result.current.mutateAsync({ reglaId: REGLA, operationId: 'op-fijo' })
      await result.current.mutateAsync({ reglaId: REGLA })
      await result.current.mutateAsync({ reglaId: REGLA })
    })

    expect(operationId(0)).toBe('op-fijo')
    expect(operationId(1)).toBe('op-fijo')
    expect(operationId(2)).toBeTruthy()
    expect(operationId(3)).not.toBe(operationId(2))
  })

  it('un rechazo de dominio no se reintenta y conserva código, estado y mensaje', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(409, { title: 'La regla no está en un estado que lo permita', codigo: 'REGLA_ESTADO_INVALIDO' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => usePausarReglaDescuento(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ reglaId: REGLA })).rejects.toMatchObject({
        codigo: 'REGLA_ESTADO_INVALIDO',
        estado: 409,
        message: 'La regla no está en un estado que lo permita',
      })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('un 403 de una escritura es PermisoRequeridoDescuentosError; un 422 es ErrorDeApiDescuentos', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(403, { title: 'Falta el permiso', codigo: 'PERMISO_REQUERIDO' }))
      .mockResolvedValueOnce(respuesta(422, { title: 'Tope fuera de rango', codigo: 'IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO' }))
    const { wrapper } = envoltorio()
    const crear = renderHook(() => useCrearReglaDescuento(), { wrapper })
    const tope = renderHook(() => useDefinirTopeDeRol(), { wrapper })

    await act(async () => {
      await expect(crear.result.current.mutateAsync(ALTA)).rejects.toBeInstanceOf(PermisoRequeridoDescuentosError)
      await expect(tope.result.current.mutateAsync({ rolId: ROL, tope_descuento: '1.200000' })).rejects.toBeInstanceOf(
        ErrorDeApiDescuentos,
      )
    })
  })
})

describe('mapa de error a campo y mensajes (TR-10)', () => {
  it.each([
    ['UMBRAL_INVALIDO', 'umbral'],
    ['ACCION_INVALIDA', 'accion_valor'],
    ['PRIORIDAD_INVALIDA', 'prioridad'],
    ['ALCANCE_INVALIDO', 'alcances'],
    ['VIGENCIA_INVALIDA', 'vigencia_hasta'],
    ['NOMBRE_INVALIDO', 'nombre'],
  ])('%s se muestra junto a %s', (codigo, campo) => {
    expect(campoDeReglaDeDescuentoParaCodigo(codigo)).toBe(campo)
  })

  it.each(['REGLA_NO_ES_BORRADOR', 'REGLA_ESTADO_INVALIDO', 'REGLA_DESCUENTO_INVALIDA', 'PERMISO_REQUERIDO', 'OTRO'])(
    '%s no corresponde a un campo',
    (codigo) => {
      expect(campoDeReglaDeDescuentoParaCodigo(codigo)).toBeNull()
    },
  )

  it('el tope fuera de rango se muestra junto al tope; el resto no es de campo', () => {
    expect(campoDeTopeParaCodigo('IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO')).toBe('tope_descuento')
    expect(campoDeTopeParaCodigo('RECURSO_NO_ENCONTRADO')).toBeNull()
  })

  it('REGLA_ESTADO_INVALIDO y REGLA_NO_ES_BORRADOR tienen un mensaje propio; el resto usa el del servidor', () => {
    expect(mensajeDeErrorDeDescuentos('REGLA_ESTADO_INVALIDO', 'texto del servidor')).toMatch(/cambió de estado/i)
    expect(mensajeDeErrorDeDescuentos('REGLA_NO_ES_BORRADOR', 'texto del servidor')).toMatch(/ya no es un borrador/i)
    expect(mensajeDeErrorDeDescuentos('UMBRAL_INVALIDO', 'El umbral debe ser mayor que 0')).toBe('El umbral debe ser mayor que 0')
    expect(mensajeDeErrorDeDescuentos('IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO', 'Fuera de rango')).toBe('Fuera de rango')
  })
})
