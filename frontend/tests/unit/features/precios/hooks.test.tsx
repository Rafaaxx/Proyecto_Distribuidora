import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { campoDeListaParaCodigo, campoDePrecioParaCodigo, campoDePublicacionParaCodigo, campoDeReglaParaCodigo } from '../../../../src/features/precios/mapaErrorACampo'
import { ErrorDePrecios, PermisoRequeridoPreciosError } from '../../../../src/features/precios/errores'
import {
  useAnularVersion,
  useBorrador,
  useCrearLista,
  useCrearRegla,
  useDefinirListaPredeterminada,
  useDefinirRedondeoDeCategoria,
  useFijarPrecioManual,
  useGenerarBorrador,
  useListaDetalle,
  useListaPredeterminada,
  useListas,
  useModificarLista,
  useModificarRegla,
  useOpcionesDeListas,
  usePreciosDeVersion,
  usePublicarVersion,
  useReglas,
  useVersiones,
} from '../../../../src/features/precios/hooks'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const LISTA = '11111111-1111-4111-8111-111111111111'
const VERSION = '22222222-2222-4222-8222-222222222222'
const PRODUCTO = '33333333-3333-4333-8333-333333333333'
const REGLA = '44444444-4444-4444-8444-444444444444'
const CATEGORIA = '55555555-5555-4555-8555-555555555555'

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

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('lecturas de precios (tarea 12.2)', () => {
  it.each([
    ['useListas', () => useListas(), '/precios/listas'],
    ['useListaDetalle', () => useListaDetalle(LISTA), `/precios/listas/${LISTA}`],
    ['useReglas', () => useReglas(LISTA), `/precios/listas/${LISTA}/reglas`],
    ['useVersiones', () => useVersiones(LISTA), `/precios/listas/${LISTA}/versiones`],
    ['useListaPredeterminada', () => useListaPredeterminada(), '/precios/lista-predeterminada'],
    ['useOpcionesDeListas', () => useOpcionesDeListas(), '/precios/listas/opciones'],
  ] as const)('%s pide su ruta', async (_nombre, hook, ruta) => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { items: [] }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(hook, { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(ruta)
  })

  it('las lecturas por id no piden nada sin id', () => {
    const { wrapper } = envoltorio()

    renderHook(() => useListaDetalle(undefined), { wrapper })
    renderHook(() => useReglas(undefined), { wrapper })
    renderHook(() => useBorrador(undefined), { wrapper })
    renderHook(() => useVersiones(undefined), { wrapper })

    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('useBorrador sigue con el cursor y junta las páginas', async () => {
    apiFetchMock
      .mockResolvedValueOnce(respuesta(200, { precios: [{ producto_id: 'a' }], siguiente_cursor: 'c1', productos_sin_precio: [] }))
      .mockResolvedValueOnce(respuesta(200, { precios: [{ producto_id: 'b' }], siguiente_cursor: null, productos_sin_precio: [] }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useBorrador(LISTA), { wrapper })
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await act(async () => {
      await result.current.fetchNextPage()
    })

    expect(url(0).pathname).toBe(`/precios/listas/${LISTA}/borrador`)
    expect(url(0).searchParams.has('cursor')).toBe(false)
    expect(url(1).searchParams.get('cursor')).toBe('c1')
    await waitFor(() => expect(result.current.hasNextPage).toBe(false))
    expect(result.current.data?.pages).toHaveLength(2)
  })

  it('usePreciosDeVersion pide los precios de la versión con cursor', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { precios: [], siguiente_cursor: null }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => usePreciosDeVersion(LISTA, VERSION), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(url(0).pathname).toBe(`/precios/listas/${LISTA}/versiones/${VERSION}/precios`)
  })

  it('un 403 de una lectura se traduce a PermisoRequeridoPreciosError', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Sin permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()

    const { result } = renderHook(() => useListas(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(PermisoRequeridoPreciosError)
  })
})

describe('escrituras de precios (tarea 12.2)', () => {
  it('useCrearLista envía POST con Operation-Id e invalida el listado y las opciones', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(201, { id: LISTA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useCrearLista(), { wrapper })
    const cuerpo = { nombre: 'General', redondeo_multiplo: '100', redondeo_direccion: 'ARRIBA' }

    await act(async () => {
      await result.current.mutateAsync(cuerpo)
    })

    expect(url(0).pathname).toBe('/precios/listas')
    expect(opciones(0).method).toBe('POST')
    expect(operationId(0)).toBeTruthy()
    expect(JSON.parse(String(opciones(0).body))).toEqual(cuerpo)
    expect(clavesInvalidadas(invalidar)).toEqual(
      expect.arrayContaining(['["precios","listado"]', '["precios","opciones"]']),
    )
  })

  it('useModificarLista envía PUT sin los ids en el cuerpo e invalida el detalle', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { id: LISTA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useModificarLista(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        listaId: LISTA,
        nombre: 'General',
        redondeo_multiplo: '50',
        redondeo_direccion: 'CERCANO',
        activo: true,
      })
    })

    expect(url(0).pathname).toBe(`/precios/listas/${LISTA}`)
    expect(opciones(0).method).toBe('PUT')
    expect(JSON.parse(String(opciones(0).body))).toEqual({
      nombre: 'General',
      redondeo_multiplo: '50',
      redondeo_direccion: 'CERCANO',
      activo: true,
    })
    expect(clavesInvalidadas(invalidar)).toEqual(
      expect.arrayContaining(['["precios","listado"]', `["precios","lista","${LISTA}"]`]),
    )
  })

  it('reglas y redondeo por categoría invalidan las reglas y el detalle de la lista', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, {}))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const crear = renderHook(() => useCrearRegla(), { wrapper })
    const modificar = renderHook(() => useModificarRegla(), { wrapper })
    const redondeo = renderHook(() => useDefinirRedondeoDeCategoria(), { wrapper })

    await act(async () => {
      await crear.result.current.mutateAsync({
        listaId: LISTA,
        tipo: 'MARKUP',
        valor: '0.300000',
        alcance_tipo: 'CATEGORIA',
        alcance_id: CATEGORIA,
      })
      await modificar.result.current.mutateAsync({
        listaId: LISTA,
        reglaId: REGLA,
        tipo: 'MARGEN_BRUTO',
        valor: '0.250000',
        activo: false,
      })
      await redondeo.result.current.mutateAsync({
        listaId: LISTA,
        categoriaId: CATEGORIA,
        multiplo: '50',
        direccion: 'CERCANO',
        activo: true,
      })
    })

    expect(url(0).pathname).toBe(`/precios/listas/${LISTA}/reglas`)
    expect(opciones(0).method).toBe('POST')
    expect(JSON.parse(String(opciones(0).body))).toEqual({
      tipo: 'MARKUP',
      valor: '0.300000',
      alcance_tipo: 'CATEGORIA',
      alcance_id: CATEGORIA,
    })
    expect(url(1).pathname).toBe(`/precios/listas/${LISTA}/reglas/${REGLA}`)
    expect(opciones(1).method).toBe('PUT')
    expect(url(2).pathname).toBe(`/precios/listas/${LISTA}/redondeos-categoria/${CATEGORIA}`)
    expect(JSON.parse(String(opciones(2).body))).toEqual({ multiplo: '50', direccion: 'CERCANO', activo: true })
    const claves = clavesInvalidadas(invalidar)
    expect(claves).toContain(`["precios","lista","${LISTA}","reglas"]`)
    expect(claves).toContain(`["precios","lista","${LISTA}"]`)
  })

  it.each([
    [
      'generar',
      () => useGenerarBorrador(),
      (m: ReturnType<typeof useGenerarBorrador>) => m.mutateAsync({ listaId: LISTA }),
      'POST',
      `/precios/listas/${LISTA}/borrador`,
    ],
    [
      'fijar',
      () => useFijarPrecioManual(),
      (m: ReturnType<typeof useFijarPrecioManual>) =>
        m.mutateAsync({ listaId: LISTA, versionId: VERSION, productoId: PRODUCTO, precio_final: '9000.00' }),
      'PUT',
      `/precios/listas/${LISTA}/versiones/${VERSION}/precios/${PRODUCTO}`,
    ],
    [
      'publicar',
      () => usePublicarVersion(),
      (m: ReturnType<typeof usePublicarVersion>) =>
        m.mutateAsync({ listaId: LISTA, versionId: VERSION, vigencia_desde: null, vigencia_hasta: null }),
      'POST',
      `/precios/listas/${LISTA}/versiones/${VERSION}/publicar`,
    ],
    [
      'anular',
      () => useAnularVersion(),
      (m: ReturnType<typeof useAnularVersion>) => m.mutateAsync({ listaId: LISTA, versionId: VERSION }),
      'POST',
      `/precios/listas/${LISTA}/versiones/${VERSION}/anular`,
    ],
  ] as const)(
    '%s invalida el borrador, las versiones y el listado de la lista',
    async (_nombre, hook, ejecutar, metodo, ruta) => {
      apiFetchMock.mockResolvedValueOnce(respuesta(200, {}))
      const { wrapper, queryClient } = envoltorio()
      const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
      const { result } = renderHook(hook as () => never, { wrapper })

      await act(async () => {
        await (ejecutar as (m: never) => Promise<unknown>)(result.current)
      })

      expect(url(0).pathname).toBe(ruta)
      expect(opciones(0).method).toBe(metodo)
      expect(operationId(0)).toBeTruthy()
      const claves = clavesInvalidadas(invalidar)
      expect(claves).toContain(`["precios","lista","${LISTA}","borrador"]`)
      expect(claves).toContain(`["precios","lista","${LISTA}","versiones"]`)
      expect(claves).toContain('["precios","listado"]')
    },
  )

  it('el cuerpo de fijar solo lleva el precio y el de publicar solo las vigencias', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, {}))
    const { wrapper } = envoltorio()
    const fijar = renderHook(() => useFijarPrecioManual(), { wrapper })
    const publicar = renderHook(() => usePublicarVersion(), { wrapper })

    await act(async () => {
      await fijar.result.current.mutateAsync({ listaId: LISTA, versionId: VERSION, productoId: PRODUCTO, precio_final: null })
      await publicar.result.current.mutateAsync({
        listaId: LISTA,
        versionId: VERSION,
        vigencia_desde: '2026-10-10T12:00:00.000Z',
        vigencia_hasta: null,
      })
    })

    expect(JSON.parse(String(opciones(0).body))).toEqual({ precio_final: null })
    expect(JSON.parse(String(opciones(1).body))).toEqual({
      vigencia_desde: '2026-10-10T12:00:00.000Z',
      vigencia_hasta: null,
    })
  })

  it('definir la lista predeterminada invalida la predeterminada y las opciones', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(200, { lista_id: LISTA }))
    const { wrapper, queryClient } = envoltorio()
    const invalidar = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useDefinirListaPredeterminada(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ lista_id: LISTA })
    })

    expect(url(0).pathname).toBe('/precios/lista-predeterminada')
    expect(opciones(0).method).toBe('PUT')
    expect(JSON.parse(String(opciones(0).body))).toEqual({ lista_id: LISTA })
    expect(clavesInvalidadas(invalidar)).toEqual(
      expect.arrayContaining(['["precios","predeterminada"]', '["precios","listado"]']),
    )
  })
})

