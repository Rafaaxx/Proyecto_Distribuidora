/**
 * Change 20c, tarea 7.4: pestaña "Redondeo por defecto" de Configuración (spec
 * `parametros-de-organizacion`, requisito "El redondeo por defecto se administra desde la pantalla
 * de configuración"; `design.md` D10, D11, D12; PRC-01, PRC-14, INV-03, INV-06, ADR-027, ADR-061).
 * Incluye el "(?)" de la tarea 9.1.
 */

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ConfiguracionArea from '../../../../../src/areas/admin/configuracion/ConfiguracionArea'
import { AYUDAS } from '../../../../../src/ayuda/textos'
import { clavesConfiguracion } from '../../../../../src/features/configuracion/claves'
import { enrutar, llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

const URL = '/configuracion/redondeo-por-defecto'

interface Redondeo {
  multiplo: string | null
  direccion: string | null
}

function servidor(inicial: Redondeo, opciones: { alRecibir?: ReglaDeApi['responder'] } = {}) {
  let actual = inicial
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: URL, responder: () => ({ status: 200, cuerpo: actual }) },
    {
      metodo: 'POST',
      ruta: URL,
      responder: (url, init) => {
        if (opciones.alRecibir) return opciones.alRecibir(url, init)
        actual = JSON.parse(String(init?.body)) as Redondeo
        return { status: 200, cuerpo: actual }
      },
    },
  ])
}

let queryClient: QueryClient

