import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CategoriasYMarcasScreen } from '../../../../../src/areas/admin/catalogo/CategoriasYMarcasScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const CATEGORIA_ACTIVA = {
  id: '11111111-1111-4111-8111-111111111111',
  nombre: 'Bebidas',
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const MARCA_ACTIVA = {
  id: '22222222-2222-4222-8222-222222222222',
  nombre: 'Coca-Cola',
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

function renderPantalla() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <CategoriasYMarcasScreen />
    </QueryClientProvider>,
  )
}

describe('CategoriasYMarcasScreen (tarea 10.6)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista categorías y marcas con su estado', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, { items: [CATEGORIA_ACTIVA], cursor_siguiente: null }))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, { items: [MARCA_ACTIVA], cursor_siguiente: null }))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    renderPantalla()

    const filaCategoria = (await screen.findByText('Bebidas')).closest('tr') as HTMLElement
    expect(within(filaCategoria).getByText('Activa')).toBeInTheDocument()

    const filaMarca = (await screen.findByText('Coca-Cola')).closest('tr') as HTMLElement
    expect(within(filaMarca).getByText('Activa')).toBeInTheDocument()
  })

  it('crea una categoría nueva', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (ruta === '/catalogo/categorias' && init?.method === 'POST') {
        return Promise.resolve(respuesta(201, { ...CATEGORIA_ACTIVA, id: '33333333-3333-4333-8333-333333333333', nombre: 'Snacks' }))
      }
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, { items: [CATEGORIA_ACTIVA], cursor_siguiente: null }))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByText('Bebidas')
    await usuarioEvento.click(screen.getByRole('button', { name: /nueva categoría/i }))
    await usuarioEvento.type(screen.getByLabelText(/^nombre$/i), 'Snacks')
    await usuarioEvento.click(screen.getByRole('button', { name: /^crear$/i }))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith('/catalogo/categorias', expect.objectContaining({ method: 'POST' })),
    )
    const llamada = apiFetchMock.mock.calls.find(([ruta, init]) => ruta === '/catalogo/categorias' && (init as RequestInit | undefined)?.method === 'POST')
    const [, opciones] = llamada as [string, RequestInit]
    expect(JSON.parse(opciones.body as string)).toEqual({ nombre: 'Snacks' })
  })

  it('desactivar una categoría activa envía activo=false conservando el nombre', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (ruta === `/catalogo/categorias/${CATEGORIA_ACTIVA.id}` && init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...CATEGORIA_ACTIVA, activo: false }))
      }
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, { items: [CATEGORIA_ACTIVA], cursor_siguiente: null }))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    const fila = (await screen.findByText('Bebidas')).closest('tr') as HTMLElement
    await usuarioEvento.click(within(fila).getByRole('button', { name: /desactivar/i }))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        `/catalogo/categorias/${CATEGORIA_ACTIVA.id}`,
        expect.objectContaining({ method: 'PUT' }),
      ),
    )
    const llamada = apiFetchMock.mock.calls.find(
      ([ruta, init]) => ruta === `/catalogo/categorias/${CATEGORIA_ACTIVA.id}` && (init as RequestInit | undefined)?.method === 'PUT',
    )
    const [, opciones] = llamada as [string, RequestInit]
    expect(JSON.parse(opciones.body as string)).toEqual({ nombre: 'Bebidas', activo: false })
  })

  it('renombrar una marca envía el nuevo nombre conservando su estado', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (ruta === `/catalogo/marcas/${MARCA_ACTIVA.id}` && init?.method === 'PUT') {
        return Promise.resolve(respuesta(200, { ...MARCA_ACTIVA, nombre: 'Coca Cola Co.' }))
      }
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, { items: [MARCA_ACTIVA], cursor_siguiente: null }))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    const fila = (await screen.findByText('Coca-Cola')).closest('tr') as HTMLElement
    await usuarioEvento.click(within(fila).getByRole('button', { name: /renombrar/i }))

    const campoNombre = await screen.findByLabelText(/^nombre$/i)
    await usuarioEvento.clear(campoNombre)
    await usuarioEvento.type(campoNombre, 'Coca Cola Co.')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar/i }))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        `/catalogo/marcas/${MARCA_ACTIVA.id}`,
        expect.objectContaining({ method: 'PUT' }),
      ),
    )
    const llamada = apiFetchMock.mock.calls.find(
      ([ruta, init]) => ruta === `/catalogo/marcas/${MARCA_ACTIVA.id}` && (init as RequestInit | undefined)?.method === 'PUT',
    )
    const [, opciones] = llamada as [string, RequestInit]
    expect(JSON.parse(opciones.body as string)).toEqual({ nombre: 'Coca Cola Co.', activo: true })
  })

  it('ante CATEGORIA_CON_PRODUCTOS_ACTIVOS muestra el mensaje de error (D11)', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (ruta === `/catalogo/categorias/${CATEGORIA_ACTIVA.id}` && init?.method === 'PUT') {
        return Promise.resolve(
          respuesta(409, {
            title: 'No se puede desactivar: tiene productos activos.',
            codigo: 'CATEGORIA_CON_PRODUCTOS_ACTIVOS',
          }),
        )
      }
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, { items: [CATEGORIA_ACTIVA], cursor_siguiente: null }))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    const fila = (await screen.findByText('Bebidas')).closest('tr') as HTMLElement
    await usuarioEvento.click(within(fila).getByRole('button', { name: /desactivar/i }))

    expect(await screen.findByText('No se puede desactivar: tiene productos activos.')).toBeInTheDocument()
  })
})