describe('Operation-Id de las escrituras de precios (INV-06, tarea 12.2)', () => {
  it('reenvía el mismo Operation-Id tras un error de red', async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(200, {}))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useGenerarBorrador(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ listaId: LISTA })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(operationId(0)).toBeTruthy()
    expect(operationId(1)).toBe(operationId(0))
  })

  it('usa el operationId recibido (reintento manual del mismo contenido) y no lo manda en el cuerpo', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, {}))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useFijarPrecioManual(), { wrapper })
    const variables = { listaId: LISTA, versionId: VERSION, productoId: PRODUCTO, precio_final: '9000.00' }

    await act(async () => {
      await result.current.mutateAsync({ ...variables, operationId: 'op-fijo' })
      await result.current.mutateAsync({ ...variables, operationId: 'op-fijo' })
    })

    expect(operationId(0)).toBe('op-fijo')
    expect(operationId(1)).toBe('op-fijo')
    expect(JSON.parse(String(opciones(0).body))).toEqual({ precio_final: '9000.00' })
  })

  it('sin operationId, cada envío genera uno nuevo', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, {}))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useAnularVersion(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ listaId: LISTA, versionId: VERSION })
      await result.current.mutateAsync({ listaId: LISTA, versionId: VERSION })
    })

    expect(operationId(0)).toBeTruthy()
    expect(operationId(1)).toBeTruthy()
    expect(operationId(1)).not.toBe(operationId(0))
  })

  it('un rechazo de dominio no se reintenta y conserva código, estado y mensaje', async () => {
    apiFetchMock.mockResolvedValueOnce(
      respuesta(409, { title: 'Ya hay una regla para esa categoría', codigo: 'REGLA_DUPLICADA' }),
    )
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => useCrearRegla(), { wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          listaId: LISTA,
          tipo: 'MARKUP',
          valor: '0.300000',
          alcance_tipo: 'CATEGORIA',
          alcance_id: CATEGORIA,
        }),
      ).rejects.toMatchObject({ codigo: 'REGLA_DUPLICADA', estado: 409, message: 'Ya hay una regla para esa categoría' })
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  it('un 403 de una escritura es PermisoRequeridoPreciosError con el código PERMISO_REQUERIDO', async () => {
    apiFetchMock.mockResolvedValueOnce(respuesta(403, { title: 'Falta el permiso', codigo: 'PERMISO_REQUERIDO' }))
    const { wrapper } = envoltorio()
    const { result } = renderHook(() => usePublicarVersion(), { wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({ listaId: LISTA, versionId: VERSION, vigencia_desde: null, vigencia_hasta: null }),
      ).rejects.toBeInstanceOf(PermisoRequeridoPreciosError)
    })
  })
})