function montar(rol: 'ADM' | 'GES' = 'ADM') {
  queryClient = queryClientConYo(rol)
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/configuracion/redondeo']}>
        <Routes>
          <Route path="/admin/configuracion/*" element={<ConfiguracionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const envios = () => llamadas(apiFetchMock, 'POST', URL)
const cuerpoDe = (i: number) => JSON.parse(String(envios()[i]?.init.body)) as Redondeo
const operationId = (envio: { init: RequestInit }) => new Headers(envio.init.headers).get('Operation-Id')

describe('pestaña Redondeo por defecto (tarea 7.4)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('la pestaña está en el menú; sin definir muestra el múltiplo vacío y la dirección sin elegir', async () => {
    servidor({ multiplo: null, direccion: null })
    montar()

    const multiplo = await screen.findByLabelText('Múltiplo de redondeo')
    expect(screen.getByRole('link', { name: 'Redondeo por defecto' })).toHaveAttribute('href', '/admin/configuracion/redondeo')
    expect(multiplo).toHaveValue('')
    expect(screen.getByLabelText('Dirección del redondeo')).toHaveValue('')
    expect(screen.getByText(/sin definir/i)).toBeInTheDocument()
  })

  it('definido, muestra el múltiplo y la dirección actuales', async () => {
    servidor({ multiplo: '500.00', direccion: 'ABAJO' })
    montar()

    expect(await screen.findByLabelText('Múltiplo de redondeo')).toHaveValue('500.00')
    expect(screen.getByLabelText('Dirección del redondeo')).toHaveValue('ABAJO')
  })

  it('guarda 500 "Hacia abajo": el POST lleva el múltiplo string y la dirección, con Operation-Id, y avisa que se guardó', async () => {
    servidor({ multiplo: null, direccion: null })
    const usuario = userEvent.setup()
    montar()

    await usuario.type(await screen.findByLabelText('Múltiplo de redondeo'), '500')
    await usuario.selectOptions(screen.getByLabelText('Dirección del redondeo'), 'Hacia abajo')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/se guardó/i)
    expect(cuerpoDe(0)).toEqual({ multiplo: '500', direccion: 'ABAJO' })
    expect(operationId(envios()[0] as { init: RequestInit })).toBeTruthy()
    expect(queryClient.getQueryState(clavesConfiguracion.redondeoPorDefecto())?.isInvalidated).toBeDefined()
  })

  it('acepta la coma decimal y la lleva al punto', async () => {
    servidor({ multiplo: null, direccion: null })
    const usuario = userEvent.setup()
    montar()

    await usuario.type(await screen.findByLabelText('Múltiplo de redondeo'), '2,5')
    await usuario.selectOptions(screen.getByLabelText('Dirección del redondeo'), 'Al más cercano')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    await waitFor(() => expect(envios()).toHaveLength(1))
    expect(cuerpoDe(0)).toEqual({ multiplo: '2.5', direccion: 'CERCANO' })
  })

  it.each([
    ['0', 'ABAJO'],
    ['10,005', 'ABAJO'],
    ['', 'ABAJO'],
    ['100', ''],
  ])('múltiplo %j con dirección %j no se envía y avisa', async (multiplo, direccion) => {
    servidor({ multiplo: null, direccion: null })
    const usuario = userEvent.setup()
    montar()

    const campo = await screen.findByLabelText('Múltiplo de redondeo')
    if (multiplo) await usuario.type(campo, multiplo)
    if (direccion) await usuario.selectOptions(screen.getByLabelText('Dirección del redondeo'), direccion)
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0)
    expect(envios()).toHaveLength(0)
  })

  it('"Quitar" envía los dos nulos y deja el formulario vacío; solo se ofrece si hay uno definido', async () => {
    servidor({ multiplo: '500.00', direccion: 'ABAJO' })
    const usuario = userEvent.setup()
    montar()
    await screen.findByLabelText('Múltiplo de redondeo')

    await usuario.click(screen.getByRole('button', { name: 'Quitar' }))

    await waitFor(() => expect(envios()).toHaveLength(1))
    expect(cuerpoDe(0)).toEqual({ multiplo: null, direccion: null })
    expect(await screen.findByRole('status')).toHaveTextContent(/se quitó/i)
    await waitFor(() => expect(screen.getByLabelText('Múltiplo de redondeo')).toHaveValue(''))
    expect(screen.queryByRole('button', { name: 'Quitar' })).not.toBeInTheDocument()
  })

  it('REDONDEO_INVALIDO del servidor se explica en palabras simples', async () => {
    servidor(
      { multiplo: null, direccion: null },
      { alRecibir: () => ({ status: 422, cuerpo: { title: 'Inválido.', codigo: 'REDONDEO_INVALIDO' } }) },
    )
    const usuario = userEvent.setup()
    montar()

    await usuario.type(await screen.findByLabelText('Múltiplo de redondeo'), '100')
    await usuario.selectOptions(screen.getByLabelText('Dirección del redondeo'), 'Hacia arriba')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByText(/múltiplo mayor que cero/i)).toBeInTheDocument()
  })

  it('el reintento tras un corte de red reenvía el mismo Operation-Id (INV-06)', async () => {
    let intentos = 0
    servidor(
      { multiplo: null, direccion: null },
      {
        alRecibir: () => {
          intentos += 1
          if (intentos <= 3) throw new TypeError('Failed to fetch')
          return { status: 200, cuerpo: { multiplo: '100', direccion: 'ARRIBA' } }
        },
      },
    )
    const usuario = userEvent.setup()
    montar()

    await usuario.type(await screen.findByLabelText('Múltiplo de redondeo'), '100')
    await usuario.selectOptions(screen.getByLabelText('Dirección del redondeo'), 'Hacia arriba')
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText(/se necesita conexión/i)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/se guardó/i)
    expect(new Set(envios().map(operationId)).size).toBe(1)
  })

  it('trae el "(?)" con el texto aprobado (tarea 9.1)', async () => {
    servidor({ multiplo: null, direccion: null })
    const usuario = userEvent.setup()
    montar()
    await screen.findByLabelText('Múltiplo de redondeo')

    await usuario.click(screen.getByRole('button', { name: `Ayuda: ${AYUDAS['configuracion.redondeoPorDefecto'].titulo}` }))

    expect(await screen.findByText(AYUDAS['configuracion.redondeoPorDefecto'].texto)).toBeInTheDocument()
  })

  it('sin ADMIN_CONFIGURACION no se ofrece la pestaña, la pantalla avisa y no pide nada (ADR-027)', async () => {
    servidor({ multiplo: null, direccion: null })
    montar('GES')

    expect(await screen.findByText(/no tenés permiso/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Redondeo por defecto' })).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', URL)).toHaveLength(0)
  })
})
