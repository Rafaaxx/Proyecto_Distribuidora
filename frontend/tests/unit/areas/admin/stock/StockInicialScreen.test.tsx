import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { StockInicialScreen } from '../../../../../src/areas/admin/stock/StockInicialScreen'
import { enrutar, llamadas, respuestaJson, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const UBICACION = '11111111-1111-4111-8111-111111111111'
const VINO = '22222222-2222-4222-8222-222222222222'
const CERVEZA = '33333333-3333-4333-8333-333333333333'
const ACEPTADO = { ubicacion_id: UBICACION, lineas: [] }

const PRODUCTOS = [
  { id: VINO, codigo: 'COD-1', nombre: 'Vino A', activo: true },
  { id: CERVEZA, codigo: 'COD-2', nombre: 'Cerveza B', activo: true },
]

function detalle(id: string, unidadesBase: number | null) {
  return {
    ...(PRODUCTOS.find((p) => p.id === id) ?? {}),
    presentaciones:
      unidadesBase === null
        ? []
        : [{ id: `${id}-p`, producto_id: id, nombre: `Caja x${String(unidadesBase)}`, unidades_base: unidadesBase, es_referencia: true }],
  }
}

function reglasBase(): ReglaDeApi[] {
  return [
    { metodo: 'GET', ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: { items: [{ id: UBICACION, nombre: 'Depósito central', tipo: 'DEPOSITO', requiere_toma: false, activo: true, actualizado_en: '2026-01-01T00:00:00Z' }], cursor_siguiente: null } }) },
    { metodo: 'GET', ruta: '/catalogo/productos', responder: () => ({ status: 200, cuerpo: { items: PRODUCTOS, cursor_siguiente: null } }) },
    { metodo: 'GET', ruta: `/catalogo/productos/${VINO}`, responder: () => ({ status: 200, cuerpo: detalle(VINO, 6) }) },
    { metodo: 'GET', ruta: `/catalogo/productos/${CERVEZA}`, responder: () => ({ status: 200, cuerpo: detalle(CERVEZA, null) }) },
    { metodo: 'GET', ruta: `/catalogo/productos/${VINO}/costo`, responder: () => ({ status: 200, cuerpo: { producto_id: VINO, costo_promedio: '1000.000000', stock_total: 60 } }) },
    { metodo: 'GET', ruta: `/catalogo/productos/${CERVEZA}/costo`, responder: () => ({ status: 200, cuerpo: { producto_id: CERVEZA, costo_promedio: null, stock_total: 0 } }) },
    { metodo: 'POST', ruta: '/stock/iniciales', responder: () => ({ status: 201, cuerpo: ACEPTADO }) },
  ]
}

