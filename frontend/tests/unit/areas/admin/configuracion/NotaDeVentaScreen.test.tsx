/**
 * Change 20, tarea 7.3: sección "Nota de venta" de Configuración (spec
 * `organizacion/parametros-de-organizacion`; VTA-13, AUD-01, INV-06, SEG-06, ADR-027; D3, D4, D10).
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

interface Configuracion {
  muestra_saldo: boolean
  domicilio: string | null
  telefono: string | null
}

/** Un servidor que guarda lo que recibe, como el real (y rechaza un domicilio de más de 200 caracteres). */
function servidor(inicial: Configuracion = { muestra_saldo: false, domicilio: null, telefono: null }) {
  let actual = inicial
  const reglas: ReglaDeApi[] = [
    { metodo: 'GET', ruta: '/configuracion/nota-de-venta', responder: () => ({ status: 200, cuerpo: actual }) },
    {
      metodo: 'POST',
      ruta: '/configuracion/nota-de-venta',
      responder: (_url, init) => {
        const datos = JSON.parse(String(init?.body)) as Configuracion
        if ((datos.domicilio ?? '').length > 200) {
          return {
            status: 422,
            cuerpo: { title: 'El domicilio de la nota no puede superar los 200 caracteres (VTA-13).', codigo: 'DATO_DE_NOTA_INVALIDO' },
          }
        }
        actual = { ...datos, domicilio: datos.domicilio?.trim() || null, telefono: datos.telefono?.trim() || null }
        return { status: 200, cuerpo: actual }
      },
    },
  ]
  enrutar(apiFetchMock, reglas)
}

function renderPantalla(rol: RolDePrueba = 'ADM') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/configuracion/nota-de-venta']}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function cuerpoDelPost(indice = 0): Record<string, unknown> {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', '/configuracion/nota-de-venta')[indice]?.init.body)) as Record<string, unknown>
}

describe('Nota de venta en Configuración (7.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('el Administrador ve los valores vigentes, el enlace del menú y las dos ayudas', async () => {
    servidor({ muestra_saldo: true, domicilio: 'Av. Siempreviva 742', telefono: '261 555-0100' })
    renderPantalla('ADM')

    const bloque = await screen.findByTestId('bloque-nota-de-venta')
    expect(within(bloque).getByRole('checkbox', { name: /mostrar el saldo/i })).toBeChecked()
    expect(within(bloque).getByLabelText(/^domicilio$/i)).toHaveValue('Av. Siempreviva 742')
    expect(within(bloque).getByLabelText(/^tel[eé]fono$/i)).toHaveValue('261 555-0100')
    expect(screen.getByRole('link', { name: /^nota de venta$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: saldo en la nota/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ayuda: domicilio y tel[eé]fono/i })).toBeInTheDocument()
  })

  it('sin ADMIN_CONFIGURACION no se monta ni pide nada (ADR-027, SEG-06)', () => {
    servidor()
    renderPantalla('VEN')

    expect(screen.getByText(/no ten[eé]s permiso para cambiar la configuraci[oó]n/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/configuracion/nota-de-venta')).toHaveLength(0)
    expect(screen.queryByRole('link', { name: /^nota de venta$/i })).not.toBeInTheDocument()
  })

  it('activar "mostrar saldo" y cargar domicilio y teléfono guarda los tres valores con su Operation-Id (INV-06)', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-nota-de-venta')
    const guardar = within(bloque).getByRole('button', { name: /guardar nota de venta/i })
    expect(guardar).toBeDisabled()

    await usuario.click(within(bloque).getByRole('checkbox', { name: /mostrar el saldo/i }))
    await usuario.type(within(bloque).getByLabelText(/^domicilio$/i), 'Av. Siempreviva 742')
    await usuario.type(within(bloque).getByLabelText(/^tel[eé]fono$/i), '261 555-0100')
    await usuario.click(guardar)

    await screen.findByText(/se guardó la configuración de la nota de venta/i)
    expect(cuerpoDelPost()).toEqual({ muestra_saldo: true, domicilio: 'Av. Siempreviva 742', telefono: '261 555-0100' })
    const encabezados = new Headers(llamadas(apiFetchMock, 'POST', '/configuracion/nota-de-venta')[0]?.init.headers)
    expect(encabezados.get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/i)
  })

  it('vaciar el domicilio y el teléfono envía nulo, no texto vacío (D3)', async () => {
    servidor({ muestra_saldo: false, domicilio: 'Av. Siempreviva 742', telefono: '261 555-0100' })
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-nota-de-venta')

    await usuario.clear(within(bloque).getByLabelText(/^domicilio$/i))
    await usuario.clear(within(bloque).getByLabelText(/^tel[eé]fono$/i))
    await usuario.click(within(bloque).getByRole('button', { name: /guardar nota de venta/i }))

    await screen.findByText(/se guardó la configuración de la nota de venta/i)
    expect(cuerpoDelPost()).toEqual({ muestra_saldo: false, domicilio: null, telefono: null })
  })

  it('DATO_DE_NOTA_INVALIDO se muestra junto al campo y no dice que se guardó', async () => {
    servidor()
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-nota-de-venta')

    await usuario.click(within(bloque).getByLabelText(/^domicilio$/i))
    await usuario.paste('x'.repeat(201))
    await usuario.click(within(bloque).getByRole('button', { name: /guardar nota de venta/i }))

    const campo = await screen.findByTestId('campo-domicilio')
    expect(within(campo).getByRole('alert')).toHaveTextContent(/el domicilio de la nota no puede superar los 200 caracteres/i)
    expect(screen.queryByText(/se guardó la configuración de la nota de venta/i)).not.toBeInTheDocument()
  })

  it('un error de red se avisa con el mensaje de reintento', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/configuracion/nota-de-venta', responder: () => ({ status: 200, cuerpo: { muestra_saldo: false, domicilio: null, telefono: null } }) },
      {
        metodo: 'POST',
        ruta: '/configuracion/nota-de-venta',
        responder: () => {
          throw new TypeError('network')
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    const bloque = await screen.findByTestId('bloque-nota-de-venta')

    await usuario.click(within(bloque).getByRole('checkbox', { name: /mostrar el saldo/i }))
    await usuario.click(within(bloque).getByRole('button', { name: /guardar nota de venta/i }))

    expect(await within(bloque).findByRole('alert')).toHaveTextContent(/no se pudo guardar/i)
  })
})
