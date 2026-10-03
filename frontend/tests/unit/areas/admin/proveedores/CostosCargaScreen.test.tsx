import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CostosCargaScreen } from '../../../../../src/areas/admin/proveedores/CostosCargaScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PROVEEDOR_ID = '11111111-1111-4111-8111-111111111111'
const PROVEEDOR = {
  id: PROVEEDOR_ID,
  nombre: 'Cervecería Central',
  cuit: null,
  contacto: null,
  telefono: null,
  email: null,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const CERVEZA_B_ID = '22222222-2222-4222-8222-222222222222'
const PRESENTACION_CAJA_X12_ID = '33333333-3333-4333-8333-333333333333'
const VINO_A_ID = '44444444-4444-4444-8444-444444444444'
const PRESENTACION_BOTELLA_ID = '55555555-5555-4555-8555-555555555555'
const PRESENTACION_CAJA_X6_SOLO_VENTA_ID = '66666666-6666-4666-8666-666666666666'
const ALICUOTA_21_ID = '77777777-7777-4777-8777-777777777777'
const ALICUOTA_0_ID = '88888888-8888-4888-8888-888888888888'

const PRODUCTO_CERVEZA_B = {
  id: CERVEZA_B_ID,
  codigo: 'CER-B',
  nombre: 'Cerveza B',
  categoria_id: 'c1',
  marca_id: null,
  proveedor_id: PROVEEDOR_ID,
  unidad_base: 'unidad',
  alicuota_id: ALICUOTA_21_ID,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const PRODUCTO_VINO_A = {
  id: VINO_A_ID,
  codigo: 'VIN-A',
  nombre: 'Vino A',
  categoria_id: 'c1',
  marca_id: null,
  proveedor_id: PROVEEDOR_ID,
  unidad_base: 'unidad',
  alicuota_id: ALICUOTA_0_ID,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const DETALLE_CERVEZA_B = {
  ...PRODUCTO_CERVEZA_B,
  proveedor_nombre: 'Cervecería Central',
  presentaciones: [
    {
      id: PRESENTACION_CAJA_X12_ID,
      producto_id: CERVEZA_B_ID,
      nombre: 'Caja x12',
      unidades_base: 12,
      usar_en_venta: true,
      usar_en_compra: true,
      es_referencia: true,
      activo: true,
      creado_en: '2026-01-01T00:00:00Z',
      actualizado_en: '2026-01-01T00:00:00Z',
    },
  ],
}

const DETALLE_VINO_A = {
  ...PRODUCTO_VINO_A,
  proveedor_nombre: 'Cervecería Central',
  presentaciones: [
    {
      id: PRESENTACION_BOTELLA_ID,
      producto_id: VINO_A_ID,
      nombre: 'Botella',
      unidades_base: 1,
      usar_en_venta: true,
      usar_en_compra: true,
      es_referencia: true,
      activo: true,
      creado_en: '2026-01-01T00:00:00Z',
      actualizado_en: '2026-01-01T00:00:00Z',
    },
    {
      id: PRESENTACION_CAJA_X6_SOLO_VENTA_ID,
      producto_id: VINO_A_ID,
      nombre: 'Caja x6',
      unidades_base: 6,
      usar_en_venta: true,
      usar_en_compra: false,
      es_referencia: false,
      activo: true,
      creado_en: '2026-01-01T00:00:00Z',
      actualizado_en: '2026-01-01T00:00:00Z',
    },
  ],
}

const ALICUOTAS = {
  items: [
    { id: ALICUOTA_21_ID, nombre: 'IVA 21%', valor: '0.21', activo: true },
    { id: ALICUOTA_0_ID, nombre: 'Exento', valor: '0', activo: true },
  ],
  cursor_siguiente: null,
}

function mockApiBase() {
  apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
    if (ruta === `/proveedores/${PROVEEDOR_ID}`) return Promise.resolve(respuesta(200, PROVEEDOR))
    if (ruta.startsWith('/catalogo/productos/') && !ruta.includes('?')) {
      const id = ruta.split('/').pop()
      if (id === CERVEZA_B_ID) return Promise.resolve(respuesta(200, DETALLE_CERVEZA_B))
      if (id === VINO_A_ID) return Promise.resolve(respuesta(200, DETALLE_VINO_A))
    }
    if (ruta.startsWith('/catalogo/productos')) {
      return Promise.resolve(respuesta(200, { items: [PRODUCTO_CERVEZA_B, PRODUCTO_VINO_A], cursor_siguiente: null }))
    }
    if (ruta.startsWith('/configuracion/alicuotas')) {
      return Promise.resolve(respuesta(200, ALICUOTAS))
    }
    if (ruta === '/costos' && init?.method === 'POST') {
      return Promise.resolve(
        respuesta(201, { costos: [{ id: 'a', costo_base: '1239.669421' }] }),
      )
    }
    return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
  })
}

const SIN_PERMISO_DE_COSTOS = 'No tenés permiso para cargar costos.'

/** Monta con `['yo']` ya sembrado (auxiliar compartido de la tarea 6.7): el
 * permiso de la pantalla es `EDITAR_COSTOS` (`01` §19), y el default es el
 * rol Administración, que lo tiene. */
function renderPantalla(queryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/proveedores/${PROVEEDOR_ID}/costos`]}>
        <Routes>
          <Route path="/admin/proveedores/:proveedorId/costos" element={<CostosCargaScreen />} />
          <Route path="/admin/proveedores/:proveedorId" element={<p>Ficha del proveedor</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Tarea 11.4: vista previa del costo base, envío único de un lote, error
 * en una fila conserva ambas y no marca ningún costo como registrado, y
 * el selector de presentación solo ofrece las de compra (spec
 * `administracion-de-proveedores`).
 */
describe('CostosCargaScreen (tarea 11.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('vista previa de una caja con IVA: 18000 con IVA incluido muestra 1.239,669421', async () => {
    mockApiBase()
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
    await usuarioEvento.selectOptions(await screen.findByLabelText(/presentaci[oó]n/i), PRESENTACION_CAJA_X12_ID)
    await usuarioEvento.type(screen.getByLabelText(/^valor$/i), '18000')
    await usuarioEvento.click(screen.getByLabelText(/incluye iva/i))

    await waitFor(() => expect(screen.getByTestId('vista-previa-0')).toHaveTextContent('1.239,669421'))
  })

  it('bonificación en porcentaje: 18000 sin IVA y bonificación 10% muestra 1.350,000000', async () => {
    mockApiBase()
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
    await usuarioEvento.selectOptions(await screen.findByLabelText(/presentaci[oó]n/i), PRESENTACION_CAJA_X12_ID)
    await usuarioEvento.type(screen.getByLabelText(/^valor$/i), '18000')
    await usuarioEvento.clear(screen.getByLabelText(/bonificaci[oó]n/i))
    await usuarioEvento.type(screen.getByLabelText(/bonificaci[oó]n/i), '10')

    await waitFor(() => expect(screen.getByTestId('vista-previa-0')).toHaveTextContent('1.350,000000'))
  })

  it('solo presentaciones de compra: Vino A ofrece Botella y no Caja x6', async () => {
    mockApiBase()
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Vino A' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), VINO_A_ID)

    const selectPresentacion = await screen.findByLabelText(/presentaci[oó]n/i)
    const opciones = within(selectPresentacion as HTMLSelectElement).getAllByRole('option')
    expect(opciones.map((o) => o.textContent)).toEqual(['Elegí una presentación', 'Botella'])
  })

  it('carga de dos costos en un envío: se envía un único COSTO_INFORMAR con las dos filas', async () => {
    mockApiBase()
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
    await usuarioEvento.selectOptions(await screen.findByLabelText(/presentaci[oó]n/i), PRESENTACION_CAJA_X12_ID)
    await usuarioEvento.type(screen.getByLabelText(/^valor$/i), '18000')

    await usuarioEvento.click(screen.getByRole('button', { name: /agregar costo/i }))
    const productos = screen.getAllByLabelText(/^producto$/i)
    await usuarioEvento.selectOptions(productos[1] as HTMLSelectElement, VINO_A_ID)
    const presentaciones = await screen.findAllByLabelText(/presentaci[oó]n/i)
    await usuarioEvento.selectOptions(presentaciones[1] as HTMLSelectElement, PRESENTACION_BOTELLA_ID)
    const valores = screen.getAllByLabelText(/^valor$/i)
    await usuarioEvento.type(valores[1] as HTMLInputElement, '1000')

    await usuarioEvento.click(screen.getByRole('button', { name: /cargar costos/i }))

    await waitFor(() => expect(apiFetchMock.mock.calls.some(([ruta]) => ruta === '/costos')).toBe(true))
    const llamadaCostos = apiFetchMock.mock.calls.find(([ruta]) => ruta === '/costos') as [string, RequestInit]
    const cuerpo = JSON.parse(String(llamadaCostos[1].body)) as { proveedor_id: string; costos: unknown[] }
    expect(cuerpo.proveedor_id).toBe(PROVEEDOR_ID)
    expect(cuerpo.costos).toHaveLength(2)
  })

  it('envío exitoso navega a la ficha del proveedor (bug 13.5: sin esto el usuario no sabe si funcionó)', async () => {
    mockApiBase()
    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
    await usuarioEvento.selectOptions(await screen.findByLabelText(/presentaci[oó]n/i), PRESENTACION_CAJA_X12_ID)
    await usuarioEvento.type(screen.getByLabelText(/^valor$/i), '18000')

    await usuarioEvento.click(screen.getByRole('button', { name: /cargar costos/i }))

    expect(await screen.findByText('Ficha del proveedor')).toBeInTheDocument()
  })

  it('error del servidor en la segunda fila conserva ambas filas y no muestra ningún costo registrado', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (ruta === `/proveedores/${PROVEEDOR_ID}`) return Promise.resolve(respuesta(200, PROVEEDOR))
      if (ruta.startsWith('/catalogo/productos/') && !ruta.includes('?')) {
        const id = ruta.split('/').pop()
        if (id === CERVEZA_B_ID) return Promise.resolve(respuesta(200, DETALLE_CERVEZA_B))
        if (id === VINO_A_ID) return Promise.resolve(respuesta(200, DETALLE_VINO_A))
      }
      if (ruta.startsWith('/catalogo/productos')) {
        return Promise.resolve(respuesta(200, { items: [PRODUCTO_CERVEZA_B, PRODUCTO_VINO_A], cursor_siguiente: null }))
      }
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, ALICUOTAS))
      if (ruta === '/costos' && init?.method === 'POST') {
        return Promise.resolve(
          respuesta(422, {
            title: `La presentación ${PRESENTACION_BOTELLA_ID} no es una presentación de compra activa del producto ${VINO_A_ID}.`,
            codigo: 'PRESENTACION_INVALIDA',
            // contrato-api.md P9 (aprobado 2026-09-24): la API resuelve el
            // índice de la fila afectada, la segunda (índice 1).
            fila: 1,
          }),
        )
      }
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
    await usuarioEvento.selectOptions(await screen.findByLabelText(/presentaci[oó]n/i), PRESENTACION_CAJA_X12_ID)
    await usuarioEvento.type(screen.getByLabelText(/^valor$/i), '18000')

    await usuarioEvento.click(screen.getByRole('button', { name: /agregar costo/i }))
    const productos = screen.getAllByLabelText(/^producto$/i)
    await usuarioEvento.selectOptions(productos[1] as HTMLSelectElement, VINO_A_ID)
    const presentaciones = await screen.findAllByLabelText(/presentaci[oó]n/i)
    await usuarioEvento.selectOptions(presentaciones[1] as HTMLSelectElement, PRESENTACION_BOTELLA_ID)
    const valores = screen.getAllByLabelText(/^valor$/i)
    await usuarioEvento.type(valores[1] as HTMLInputElement, '1000')

    await usuarioEvento.click(screen.getByRole('button', { name: /cargar costos/i }))

    expect(await screen.findByText(/presentaci[oó]n.*no es una presentaci[oó]n de compra/i)).toBeInTheDocument()
    // Ambas filas siguen cargadas.
    expect(screen.getAllByLabelText(/^producto$/i)).toHaveLength(2)
    expect((screen.getAllByLabelText(/^valor$/i)[0] as HTMLInputElement).value).toBe('18000')
    expect((screen.getAllByLabelText(/^valor$/i)[1] as HTMLInputElement).value).toBe('1000')
  })

  it('error del servidor sin fila y que no es de permiso (p. ej. PROVEEDOR_INACTIVO) se muestra como mensaje general', async () => {
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if (ruta === `/proveedores/${PROVEEDOR_ID}`) return Promise.resolve(respuesta(200, PROVEEDOR))
      if (ruta.startsWith('/catalogo/productos/') && !ruta.includes('?')) {
        const id = ruta.split('/').pop()
        if (id === CERVEZA_B_ID) return Promise.resolve(respuesta(200, DETALLE_CERVEZA_B))
        if (id === VINO_A_ID) return Promise.resolve(respuesta(200, DETALLE_VINO_A))
      }
      if (ruta.startsWith('/catalogo/productos')) {
        return Promise.resolve(respuesta(200, { items: [PRODUCTO_CERVEZA_B, PRODUCTO_VINO_A], cursor_siguiente: null }))
      }
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, ALICUOTAS))
      if (ruta === '/costos' && init?.method === 'POST') {
        // Sin `fila`: error no específico de una fila (p. ej. proveedor
        // inactivo). Cae al mensaje general, no marca ningún campo.
        return Promise.resolve(
          respuesta(422, { title: 'El proveedor está inactivo (D5).', codigo: 'PROVEEDOR_INACTIVO' }),
        )
      }
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })

    const usuarioEvento = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    await usuarioEvento.selectOptions(screen.getByLabelText(/^producto$/i), CERVEZA_B_ID)
    await usuarioEvento.selectOptions(await screen.findByLabelText(/presentaci[oó]n/i), PRESENTACION_CAJA_X12_ID)
    await usuarioEvento.type(screen.getByLabelText(/^valor$/i), '18000')

    await usuarioEvento.click(screen.getByRole('button', { name: /cargar costos/i }))

    expect(await screen.findByText(/proveedor está inactivo/i)).toBeInTheDocument()
  })

  /**
   * Tarea 8.5 del change 06b, escenario "Usuario sin permiso" de la spec
   * `administracion-de-proveedores`: entrar por URL a la carga de costos sin
   * `EDITAR_COSTOS` muestra la falta de permiso y no pide nada
   * (**B2**, `design.md` D4-A). Antes esta pantalla no tenía ninguna
   * Red de seguridad del 403: un 403 caía en el mensaje genérico "No se
   * pudo obtener el proveedor".
   *
   * Línea base de la suite: 7 casos, todos verdes antes de la tarea 8.5.
   */
  it('sin EDITAR_COSTOS en la consulta de sesión no pide el proveedor ni los productos y muestra que falta el permiso (B2)', async () => {
    renderPantalla(queryClientConYo('VEN'))

    expect(await screen.findByText(SIN_PERMISO_DE_COSTOS)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cargar costos/i })).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('si el servidor rechaza aunque la interfaz creía tener el permiso, muestra la falta de permiso y no el mensaje genérico (red de seguridad, SEG-06)', async () => {
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta === `/proveedores/${PROVEEDOR_ID}`) {
        return Promise.resolve(
          respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
        )
      }
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })

    renderPantalla()

    expect(await screen.findByText(SIN_PERMISO_DE_COSTOS)).toBeInTheDocument()
    expect(screen.queryByText(/no se pudo obtener el proveedor/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cargar costos/i })).not.toBeInTheDocument()
  })
})

/**
 * Change 11, tarea 11.2 (deuda del change 06): el selector ofrece los productos del
 * proveedor que el SERVIDOR devuelve con `proveedor_id`, no los de la primera página
 * del catálogo filtrados en el cliente (con más de una página, un producto del proveedor
 * podía no aparecer nunca).
 */
describe('CostosCargaScreen pide los productos del proveedor al servidor (tarea 11.2)', () => {
  const PRODUCTO_AJENO = { ...PRODUCTO_VINO_A, id: '99999999-9999-4999-8999-999999999999', nombre: 'Gaseosa Ajena', proveedor_id: 'otro' }

  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockImplementation((ruta: string) => {
      if (ruta === `/proveedores/${PROVEEDOR_ID}`) return Promise.resolve(respuesta(200, PROVEEDOR))
      if (ruta.startsWith('/catalogo/productos?')) {
        const url = new URL(ruta, 'http://x')
        const items =
          url.searchParams.get('proveedor_id') === PROVEEDOR_ID ? [PRODUCTO_CERVEZA_B] : [PRODUCTO_CERVEZA_B, PRODUCTO_AJENO]
        return Promise.resolve(respuesta(200, { items, cursor_siguiente: null }))
      }
      if (ruta.startsWith('/configuracion/alicuotas')) return Promise.resolve(respuesta(200, ALICUOTAS))
      return Promise.resolve(respuesta(200, { items: [], cursor_siguiente: null }))
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('manda proveedor_id y activo al listar productos', async () => {
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    const pedidos = apiFetchMock.mock.calls
      .map(([ruta]) => String(ruta))
      .filter((ruta) => ruta.startsWith('/catalogo/productos?'))
      .map((ruta) => new URL(ruta, 'http://x').searchParams)
    expect(pedidos.length).toBeGreaterThan(0)
    for (const params of pedidos) {
      expect(params.get('proveedor_id')).toBe(PROVEEDOR_ID)
      expect(params.get('activo')).toBe('true')
    }
  })

  it('ofrece exactamente lo que devuelve el servidor y no filtra de nuevo en el cliente', async () => {
    renderPantalla()

    await screen.findByRole('option', { name: 'Cerveza B' })
    const opciones = within(screen.getByLabelText(/^producto$/i) as HTMLSelectElement).getAllByRole('option')
    expect(opciones.map((o) => o.textContent)).toEqual(['Elegí un producto', 'Cerveza B'])
  })
})
