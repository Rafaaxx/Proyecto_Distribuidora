import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { RevisionArea } from '../../../../../src/areas/admin/revision/RevisionArea'
import { formatearFechaHora } from '../../../../../src/lib/fecha'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  COBRANZA_VINCULADA_ID,
  CUARENTENA_ID,
  RECHAZO_ID,
  VENTA_VINCULADA_ID,
  montarApi,
  pagina,
  rechazo,
} from './revisionDePrueba'

const PERMISOS_DE_REVISION = ['REVISAR_OBSERVACIONES', 'VENDER', 'REGISTRAR_COBRANZA']
const CLIENTE_ID = '12121212-1212-4121-8121-121212121212'

function renderPantalla(permisos: string[] = PERMISOS_DE_REVISION, ruta = '/admin/revision/rechazadas') {
  const cliente = queryClientConYo('GES', { permisos } as never)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/revision/*" element={<RevisionArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function reglaDeRechazos(items: unknown[] = [rechazo()]) {
  return { metodo: 'GET', ruta: '/observaciones/rechazos', responder: () => ({ status: 200, cuerpo: pagina(items) }) }
}

const RESOLUCION_OK = {
  id: RECHAZO_ID,
  origen: 'RECHAZO',
  estado: 'RESUELTO',
  resuelto_en: '2026-11-05T12:00:00Z',
  comentario: 'No ocurrió',
  vinculo_tipo: null,
  vinculo_id: null,
}

function reglaDeResolucion(id: string, respuesta: { status: number; cuerpo: unknown } = { status: 200, cuerpo: RESOLUCION_OK }) {
  return { metodo: 'POST', ruta: `/observaciones/rechazos/${id}/resolucion`, responder: () => respuesta }
}

async function abrirResolucion(usuario: ReturnType<typeof userEvent.setup>) {
  await screen.findByText('Kiosco La Esquina')
  await usuario.click(screen.getByRole('button', { name: 'Resolver' }))
  return screen.findByRole('dialog')
}

/**
 * Change 25, tarea 14.1 (D7, D11; SYN-06, SYN-08, SYN-09): la pestaña «Rechazadas» de `/admin/revision`.
 */
describe('RechazadasScreen (tarea 14.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('sin REVISAR_OBSERVACIONES no pide nada (SEG-06)', async () => {
    montarApi(apiFetchMock, [reglaDeRechazos()])
    renderPantalla(['VENDER'])

    expect(await screen.findByText(/no ten[eé]s permiso para ver la revisi[oó]n/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/observaciones/rechazos')).toHaveLength(0)
  })

  it('muestra tipo, vendedor, jornada, motivo traducido y lo que envió el teléfono', async () => {
    montarApi(apiFetchMock, [reglaDeRechazos([rechazo({ codigo: 'DISPOSITIVO_REVOCADO' })])])
    renderPantalla()

    const fila = (await screen.findAllByRole('row'))[1] as HTMLElement
    expect(within(fila).getByText('Venta')).toBeInTheDocument()
    expect(within(fila).getByText('Juan')).toBeInTheDocument()
    expect(within(fila).getByText('c0000000')).toBeInTheDocument()
    expect(within(fila).getByText('Este teléfono fue dado de baja; la venta quedó para revisión.')).toBeInTheDocument()
    expect(within(fila).getByText('Kiosco La Esquina')).toBeInTheDocument()
    expect(within(fila).getByText('0001-00000013')).toBeInTheDocument()
    expect(within(fila).getByText('$ 8.000,00')).toBeInTheDocument()
    expect(within(fila).getByText(/Gaseosa 2 L/)).toBeInTheDocument()
    expect(within(fila).getByText(/Efectivo/)).toBeInTheDocument()
    expect(within(fila).queryByText('Aceptada después')).not.toBeInTheDocument()
  })

  it('«Llegó» muestra cuándo llegó al servidor, como en Observaciones (revisión del usuario, 26.1)', async () => {
    montarApi(apiFetchMock, [
      reglaDeRechazos([rechazo({ recibido_en: '2026-11-04T18:00:00Z', occurred_at: '2026-11-04T15:00:00Z' })]),
    ])
    renderPantalla()

    expect(await screen.findByRole('columnheader', { name: 'Llegó' })).toBeInTheDocument()
    const fila = (await screen.findAllByRole('row'))[1] as HTMLElement
    expect(within(fila).getByText(formatearFechaHora('2026-11-04T18:00:00Z'))).toBeInTheDocument()
    expect(within(fila).queryByText(formatearFechaHora('2026-11-04T15:00:00Z'))).not.toBeInTheDocument()
  })

  it('el vínculo dice que es opcional (revisión del usuario, 26.1)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeRechazos()])
    renderPantalla()
    const dialogo = await abrirResolucion(usuario)

    expect(within(dialogo).getByText('Vincular con (opcional)')).toBeInTheDocument()
    expect(within(dialogo).getByRole('radio', { name: 'Sin vincular' })).toBeChecked()
  })

  it('la cuarentena dice «Teléfono dado de baja» y «Aceptada después» marca lo que se aceptó más tarde (SYN-09)', async () => {
    montarApi(apiFetchMock, [
      reglaDeRechazos([
        rechazo({ id: CUARENTENA_ID, origen: 'CUARENTENA', codigo: 'DISPOSITIVO_REVOCADO' }),
        rechazo({ aceptada_despues: true }),
      ]),
    ])
    renderPantalla()

    const filas = await screen.findAllByRole('row')
    expect(within(filas[1] as HTMLElement).getByText('Teléfono dado de baja')).toBeInTheDocument()
    expect(within(filas[2] as HTMLElement).getByText('Aceptada después')).toBeInTheDocument()
  })

  it('un resumen nulo no rompe: muestra el tipo y el código sin inventar', async () => {
    montarApi(apiFetchMock, [reglaDeRechazos([rechazo({ resumen: null, codigo: 'CODIGO_NUEVO' })])])
    renderPantalla()

    expect(await screen.findByText('El sistema no aceptó esta venta. (CODIGO_NUEVO)')).toBeInTheDocument()
  })

  it('pide los pendientes por defecto y cada filtro vuelve a pedir con su parámetro; la jornada llega por la URL', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeRechazos()])
    renderPantalla(PERMISOS_DE_REVISION, '/admin/revision/rechazadas?jornada=c0000000-0000-4000-8000-000000000001')
    await screen.findByText('Kiosco La Esquina')

    const primera = llamadas(apiFetchMock, 'GET', '/observaciones/rechazos')[0]?.url.searchParams
    expect(primera?.get('estado')).toBe('PENDIENTE')
    expect(primera?.get('jornada_id')).toBe('c0000000-0000-4000-8000-000000000001')

    await usuario.selectOptions(screen.getByLabelText('Estado'), 'TODOS')
    await usuario.selectOptions(screen.getByLabelText('Tipo de operación'), 'COBRANZA_REGISTRAR')
    await usuario.selectOptions(screen.getByLabelText('Origen'), 'CUARENTENA')
    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/observaciones/rechazos').at(-1)?.url.searchParams
      expect(ultima?.get('estado')).toBe('TODOS')
      expect(ultima?.getAll('tipo')).toEqual(['COBRANZA_REGISTRAR'])
      expect(ultima?.get('origen')).toBe('CUARENTENA')
    })
  })

  it('sin rechazos dice «Sin operaciones rechazadas.»', async () => {
    montarApi(apiFetchMock, [reglaDeRechazos([])])
    renderPantalla()

    expect(await screen.findByText('Sin operaciones rechazadas.')).toBeInTheDocument()
  })

  it('resuelve sin vincular: pide confirmación y comentario y manda el origen (SYN-08)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeRechazos(), reglaDeResolucion(RECHAZO_ID)])
    renderPantalla()
    const dialogo = await abrirResolucion(usuario)

    expect(within(dialogo).getByText('¿Resolver esta operación rechazada? No se puede deshacer.')).toBeInTheDocument()
    expect(within(dialogo).getByLabelText('Sin vincular')).toBeChecked()
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'No ocurrió')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)[0]
    expect(JSON.parse(envio?.init.body as string)).toEqual({ origen: 'RECHAZO', comentario: 'No ocurrió', vinculo: null })
    expect((envio?.init.headers as Record<string, string>)['Operation-Id']).toMatch(/^[0-9a-f-]{36}$/)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('una cuarentena se resuelve con su origen', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      reglaDeRechazos([rechazo({ id: CUARENTENA_ID, origen: 'CUARENTENA' })]),
      reglaDeResolucion(CUARENTENA_ID),
    ])
    renderPantalla()
    const dialogo = await abrirResolucion(usuario)
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Teléfono perdido')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${CUARENTENA_ID}/resolucion`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${CUARENTENA_ID}/resolucion`)[0]
    expect(JSON.parse(envio?.init.body as string)).toMatchObject({ origen: 'CUARENTENA' })
  })

  it('vincula con una venta buscada por número en el servidor, sin filtrar en el cliente (D7)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      reglaDeRechazos(),
      reglaDeResolucion(RECHAZO_ID),
      {
        metodo: 'GET',
        ruta: '/ventas',
        // El servidor busca sin distinguir mayúsculas: el texto escrito no está literal en el número.
        responder: () => ({
          status: 200,
          cuerpo: pagina([
            { venta_id: VENTA_VINCULADA_ID, numero: 'V01-00000040', cliente_nombre: 'Kiosco La Esquina', total: '8000.00', estado: 'CONFIRMADA' },
            { venta_id: 'f0000000-0000-4000-8000-0000000000ff', numero: 'V01-00000041', cliente_nombre: 'Almacén Don Pedro', total: '1000.00', estado: 'ANULADA' },
          ]),
        }),
      },
    ])
    renderPantalla()
    const dialogo = await abrirResolucion(usuario)

    await usuario.type(within(dialogo).getByLabelText('Buscar venta por número'), 'v01-0004')
    expect(await within(dialogo).findByLabelText(/Venta V01-00000040 · Kiosco La Esquina/)).toBeInTheDocument()
    expect(within(dialogo).getByLabelText(/Venta V01-00000041/)).toBeInTheDocument()
    const pedidos = llamadas(apiFetchMock, 'GET', '/ventas')
    const ultimo = pedidos[pedidos.length - 1]
    expect(ultimo?.url.searchParams.get('numero')).toBe('v01-0004')
    expect(ultimo?.url.searchParams.get('estado')).toBeNull()
    expect(Number(ultimo?.url.searchParams.get('limite'))).toBeLessThan(200)
    await usuario.click(within(dialogo).getByLabelText(/Venta V01-00000040/))
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Se cargó con conexión')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)[0]
    expect(JSON.parse(envio?.init.body as string)).toEqual({
      origen: 'RECHAZO',
      comentario: 'Se cargó con conexión',
      vinculo: { tipo: 'VENTA', id: VENTA_VINCULADA_ID },
    })
  })

  it('la anulación rechazada no ofrece vincular y se resuelve solo con comentario (D7)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      reglaDeRechazos([rechazo({ tipo: 'VENTA_ANULAR', resumen: null })]),
      reglaDeResolucion(RECHAZO_ID),
    ])
    renderPantalla()
    await screen.findByRole('button', { name: 'Resolver' })
    await usuario.click(screen.getByRole('button', { name: 'Resolver' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).queryByText(/Vincular con/)).not.toBeInTheDocument()

    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Ya estaba anulada')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)[0]
    expect(JSON.parse(envio?.init.body as string)).toEqual({ origen: 'RECHAZO', comentario: 'Ya estaba anulada', vinculo: null })
  })

  it('vincula con una cobranza del cliente elegido', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      reglaDeRechazos([rechazo({ tipo: 'COBRANZA_REGISTRAR', resumen: null })]),
      reglaDeResolucion(RECHAZO_ID),
      {
        metodo: 'GET',
        ruta: '/clientes/opciones',
        responder: () => ({
          status: 200,
          cuerpo: pagina([{ id: CLIENTE_ID, nombre: 'Kiosco La Esquina', codigo: 'C1', estado: 'ACTIVO', es_consumidor_final: false }]),
        }),
      },
      {
        metodo: 'GET',
        ruta: '/cobranzas',
        responder: (url) => ({
          status: 200,
          cuerpo: pagina(
            url.searchParams.get('cliente_id') === CLIENTE_ID
              ? [{ cobranza_id: COBRANZA_VINCULADA_ID, occurred_at: '2026-11-04T15:00:00Z', importe: '5000.00', cliente_nombre: 'Kiosco La Esquina', estado: 'CONFIRMADA' }]
              : [],
          ),
        }),
      },
    ])
    renderPantalla()
    await screen.findByRole('button', { name: 'Resolver' })
    await usuario.click(screen.getByRole('button', { name: 'Resolver' }))
    const dialogo = await screen.findByRole('dialog')

    await usuario.selectOptions(await within(dialogo).findByLabelText('Buscar cobranza del cliente'), CLIENTE_ID)
    await usuario.click(await within(dialogo).findByLabelText(/Cobranza .* \$ 5\.000,00/))
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Cobrada en la oficina')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', `/observaciones/rechazos/${RECHAZO_ID}/resolucion`)[0]
    expect(JSON.parse(envio?.init.body as string)).toMatchObject({
      vinculo: { tipo: 'COBRANZA', id: COBRANZA_VINCULADA_ID },
    })
  })

  it('la entrega del día no ofrece vincular (D7)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeRechazos([rechazo({ tipo: 'JORNADA_ENTREGAR', resumen: null })])])
    renderPantalla()
    await screen.findByRole('button', { name: 'Resolver' })
    await usuario.click(screen.getByRole('button', { name: 'Resolver' }))

    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).queryByText(/Vincular con/)).not.toBeInTheDocument()
  })

  it('sin permiso para abrir ventas y cobranzas no ofrece vincular, pero se puede resolver', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeRechazos()])
    renderPantalla(['REVISAR_OBSERVACIONES'])
    const dialogo = await abrirResolucion(usuario)

    expect(within(dialogo).queryByText(/Vincular con/)).not.toBeInTheDocument()
  })

  it('VINCULO_INVALIDO y RECHAZO_YA_RESUELTO muestran su texto; el segundo recarga la lista', async () => {
    const usuario = userEvent.setup()
    let respuesta = { status: 422, cuerpo: { title: 'x', codigo: 'VINCULO_INVALIDO' } }
    montarApi(apiFetchMock, [
      reglaDeRechazos(),
      { metodo: 'POST', ruta: `/observaciones/rechazos/${RECHAZO_ID}/resolucion`, responder: () => respuesta },
    ])
    renderPantalla()
    const dialogo = await abrirResolucion(usuario)
    const cargasAntes = llamadas(apiFetchMock, 'GET', '/observaciones/rechazos').length
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Revisado')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))
    expect(await within(dialogo).findByText('La operación elegida no corresponde a lo rechazado.')).toBeInTheDocument()

    respuesta = { status: 409, cuerpo: { title: 'x', codigo: 'RECHAZO_YA_RESUELTO' } }
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))
    expect(await within(dialogo).findByText('Esta operación ya la resolvió otra persona.')).toBeInTheDocument()
    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/observaciones/rechazos').length).toBeGreaterThan(cargasAntes))
  })

  it('un 404 dice «No se encontró la operación.»', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeRechazos(), reglaDeResolucion(RECHAZO_ID, { status: 404, cuerpo: { title: 'x', codigo: 'RECURSO_NO_ENCONTRADO' } })])
    renderPantalla()
    const dialogo = await abrirResolucion(usuario)
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Revisado')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    expect(await within(dialogo).findByText('No se encontró la operación.')).toBeInTheDocument()
  })

  it('un rechazo resuelto muestra quién, cuándo, el comentario y el vínculo, y no ofrece «Resolver»', async () => {
    montarApi(apiFetchMock, [
      reglaDeRechazos([
        rechazo({
          estado: 'RESUELTO',
          resuelto_por_id: 'u9',
          resuelto_por_nombre: 'Marta',
          resuelto_en: '2026-11-05T12:00:00Z',
          comentario: 'Se cargó con conexión',
          vinculo_tipo: 'VENTA',
          vinculo_id: VENTA_VINCULADA_ID,
        }),
      ]),
    ])
    renderPantalla()

    expect(await screen.findByText(/^Resuelta por Marta el \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}: Se cargó con conexión$/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver venta vinculada' })).toHaveAttribute('href', `/admin/ventas/${VENTA_VINCULADA_ID}`)
    expect(screen.queryByRole('button', { name: 'Resolver' })).not.toBeInTheDocument()
  })
})
