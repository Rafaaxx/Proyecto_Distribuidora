/**
 * Change 20c, tarea 8.1: el formulario de una lista nueva precarga el redondeo por defecto (spec
 * `precios/administracion-de-listas`, requisito "El formulario de una lista nueva precarga el
 * redondeo por defecto"; `design.md` D11; `01` §4, PRC-01, PRC-14, INV-03). Sin definir ya no se
 * precarga 100 / ARRIBA.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ListaFormScreen } from '../../../../../src/areas/admin/precios/ListaFormScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { LISTA_ID, lista, listaDetalle, montarApi } from './preciosDePrueba'

const URL_REDONDEO = '/configuracion/redondeo-por-defecto'

function renderForm(ruta: string, rol: RolDePrueba = 'GES') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/precios/nueva" element={<ListaFormScreen />} />
          <Route path="/admin/precios/:listaId/editar" element={<ListaFormScreen />} />
          <Route path="/admin/precios/:listaId" element={<p>Detalle de la lista</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const redondeo = (multiplo: string | null, direccion: string | null) => ({
  metodo: 'GET',
  ruta: URL_REDONDEO,
  responder: () => ({ status: 200, cuerpo: { multiplo, direccion } }),
})

const altas = () => llamadas(apiFetchMock, 'POST', '/precios/listas')

describe('ListaFormScreen: redondeo por defecto (tarea 8.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('con redondeo por defecto, "Nueva lista" trae el múltiplo y la dirección definidos', async () => {
    montarApi(apiFetchMock, [redondeo('500.00', 'ABAJO')])
    renderForm('/admin/precios/nueva')

    await waitFor(() => expect(screen.getByLabelText(/múltiplo de redondeo/i)).toHaveValue('500.00'))
    expect(screen.getByLabelText(/dirección del redondeo/i)).toHaveValue('ABAJO')
  })

  it('lo definido viaja al crear la lista sin tocar nada más que el nombre', async () => {
    montarApi(apiFetchMock, [
      redondeo('500.00', 'ABAJO'),
      { metodo: 'POST', ruta: '/precios/listas', responder: () => ({ status: 201, cuerpo: lista() }) },
    ])
    const usuario = userEvent.setup()
    renderForm('/admin/precios/nueva')
    await waitFor(() => expect(screen.getByLabelText(/múltiplo de redondeo/i)).toHaveValue('500.00'))

    await usuario.type(screen.getByLabelText(/^nombre$/i), 'Mayorista')
    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))

    expect(await screen.findByText(/detalle de la lista/i)).toBeInTheDocument()
    expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({
      nombre: 'Mayorista',
      redondeo_multiplo: '500.00',
      redondeo_direccion: 'ABAJO',
    })
  })

  it('sin redondeo por defecto, el múltiplo queda vacío y la dirección sin elegir (ya no 100 / ARRIBA)', async () => {
    montarApi(apiFetchMock, [redondeo(null, null)])
    renderForm('/admin/precios/nueva')

    const multiplo = await screen.findByLabelText(/múltiplo de redondeo/i)
    expect(multiplo).toHaveValue('')
    expect(screen.getByLabelText(/dirección del redondeo/i)).toHaveValue('')
  })

  it('sin redondeo por defecto no se envía hasta completarlos, y completados se envía', async () => {
    montarApi(apiFetchMock, [
      redondeo(null, null),
      { metodo: 'POST', ruta: '/precios/listas', responder: () => ({ status: 201, cuerpo: lista() }) },
    ])
    const usuario = userEvent.setup()
    renderForm('/admin/precios/nueva')
    await usuario.type(await screen.findByLabelText(/^nombre$/i), 'General')

    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))
    expect(await screen.findByText(/múltiplo mayor que cero/i)).toBeInTheDocument()
    expect(screen.getByText(/elegí una dirección de redondeo/i)).toBeInTheDocument()
    expect(altas()).toHaveLength(0)

    await usuario.type(screen.getByLabelText(/múltiplo de redondeo/i), '100')
    await usuario.selectOptions(screen.getByLabelText(/dirección del redondeo/i), 'ARRIBA')
    await usuario.click(screen.getByRole('button', { name: /crear lista/i }))

    expect(await screen.findByText(/detalle de la lista/i)).toBeInTheDocument()
    expect(JSON.parse(String(altas()[0]?.init.body))).toEqual({
      nombre: 'General',
      redondeo_multiplo: '100',
      redondeo_direccion: 'ARRIBA',
    })
  })

  it('el usuario con GESTIONAR_LISTAS y sin ADMIN_CONFIGURACION también recibe el redondeo por defecto', async () => {
    montarApi(apiFetchMock, [redondeo('50.00', 'CERCANO')])
    renderForm('/admin/precios/nueva', 'GES')

    await waitFor(() => expect(screen.getByLabelText(/múltiplo de redondeo/i)).toHaveValue('50.00'))
    expect(llamadas(apiFetchMock, 'GET', URL_REDONDEO)).toHaveLength(1)
  })

  it('si la lectura del redondeo falla, el formulario sigue usable y vacío', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: URL_REDONDEO, responder: () => ({ status: 500, cuerpo: { title: 'Error.' } }) },
    ])
    renderForm('/admin/precios/nueva')

    expect(await screen.findByLabelText(/múltiplo de redondeo/i)).toHaveValue('')
    expect(screen.getByRole('button', { name: /crear lista/i })).toBeInTheDocument()
  })

  it('editar una lista existente muestra su propio redondeo, sin pedir el por defecto', async () => {
    montarApi(apiFetchMock, [
      redondeo('500.00', 'ABAJO'),
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}`,
        responder: () => ({ status: 200, cuerpo: listaDetalle({ redondeo_multiplo: '25.00', redondeo_direccion: 'CERCANO' }) }),
      },
    ])
    renderForm(`/admin/precios/${LISTA_ID}/editar`)

    await waitFor(() => expect(screen.getByLabelText(/múltiplo de redondeo/i)).toHaveValue('25.00'))
    expect(screen.getByLabelText(/dirección del redondeo/i)).toHaveValue('CERCANO')
    expect(llamadas(apiFetchMock, 'GET', URL_REDONDEO)).toHaveLength(0)
  })
})
