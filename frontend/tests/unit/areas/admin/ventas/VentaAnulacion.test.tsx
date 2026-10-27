import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VentaDetalleScreen } from '../../../../../src/areas/admin/ventas/VentaDetalleScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { COBRANZA_ID, LINEA_BOTELLAS, LINEA_CAJAS, VENTA_ID, montarApi, ventaDetalle } from './ventasDePrueba'

/**
 * Pantalla de anulación de una venta (change 19, tarea 9.1; specs `ventas/administracion-de-ventas`
 * y `ventas/anulacion-de-venta`; `design.md` D2, D3, D16). Reglas: VTA-20, VTA-21, VTA-22, CLI-03.
 */

const MOTIVO_ANULACION_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
const URL_ANULACION = `/ventas/${VENTA_ID}/anulacion`

const MOTIVOS_DE_ANULACION = {
  items: [
    { id: MOTIVO_ANULACION_ID, nombre: 'Error de carga' },
    { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2', nombre: 'Devolución del cliente' },
  ],
}

function renderPantalla(rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/ventas/${VENTA_ID}`]}>
        <Routes>
          <Route path="/admin/ventas/:ventaId" element={<VentaDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function detalle(campos: Partial<Record<string, unknown>> = {}): ReglaDeApi {
  return {
    metodo: 'GET',
    ruta: `/ventas/${VENTA_ID}`,
    responder: () => ({ status: 200, cuerpo: ventaDetalle({ cliente_es_consumidor_final: false, ...campos }) }),
  }
}

const MOTIVOS: ReglaDeApi = {
  metodo: 'GET',
  ruta: '/configuracion/motivos',
  responder: () => ({ status: 200, cuerpo: MOTIVOS_DE_ANULACION }),
}

function anulacionOk(campos: Record<string, unknown> = {}): ReglaDeApi {
  return {
    metodo: 'POST',
    ruta: URL_ANULACION,
    responder: () => ({
      status: 200,
      cuerpo: { venta_id: VENTA_ID, estado: 'ANULADA', saldo: '150000.00', cobranza_id: null, cobranza_anulada: false, ...campos },
    }),
  }
}

function rechazo(status: number, codigo: string, title: string): ReglaDeApi {
  return { metodo: 'POST', ruta: URL_ANULACION, responder: () => ({ status, cuerpo: { title, codigo } }) }
}

const SIN_COBRANZA = { cobranza: null }
const COBRANZA_ANULADA = { cobranza: { cobranza_id: COBRANZA_ID, importe: '20000.00', estado: 'ANULADA' } }
const ANULACION = {
  anulada_en: '2026-10-21T10:00:00Z',
  usuario_id: 'a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1',
  usuario_nombre: 'Marta Anuladora',
  motivo_id: MOTIVO_ANULACION_ID,
  motivo_nombre: 'Error de carga',
  observacion: 'se cargó dos veces',
  devuelve_dinero: true,
}

async function abrirElDialogo(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.click(await screen.findByRole('button', { name: /^anular venta$/i }))
  const dialogo = await screen.findByRole('dialog')
  await within(dialogo).findByRole('option', { name: 'Error de carga' })
  return dialogo
}

function cuerpoEnviado(): Record<string, unknown> {
  return JSON.parse(String(llamadas(apiFetchMock, 'POST', URL_ANULACION)[0]?.init.body)) as Record<string, unknown>
}

describe('anular una venta desde el detalle (tarea 9.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  // Escenario: "Anular desde el detalle" (permiso y estado)
  // Escenarios: "Botón visible solo con permiso" y "Venta ya anulada" (administracion-de-ventas)
  it('"Anular venta" solo con ANULAR_VENTA y la venta CONFIRMADA (VTA-20)', async () => {
    montarApi(apiFetchMock, [detalle()])
    const sin = renderPantalla('VEN')
    await screen.findByTestId('total-de-la-venta')
    expect(screen.queryByRole('button', { name: /anular venta/i })).not.toBeInTheDocument()
    sin.unmount()

    montarApi(apiFetchMock, [detalle({ estado: 'ANULADA', anulacion: ANULACION })])
    const anulada = renderPantalla('GES')
    await screen.findByTestId('total-de-la-venta')
    expect(screen.queryByRole('button', { name: /anular venta/i })).not.toBeInTheDocument()
    anulada.unmount()

    montarApi(apiFetchMock, [detalle()])
    renderPantalla('GES')
    expect(await screen.findByRole('button', { name: /^anular venta$/i })).toBeInTheDocument()
  })

  it('el detalle de una venta anulada muestra el bloque "Anulación" con quién, motivo, observación y devolución', async () => {
    montarApi(apiFetchMock, [detalle({ estado: 'ANULADA', anulacion: ANULACION })])
    renderPantalla('GES')

    const bloque = await screen.findByTestId('anulacion-de-la-venta')
    expect(within(bloque).getByRole('heading', { name: /anulaci[oó]n/i })).toBeInTheDocument()
    expect(bloque).toHaveTextContent('Marta Anuladora')
    expect(bloque).toHaveTextContent('Motivo: Error de carga')
    expect(bloque).toHaveTextContent('Observación: se cargó dos veces')
    expect(bloque).toHaveTextContent('Se devolvió el dinero cobrado')
  })

  it('el bloque "Anulación" dice que no se devolvió el dinero, y no aparece si la venta no está anulada', async () => {
    montarApi(apiFetchMock, [detalle({ estado: 'ANULADA', anulacion: { ...ANULACION, devuelve_dinero: false } })])
    const anulada = renderPantalla('GES')
    expect(await screen.findByTestId('anulacion-de-la-venta')).toHaveTextContent(
      'No se devolvió el dinero: quedó a favor del cliente',
    )
    anulada.unmount()

    montarApi(apiFetchMock, [detalle()])
    renderPantalla('GES')
    await screen.findByTestId('total-de-la-venta')
    expect(screen.queryByTestId('anulacion-de-la-venta')).not.toBeInTheDocument()
  })

  // Escenario: "Anular desde el detalle", venta sin cobro
  it('sin cobranza el diálogo pide motivo y observación, no pregunta por el dinero y muestra el efecto (VTA-21)', async () => {
    montarApi(apiFetchMock, [detalle(SIN_COBRANZA), MOTIVOS])
    const usuario = userEvent.setup()
    renderPantalla('GES')

    const dialogo = await abrirElDialogo(usuario)

    expect(within(dialogo).getByLabelText(/^motivo$/i)).toBeInTheDocument()
    expect(within(dialogo).getByLabelText(/observaci[oó]n/i)).toBeInTheDocument()
    expect(within(dialogo).queryByText(/devolv[eé]s lo que cobraste/i)).not.toBeInTheDocument()
    const mercaderia = within(dialogo).getByTestId('reingreso-de-la-mercaderia')
    expect(mercaderia).toHaveTextContent('Depósito central')
    expect(mercaderia).toHaveTextContent('2 × Caja x6 (12 unidades)')
    expect(mercaderia).toHaveTextContent('3 × Botella (3 unidades)')
    expect(within(dialogo).getByTestId('efecto-en-la-cuenta')).toHaveTextContent('La cuenta del cliente baja $ 31.250,00.')
    expect(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i })).toBeDisabled()
  })

  it('anula sin cobro: envía motivo y observación, no envía devuelve_dinero y muestra el saldo que devuelve el comando', async () => {
    montarApi(apiFetchMock, [detalle(SIN_COBRANZA), MOTIVOS, anulacionOk({ saldo: '150000.00' })])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)

    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)
    await usuario.type(within(dialogo).getByLabelText(/observaci[oó]n/i), 'se cargó dos veces')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', URL_ANULACION)).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', URL_ANULACION)[0]
    expect((llamada?.init.headers as Record<string, string>)['Operation-Id']).toBeTruthy()
    expect(cuerpoEnviado()).toEqual({
      motivo_id: MOTIVO_ANULACION_ID,
      observacion: 'se cargó dos veces',
      devuelve_dinero: null,
    })
    expect(await screen.findByTestId('saldo-tras-anular')).toHaveTextContent('Nos debe $ 150.000,00')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('tras anular invalida el detalle y el listado: vuelve a pedir la venta (INV-06)', async () => {
    montarApi(apiFetchMock, [detalle(SIN_COBRANZA), MOTIVOS, anulacionOk()])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    expect(llamadas(apiFetchMock, 'GET', `/ventas/${VENTA_ID}`)).toHaveLength(1)

    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', `/ventas/${VENTA_ID}`).length).toBeGreaterThan(1))
  })

  // Escenarios: "Anular con devolución" / "Anular sin devolución"
  it('con cobranza confirmada pregunta si devuelve el dinero y no deja confirmar sin elegir (D2)', async () => {
    montarApi(apiFetchMock, [detalle(), MOTIVOS])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    expect(within(dialogo).getByText(/¿devolv[eé]s lo que cobraste\?/i)).toBeInTheDocument()
    expect(within(dialogo).getByRole('radio', { name: /^s[ií]/i })).not.toBeChecked()
    expect(within(dialogo).getByRole('radio', { name: /^no/i })).not.toBeChecked()
    expect(within(dialogo).queryByTestId('efecto-en-la-cuenta')).not.toBeInTheDocument()
    expect(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i })).toBeDisabled()
  })

  // Escenario: "Resumen del efecto con devolución" (administracion-de-ventas)
  it('con devolución el efecto suma el cobro devuelto y envía devuelve_dinero verdadero (VTA-22)', async () => {
    montarApi(apiFetchMock, [detalle(), MOTIVOS, anulacionOk({ cobranza_id: COBRANZA_ID, cobranza_anulada: true })])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    await usuario.click(within(dialogo).getByRole('radio', { name: /^s[ií]/i }))

    const efecto = within(dialogo).getByTestId('efecto-en-la-cuenta')
    expect(efecto).toHaveTextContent('La cuenta del cliente baja $ 31.250,00.')
    expect(efecto).toHaveTextContent('Y sube $ 20.000,00 por el cobro devuelto.')
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', URL_ANULACION)).toHaveLength(1))
    expect(cuerpoEnviado()).toMatchObject({ devuelve_dinero: true })
  })

  it('sin devolución el cobro queda a favor y envía devuelve_dinero falso (VTA-22)', async () => {
    montarApi(apiFetchMock, [detalle(), MOTIVOS, anulacionOk({ cobranza_id: COBRANZA_ID })])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    await usuario.click(within(dialogo).getByRole('radio', { name: /^no/i }))

    expect(within(dialogo).getByTestId('efecto-en-la-cuenta')).toHaveTextContent(
      'El cobro de $ 20.000,00 queda a favor del cliente.',
    )
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', URL_ANULACION)).toHaveLength(1))
    expect(cuerpoEnviado()).toMatchObject({ devuelve_dinero: false })
  })

  it('una cobranza ya anulada no cuenta: no pregunta por el dinero (D2)', async () => {
    montarApi(apiFetchMock, [detalle(COBRANZA_ANULADA), MOTIVOS])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)

    expect(within(dialogo).queryByText(/devolv[eé]s lo que cobraste/i)).not.toBeInTheDocument()
  })

  // Escenario: "Consumidor final"
  it('consumidor final con cobro: la devolución queda fija en Sí, explicada, y viaja verdadera (CLI-03, D3)', async () => {
    montarApi(apiFetchMock, [
      detalle({
        cliente_es_consumidor_final: true,
        cobranza: { cobranza_id: COBRANZA_ID, importe: '31250.00', estado: 'CONFIRMADA' },
      }),
      MOTIVOS,
      anulacionOk({ cobranza_id: COBRANZA_ID, cobranza_anulada: true, saldo: '0.00' }),
    ])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    expect(within(dialogo).queryByRole('radio')).not.toBeInTheDocument()
    expect(within(dialogo).getByTestId('devolucion-fija')).toHaveTextContent(/siempre se le devuelve/i)
    expect(within(dialogo).getByTestId('efecto-en-la-cuenta')).toHaveTextContent(
      'Y sube $ 31.250,00 por el cobro devuelto.',
    )
    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', URL_ANULACION)).toHaveLength(1))
    expect(cuerpoEnviado()).toMatchObject({ devuelve_dinero: true })
  })

  // Errores con su texto (D16)
  it('VENTA_YA_ANULADA cierra el diálogo, lo informa y vuelve a leer la venta', async () => {
    montarApi(apiFetchMock, [detalle(SIN_COBRANZA), MOTIVOS, rechazo(409, 'VENTA_YA_ANULADA', 'La venta ya está anulada')])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await screen.findByText(/la venta ya estaba anulada/i)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', `/ventas/${VENTA_ID}`).length).toBeGreaterThan(1))
  })

  it.each([
    ['UBICACION_TOMADA', 409, /jornada de otro vendedor/i],
    ['UBICACION_INACTIVA', 409, /ubicaci[oó]n de la venta est[aá] inactiva/i],
    ['MOTIVO_INVALIDO', 422, /motivo elegido ya no es v[aá]lido/i],
  ])('%s se muestra dentro del diálogo con su texto y el diálogo sigue abierto', async (codigo, status, texto) => {
    montarApi(apiFetchMock, [detalle(SIN_COBRANZA), MOTIVOS, rechazo(status, codigo, 'mensaje del servidor')])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(await within(await screen.findByRole('dialog')).findByText(texto)).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: /confirmar anulaci[oó]n/i })).toBeEnabled()
  })

  it('un código sin texto propio (OBSERVACION_INVALIDA) muestra el mensaje del servidor', async () => {
    montarApi(apiFetchMock, [
      detalle(SIN_COBRANZA),
      MOTIVOS,
      rechazo(422, 'OBSERVACION_INVALIDA', 'La observación supera los 500 caracteres'),
    ])
    const usuario = userEvent.setup()
    renderPantalla('GES')
    const dialogo = await abrirElDialogo(usuario)
    await usuario.selectOptions(within(dialogo).getByLabelText(/^motivo$/i), MOTIVO_ANULACION_ID)

    await usuario.click(within(dialogo).getByRole('button', { name: /confirmar anulaci[oó]n/i }))

    expect(
      await within(await screen.findByRole('dialog')).findByText('La observación supera los 500 caracteres'),
    ).toBeInTheDocument()
  })

  it('el costo de las líneas no se muestra en el diálogo ni con VER_COSTOS (solo la ayuda)', async () => {
    montarApi(apiFetchMock, [
      detalle({
        ...SIN_COBRANZA,
        lineas: [{ ...LINEA_CAJAS, costo_unitario: '1050.000000', costo_total: '75600.00' }, LINEA_BOTELLAS],
      }),
      MOTIVOS,
    ])
    const usuario = userEvent.setup()
    renderPantalla('ADM')
    const dialogo = await abrirElDialogo(usuario)

    expect(within(dialogo).queryByText(/1\.050/)).not.toBeInTheDocument()
  })

  // Escenario: "Costo solo con permiso" (spec `ayuda-contextual`, D18)
  it('ofrece los "(?)" de anular, motivo y adónde vuelve la mercadería; el del costo solo con VER_COSTOS', async () => {
    montarApi(apiFetchMock, [detalle(SIN_COBRANZA), MOTIVOS])
    const usuario = userEvent.setup()
    const sinCostos = renderPantalla('GES', ['ANULAR_VENTA'])
    expect(await screen.findByRole('button', { name: 'Ayuda: Anular una venta' })).toBeInTheDocument()
    await abrirElDialogo(usuario)
    for (const nombre of ['Motivo', 'Adónde vuelve la mercadería']) {
      expect(screen.getByRole('button', { name: `Ayuda: ${nombre}` })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: 'Ayuda: Costo de lo que vuelve' })).not.toBeInTheDocument()
    sinCostos.unmount()

    renderPantalla('ADM')
    await abrirElDialogo(usuario)
    expect(screen.getByRole('button', { name: 'Ayuda: Costo de lo que vuelve' })).toBeInTheDocument()
  })

  it('con cobranza ofrece el "(?)" de devolver el dinero; con el consumidor final, el suyo', async () => {
    montarApi(apiFetchMock, [detalle(), MOTIVOS])
    const usuario = userEvent.setup()
    const comun = renderPantalla('GES')
    await abrirElDialogo(usuario)
    expect(screen.getByRole('button', { name: 'Ayuda: ¿Devolvés lo que cobraste?' })).toBeInTheDocument()
    comun.unmount()

    montarApi(apiFetchMock, [detalle({ cliente_es_consumidor_final: true }), MOTIVOS])
    renderPantalla('GES')
    await abrirElDialogo(usuario)
    expect(screen.getByRole('button', { name: 'Ayuda: Consumidor final' })).toBeInTheDocument()
  })
})
