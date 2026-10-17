import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CobranzaFormScreen } from '../../../../../src/areas/admin/cobranzas/CobranzaFormScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  CLIENTE_ID,
  COBRANZA_ID,
  COBRANZA_REGISTRADA,
  EFECTIVO_ID,
  JORNADA_ID,
  TRANSFERENCIA_ID,
  montarApi,
} from './cobranzasDePrueba'

function renderPantalla(rol: 'GES' | 'VEN' | 'CON' = 'GES', ruta = '/admin/cobranzas/nuevo', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/cobranzas/nuevo" element={<CobranzaFormScreen />} />
          <Route path="/admin/cobranzas" element={<p>Listado de cobranzas</p>} />
          <Route path="/admin/cobranzas/:cobranzaId" element={<p>Detalle de la cobranza</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

type Usuario = ReturnType<typeof userEvent.setup>

async function elegirCliente(usuario: Usuario) {
  await screen.findByRole('option', { name: 'Kiosco La Esquina' })
  await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), CLIENTE_ID)
}

async function tipearImporte(usuario: Usuario, importe: string) {
  await usuario.clear(screen.getByLabelText(/^importe$/i))
  await usuario.type(screen.getByLabelText(/^importe$/i), importe)
}

async function cargarEfectivo(usuario: Usuario, importe: string, posicion = 0) {
  await screen.findByRole('option', { name: 'Efectivo' })
  await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[posicion] as HTMLElement, EFECTIVO_ID)
  await usuario.clear(screen.getAllByLabelText(/^importe del medio$/i)[posicion] as HTMLElement)
  await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[posicion] as HTMLElement, importe)
}

function cuerpoDelPost(indice = 0): Record<string, unknown> {
  const llamada = llamadas(apiFetchMock, 'POST', '/cobranzas')[indice]
  return JSON.parse(String(llamada?.init.body)) as Record<string, unknown>
}

function idDeOperacion(indice: number): string | null {
  return new Headers(llamadas(apiFetchMock, 'POST', '/cobranzas')[indice]?.init.headers).get('Operation-Id')
}

const registrarOk: ReglaDeApi = {
  metodo: 'POST',
  ruta: '/cobranzas',
  responder: () => ({ status: 201, cuerpo: COBRANZA_REGISTRADA }),
}

