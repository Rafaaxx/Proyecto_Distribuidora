import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ProductosListScreen } from '../../../../../src/areas/admin/catalogo/ProductosListScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PRODUCTO_1 = {
  id: '11111111-1111-4111-8111-111111111111',
  codigo: 'GAS-001',
  nombre: 'Gaseosa cola',
  categoria_id: 'c1',
  marca_id: null,
  unidad_base: 'unidad',
  alicuota_id: 'a1',
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const PAGINA_VACIA_CATEGORIAS = { items: [], cursor_siguiente: null }
const PAGINA_VACIA_MARCAS = { items: [], cursor_siguiente: null }

function renderPantalla() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/catalogo/productos']}>
        <ProductosListScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Tarea 10.4: listado con búsqueda, filtros y "cargar más"; mensaje de
 * "sin permiso" ante `PERMISO_REQUERIDO`. */
describe('ProductosListScreen (tarea 10.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los productos de la primera página', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      return Promise.resolve(respuesta(200, { items: [PRODUCTO_1], cursor_siguiente: null }))
    })

    renderPantalla()

    expect(await screen.findByText('Gaseosa cola')).toBeInTheDocument()
    expect(screen.getByText('GAS-001')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cargar más/i })).not.toBeInTheDocument()
  })

  it('muestra "cargar más" cuando hay cursor_siguiente y trae la página siguiente al hacer click', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      if (ruta.includes('cursor=abc')) {
        return Promise.resolve(
          respuesta(200, {
            items: [{ ...PRODUCTO_1, id: '22222222-2222-4222-8222-222222222222', codigo: 'GAS-002', nombre: 'Gaseosa lima' }],
            cursor_siguiente: null,
          }),
        )
      }
      return Promise.resolve(respuesta(200, { items: [PRODUCTO_1], cursor_siguiente: 'abc' }))
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    const botonCargarMas = await screen.findByRole('button', { name: /cargar más/i })
    await usuarioEvento.click(botonCargarMas)

    expect(await screen.findByText('Gaseosa lima')).toBeInTheDocument()
    expect(screen.getByText('Gaseosa cola')).toBeInTheDocument()
  })

  it('reenvía el texto de búsqueda como filtro', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByText(/no hay productos/i)
    await usuarioEvento.type(screen.getByLabelText(/buscar/i), 'cola')

    await waitFor(() =>
      expect(apiFetchMock.mock.calls.some(([ruta]) => String(ruta).includes('texto=cola'))).toBe(true),
    )
  })

  it('la fila entera es navegable al detalle (código y nombre son enlaces), no solo el nombre (tarea 10.10)', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      return Promise.resolve(respuesta(200, { items: [PRODUCTO_1], cursor_siguiente: null }))
    })

    renderPantalla()
    await screen.findByText('Gaseosa cola')

    const enlaceCodigo = screen.getByRole('link', { name: 'GAS-001' })
    const enlaceNombre = screen.getByRole('link', { name: 'Gaseosa cola' })
    expect(enlaceCodigo).toHaveAttribute('href', `/admin/catalogo/productos/${PRODUCTO_1.id}`)
    expect(enlaceNombre).toHaveAttribute('href', `/admin/catalogo/productos/${PRODUCTO_1.id}`)
  })

  it('cada fila tiene un enlace "Editar" explícito al detalle del producto (tarea 10.10)', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      return Promise.resolve(respuesta(200, { items: [PRODUCTO_1], cursor_siguiente: null }))
    })

    renderPantalla()
    await screen.findByText('Gaseosa cola')

    const enlaceEditar = screen.getByRole('link', { name: /editar/i })
    expect(enlaceEditar).toHaveAttribute('href', `/admin/catalogo/productos/${PRODUCTO_1.id}`)
  })

  it('ante PERMISO_REQUERIDO muestra el mensaje de falta de permiso y no la tabla', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      return Promise.resolve(
        respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
      )
    })

    renderPantalla()

    expect(await screen.findByText(/no ten[eé]s permiso/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
