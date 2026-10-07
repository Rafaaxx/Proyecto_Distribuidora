import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ListaFormScreen } from '../../../../../src/areas/admin/precios/ListaFormScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { llamadas } from '../../../utils/enrutarApi'
import { LISTA_ID, lista, listaDetalle, montarApi } from './preciosDePrueba'

function renderForm(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('GES')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/precios/nueva" element={<ListaFormScreen />} />
          <Route path="/admin/precios/:listaId/editar" element={<ListaFormScreen />} />
          <Route path="/admin/precios/:listaId" element={<p>Detalle de la lista</p>} />
          <Route path="/admin/precios" element={<p>Listado de listas</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function completarAlta(usuario: ReturnType<typeof userEvent.setup>, multiplo = '100') {
  await usuario.type(screen.getByLabelText(/^nombre$/i), 'General')
  await usuario.clear(screen.getByLabelText(/múltiplo de redondeo/i))
  await usuario.type(screen.getByLabelText(/múltiplo de redondeo/i), multiplo)
  await usuario.selectOptions(screen.getByLabelText(/dirección del redondeo/i), 'ARRIBA')
}

describe('ListaFormScreen: alta (tarea 13.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('crea la lista con un único POST con Operation-Id, múltiplo como string, y va al detalle', async () => {
    montarApi(apiFetchMock, [{ metodo: 'POST', ruta: '/precios/listas', responder: () => ({ status: 201, cuerpo: lista() }) }])
    const usuario = userEvent.setup()
    renderForm('/admin/precios/nueva')

    await completarAlta(usuario, '100,50')
    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))

    expect(await screen.findByText(/detalle de la lista/i)).toBeInTheDocument()
    const envios = llamadas(apiFetchMock, 'POST', '/precios/listas')
    expect(envios).toHaveLength(1)
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({
      nombre: 'General',
      redondeo_multiplo: '100.50',
      redondeo_direccion: 'ARRIBA',
    })
  })

  it.each([['0'], ['1.005'], ['abc']])('un múltiplo %s se marca junto al campo y no envía nada', async (multiplo) => {
    montarApi(apiFetchMock, [])
    const usuario = userEvent.setup()
    renderForm('/admin/precios/nueva')

    await completarAlta(usuario, multiplo)
    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))

    expect(await screen.findByText(/múltiplo mayor que cero, con hasta dos decimales/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('un nombre duplicado informado por el servidor se muestra junto al nombre y conserva lo cargado', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/precios/listas',
        responder: () => ({ status: 409, cuerpo: { title: 'Ya existe una lista con ese nombre.', codigo: 'NOMBRE_DUPLICADO' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderForm('/admin/precios/nueva')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))

    expect(await screen.findByText('Ya existe una lista con ese nombre.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^nombre$/i)).toHaveValue('General')
    expect(screen.getByLabelText(/múltiplo de redondeo/i)).toHaveValue('100')
    expect(llamadas(apiFetchMock, 'POST', '/precios/listas')).toHaveLength(1)
  })

  it('un corte de red avisa que hace falta conexión, sin encolar', async () => {
    apiFetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const usuario = userEvent.setup()
    renderForm('/admin/precios/nueva')

    await completarAlta(usuario)
    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))

    expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
  })
})

describe('ListaFormScreen: edición (tarea 13.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  const rutaEdicion = `/admin/precios/${LISTA_ID}/editar`

  it('precarga la lista y envía PUT con el nombre, el redondeo y la actividad', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/precios/listas/${LISTA_ID}`, responder: () => ({ status: 200, cuerpo: listaDetalle() }) },
      { metodo: 'PUT', ruta: `/precios/listas/${LISTA_ID}`, responder: () => ({ status: 200, cuerpo: lista() }) },
    ])
    const usuario = userEvent.setup()
    renderForm(rutaEdicion)

    expect(await screen.findByLabelText(/^nombre$/i)).toHaveValue('General')
    expect(screen.getByLabelText(/múltiplo de redondeo/i)).toHaveValue('100.00')
    expect(screen.getByLabelText(/dirección del redondeo/i)).toHaveValue('ARRIBA')
    expect(screen.getByLabelText(/^activa$/i)).toBeChecked()

    await usuario.clear(screen.getByLabelText(/múltiplo de redondeo/i))
    await usuario.type(screen.getByLabelText(/múltiplo de redondeo/i), '50')
    await usuario.selectOptions(screen.getByLabelText(/dirección del redondeo/i), 'CERCANO')
    await usuario.click(screen.getByRole('button', { name: /guardar cambios/i }))

    await waitFor(() => expect(screen.getByText(/detalle de la lista/i)).toBeInTheDocument())
    const envios = llamadas(apiFetchMock, 'PUT', `/precios/listas/${LISTA_ID}`)
    expect(envios).toHaveLength(1)
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({
      nombre: 'General',
      redondeo_multiplo: '50',
      redondeo_direccion: 'CERCANO',
      activo: true,
    })
  })

  it('LISTA_EN_USO al desactivar: explica el motivo junto a "Activa" y la lista sigue activa', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/precios/listas/${LISTA_ID}`, responder: () => ({ status: 200, cuerpo: listaDetalle() }) },
      {
        metodo: 'PUT',
        ruta: `/precios/listas/${LISTA_ID}`,
        responder: () => ({ status: 409, cuerpo: { title: 'La lista está en uso.', codigo: 'LISTA_EN_USO' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderForm(rutaEdicion)

    await usuario.click(await screen.findByLabelText(/^activa$/i))
    await usuario.click(screen.getByRole('button', { name: /guardar cambios/i }))

    expect(
      await screen.findByText(/es la predeterminada de la organización o está asignada a clientes/i),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/^activa$/i)).toBeChecked()
    expect(screen.queryByText(/detalle de la lista/i)).not.toBeInTheDocument()
  })

  it('una lista que no existe se informa', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}`,
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
    ])
    renderForm(rutaEdicion)

    expect(await screen.findByText(/no se encontró la lista/i)).toBeInTheDocument()
  })
})
