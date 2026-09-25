import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import type { components } from '../../../../../src/api/schema.gen'
import { ProductoFormScreen } from '../../../../../src/areas/admin/catalogo/ProductoFormScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PAGINA_VACIA = { items: [], cursor_siguiente: null }
const CATEGORIA_ID = '11111111-1111-4111-8111-111111111111'
const ALICUOTA_ID = '22222222-2222-4222-8222-222222222222'
// Change 06 (D8/D9/D13, tarea 11.6): el selector de proveedor del
// formulario de producto usa `GET /proveedores/opciones`.
const PROVEEDOR_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const PAGINA_CATEGORIAS = {
  items: [{ id: CATEGORIA_ID, nombre: 'Bebidas', activo: true, creado_en: '2026-01-01T00:00:00Z', actualizado_en: '2026-01-01T00:00:00Z' }],
  cursor_siguiente: null,
}
const PAGINA_ALICUOTAS = {
  items: [{ id: ALICUOTA_ID, nombre: '21%', valor: '0.210000', activo: true }],
  cursor_siguiente: null,
}
const PAGINA_PROVEEDOR_OPCIONES = {
  items: [{ id: PROVEEDOR_ID, nombre: 'Bodega Andina' }],
  cursor_siguiente: null,
}

/**
 * Tarea 10.9: registra TAMBIÉN la ruta de detalle (`:productoId`), no solo
 * `nuevo`. La versión anterior de este render solo montaba
 * `ProductoFormScreen` en `/admin/catalogo/productos/nuevo` y mockeaba
 * `useNavigate` entero -- así se podía comprobar que se *llamaba* a
 * `navigate(...)` con el string correcto, pero nunca que React Router
 * realmente resolviera esa ruta y renderizara algo. Con las dos rutas
 * reales registradas, `navigate()` (sin mockear) fuerza un re-render real
 * del árbol y esta prueba puede afirmar que la pantalla de detalle
 * efectivamente aparece.
 */