describe('mapa de errores a campos (TR-10)', () => {
  it.each([
    ['NOMBRE_INVALIDO', 'nombre'],
    ['NOMBRE_DUPLICADO', 'nombre'],
    ['REDONDEO_INVALIDO', 'redondeo_multiplo'],
    ['LISTA_EN_USO', 'activo'],
    ['CODIGO_QUE_NO_ES_DE_LISTA', null],
  ])('lista: %s va a %s', (codigo, campo) => {
    expect(campoDeListaParaCodigo(codigo)).toBe(campo)
  })

  it.each([
    ['MARGEN_INVALIDO', 'porcentaje'],
    ['ALCANCE_INVALIDO', 'alcance'],
    ['REGLA_DUPLICADA', 'alcance'],
    ['LISTA_EN_USO', null],
  ])('regla: %s va a %s', (codigo, campo) => {
    expect(campoDeReglaParaCodigo(codigo)).toBe(campo)
  })

  it('publicación y precio manual', () => {
    expect(campoDePublicacionParaCodigo('VIGENCIA_INVALIDA')).toBe('vigencia_desde')
    expect(campoDePublicacionParaCodigo('VIGENCIA_DUPLICADA')).toBe('vigencia_desde')
    expect(campoDePublicacionParaCodigo('VERSION_NO_ES_BORRADOR')).toBeNull()
    expect(campoDePrecioParaCodigo('IMPORTE_INVALIDO')).toBe('precio_final')
    expect(campoDePrecioParaCodigo('PRECIO_NO_POSITIVO')).toBe('precio_final')
    expect(campoDePrecioParaCodigo('VERSION_NO_ES_BORRADOR')).toBeNull()
  })

  it('ErrorDePrecios conserva código y estado', () => {
    const error = new ErrorDePrecios('LISTA_EN_USO', 'La lista está en uso', 409)

    expect([error.codigo, error.estado, error.message]).toEqual(['LISTA_EN_USO', 409, 'La lista está en uso'])
  })
})