function renderForm(rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[`/admin/stock/ubicaciones/${UBICACION}/stock-inicial`]}>
        <Routes>
          <Route path="/admin/stock/ubicaciones/:ubicacionId/stock-inicial" element={<StockInicialScreen />} />
          <Route path="/admin/stock/ubicaciones/:ubicacionId/stock" element={<p>Pantalla de stock</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function elegirProducto(usuario: ReturnType<typeof userEvent.setup>, id: string, nombre: RegExp, indice = 0) {
  const selectores = await screen.findAllByLabelText('Producto')
  const selector = selectores[indice] as HTMLSelectElement
  await waitFor(() => expect(within(selector).getByRole('option', { name: nombre })).toBeInTheDocument())
  await usuario.selectOptions(selector, id)
}


function cuerpoDePost(indice = 0): unknown {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', '/stock/iniciales')[indice]?.init.body))
}

function operationId(indice: number): string | null {
  return new Headers(llamadas(apiFetchMock, 'POST', '/stock/iniciales')[indice]?.init.headers).get('Operation-Id')
}

describe('StockInicialScreen (tarea 8.4; D1, D4, D5, D6, D14, D15)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, reglasBase())
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('convierte cajas + unidades a base, manda el costo como string y vuelve al stock', async () => {
    const usuario = userEvent.setup()
    renderForm()

    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Cajas'), '5')
    await usuario.type(screen.getByLabelText('Unidades'), '1')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '1100.50')
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    expect(await screen.findByText('Pantalla de stock')).toBeInTheDocument()
    expect(cuerpoDePost()).toEqual({
      ubicacion_id: UBICACION,
      lineas: [{ producto_id: VINO, cantidad_base: 31, costo_unitario: '1100.50' }],
    })
    expect(operationId(0)).toBeTruthy()
  })

  it('un producto sin presentación de referencia se carga solo en unidades', async () => {
    const usuario = userEvent.setup()
    renderForm()

    await elegirProducto(usuario, CERVEZA, /Cerveza B/)
    await waitFor(() => expect(screen.getByLabelText('Cajas')).toBeDisabled())
    await usuario.type(screen.getByLabelText('Unidades'), '24')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '7')
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    await screen.findByText('Pantalla de stock')
    expect(cuerpoDePost()).toEqual({
      ubicacion_id: UBICACION,
      lineas: [{ producto_id: CERVEZA, cantidad_base: 24, costo_unitario: '7' }],
    })
  })

  it('admite varias líneas, y una corrección lleva cantidad negativa y ningún costo', async () => {
    const usuario = userEvent.setup()
    renderForm()

    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Unidades'), '10')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '5')
    await usuario.click(screen.getByRole('button', { name: 'Agregar línea' }))
    await elegirProducto(usuario, CERVEZA, /Cerveza B/, 1)
    await usuario.selectOptions(screen.getAllByLabelText('Tipo de línea')[1] as HTMLElement, 'CORRECCION')
    expect(screen.getAllByLabelText('Costo por unidad base')).toHaveLength(1) // la corrección no lleva costo
    await usuario.type(screen.getAllByLabelText('Unidades')[1] as HTMLElement, '3')
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    await screen.findByText('Pantalla de stock')
    expect(cuerpoDePost()).toEqual({
      ubicacion_id: UBICACION,
      lineas: [
        { producto_id: VINO, cantidad_base: 10, costo_unitario: '5' },
        { producto_id: CERVEZA, cantidad_base: -3 },
      ],
    })
  })

  it('una línea se puede quitar y no se envía un producto repetido', async () => {
    const usuario = userEvent.setup()
    renderForm()
    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Unidades'), '1')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '5')
    await usuario.click(screen.getByRole('button', { name: 'Agregar línea' }))
    await elegirProducto(usuario, VINO, /Vino A/, 1)
    await usuario.type(screen.getAllByLabelText('Unidades')[1] as HTMLElement, '1')
    await usuario.type(screen.getAllByLabelText('Costo por unidad base')[1] as HTMLElement, '5')

    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Línea 2: Un producto no puede repetirse en el mismo envío.')
    expect(llamadas(apiFetchMock, 'POST', '/stock/iniciales')).toHaveLength(0)

    await usuario.click(screen.getAllByRole('button', { name: 'Quitar línea' })[1] as HTMLElement)
    expect(screen.getAllByLabelText('Unidades')).toHaveLength(1)
  })

  it('una línea inválida no se envía y dice cuál es', async () => {
    const usuario = userEvent.setup()
    renderForm()

    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Cajas'), '1')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '1,5')
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Línea 1: Ingresá un costo mayor a cero')
    expect(llamadas(apiFetchMock, 'POST', '/stock/iniciales')).toHaveLength(0)
  })

  it('avisa que requiere conexión y no encola nada', async () => {
    renderForm()

    expect(await screen.findByText(/requiere conexión con el servidor/)).toBeInTheDocument()
  })

  it('tras un corte de red reintenta con el mismo Operation-Id; con datos distintos, con otro', async () => {
    apiFetchMock.mockReset()
    let intentos = 0
    const reglas = reglasBase().filter((r) => r.metodo !== 'POST')
    enrutar(apiFetchMock, reglas)
    const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        intentos += 1
        return intentos <= 3 ? Promise.reject(new TypeError('Failed to fetch')) : Promise.resolve(respuestaJson(201, ACEPTADO))
      }
      return base(ruta, init)
    })
    const usuario = userEvent.setup()
    renderForm()
    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Unidades'), '10')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '5')

    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Se necesita conexión')
    const primero = operationId(0)
    expect(primero).toBeTruthy()
    const enviados = llamadas(apiFetchMock, 'POST', '/stock/iniciales').length

    // El usuario reintenta exactamente lo mismo: el mismo Operation-Id.
    intentos = 3
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))
    await screen.findByText('Pantalla de stock')
    expect(operationId(enviados)).toBe(primero)
  })

  it('un cambio de datos tras un corte de red usa otro Operation-Id', async () => {
    apiFetchMock.mockReset()
    let intentos = 0
    const reglas = reglasBase().filter((r) => r.metodo !== 'POST')
    enrutar(apiFetchMock, reglas)
    const base = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
    apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        intentos += 1
        return intentos <= 3 ? Promise.reject(new TypeError('Failed to fetch')) : Promise.resolve(respuestaJson(201, ACEPTADO))
      }
      return base(ruta, init)
    })
    const usuario = userEvent.setup()
    renderForm()
    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Unidades'), '10')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '5')
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))
    await screen.findByRole('alert')
    const primero = operationId(0)
    const enviados = llamadas(apiFetchMock, 'POST', '/stock/iniciales').length

    await usuario.type(screen.getByLabelText('Unidades'), '5') // 105 unidades: otro dato
    intentos = 3
    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    await screen.findByText('Pantalla de stock')
    expect(operationId(enviados)).not.toBe(primero)
  })

  it('muestra el mensaje del servidor ante un rechazo y no lo reintenta solo', async () => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      ...reglasBase().filter((r) => r.metodo !== 'POST'),
      {
        metodo: 'POST',
        ruta: '/stock/iniciales',
        responder: () => ({ status: 409, cuerpo: { title: 'El saldo es 0 y se pretende egresar 3.', codigo: 'STOCK_INSUFICIENTE' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderForm()
    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.selectOptions(screen.getByLabelText('Tipo de línea'), 'CORRECCION')
    await usuario.type(screen.getByLabelText('Unidades'), '3')

    await usuario.click(screen.getByRole('button', { name: 'Registrar stock inicial' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('El saldo es 0 y se pretende egresar 3.')
    expect(llamadas(apiFetchMock, 'POST', '/stock/iniciales')).toHaveLength(1)
  })

  it('un Administrador ve la previsualización del promedio con la función de CST-11', async () => {
    const usuario = userEvent.setup()
    renderForm('ADM')

    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Cajas'), '10') // 60 unidades
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '1100')

    // 60 a 1000 (vigente) + 60 a 1100 = 1050 (`01` §6.2).
    expect(await screen.findByText('Promedio resultante: $ 1.050,000000')).toBeInTheDocument()
  })

  it('la previsualización con stock previo 0 y sin promedio es el costo del ingreso', async () => {
    const usuario = userEvent.setup()
    renderForm('ADM')

    await elegirProducto(usuario, CERVEZA, /Cerveza B/)
    await usuario.type(screen.getByLabelText('Unidades'), '10')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '7.5')

    expect(await screen.findByText('Promedio resultante: $ 7,500000')).toBeInTheDocument()
  })

  it('sin IMPORTAR_DATOS no se monta el formulario ni se pide nada', async () => {
    renderForm('VEN')

    expect(await screen.findByText('No tenés permiso para registrar stock inicial.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Registrar stock inicial' })).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('quien tiene IMPORTAR_DATOS pero no VER_COSTOS no ve la previsualización ni pide costos', async () => {
    const usuario = userEvent.setup()
    const queryClient = queryClientConYo('ADM', {
      permisos: ['IMPORTAR_DATOS', 'TRANSFERIR_STOCK', 'GESTIONAR_CATALOGO'],
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/admin/stock/ubicaciones/${UBICACION}/stock-inicial`]}>
          <Routes>
            <Route path="/admin/stock/ubicaciones/:ubicacionId/stock-inicial" element={<StockInicialScreen />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await elegirProducto(usuario, VINO, /Vino A/)
    await usuario.type(screen.getByLabelText('Unidades'), '10')
    await usuario.type(screen.getByLabelText('Costo por unidad base'), '1100')

    expect(screen.queryByText(/Promedio resultante/)).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', /\/costo$/)).toHaveLength(0)
  })
})
