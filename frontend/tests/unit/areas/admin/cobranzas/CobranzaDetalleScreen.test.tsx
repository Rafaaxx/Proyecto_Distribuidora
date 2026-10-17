import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CobranzaDetalleScreen } from '../../../../../src/areas/admin/cobranzas/CobranzaDetalleScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  ANULACION_DE_COBRANZA,
  COBRANZA_ID,
  EFECTIVO_ID,
  JORNADA_ID,
  MOTIVO_COBRANZA_ID,
  TRANSFERENCIA_ID,
  cobranzaDetalle,
  montarApi,
} from './cobranzasDePrueba'

function renderPantalla(rol: 'GES' | 'VEN' | 'CON' = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/cobranzas/${COBRANZA_ID}`]}>
        <Routes>
          <Route path="/admin/cobranzas/:cobranzaId" element={<CobranzaDetalleScreen />} />
          <Route path="/admin/cobranzas" element={<p>Listado de cobranzas</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function detalle(campos: Partial<Record<string, unknown>> = {}): ReglaDeApi {
  return { metodo: 'GET', ruta: `/cobranzas/${COBRANZA_ID}`, responder: () => ({ status: 200, cuerpo: cobranzaDetalle(campos) }) }
}

const obs = (codigo: string, detalleObs: Record<string, unknown> | null) => ({ codigo, estado: 'PENDIENTE', detalle: detalleObs })

describe('CobranzaDetalleScreen (tareas 14.1 y 14.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin permisos de cobranza muestra la falta de permiso y no pide nada', async () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla('CON')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las cobranzas/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/cobranzas/${COBRANZA_ID}`)).toHaveLength(0)
  })

  it('muestra cliente, importe, medios con referencia, usuario, observación y estado', async () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla()

    expect(await screen.findByTestId('importe-de-la-cobranza')).toHaveTextContent('50.000,00')
    expect(screen.getByText(/Kiosco La Esquina/)).toBeInTheDocument()
    expect(screen.getByText(/Juan Vendedor/)).toBeInTheDocument()
    expect(screen.getByText(/Pagó en mostrador/)).toBeInTheDocument()
    expect(screen.getByText('Confirmada')).toBeInTheDocument()
    const medios = screen.getAllByTestId('medio-de-la-cobranza')
    expect(medios[0]).toHaveTextContent('Efectivo: 30.000,00')
    expect(medios[1]).toHaveTextContent('Transferencia: 20.000,00 (ref. 0042)')
  })

  it('sin jornada dice "Sin jornada"; con jornada enlaza a las cobranzas de esa jornada', async () => {
    montarApi(apiFetchMock, [detalle()])
    const primera = renderPantalla()
    expect(await screen.findByText(/sin jornada/i)).toBeInTheDocument()
    primera.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [detalle({ jornada_id: JORNADA_ID })])
    renderPantalla()
    expect(await screen.findByRole('link', { name: /ver las cobranzas de esta jornada/i })).toHaveAttribute(
      'href',
      `/admin/cobranzas?jornada=${JORNADA_ID}`,
    )
  })

  // Escenario: "Cobranza con observación de sincronización"
  // Escenario: "Observación de medio en el detalle"
  it('las observaciones de medio se ven junto a su línea y las demás aparte (SYN-07, D13)', async () => {
    montarApi(apiFetchMock, [
      detalle({
        medios: [
          { medio_pago_id: EFECTIVO_ID, medio_nombre: 'Billetera', importe: '10000.00', referencia: null },
          { medio_pago_id: TRANSFERENCIA_ID, medio_nombre: 'Transferencia', importe: '20000.00', referencia: null },
        ],
        observaciones: [
          obs('MEDIO_INACTIVO', { medio: 0, medio_pago_id: EFECTIVO_ID, nombre: 'Billetera', importe: '10000.00' }),
          obs('REFERENCIA_FALTANTE', { medio: 1, medio_pago_id: TRANSFERENCIA_ID, nombre: 'Transferencia', importe: '20000.00' }),
          obs('PERMISO_REVOCADO', { permiso: 'REGISTRAR_COBRANZA', motivo: 'PERMISO_QUITADO' }),
        ],
      }),
    ])
    renderPantalla()

    const [linea0, linea1] = await screen.findAllByTestId('medio-de-la-cobranza')
    expect(within(linea0 as HTMLElement).getByText('Medio de pago inactivo')).toBeInTheDocument()
    expect(within(linea0 as HTMLElement).queryByText('Falta la referencia')).not.toBeInTheDocument()
    expect(within(linea1 as HTMLElement).getByText('Falta la referencia')).toBeInTheDocument()
    expect(within(linea1 as HTMLElement).getByText('Transferencia · $ 20.000,00')).toBeInTheDocument()
    const generales = screen.getByTestId('observaciones-de-sincronizacion')
    expect(within(generales).getByText('Permiso revocado')).toBeInTheDocument()
    expect(within(generales).getByText('Se le quitó el permiso de cobrar')).toBeInTheDocument()
    expect(within(generales).queryByText('Medio de pago inactivo')).not.toBeInTheDocument()
  })

  it('una cobranza sin observaciones no muestra la sección de sincronización', async () => {
    montarApi(apiFetchMock, [detalle()])
    renderPantalla()

    await screen.findByTestId('importe-de-la-cobranza')
    expect(screen.queryByTestId('observaciones-de-sincronizacion')).not.toBeInTheDocument()
  })

  it('una cobranza anulada muestra la anulación y no ofrece anular', async () => {
    montarApi(apiFetchMock, [detalle({ estado: 'ANULADA', anulacion: ANULACION_DE_COBRANZA })])
    renderPantalla()

    const anulacion = await screen.findByTestId('anulacion-de-la-cobranza')
    expect(anulacion).toHaveTextContent('Motivo: Cheque rechazado')
    expect(anulacion).toHaveTextContent('Marta Anuladora')
    expect(anulacion).toHaveTextContent('Volvió rechazado')
    expect(screen.queryByRole('button', { name: /anular cobranza/i })).not.toBeInTheDocument()
  })

  it('"Anular cobranza" solo con ANULAR_COBRANZA y sobre una CONFIRMADA independiente', async () => {
    montarApi(apiFetchMock, [detalle()])
    const sin = renderPantalla('GES', ['REGISTRAR_COBRANZA'])
    await screen.findByTestId('importe-de-la-cobranza')
    expect(screen.queryByRole('button', { name: /anular cobranza/i })).not.toBeInTheDocument()
    sin.unmount()

    renderPantalla('GES', ['ANULAR_COBRANZA'])
    expect(await screen.findByRole('button', { name: /anular cobranza/i })).toBeInTheDocument()
  })

  it('una cobranza de una venta no se anula desde acá (D7)', async () => {
    montarApi(apiFetchMock, [detalle({ origen: 'VENTA' })])
    renderPantalla()

    await screen.findByTestId('importe-de-la-cobranza')
    expect(screen.queryByRole('button', { name: /anular cobranza/i })).not.toBeInTheDocument()
  })

  // Escenario: "Anular desde el detalle"
  it('el diálogo pide motivo obligatorio, muestra el saldo resultante y anula con motivo y observación', async () => {
    montarApi(apiFetchMock, [
      detalle(),
      {
        metodo: 'POST',
        ruta: `/cobranzas/${COBRANZA_ID}/anulacion`,
        responder: () => ({ status: 200, cuerpo: { cobranza_id: COBRANZA_ID, estado: 'ANULADA', importe: '50000.00', saldo: '200000.00' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await usuario.click(await screen.findByRole('button', { name: /anular cobranza/i }))
    const dialogo = await screen.findByRole('dialog')
    const confirmar = within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i })
    expect(confirmar).toBeDisabled()
    expect(await within(dialogo).findByTestId('saldo-tras-anular')).toHaveTextContent('Saldo después de anular: Nos debe $ 200.000,00')

    await within(dialogo).findByRole('option', { name: 'Cheque rechazado' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_COBRANZA_ID)
    await usuario.type(within(dialogo).getByLabelText(/observaci[oó]n/i), 'Volvió rechazado')
    expect(confirmar).toBeEnabled()
    await usuario.click(confirmar)

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/cobranzas/${COBRANZA_ID}/anulacion`)).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', `/cobranzas/${COBRANZA_ID}/anulacion`)[0]
    expect(JSON.parse(String(llamada?.init.body))).toEqual({ motivo_id: MOTIVO_COBRANZA_ID, observacion: 'Volvió rechazado' })
    expect(new Headers(llamada?.init.headers).get('Operation-Id')).toMatch(/^[0-9a-f-]{36}$/i)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('sin observación manda observacion nula', async () => {
    montarApi(apiFetchMock, [
      detalle(),
      {
        metodo: 'POST',
        ruta: `/cobranzas/${COBRANZA_ID}/anulacion`,
        responder: () => ({ status: 200, cuerpo: { cobranza_id: COBRANZA_ID, estado: 'ANULADA', importe: '50000.00', saldo: '200000.00' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await usuario.click(await screen.findByRole('button', { name: /anular cobranza/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Error de carga' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_COBRANZA_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/cobranzas/${COBRANZA_ID}/anulacion`)).toHaveLength(1))
    const cuerpo = JSON.parse(String(llamadas(apiFetchMock, 'POST', `/cobranzas/${COBRANZA_ID}/anulacion`)[0]?.init.body)) as Record<string, unknown>
    expect(cuerpo.observacion).toBeNull()
  })

  it('si ya estaba anulada (COBRANZA_YA_ANULADA) cierra el diálogo y lo informa', async () => {
    montarApi(apiFetchMock, [
      detalle(),
      {
        metodo: 'POST',
        ruta: `/cobranzas/${COBRANZA_ID}/anulacion`,
        responder: () => ({ status: 409, cuerpo: { title: 'La cobranza ya está anulada', codigo: 'COBRANZA_YA_ANULADA' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await usuario.click(await screen.findByRole('button', { name: /anular cobranza/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Cheque rechazado' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_COBRANZA_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await screen.findByText('La cobranza ya está anulada')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('otro error de dominio se muestra dentro del diálogo, que sigue abierto', async () => {
    montarApi(apiFetchMock, [
      detalle(),
      {
        metodo: 'POST',
        ruta: `/cobranzas/${COBRANZA_ID}/anulacion`,
        responder: () => ({ status: 422, cuerpo: { title: 'El motivo no es válido', codigo: 'MOTIVO_INVALIDO' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await usuario.click(await screen.findByRole('button', { name: /anular cobranza/i }))
    const dialogo = await screen.findByRole('dialog')
    await within(dialogo).findByRole('option', { name: 'Cheque rechazado' })
    await usuario.selectOptions(within(dialogo).getByLabelText(/motivo/i), MOTIVO_COBRANZA_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await within(await screen.findByRole('dialog')).findByText('El motivo no es válido')).toBeInTheDocument()
  })

  it('una cobranza inexistente (404) dice que no se encontró', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/cobranzas/${COBRANZA_ID}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
    renderPantalla()

    expect(await screen.findByText(/no se encontr[oó] la cobranza/i)).toBeInTheDocument()
  })

  it('un error cualquiera dice que no se pudo obtener', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/cobranzas/${COBRANZA_ID}`, responder: () => ({ status: 500, cuerpo: { title: 'Falló' } }) },
    ])
    renderPantalla()

    expect(await screen.findByText(/no se pudo obtener la cobranza/i)).toBeInTheDocument()
  })
})
