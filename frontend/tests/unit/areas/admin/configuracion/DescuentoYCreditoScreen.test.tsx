/**
 * Change 18b, tarea 14.1: pantalla "Descuento y crédito" de Configuración (spec
 * `organizacion/parametros-de-organizacion`; D13, D14; DSC-06, CRE-03, CRE-06, INV-06, SEG-06,
 * ADR-027).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

interface Credito {
  politica: string
  tolerancia_tipo: string | null
  tolerancia_valor: string | null
}

/** Un servidor que guarda lo que recibe, como el real (y rechaza una tolerancia incompleta). */
function servidor() {
  let descuento = { habilitado: true, motivo_obligatorio: false }
  let credito: Credito = { politica: 'AUTORIZAR', tolerancia_tipo: null, tolerancia_valor: null }
  const reglas: ReglaDeApi[] = [
    { metodo: 'GET', ruta: '/configuracion/descuento-manual', responder: () => ({ status: 200, cuerpo: descuento }) },
    {
      metodo: 'POST',
      ruta: '/configuracion/descuento-manual',
      responder: (_url, init) => {
        descuento = JSON.parse(String(init?.body)) as typeof descuento
        return { status: 200, cuerpo: descuento }
      },
    },
    { metodo: 'GET', ruta: '/configuracion/credito', responder: () => ({ status: 200, cuerpo: credito }) },
    {
      metodo: 'POST',
      ruta: '/configuracion/credito',
      responder: (_url, init) => {
        const datos = JSON.parse(String(init?.body)) as Credito
        if ((datos.tolerancia_tipo === null) !== (datos.tolerancia_valor === null)) {
          return { status: 422, cuerpo: { title: 'La tolerancia se informa en pareja.', codigo: 'TOLERANCIA_OFFLINE_INVALIDA' } }
        }
        credito = datos
        return { status: 200, cuerpo: credito }
      },
    },
  ]
  enrutar(apiFetchMock, reglas)
}

function renderPantalla(rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/configuracion/descuento-y-credito']}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function cuerpoDelPost(ruta: string, indice = 0): Record<string, unknown> {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', ruta)[indice]?.init.body)) as Record<string, unknown>
}

