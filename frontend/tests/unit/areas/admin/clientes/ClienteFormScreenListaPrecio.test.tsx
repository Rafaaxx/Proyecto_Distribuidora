import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ClienteFormScreen } from '../../../../../src/areas/admin/clientes/ClienteFormScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { LISTA_ID, OTRA_LISTA_ID, OPCIONES_DE_LISTAS, montarApi } from '../precios/preciosDePrueba'

/**
 * Change 13, tarea 13.4 (delta `clientes/administracion-de-clientes`, D11): el formulario del
 * cliente ofrece la lista de precios asignada con las listas activas y la opción de la
 * predeterminada de la organización. Se ve con `GESTIONAR_CLIENTES`, sin necesitar
 * `GESTIONAR_LISTAS`; `LISTA_INACTIVA` se muestra junto al selector.
 */

const CLIENTE_ID = '11111111-1111-4111-8111-111111111111'

const CLIENTE = {
  id: CLIENTE_ID,
  codigo: null,
  nombre: 'Kiosco El Faro',
  razon_social: null,
  documento_tipo: null,
  documento_numero: null,
  direccion: 'Av. San Martín 1420',
  contacto: 'Rocío',
  telefono: null,
  email: null,
  lista_precio_id: OTRA_LISTA_ID,
  limite_credito: null,
  politica_credito: null,
  tolerancia_offline_tipo: null,
  tolerancia_offline_valor: null,
  estado_facturacion_default: null,
  es_consumidor_final: false,
  estado: 'ACTIVO',
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

const reglaOpciones: ReglaDeApi = {
  metodo: 'GET',
  ruta: '/precios/listas/opciones',
  responder: () => ({ status: 200, cuerpo: OPCIONES_DE_LISTAS }),
}

function renderCliente(ruta: string, cliente: QueryClient = queryClientConYo('GES')) {
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/clientes" element={<p>Listado de clientes</p>} />
          <Route path="/admin/clientes/nuevo" element={<ClienteFormScreen />} />
          <Route path="/admin/clientes/:clienteId" element={<ClienteFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function completarAlta(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.type(screen.getByLabelText(/^nombre$/i), 'Kiosco El Faro')
  await usuario.type(screen.getByLabelText(/^dirección$/i), 'Av. San Martín 1420')
  await usuario.type(screen.getByLabelText(/^contacto$/i), 'Rocío')
}

describe('ClienteFormScreen: lista de precios asignada (tarea 13.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un usuario con GESTIONAR_CLIENTES y sin GESTIONAR_LISTAS ve el selector con las listas activas y la predeterminada', async () => {
    montarApi(apiFetchMock, [reglaOpciones])
    renderCliente('/admin/clientes/nuevo', queryClientConYo('GES', { permisos: ['GESTIONAR_CLIENTES'] } as never))

    await screen.findByRole('option', { name: 'Mayorista' })
    const selector = screen.getByLabelText(/lista de precios/i)
    const opciones = Array.from(selector.querySelectorAll('option')).map((o) => [o.value, o.textContent])
    expect(opciones).toEqual([
      ['', 'Predeterminada de la organización'],
      [LISTA_ID, 'General'],
      [OTRA_LISTA_ID, 'Mayorista'],
    ])
    expect(selector).toHaveValue('')
  })

  it('el alta sin elegir lista manda lista_precio_id nulo (la de la organización)', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      { metodo: 'POST', ruta: '/clientes', responder: () => ({ status: 201, cuerpo: CLIENTE }) },
    ])
    const usuario = userEvent.setup()
    renderCliente('/admin/clientes/nuevo')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /crear cliente/i }))

    await screen.findByText(/listado de clientes/i)
    const envio = llamadas(apiFetchMock, 'POST', '/clientes')[0]
    expect(JSON.parse(String(envio?.init.body))).toMatchObject({ nombre: 'Kiosco El Faro', lista_precio_id: null })
  })

  it('el alta con una lista elegida la manda', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      { metodo: 'POST', ruta: '/clientes', responder: () => ({ status: 201, cuerpo: CLIENTE }) },
    ])
    const usuario = userEvent.setup()
    renderCliente('/admin/clientes/nuevo')

    await completarAlta(usuario)
    await screen.findByRole('option', { name: 'Mayorista' })
    await usuario.selectOptions(screen.getByLabelText(/lista de precios/i), OTRA_LISTA_ID)
    await usuario.click(screen.getByRole('button', { name: /crear cliente/i }))

    await screen.findByText(/listado de clientes/i)
    const envio = llamadas(apiFetchMock, 'POST', '/clientes')[0]
    expect(JSON.parse(String(envio?.init.body))).toMatchObject({ lista_precio_id: OTRA_LISTA_ID })
  })

  it('la edición precarga la lista asignada y la reenvía al guardar (el PUT la envía siempre)', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      { metodo: 'GET', ruta: `/clientes/${CLIENTE_ID}`, responder: () => ({ status: 200, cuerpo: CLIENTE }) },
      { metodo: 'PUT', ruta: `/clientes/${CLIENTE_ID}`, responder: () => ({ status: 200, cuerpo: CLIENTE }) },
    ])
    const usuario = userEvent.setup()
    renderCliente(`/admin/clientes/${CLIENTE_ID}`)

    await screen.findByRole('option', { name: 'Mayorista' })
    await waitFor(() => expect(screen.getByLabelText(/lista de precios/i)).toHaveValue(OTRA_LISTA_ID))
    await usuario.click(screen.getByRole('button', { name: /guardar cambios/i }))

    await screen.findByText(/listado de clientes/i)
    const envio = llamadas(apiFetchMock, 'PUT', `/clientes/${CLIENTE_ID}`)[0]
    expect(JSON.parse(String(envio?.init.body))).toMatchObject({ lista_precio_id: OTRA_LISTA_ID })
  })

  it('volver a "Predeterminada de la organización" manda nulo', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      { metodo: 'GET', ruta: `/clientes/${CLIENTE_ID}`, responder: () => ({ status: 200, cuerpo: CLIENTE }) },
      { metodo: 'PUT', ruta: `/clientes/${CLIENTE_ID}`, responder: () => ({ status: 200, cuerpo: CLIENTE }) },
    ])
    const usuario = userEvent.setup()
    renderCliente(`/admin/clientes/${CLIENTE_ID}`)

    await screen.findByRole('option', { name: 'Mayorista' })
    await usuario.selectOptions(screen.getByLabelText(/lista de precios/i), '')
    await usuario.click(screen.getByRole('button', { name: /guardar cambios/i }))

    await screen.findByText(/listado de clientes/i)
    const envio = llamadas(apiFetchMock, 'PUT', `/clientes/${CLIENTE_ID}`)[0]
    expect(JSON.parse(String(envio?.init.body))).toMatchObject({ lista_precio_id: null })
  })

  it('una lista asignada que ya no está activa se sigue mostrando, para no cambiarla en silencio', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      {
        metodo: 'GET',
        ruta: `/clientes/${CLIENTE_ID}`,
        responder: () => ({ status: 200, cuerpo: { ...CLIENTE, lista_precio_id: 'f0f0f0f0-f0f0-40f0-80f0-f0f0f0f0f0f0' } }),
      },
    ])
    renderCliente(`/admin/clientes/${CLIENTE_ID}`)

    await screen.findByRole('option', { name: 'Mayorista' })
    expect(screen.getByRole('option', { name: /lista asignada \(no activa\)/i })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByLabelText(/lista de precios/i)).toHaveValue('f0f0f0f0-f0f0-40f0-80f0-f0f0f0f0f0f0'),
    )
  })

  it('LISTA_INACTIVA se muestra junto al selector y conserva lo cargado', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      {
        metodo: 'POST',
        ruta: '/clientes',
        responder: () => ({ status: 409, cuerpo: { title: 'La lista de precios está inactiva.', codigo: 'LISTA_INACTIVA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderCliente('/admin/clientes/nuevo')

    await completarAlta(usuario)
    await screen.findByRole('option', { name: 'Mayorista' })
    await usuario.selectOptions(screen.getByLabelText(/lista de precios/i), OTRA_LISTA_ID)
    await usuario.click(screen.getByRole('button', { name: /crear cliente/i }))

    expect(await screen.findByText('La lista de precios está inactiva.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('Kiosco El Faro')
    expect(screen.getByLabelText(/lista de precios/i)).toHaveValue(OTRA_LISTA_ID)
  })

  it('si las listas no se pueden obtener, el selector igual ofrece la predeterminada', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/precios/listas/opciones', responder: () => ({ status: 500, cuerpo: { title: 'Error', codigo: 'ERROR_INTERNO' } }) },
    ])
    renderCliente('/admin/clientes/nuevo')

    expect(await screen.findByRole('option', { name: 'Predeterminada de la organización' })).toBeInTheDocument()
    expect(screen.getByLabelText(/lista de precios/i)).toHaveValue('')
  })

  it('un corte de red en el alta avisa que se necesita conexión, sin encolar nada', async () => {
    apiFetchMock.mockImplementation((ruta: string) =>
      String(ruta).startsWith('/precios/listas/opciones')
        ? Promise.resolve({ ok: true, status: 200, json: async () => OPCIONES_DE_LISTAS })
        : Promise.reject(new TypeError('Failed to fetch')),
    )
    const usuario = userEvent.setup()
    renderCliente('/admin/clientes/nuevo')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /crear cliente/i }))

    expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
    expect(screen.queryByText(/listado de clientes/i)).not.toBeInTheDocument()
  })

  it('la ficha no ofrece campos de límite, política ni tolerancia de crédito', async () => {
    montarApi(apiFetchMock, [reglaOpciones])
    renderCliente('/admin/clientes/nuevo', queryClientConYo('ADM'))

    await screen.findByLabelText(/lista de precios/i)
    expect(screen.queryByLabelText(/límite/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/política/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/tolerancia/i)).not.toBeInTheDocument()
  })
})