describe('CobranzaFormScreen (tarea 14.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin REGISTRAR_COBRANZA muestra la falta de permiso y no pide nada', async () => {
    montarApi(apiFetchMock)
    renderPantalla('CON')

    expect(await screen.findByText(/no ten[eé]s permiso para registrar cobranzas/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/clientes/opciones')).toHaveLength(0)
  })

  it('con solo ANULAR_COBRANZA tampoco se puede registrar', async () => {
    montarApi(apiFetchMock)
    renderPantalla('GES', '/admin/cobranzas/nuevo', ['ANULAR_COBRANZA'])

    expect(await screen.findByText(/no ten[eé]s permiso para registrar cobranzas/i)).toBeInTheDocument()
  })

  it('avisa que hace falta conexión y explica la jornada', async () => {
    montarApi(apiFetchMock)
    renderPantalla()

    expect(await screen.findByText(/requiere conexi[oó]n/i)).toBeInTheDocument()
    expect(screen.getByText(/entra sola en tu jornada abierta/i)).toBeInTheDocument()
  })

  it('muestra el saldo actual ("Nos debe") y el resultante ("Queda debiendo") al tipear el importe', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()

    await elegirCliente(usuario)
    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Nos debe $ 150.000,00')
    await tipearImporte(usuario, '50000')

    expect(screen.getByTestId('saldo-resultante')).toHaveTextContent('Saldo después de la cobranza: Queda debiendo $ 100.000,00')
  })

  it('un cliente con saldo a favor lo rotula "Saldo a favor"', async () => {
    montarApi(apiFetchMock, [], '-1000.00')
    const usuario = userEvent.setup()
    renderPantalla()

    await elegirCliente(usuario)

    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Saldo a favor $ 1.000,00')
  })

  // Escenario: "Suma de medios en vivo"
  it('suma los medios en vivo: "Falta $ 0,00" cuando suman el importe y habilita registrar (COB-02)', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await tipearImporte(usuario, '50000')
    await cargarEfectivo(usuario, '30000')

    expect(screen.getByTestId('diferencia-medios')).toHaveTextContent('Falta $ 20.000,00')
    expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeDisabled()

    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[1] as HTMLElement, TRANSFERENCIA_ID)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[1] as HTMLElement, '20000')
    await usuario.type(screen.getByLabelText(/^referencia/i), '0042')

    expect(screen.getByTestId('diferencia-medios')).toHaveTextContent('Falta $ 0,00')
    expect(screen.getByTestId('saldo-resultante')).toHaveTextContent('Queda debiendo $ 100.000,00')
    expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeEnabled()
  })

  it('con sobrante dice "Sobra" y no deja registrar', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await tipearImporte(usuario, '50000')
    await cargarEfectivo(usuario, '50000.50')

    expect(screen.getByTestId('diferencia-medios')).toHaveTextContent('Sobra $ 0,50')
    expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeDisabled()
  })

  it('Transferencia exige referencia: el campo aparece obligatorio y hasta completarlo no se registra', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await tipearImporte(usuario, '20000')
    await screen.findByRole('option', { name: 'Transferencia' })
    await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[0] as HTMLElement, TRANSFERENCIA_ID)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[0] as HTMLElement, '20000')

    const referencia = screen.getByLabelText(/^referencia/i)
    expect(referencia).toBeRequired()
    expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeDisabled()

    await usuario.type(referencia, '0042')

    expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeEnabled()
  })

  it('el campo de referencia no aparece en un medio que no la exige', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await cargarEfectivo(usuario, '10')

    expect(screen.queryByLabelText(/^referencia/i)).not.toBeInTheDocument()
  })

  it('una cobranza que deja saldo a favor pide confirmación explícita y solo se envía si se acepta (COB-03)', async () => {
    montarApi(apiFetchMock, [{ ...registrarOk, responder: () => ({ status: 201, cuerpo: { ...COBRANZA_REGISTRADA, importe: '160000.00', saldo: '-10000.00' } }) }])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '160000')
    await cargarEfectivo(usuario, '160000')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Le queda saldo a favor de $ 10.000,00')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/cobranzas')).toHaveLength(0)

    await usuario.click(within(dialogo).getByRole('button', { name: /cancelar/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/cobranzas')).toHaveLength(0)

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
    await usuario.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /aceptar y registrar/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/cobranzas')).toHaveLength(1))
    expect(await screen.findByText(/cobranza registrada/i)).toBeInTheDocument()
    expect(screen.getByTestId('saldo-final')).toHaveTextContent('Saldo a favor $ 10.000,00')
  })

  describe('saldo del cliente que no se puede leer (COB-03, D5)', () => {
    const AVISO = /no pudimos leer el saldo del cliente; no podemos avisarte si esta cobranza supera su deuda/i
    const saldoCaido = (status: number): ReglaDeApi => ({
      metodo: 'GET',
      ruta: `/clientes/${CLIENTE_ID}/saldo`,
      responder: () => ({ status, cuerpo: { title: 'No disponible', codigo: 'ERROR' } }),
    })

    it.each([500, 403])('con un error %i muestra el aviso, pide confirmación y solo envía si se acepta', async (status) => {
      montarApi(apiFetchMock, [saldoCaido(status), registrarOk])
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirCliente(usuario)
      await tipearImporte(usuario, '100000')
      await cargarEfectivo(usuario, '100000')

      expect(await screen.findByText(AVISO)).toBeInTheDocument()
      await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
      const dialogo = await screen.findByRole('dialog')
      expect(within(dialogo).getByText(AVISO)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/cobranzas')).toHaveLength(0)

      await usuario.click(within(dialogo).getByRole('button', { name: /aceptar y registrar/i }))

      expect(await screen.findByText(/cobranza registrada/i)).toBeInTheDocument()
      expect(llamadas(apiFetchMock, 'POST', '/cobranzas')).toHaveLength(1)
    })

    it('mientras el saldo carga no se puede enviar', async () => {
      montarApi(apiFetchMock, [registrarOk])
      const previo = apiFetchMock.getMockImplementation() as (ruta: string, init?: RequestInit) => Promise<unknown>
      apiFetchMock.mockImplementation((ruta: string, init?: RequestInit) =>
        ruta.includes('/saldo') ? new Promise(() => undefined) : previo(ruta, init),
      )
      const usuario = userEvent.setup()
      renderPantalla()
      await elegirCliente(usuario)
      await tipearImporte(usuario, '100')
      await cargarEfectivo(usuario, '100')

      expect(await screen.findByText(/cargando saldo/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeDisabled()
    })
  })

  it('una cobranza que no deja saldo a favor se envía sin diálogo, con el cuerpo esperado y los identificadores', async () => {
    montarApi(apiFetchMock, [registrarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '50000')
    await cargarEfectivo(usuario, '30000')
    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[1] as HTMLElement, TRANSFERENCIA_ID)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[1] as HTMLElement, '20000')
    await usuario.type(screen.getByLabelText(/^referencia/i), '0042')
    await usuario.type(screen.getByLabelText(/observaci[oó]n/i), 'Pagó en mostrador')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))

    expect(await screen.findByText(/cobranza registrada/i)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(cuerpoDelPost()).toEqual({
      cobranza_id: expect.stringMatching(/^[0-9a-f-]{36}$/i),
      cliente_id: CLIENTE_ID,
      importe: '50000.00',
      observacion: 'Pagó en mostrador',
      medios: [
        { medio_pago_id: EFECTIVO_ID, importe: '30000.00', referencia: null },
        { medio_pago_id: TRANSFERENCIA_ID, importe: '20000.00', referencia: '0042' },
      ],
    })
    expect(idDeOperacion(0)).toMatch(/^[0-9a-f-]{36}$/i)
    expect(screen.getByRole('link', { name: /ver la cobranza/i })).toHaveAttribute('href', `/admin/cobranzas/${COBRANZA_ID}`)
    expect(screen.getByTestId('saldo-final')).toHaveTextContent('Nos debe $ 100.000,00')
  })

  it('muestra en qué jornada quedó la cobranza, o que quedó sin jornada', async () => {
    montarApi(apiFetchMock, [{ ...registrarOk, responder: () => ({ status: 201, cuerpo: { ...COBRANZA_REGISTRADA, jornada_id: JORNADA_ID } }) }])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))

    expect(await screen.findByText(/qued[oó] en tu jornada/i)).toBeInTheDocument()
  })

  it('con el cliente precargado en la URL (?cliente=) lo elige aunque no figure en las opciones (inactivo)', async () => {
    const inactivo = '99999999-9999-4999-8999-999999999999'
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: `/clientes/${inactivo}/saldo`, responder: () => ({ status: 200, cuerpo: { saldo: '700.00' } }) }])
    renderPantalla('GES', `/admin/cobranzas/nuevo?cliente=${inactivo}`)

    expect(await screen.findByRole('option', { name: /cliente de la cuenta corriente/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/^cliente$/i)).toHaveValue(inactivo)
    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Nos debe $ 700,00')
  })

  it('el cliente precargado de la lista se elige solo y muestra su saldo', async () => {
    montarApi(apiFetchMock)
    renderPantalla('GES', `/admin/cobranzas/nuevo?cliente=${CLIENTE_ID}`)

    expect(await screen.findByTestId('saldo-actual')).toHaveTextContent('Nos debe $ 150.000,00')
    expect(screen.getByLabelText(/^cliente$/i)).toHaveValue(CLIENTE_ID)
  })

  it('el buscador de clientes pide las opciones con el texto tipeado', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('option', { name: 'Kiosco La Esquina' })

    await usuario.type(screen.getByLabelText(/buscar cliente/i), 'kio')

    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/clientes/opciones').at(-1)?.url.searchParams.get('texto')).toBe('kio'))
  })

  it('un error del servidor sobre el segundo medio se muestra junto a ese medio y conserva lo cargado', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/cobranzas',
        responder: () => ({ status: 422, cuerpo: { title: 'Medio 2: el medio de pago está inactivo', codigo: 'MEDIO_PAGO_INACTIVO', medio: 1 } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await tipearImporte(usuario, '50000')
    await cargarEfectivo(usuario, '30000')
    await usuario.click(screen.getByRole('button', { name: /agregar medio/i }))
    await usuario.selectOptions(screen.getAllByLabelText(/^medio de pago$/i)[1] as HTMLElement, TRANSFERENCIA_ID)
    await usuario.type(screen.getAllByLabelText(/^importe del medio$/i)[1] as HTMLElement, '20000')
    await usuario.type(screen.getByLabelText(/^referencia/i), '0042')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))

    const medio2 = await screen.findByTestId('medio-1')
    expect(await within(medio2).findByText('Medio 2: el medio de pago está inactivo')).toBeInTheDocument()
    expect(within(screen.getByTestId('medio-0')).queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByLabelText(/^importe$/i)).toHaveValue('50000')
    expect(screen.getByLabelText(/^referencia/i)).toHaveValue('0042')
  })

  it.each([
    ['MEDIOS_NO_SUMAN_IMPORTE', 'Los medios no suman el importe', 'importe'],
    ['CONSUMIDOR_FINAL_SIN_CUENTA', 'El consumidor final no tiene cuenta', 'cliente'],
    ['OBSERVACION_INVALIDA', 'La observación es demasiado larga', 'observacion'],
  ])('el error %s se muestra junto a su campo (%s)', async (codigo, mensaje, campo) => {
    montarApi(apiFetchMock, [{ metodo: 'POST', ruta: '/cobranzas', responder: () => ({ status: 422, cuerpo: { title: mensaje, codigo } }) }])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))

    const texto = await screen.findByText(mensaje)
    const contenedor = screen.getByTestId(`campo-${campo}`)
    expect(contenedor).toContainElement(texto)
  })

  it('un error general (jornada ajena) se muestra como alerta de la pantalla', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'POST', ruta: '/cobranzas', responder: () => ({ status: 409, cuerpo: { title: 'La jornada no es tuya', codigo: 'JORNADA_AJENA' } }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))

    expect(await screen.findByText('La jornada no es tuya')).toBeInTheDocument()
  })

  // Escenario: "Reintento tras un corte"
  it('tras un error de red el reintento reenvía el mismo Operation-Id y la misma cobranza; si cambia el contenido, un Operation-Id nuevo pero la misma cobranza', async () => {
    let intento = 0
    montarApi(apiFetchMock, [
      {
        metodo: 'POST',
        ruta: '/cobranzas',
        responder: () => {
          intento += 1
          if (intento <= 6) throw new TypeError('Failed to fetch')
          return { status: 201, cuerpo: COBRANZA_REGISTRADA }
        },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
    await screen.findByText(/revis[aá] la conexi[oó]n/i)
    const enviadas = llamadas(apiFetchMock, 'POST', '/cobranzas').length
    expect(enviadas).toBeGreaterThanOrEqual(2)
    for (let i = 1; i < enviadas; i += 1) {
      expect(idDeOperacion(i)).toBe(idDeOperacion(0))
      expect(cuerpoDelPost(i).cobranza_id).toBe(cuerpoDelPost(0).cobranza_id)
    }

    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/cobranzas').length).toBeGreaterThan(enviadas))
    await waitFor(() => expect(screen.getByRole('button', { name: /confirmar cobranza/i })).toBeEnabled())
    expect(idDeOperacion(enviadas)).toBe(idDeOperacion(0))
    expect(cuerpoDelPost(enviadas).cobranza_id).toBe(cuerpoDelPost(0).cobranza_id)

    await screen.findByRole('alert')
    await usuario.type(screen.getByLabelText(/observaci[oó]n/i), 'nueva')
    const antes = llamadas(apiFetchMock, 'POST', '/cobranzas').length
    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/cobranzas').length).toBeGreaterThan(antes))
    expect(idDeOperacion(antes)).not.toBe(idDeOperacion(0))
    expect(cuerpoDelPost(antes).cobranza_id).toBe(cuerpoDelPost(0).cobranza_id)
  })

  it('"Registrar otra cobranza" deja el formulario limpio y usa un identificador de cobranza nuevo', async () => {
    montarApi(apiFetchMock, [registrarOk])
    const usuario = userEvent.setup()
    renderPantalla()
    await elegirCliente(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')
    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
    await screen.findByText(/cobranza registrada/i)

    await usuario.click(screen.getByRole('button', { name: /registrar otra cobranza/i }))
    await elegirCliente(usuario)
    await screen.findByTestId('saldo-actual')
    await tipearImporte(usuario, '100')
    await cargarEfectivo(usuario, '100')
    await usuario.click(screen.getByRole('button', { name: /confirmar cobranza/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/cobranzas')).toHaveLength(2))

    expect(cuerpoDelPost(1).cobranza_id).not.toBe(cuerpoDelPost(0).cobranza_id)
    expect(idDeOperacion(1)).not.toBe(idDeOperacion(0))
  })
})