describe('Descuento y crédito en Configuración (tarea 14.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('el Administrador ve los valores vigentes y la pestaña del menú de configuración', async () => {
    servidor()
    renderPantalla('ADM')

    const descuento = await screen.findByTestId('bloque-descuento-manual')
    expect(within(descuento).getByRole('checkbox', { name: /permitir descuentos manuales/i })).toBeChecked()
    expect(within(descuento).getByRole('checkbox', { name: /exigir un motivo/i })).not.toBeChecked()
    const credito = await screen.findByTestId('bloque-credito')
    expect(within(credito).getByLabelText(/si un cliente se pasa de su límite/i)).toHaveValue('AUTORIZAR')
    expect(within(credito).getByLabelText(/tolerancia sin señal/i)).toHaveValue('')
    expect(screen.getByRole('link', { name: /descuento y crédito/i })).toBeInTheDocument()
  })

  it('sin ADMIN_CONFIGURACION no se monta ni pide nada (ADR-027, SEG-06)', () => {
    servidor()
    renderPantalla('VEN')

    expect(screen.getByText(/no ten[eé]s permiso para cambiar la configuraci[oó]n/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/configuracion/descuento-manual')).toHaveLength(0)
    expect(llamadas(apiFetchMock, 'GET', '/configuracion/credito')).toHaveLength(0)
  })

  it('cambiar a "exigir motivo" y deshabilitar envía los dos booleanos con su Operation-Id (D13)', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-descuento-manual')
    const guardar = within(bloque).getByRole('button', { name: /guardar descuento manual/i })
    expect(guardar).toBeDisabled()

    await usuario.click(within(bloque).getByRole('checkbox', { name: /exigir un motivo/i }))
    await usuario.click(guardar)

    await screen.findByText(/se guardó la configuración del descuento manual/i)
    expect(cuerpoDelPost('/configuracion/descuento-manual')).toEqual({ habilitado: true, motivo_obligatorio: true })
    const encabezados = new Headers(llamadas(apiFetchMock, 'POST', '/configuracion/descuento-manual')[0]?.init.headers)
    expect(encabezados.get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/i)
  })

  // Escenario: "Cambiar la política por defecto"
  it('cambiar la política a ADVERTIR y guardar muestra el valor nuevo (CRE-03)', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-credito')

    await usuario.selectOptions(within(bloque).getByLabelText(/si un cliente se pasa de su límite/i), 'ADVERTIR')
    await usuario.click(within(bloque).getByRole('button', { name: /guardar crédito por defecto/i }))

    await screen.findByText(/se guardó el crédito por defecto/i)
    expect(cuerpoDelPost('/configuracion/credito')).toEqual({
      politica: 'ADVERTIR',
      tolerancia_tipo: null,
      tolerancia_valor: null,
    })
    await waitFor(() => expect(within(bloque).getByLabelText(/si un cliente se pasa de su límite/i)).toHaveValue('ADVERTIR'))
  })

  // Escenario: "Cargar la tolerancia de la organización"
  it('cargar una tolerancia en importe la envía como texto con dos decimales (CRE-06, INV-03)', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-credito')

    await usuario.selectOptions(within(bloque).getByLabelText(/tolerancia sin señal/i), 'IMPORTE')
    await usuario.type(within(bloque).getByLabelText(/importe de la tolerancia/i), '20000')
    await usuario.click(within(bloque).getByRole('button', { name: /guardar crédito por defecto/i }))

    await screen.findByText(/se guardó el crédito por defecto/i)
    expect(cuerpoDelPost('/configuracion/credito')).toEqual({
      politica: 'AUTORIZAR',
      tolerancia_tipo: 'IMPORTE',
      tolerancia_valor: '20000.00',
    })
  })

  it('una tolerancia con un valor inválido se avisa y no se puede guardar', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-credito')

    await usuario.selectOptions(within(bloque).getByLabelText(/tolerancia sin señal/i), 'PORCENTAJE')
    await usuario.type(within(bloque).getByLabelText(/porcentaje del límite/i), '150')

    expect(within(bloque).getByText(/no puede pasar de 100/i)).toBeInTheDocument()
    expect(within(bloque).getByRole('button', { name: /guardar crédito por defecto/i })).toBeDisabled()
    expect(llamadas(apiFetchMock, 'POST', '/configuracion/credito')).toHaveLength(0)
  })

  it('un rechazo del servidor se muestra y no dice que se guardó', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/configuracion/descuento-manual', responder: () => ({ status: 200, cuerpo: { habilitado: true, motivo_obligatorio: false } }) },
      { metodo: 'GET', ruta: '/configuracion/credito', responder: () => ({ status: 200, cuerpo: { politica: 'AUTORIZAR', tolerancia_tipo: null, tolerancia_valor: null } }) },
      {
        metodo: 'POST',
        ruta: '/configuracion/credito',
        responder: () => ({ status: 422, cuerpo: { title: 'La tolerancia se informa en pareja.', codigo: 'TOLERANCIA_OFFLINE_INVALIDA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-credito')
    await usuario.selectOptions(within(bloque).getByLabelText(/si un cliente se pasa de su límite/i), 'BLOQUEAR')
    await usuario.click(within(bloque).getByRole('button', { name: /guardar crédito por defecto/i }))

    expect(await within(bloque).findByRole('alert')).toHaveTextContent('La tolerancia se informa en pareja.')
    expect(screen.queryByText(/se guardó el crédito por defecto/i)).not.toBeInTheDocument()
  })

  it('las dos ayudas "(?)" están en la pantalla', async () => {
    servidor()
    renderPantalla()
    await screen.findByTestId('bloque-credito')
    expect(screen.getByRole('button', { name: /ayuda: descuento manual/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: crédito por defecto/i })).toBeInTheDocument()
  })
})
