import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { ListaPredeterminadaScreen } from '../../../../../src/areas/admin/configuracion/ListaPredeterminadaScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { LISTA_ID, OPCIONES_DE_LISTAS, OTRA_LISTA_ID, montarApi } from '../precios/preciosDePrueba'

/**
 * Change 13, tarea 13.5 (delta `organizacion/parametros-de-organizacion`, D11): elegir la lista de
 * precios predeterminada con `ADMIN_CONFIGURACION` y advertir cuando no hay ninguna.
 */

const SIN_PREDETERMINADA = { lista_id: null, lista_nombre: null, activa: null }
const GENERAL_PREDETERMINADA = { lista_id: LISTA_ID, lista_nombre: 'General', activa: true }

const reglaOpciones: ReglaDeApi = {
  metodo: 'GET',
  ruta: '/precios/listas/opciones',
  responder: () => ({ status: 200, cuerpo: OPCIONES_DE_LISTAS }),
}

const reglaPredeterminada = (cuerpo: unknown): ReglaDeApi => ({
  metodo: 'GET',
  ruta: '/precios/lista-predeterminada',
  responder: () => ({ status: 200, cuerpo }),
})

function renderPantalla(rol: 'ADM' | 'GES' = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/configuracion/lista-predeterminada']}>
        <Routes>
          <Route path="/admin/configuracion/lista-predeterminada" element={<ListaPredeterminadaScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ListaPredeterminadaScreen (tarea 13.5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('una organización sin lista predeterminada ve la advertencia de que los clientes sin lista no tienen precio', async () => {
    montarApi(apiFetchMock, [reglaOpciones, reglaPredeterminada(SIN_PREDETERMINADA)])
    renderPantalla()

    expect(
      await screen.findByText(/los clientes sin lista asignada no tienen precio/i),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/lista predeterminada/i)).toHaveValue('')
  })

  it('con una lista definida muestra la actual y no advierte', async () => {
    montarApi(apiFetchMock, [reglaOpciones, reglaPredeterminada(GENERAL_PREDETERMINADA)])
    renderPantalla()

    expect(await screen.findByText(/lista predeterminada actual:/i)).toHaveTextContent('General')
    expect(screen.queryByText(/no tienen precio/i)).not.toBeInTheDocument()
    await screen.findByRole('option', { name: 'Mayorista' })
    expect(screen.getByLabelText(/lista predeterminada/i)).toHaveValue(LISTA_ID)
  })

  it('ofrece solo las listas activas y elegir una la define con un PUT con Operation-Id', async () => {
    let actual: unknown = SIN_PREDETERMINADA
    montarApi(apiFetchMock, [
      reglaOpciones,
      { metodo: 'GET', ruta: '/precios/lista-predeterminada', responder: () => ({ status: 200, cuerpo: actual }) },
      {
        metodo: 'PUT',
        ruta: '/precios/lista-predeterminada',
        responder: () => {
          actual = GENERAL_PREDETERMINADA
          return { status: 200, cuerpo: GENERAL_PREDETERMINADA }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'General' })
    await usuario.selectOptions(screen.getByLabelText(/lista predeterminada/i), LISTA_ID)
    await usuario.click(screen.getByRole('button', { name: /guardar lista predeterminada/i }))

    expect(await screen.findByText(/lista predeterminada actual:/i)).toHaveTextContent('General')
    const envios = llamadas(apiFetchMock, 'PUT', '/precios/lista-predeterminada')
    expect(envios).toHaveLength(1)
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(envios[0]?.init.body))).toEqual({ lista_id: LISTA_ID })
    expect(screen.queryByText(/no tienen precio/i)).not.toBeInTheDocument()
  })

  it('cambia de General a Mayorista', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      reglaPredeterminada(GENERAL_PREDETERMINADA),
      {
        metodo: 'PUT',
        ruta: '/precios/lista-predeterminada',
        responder: () => ({ status: 200, cuerpo: { lista_id: OTRA_LISTA_ID, lista_nombre: 'Mayorista', activa: true } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Mayorista' })
    await usuario.selectOptions(screen.getByLabelText(/lista predeterminada/i), OTRA_LISTA_ID)
    await usuario.click(screen.getByRole('button', { name: /guardar lista predeterminada/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'PUT', '/precios/lista-predeterminada')).toHaveLength(1))
    expect(JSON.parse(String(llamadas(apiFetchMock, 'PUT', '/precios/lista-predeterminada')[0]?.init.body))).toEqual({
      lista_id: OTRA_LISTA_ID,
    })
  })

  it('sin elegir ninguna lista no envía nada y lo dice', async () => {
    montarApi(apiFetchMock, [reglaOpciones, reglaPredeterminada(SIN_PREDETERMINADA)])
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'General' })
    await usuario.click(screen.getByRole('button', { name: /guardar lista predeterminada/i }))

    expect(await screen.findByText(/elegí una lista/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'PUT', '/precios/lista-predeterminada')).toHaveLength(0)
  })

  it('LISTA_INACTIVA se muestra junto al selector y la predeterminada no cambia', async () => {
    montarApi(apiFetchMock, [
      reglaOpciones,
      reglaPredeterminada(GENERAL_PREDETERMINADA),
      {
        metodo: 'PUT',
        ruta: '/precios/lista-predeterminada',
        responder: () => ({ status: 409, cuerpo: { title: 'La lista está inactiva.', codigo: 'LISTA_INACTIVA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'Mayorista' })
    await usuario.selectOptions(screen.getByLabelText(/lista predeterminada/i), OTRA_LISTA_ID)
    await usuario.click(screen.getByRole('button', { name: /guardar lista predeterminada/i }))

    expect(await screen.findByText('La lista está inactiva.')).toBeInTheDocument()
    expect(screen.getByText(/lista predeterminada actual:/i)).toHaveTextContent('General')
  })

  it('sin conexión no envía el comando y avisa', async () => {
    montarApi(apiFetchMock, [reglaOpciones, reglaPredeterminada(SIN_PREDETERMINADA)])
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('option', { name: 'General' })
    await usuario.selectOptions(screen.getByLabelText(/lista predeterminada/i), LISTA_ID)
    await usuario.click(screen.getByRole('button', { name: /guardar lista predeterminada/i }))

    expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'PUT', '/precios/lista-predeterminada')).toHaveLength(0)
    vi.restoreAllMocks()
  })

  it('sin ADMIN_CONFIGURACION no ve la elección ni pide nada', async () => {
    montarApi(apiFetchMock, [reglaOpciones, reglaPredeterminada(SIN_PREDETERMINADA)])
    renderPantalla('GES')

    expect(await screen.findByText(/no ten[eé]s permiso para administrar la lista predeterminada/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/lista predeterminada/i)).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('ConfiguracionArea con la lista predeterminada (tarea 13.5)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      reglaOpciones,
      reglaPredeterminada(SIN_PREDETERMINADA),
      {
        metodo: 'GET',
        ruta: '/configuracion/fiscal',
        responder: () => ({ status: 200, cuerpo: { condicion_iva: 'MONOTRIBUTISTA', computa_credito_fiscal: false } }),
      },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  function renderArea(ruta: string) {
    return render(
      <QueryClientProvider client={queryClientConYo('ADM')}>
        <MemoryRouter initialEntries={[ruta]}>
          <Routes>
            <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('la ruta se resuelve a su pantalla y el área enlaza las dos', async () => {
    renderArea('/admin/configuracion/lista-predeterminada')

    expect(await screen.findByLabelText(/lista predeterminada/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /fiscal/i })).toHaveAttribute('href', '/admin/configuracion/fiscal')
    expect(screen.getByRole('link', { name: /lista predeterminada/i })).toHaveAttribute(
      'href',
      '/admin/configuracion/lista-predeterminada',
    )
  })

  it('la ruta índice sigue llevando a la configuración fiscal', async () => {
    renderArea('/admin/configuracion')

    expect(await screen.findByText(/condición frente al iva/i)).toBeInTheDocument()
  })
})
