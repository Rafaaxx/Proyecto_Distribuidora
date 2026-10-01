import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { UbicacionFormScreen } from '../../../../../src/areas/admin/stock/UbicacionFormScreen'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const ID = '11111111-1111-4111-8111-111111111111'
const DEPOSITO = {
  id: ID,
  nombre: 'Depósito central',
  tipo: 'DEPOSITO',
  requiere_toma: false,
  activo: true,
  actualizado_en: '2026-03-10T15:00:00Z',
}

function renderForm(rol: RolDePrueba, ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/stock/ubicaciones/nueva" element={<UbicacionFormScreen />} />
          <Route path="/admin/stock/ubicaciones/:ubicacionId" element={<UbicacionFormScreen />} />
          <Route path="/admin/stock" element={<p>Listado de stock</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function cuerpo(indice: number, metodo: string, ruta: string): unknown {
  const llamada = llamadas(apiFetchMock, metodo, ruta)[indice]
  return JSON.parse(String(llamada?.init.body))
}

describe('UbicacionFormScreen: alta (tarea 8.2, D2, D7)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { metodo: 'POST', ruta: '/stock/ubicaciones', responder: () => ({ status: 201, cuerpo: DEPOSITO }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un depósito se crea con su nombre y sin toma y vuelve al listado', async () => {
    const usuario = userEvent.setup()
    renderForm('ADM', '/admin/stock/ubicaciones/nueva')

    await usuario.type(screen.getByLabelText('Nombre'), '  Depósito norte ')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText('Listado de stock')).toBeInTheDocument()
    const [envio] = llamadas(apiFetchMock, 'POST', '/stock/ubicaciones')
    expect(new Headers(envio?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(cuerpo(0, 'POST', '/stock/ubicaciones')).toEqual({
      nombre: 'Depósito norte',
      tipo: 'DEPOSITO',
      requiere_toma: false,
    })
  })

  it('un vehículo marca la toma por sí mismo, no deja quitarla y se envía con toma', async () => {
    const usuario = userEvent.setup()
    renderForm('ADM', '/admin/stock/ubicaciones/nueva')

    await usuario.type(screen.getByLabelText('Nombre'), 'Camión 1')
    await usuario.selectOptions(screen.getByLabelText('Tipo'), 'VEHICULO')

    const toma = screen.getByLabelText('Requiere toma')
    expect(toma).toBeChecked()
    expect(toma).toHaveAttribute('aria-disabled', 'true')
    await usuario.click(toma)
    expect(toma).toBeChecked()
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await screen.findByText('Listado de stock')
    expect(cuerpo(0, 'POST', '/stock/ubicaciones')).toEqual({
      nombre: 'Camión 1',
      tipo: 'VEHICULO',
      requiere_toma: true,
    })
  })

  it('un nombre vacío no envía nada y avisa', async () => {
    const usuario = userEvent.setup()
    renderForm('ADM', '/admin/stock/ubicaciones/nueva')

    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText('Ingresá el nombre.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('muestra el mensaje del servidor ante un nombre duplicado y deja reintentar', async () => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/stock/ubicaciones',
        responder: () => ({ status: 409, cuerpo: { title: 'Ya existe una ubicación con ese nombre.', codigo: 'NOMBRE_DUPLICADO' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderForm('ADM', '/admin/stock/ubicaciones/nueva')

    await usuario.type(screen.getByLabelText('Nombre'), 'Depósito central')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe una ubicación con ese nombre.')
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()
    // Un rechazo con respuesta HTTP no se reintenta solo.
    expect(llamadas(apiFetchMock, 'POST', '/stock/ubicaciones')).toHaveLength(1)
  })

  it('un Vendedor (sin ADMIN_CONFIGURACION) no ve el formulario', async () => {
    renderForm('VEN', '/admin/stock/ubicaciones/nueva')

    expect(await screen.findByText('No tenés permiso para administrar ubicaciones.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('UbicacionFormScreen: edición (tarea 8.2, D8)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: { items: [DEPOSITO], cursor_siguiente: null } }) },
      { metodo: 'PUT', ruta: `/stock/ubicaciones/${ID}`, responder: () => ({ status: 200, cuerpo: DEPOSITO }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('carga la ubicación, permite renombrarla y desactivarla con PUT', async () => {
    const usuario = userEvent.setup()
    renderForm('ADM', `/admin/stock/ubicaciones/${ID}`)

    const nombre = await screen.findByDisplayValue('Depósito central')
    await usuario.clear(nombre)
    await usuario.type(nombre, 'Depósito sur')
    await usuario.click(screen.getByLabelText('Activa'))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await screen.findByText('Listado de stock')
    expect(cuerpo(0, 'PUT', `/stock/ubicaciones/${ID}`)).toEqual({
      nombre: 'Depósito sur',
      tipo: 'DEPOSITO',
      requiere_toma: false,
      activo: false,
    })
  })

  it('una ubicación con stock no se desactiva: muestra el mensaje del servidor', async () => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: { items: [DEPOSITO], cursor_siguiente: null } }) },
      {
        metodo: 'PUT',
        ruta: `/stock/ubicaciones/${ID}`,
        responder: () => ({ status: 409, cuerpo: { title: 'La ubicación tiene stock.', codigo: 'UBICACION_CON_STOCK' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderForm('ADM', `/admin/stock/ubicaciones/${ID}`)

    await screen.findByDisplayValue('Depósito central')
    await usuario.click(screen.getByLabelText('Activa'))
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('La ubicación tiene stock.')
  })

  it('una ubicación inexistente o ajena lo avisa sin formulario', async () => {
    renderForm('ADM', '/admin/stock/ubicaciones/99999999-9999-4999-8999-999999999999')

    await waitFor(() => expect(screen.getByText('La ubicación pedida no existe.')).toBeInTheDocument())
    expect(screen.queryByLabelText('Nombre')).not.toBeInTheDocument()
  })
})
