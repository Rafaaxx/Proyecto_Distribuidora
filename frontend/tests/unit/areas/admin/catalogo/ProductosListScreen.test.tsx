import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ProductosListScreen } from '../../../../../src/areas/admin/catalogo/ProductosListScreen'
import type { RolDePrueba } from '../../../utils/permisosDePrueba'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

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

const SIN_PERMISO_DE_CATALOGO = 'No tenés permiso para gestionar el catálogo.'

/**
 * Monta la pantalla con `['yo']` ya sembrado (auxiliar compartido de la
 * tarea 6.7): el permiso sale de la consulta de sesión y no de un `apiFetch`
 * interceptado. Los roles son los de `01-dominio.md` §19 (GES tiene
 * `GESTIONAR_CATALOGO`, SUP no).
 */
function renderPantalla(rol: RolDePrueba = 'GES') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/catalogo/productos']}>
        <ProductosListScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Tarea 10.4: listado con búsqueda, filtros y "cargar más". Tarea 8.2 del
 * change 06b: la visibilidad sale de `['yo']` y el 403 del servidor queda
 * como red de seguridad. Los tres escenarios de la spec
 * `catalogo/administracion-de-catalogo` ("Usuario con permiso", "Usuario sin
 * permiso" y "El servidor rechaza aunque la interfaz creía tener el
 * permiso") están cubiertos abajo.
 *
 * Línea base de la suite: 6 casos, todos verdes antes de la tarea 8.2. */
describe('ProductosListScreen (tareas 10.4 y 8.2, B2)', () => {
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

  it('sin el permiso en la consulta de sesión no pide datos de catálogo, no muestra el listado ni las acciones de alta o edición (B2, escenario "Usuario sin permiso")', async () => {
    renderPantalla('SUP')

    expect(await screen.findByText(SIN_PERMISO_DE_CATALOGO)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /nuevo producto/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /editar/i })).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('si el servidor rechaza aunque la interfaz creía tener el permiso, muestra la falta de permiso sin listado, sin acciones y sin error genérico (red de seguridad, SEG-06)', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA_MARCAS))
      return Promise.resolve(
        respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
      )
    })

    renderPantalla('GES')

    expect(await screen.findByText(SIN_PERMISO_DE_CATALOGO)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /editar/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/no se pudieron obtener los productos/i)).not.toBeInTheDocument()
  })
})