function renderAlta() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/catalogo/productos/nuevo']}>
        <Routes>
          <Route path="/admin/catalogo/productos/nuevo" element={<ProductoFormScreen />} />
          <Route path="/admin/catalogo/productos/:productoId" element={<ProductoFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// Tarea 10.9: tipado con `satisfies` contra `ProductoDetalleResponse` real
// (`schema.gen.ts`, generado del OpenAPI del backend) en vez de un objeto
// suelto -- si el contrato real cambia de forma (campo renombrado,
// obligatorio que pasa a faltar, etc.) este archivo deja de compilar en vez
// de seguir mockeando una forma vieja en silencio.
const PRODUCTO_DETALLE = {
  id: '33333333-3333-4333-8333-333333333333',
  codigo: 'GAS-001',
  nombre: 'Gaseosa cola',
  categoria_id: CATEGORIA_ID,
  marca_id: null,
  proveedor_id: PROVEEDOR_ID,
  unidad_base: 'unidad',
  alicuota_id: ALICUOTA_ID,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
  proveedor_nombre: 'Bodega Andina',
  presentaciones: [
    {
      id: '44444444-4444-4444-8444-444444444444',
      producto_id: '33333333-3333-4333-8333-333333333333',
      nombre: 'Caja x12',
      unidades_base: 12,
      usar_en_venta: true,
      usar_en_compra: true,
      es_referencia: true,
      activo: true,
      creado_en: '2026-01-01T00:00:00Z',
      actualizado_en: '2026-01-01T00:00:00Z',
    },
    {
      id: '55555555-5555-4555-8555-555555555555',
      producto_id: '33333333-3333-4333-8333-333333333333',
      nombre: 'Pack x24',
      unidades_base: 24,
      usar_en_venta: true,
      usar_en_compra: false,
      es_referencia: false,
      activo: true,
      creado_en: '2026-01-01T00:00:00Z',
      actualizado_en: '2026-01-01T00:00:00Z',
    },
  ],
} satisfies components['schemas']['ProductoDetalleResponse']

function renderEdicion(productoId = PRODUCTO_DETALLE.id) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/catalogo/productos/${productoId}`]}>
        <Routes>
          <Route path="/admin/catalogo/productos/:productoId" element={<ProductoFormScreen />} />
          {/* Tarea 10.12: ruta real del listado, para poder afirmar que
              "Guardar cambios" navega efectivamente ahí (no solo que se
              llamó a `navigate`). */}
          <Route path="/admin/catalogo" element={<p>Listado de catálogo</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProductoFormScreen — alta (tarea 10.5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  /**
   * Tarea 10.9 (diagnóstico del alta: "la página no cambia" reportado en la
   * verificación manual 13.5). Esta prueba ya no mockea `useNavigate`: usa
   * el `MemoryRouter` real con las dos rutas de `ProductoFormScreen`
   * registradas (`renderAlta`) y una respuesta de creación tipada contra el
   * contrato real (`PRODUCTO_DETALLE satisfies
   * components['schemas']['ProductoDetalleResponse']`). Antes solo
   * afirmaba que se había *llamado* a `navigate(...)` con el string
   * correcto; ahora afirma que la pantalla de detalle real se renderiza
   * (encabezado con código y nombre, presentación visible) -- lo que la
   * versión anterior no podía detectar si la navegación real hubiera
   * fallado.
   */
  it('crea un producto con una presentación de referencia y navega al detalle', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      if (ruta === '/catalogo/productos') return Promise.resolve(respuesta(201, PRODUCTO_DETALLE))
      if (ruta === `/catalogo/productos/${PRODUCTO_DETALLE.id}`) return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^código$/i), 'GAS-001')
    await screen.findByRole('option', { name: 'Bebidas' })
    // El campo "Nombre" del producto y el de la primera presentación
    // comparten etiqueta: el primero es el del producto.
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[0], 'Gaseosa cola')
    await usuarioEvento.selectOptions(screen.getByLabelText(/categoría/i), CATEGORIA_ID)
    await screen.findByRole('option', { name: 'Bodega Andina' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/proveedor/i), PROVEEDOR_ID)
    await screen.findByRole('option', { name: '21%' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/alícuota/i), ALICUOTA_ID)
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[1], 'Caja x12')

    await usuarioEvento.click(screen.getByRole('button', { name: /crear producto/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith('/catalogo/productos', expect.anything()))
    const llamadaCrear = apiFetchMock.mock.calls.find(([ruta]) => ruta === '/catalogo/productos')
    expect(llamadaCrear).toBeDefined()
    const [, opciones] = llamadaCrear as [string, RequestInit]
    const cuerpo = JSON.parse(opciones.body as string) as { presentaciones: unknown[]; alicuota_id: string }
    expect(cuerpo.presentaciones).toHaveLength(1)
    expect(cuerpo.alicuota_id).toBe(ALICUOTA_ID)

    // La navegación real ocurrió: la pantalla de detalle del producto
    // recién creado está en pantalla (no solo se llamó a `navigate`).
    expect(await screen.findByRole('heading', { name: `${PRODUCTO_DETALLE.codigo} — ${PRODUCTO_DETALLE.nombre}` })).toBeInTheDocument()
    expect(screen.getByText('Caja x12')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /nuevo producto/i })).not.toBeInTheDocument()
  })

  it('muestra CODIGO_DUPLICADO junto al campo código y conserva el resto de los datos cargados', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      if (ruta === '/catalogo/productos') {
        return Promise.resolve(respuesta(409, { title: 'El código ya está en uso.', codigo: 'CODIGO_DUPLICADO' }))
      }
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^código$/i), 'GAS-001')
    await screen.findByRole('option', { name: 'Bebidas' })
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[0], 'Gaseosa cola')
    await usuarioEvento.selectOptions(screen.getByLabelText(/categoría/i), CATEGORIA_ID)
    await screen.findByRole('option', { name: 'Bodega Andina' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/proveedor/i), PROVEEDOR_ID)
    await screen.findByRole('option', { name: '21%' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/alícuota/i), ALICUOTA_ID)
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[1], 'Caja x12')

    await usuarioEvento.click(screen.getByRole('button', { name: /crear producto/i }))

    expect(await screen.findByText('El código ya está en uso.')).toBeInTheDocument()
    // Los datos cargados se conservan: el nombre sigue en el campo.
    expect(screen.getAllByLabelText(/^nombre$/i)[0]).toHaveValue('Gaseosa cola')
    // No hubo navegación real: seguimos en el formulario de alta.
    expect(screen.getByRole('heading', { name: /nuevo producto/i })).toBeInTheDocument()
  })
})

describe('ProductoFormScreen — selector de alícuota (tarea 10.7, D12)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  const ALICUOTA_10_5_ID = '66666666-6666-4666-8666-666666666666'
  const ALICUOTA_27_INACTIVA_ID = '77777777-7777-4777-8777-777777777777'
  const PAGINA_ALICUOTAS_MIXTA = {
    items: [
      { id: ALICUOTA_ID, nombre: '21%', valor: '0.210000', activo: true },
      { id: ALICUOTA_10_5_ID, nombre: '10,5%', valor: '0.105000', activo: true },
      { id: ALICUOTA_27_INACTIVA_ID, nombre: '27%', valor: '0.270000', activo: false },
    ],
    cursor_siguiente: null,
  }

  it('el selector ofrece las alícuotas activas y no una desactivada', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS_MIXTA))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    renderAlta()

    expect(await screen.findByRole('option', { name: '21%' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '10,5%' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '27%' })).not.toBeInTheDocument()
  })

  it('el alta con la alícuota 21% elegida envía su alicuota_id en el comando', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS_MIXTA))
      if (ruta === '/catalogo/productos') return Promise.resolve(respuesta(201, PRODUCTO_DETALLE))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^código$/i), 'GAS-001')
    await screen.findByRole('option', { name: 'Bebidas' })
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[0], 'Gaseosa cola')
    await usuarioEvento.selectOptions(screen.getByLabelText(/categoría/i), CATEGORIA_ID)
    await screen.findByRole('option', { name: 'Bodega Andina' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/proveedor/i), PROVEEDOR_ID)
    await screen.findByRole('option', { name: '21%' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/alícuota/i), ALICUOTA_ID)
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[1], 'Caja x12')

    await usuarioEvento.click(screen.getByRole('button', { name: /crear producto/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith('/catalogo/productos', expect.anything()))
    const llamadaCrear = apiFetchMock.mock.calls.find(([ruta]) => ruta === '/catalogo/productos')
    const [, opciones] = llamadaCrear as [string, RequestInit]
    const cuerpo = JSON.parse(opciones.body as string) as { alicuota_id: string }
    expect(cuerpo.alicuota_id).toBe(ALICUOTA_ID)
  })
})

describe('ProductoFormScreen — solo categorías/marcas activas (tarea 10.6, CAT-05)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('no ofrece una categoría inactiva en el selector', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) {
        return Promise.resolve(
          respuesta(200, {
            items: [
              { id: CATEGORIA_ID, nombre: 'Bebidas', activo: true, creado_en: '2026-01-01T00:00:00Z', actualizado_en: '2026-01-01T00:00:00Z' },
              { id: '99999999-9999-4999-8999-999999999999', nombre: 'Descontinuados', activo: false, creado_en: '2026-01-01T00:00:00Z', actualizado_en: '2026-01-01T00:00:00Z' },
            ],
            cursor_siguiente: null,
          }),
        )
      }
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    renderAlta()

    expect(await screen.findByRole('option', { name: 'Bebidas' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Descontinuados' })).not.toBeInTheDocument()
  })

  it('no ofrece una marca desactivada en el selector (13.1, spec administracion-de-catalogo)', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) {
        return Promise.resolve(
          respuesta(200, {
            items: [
              { id: '88888888-8888-4888-8888-888888888888', nombre: 'Bodega Sur', activo: true, creado_en: '2026-01-01T00:00:00Z', actualizado_en: '2026-01-01T00:00:00Z' },
              { id: '99999999-9999-4999-8999-999999999998', nombre: 'Bodega Norte', activo: false, creado_en: '2026-01-01T00:00:00Z', actualizado_en: '2026-01-01T00:00:00Z' },
            ],
            cursor_siguiente: null,
          }),
        )
      }
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    renderAlta()

    expect(await screen.findByRole('option', { name: 'Bodega Sur' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Bodega Norte' })).not.toBeInTheDocument()
  })
})

describe('ProductoFormScreen — selector de proveedor (tarea 11.6, D8/D9/D13)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('el proveedor es obligatorio: sin elegirlo, no se envía el alta', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^código$/i), 'GAS-001')
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[0], 'Gaseosa cola')
    await usuarioEvento.selectOptions(screen.getByLabelText(/categoría/i), CATEGORIA_ID)
    await screen.findByRole('option', { name: '21%' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/alícuota/i), ALICUOTA_ID)
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[1], 'Caja x12')

    await usuarioEvento.click(screen.getByRole('button', { name: /crear producto/i }))

    expect(await screen.findByText('Elegí un proveedor.')).toBeInTheDocument()
    expect(apiFetchMock.mock.calls.some(([ruta, opciones]) => ruta === '/catalogo/productos' && (opciones as RequestInit)?.method === 'POST')).toBe(false)
  })

  it('PROVEEDOR_INACTIVO informado por el servidor se muestra junto al campo proveedor', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      if (ruta === '/catalogo/productos') {
        return Promise.resolve(
          respuesta(422, { title: 'El proveedor está inactivo.', codigo: 'PROVEEDOR_INACTIVO' }),
        )
      }
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    const usuarioEvento = userEvent.setup()
    renderAlta()

    await usuarioEvento.type(screen.getByLabelText(/^código$/i), 'GAS-001')
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[0], 'Gaseosa cola')
    await usuarioEvento.selectOptions(screen.getByLabelText(/categoría/i), CATEGORIA_ID)
    await screen.findByRole('option', { name: 'Bodega Andina' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/proveedor/i), PROVEEDOR_ID)
    await screen.findByRole('option', { name: '21%' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/alícuota/i), ALICUOTA_ID)
    await usuarioEvento.type(screen.getAllByLabelText(/^nombre$/i)[1], 'Caja x12')

    await usuarioEvento.click(screen.getByRole('button', { name: /crear producto/i }))

    const mensaje = await screen.findByText('El proveedor está inactivo.')
    // Junto al campo proveedor, no como error general (`errors.root`).
    expect(mensaje.closest('div')?.querySelector('#proveedorId')).not.toBeNull()
  })

  it('en edición, si el proveedor actual está inactivo se ofrece con su nombre real seguido de "(inactivo)"', async () => {
    const PROVEEDOR_INACTIVO_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    const detalleConProveedorInactivo = {
      ...PRODUCTO_DETALLE,
      proveedor_id: PROVEEDOR_INACTIVO_ID,
      proveedor_nombre: 'Bodega Sur',
    }
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      return Promise.resolve(respuesta(200, detalleConProveedorInactivo))
    })

    renderEdicion()

    expect(await screen.findByRole('option', { name: 'Bodega Sur (inactivo)' })).toBeInTheDocument()
    expect(screen.getByLabelText(/proveedor/i)).toHaveValue(PROVEEDOR_INACTIVO_ID)
    // El proveedor activo sigue disponible para poder cambiarlo.
    expect(screen.getByRole('option', { name: 'Bodega Andina' })).toBeInTheDocument()
  })
})

describe('ProductoFormScreen — edición (tarea 10.5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  function mockearDetalle() {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      if (ruta === `/catalogo/productos/${PRODUCTO_DETALLE.id}`) return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
      return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
    })
  }

  it('muestra la equivalencia CAT-08 de cada presentación contra la referencia', async () => {
    mockearDetalle()
    renderEdicion()

    // Pack x24 sobre Caja x12 (referencia) -> 2 cajas + 0 unidades.
    expect(await screen.findByText('= 2 Caja x12(s) + 0 unidad(es)')).toBeInTheDocument()
  })

  it('"usar como referencia" envía PUT a /productos/{id}/referencia con el id de la presentación', async () => {
    mockearDetalle()
    const usuarioEvento = userEvent.setup()
    renderEdicion()

    await screen.findByText('Pack x24')
    apiFetchMock.mockResolvedValueOnce(
      respuesta(200, { ...PRODUCTO_DETALLE.presentaciones[1], es_referencia: true }),
    )

    await usuarioEvento.click(screen.getByRole('button', { name: /usar como referencia/i }))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        `/catalogo/productos/${PRODUCTO_DETALLE.id}/referencia`,
        expect.objectContaining({ method: 'PUT' }),
      ),
    )
    const llamada = apiFetchMock.mock.calls.find(([ruta]) => String(ruta).includes('/referencia'))
    const [, opciones] = llamada as [string, RequestInit]
    const cuerpo = JSON.parse(opciones.body as string) as { presentacion_id: string }
    expect(cuerpo.presentacion_id).toBe(PRODUCTO_DETALLE.presentaciones[1].id)
  })

  it('ante UNIDADES_CONGELADAS al editar una presentación usada, muestra el mensaje del servidor (13.1, CAT-04/INV-18)', async () => {
    mockearDetalle()
    const usuarioEvento = userEvent.setup()
    renderEdicion()

    await screen.findByText('Pack x24')
    apiFetchMock.mockImplementation((ruta: string, opciones?: RequestInit) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.includes('/presentaciones/') && opciones?.method === 'PUT') {
        return Promise.resolve(
          respuesta(409, {
            title:
              'Las unidades de una presentación ya usada no pueden modificarse (CAT-04, INV-18): creá una presentación nueva y desactivá esta.',
            codigo: 'UNIDADES_CONGELADAS',
          }),
        )
      }
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
    })

    await usuarioEvento.click(screen.getAllByRole('button', { name: /^editar$/i })[1])
    const dialogo = await screen.findByRole('dialog', { name: /editar presentación/i })
    const campoUnidades = within(dialogo).getByLabelText(/unidades base/i)
    await usuarioEvento.clear(campoUnidades)
    await usuarioEvento.type(campoUnidades, '48')
    await usuarioEvento.click(within(dialogo).getByRole('button', { name: /^guardar$/i }))

    expect(
      await screen.findByText(
        'Las unidades de una presentación ya usada no pueden modificarse (CAT-04, INV-18): creá una presentación nueva y desactivá esta.',
      ),
    ).toBeInTheDocument()
  })

  /**
   * Tarea 10.12 (bug reportado en verificación manual 13.5): "Guardar
   * cambios" en la edición de producto guardaba correctamente pero nunca
   * redirigía al listado. Se usa el `MemoryRouter` real con la ruta
   * `/admin/catalogo` registrada para afirmar que la navegación ocurrió de
   * verdad (no solo que se llamó a `navigate`).
   */
  it('al guardar cambios exitosamente, navega al listado /admin/catalogo', async () => {
    mockearDetalle()
    const usuarioEvento = userEvent.setup()
    renderEdicion()

    await screen.findByText('Pack x24')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(await screen.findByText('Listado de catálogo')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: `${PRODUCTO_DETALLE.codigo} — ${PRODUCTO_DETALLE.nombre}` })).not.toBeInTheDocument()
  })

  /**
   * Bug 13.5 (14.3): `CostosHistorialScreen` (`/admin/proveedores/productos/:productoId/historial`)
   * estaba huérfana -- ningún enlace llevaba a ella. La spec
   * `administracion-de-proveedores` exige que el historial se muestre
   * solo con `VER_COSTOS`; no existe en el frontend un mecanismo propio
   * de permisos (el access token no los lleva), así que se reutiliza el
   * mismo criterio reactivo que ya usa `CostosHistorialScreen`: intentar
   * la consulta real de costo vigente (`GET
   * /costos/productos/{id}/vigente`) y mostrar el enlace solo si esa
   * consulta tiene éxito.
   */
  it('con VER_COSTOS, muestra el enlace "Ver historial de costos" con el href correcto', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      if (ruta.startsWith(`/costos/productos/${PRODUCTO_DETALLE.id}/vigente`)) {
        return Promise.resolve(respuesta(200, { costo: null, fecha: '2026-09-25' }))
      }
      return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
    })

    renderEdicion()

    const enlace = await screen.findByRole('link', { name: /ver historial de costos/i })
    expect(enlace).toHaveAttribute('href', `/admin/proveedores/productos/${PRODUCTO_DETALLE.id}/historial`)
  })

  it('sin VER_COSTOS (403 del servidor), no muestra el enlace "Ver historial de costos"', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      if (ruta.startsWith(`/costos/productos/${PRODUCTO_DETALLE.id}/vigente`)) {
        return Promise.resolve(respuesta(403, { title: 'No tenés permiso.', codigo: 'PERMISO_REQUERIDO' }))
      }
      return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
    })

    renderEdicion()

    await screen.findByText('Pack x24')
    expect(screen.queryByRole('link', { name: /ver historial de costos/i })).not.toBeInTheDocument()
  })

  it('en modo alta (sin producto existente), no muestra el enlace "Ver historial de costos"', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_CATEGORIAS))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      throw new Error(`ruta inesperada: ${ruta}`)
    })

    renderAlta()

    await screen.findByRole('option', { name: 'Bebidas' })
    expect(screen.queryByRole('link', { name: /ver historial de costos/i })).not.toBeInTheDocument()
  })

  it('si falla el guardado de cambios (código duplicado), no navega y muestra el error', async () => {
    apiFetchMock.mockImplementation((ruta: string, opciones?: RequestInit) => {
      if (ruta.startsWith('/proveedores/opciones')) return Promise.resolve(respuesta(200, PAGINA_PROVEEDOR_OPCIONES))
      if (ruta === `/catalogo/productos/${PRODUCTO_DETALLE.id}` && opciones?.method === 'PUT') {
        return Promise.resolve(respuesta(409, { title: 'El código ya está en uso.', codigo: 'CODIGO_DUPLICADO' }))
      }
      if (ruta.startsWith('/catalogo/categorias')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/catalogo/marcas')) return Promise.resolve(respuesta(200, PAGINA_VACIA))
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, PAGINA_ALICUOTAS))
      return Promise.resolve(respuesta(200, PRODUCTO_DETALLE))
    })

    const usuarioEvento = userEvent.setup()
    renderEdicion()

    await screen.findByText('Pack x24')
    await usuarioEvento.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(await screen.findByText('El código ya está en uso.')).toBeInTheDocument()
    // No hubo navegación: seguimos en el formulario de edición.
    expect(screen.getByRole('heading', { name: `${PRODUCTO_DETALLE.codigo} — ${PRODUCTO_DETALLE.nombre}` })).toBeInTheDocument()
    expect(screen.queryByText('Listado de catálogo')).not.toBeInTheDocument()
  })
})
