import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { RevisionArea } from '../../../../../src/areas/admin/revision/RevisionArea'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  OBS_DESCUENTO,
  OBS_STOCK_1,
  OBS_STOCK_2,
  VENTA_ID,
  montarApi,
  observacion,
  operacion,
  pagina,
} from './revisionDePrueba'

function renderPantalla(rol: 'GES' | 'VEN' | 'CON' = 'GES', permisos?: string[], ruta = '/admin/revision') {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
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

const RESOLUCION_OK = {
  observaciones: [OBS_STOCK_1, OBS_STOCK_2],
  resuelto_en: '2026-11-05T12:00:00Z',
  comentario: 'Se corrigió con un ajuste',
}

function reglaDeLista(items: unknown[] = [operacion()]) {
  return { metodo: 'GET', ruta: '/observaciones', responder: () => ({ status: 200, cuerpo: pagina(items) }) }
}

/**
 * Change 25, tarea 13.2 (D1, D3, D11; SYN-08, `01` §19, INV-01): la bandeja «Observaciones» de
 * `/admin/revision`.
 */
describe('ObservacionesScreen (tarea 13.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('sin REVISAR_OBSERVACIONES no se muestra la pantalla y no se pide nada (SEG-06)', async () => {
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla('VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver la revisi[oó]n/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/observaciones')).toHaveLength(0)
  })

  it('una operación con tres avisos es una sola fila, con etiqueta y detalle legible de cada aviso (SYN-07)', async () => {
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla()

    const filas = await screen.findAllByRole('row')
    expect(filas).toHaveLength(2) // encabezado + una operación
    const fila = filas[1] as HTMLElement
    expect(within(fila).getByText('Venta 0001-00000012')).toBeInTheDocument()
    expect(within(fila).getByText(/Kiosco La Esquina/)).toBeInTheDocument()
    expect(within(fila).getByText('Juan')).toBeInTheDocument()
    expect(within(fila).getAllByText('Stock negativo')).toHaveLength(2)
    expect(within(fila).getByText('Saldo resultante: -3 unidades')).toBeInTheDocument()
    expect(within(fila).getByText('Descuentos distintos')).toBeInTheDocument()
    expect(within(fila).getByText('Causa: faltó el motivo')).toBeInTheDocument()
  })

  it('muestra los nombres que manda el servidor: autorizador, producto, línea y vendedor de la jornada', async () => {
    const sinNombres = { autorizador: null, producto: null, linea: null, vendedor_de_jornada: null }
    montarApi(apiFetchMock, [
      reglaDeLista([
        operacion({
          observaciones: [
            observacion({
              id: 'a1',
              codigo: 'AUTORIZACION_OFFLINE',
              detalle: { tipo: 'DESCUENTO', resolucion: 'PIN_SUPERVISOR', autorizador_id: 'u9', autorizador_con_permiso: true },
              nombres: { ...sinNombres, autorizador: 'Ana Supervisora' },
            }),
            observacion({
              id: 'a2',
              codigo: 'PRODUCTO_DESACTIVADO',
              detalle: { linea_id: 'l1', producto_id: 'p1', inactivo: 'PRODUCTO' },
              nombres: { ...sinNombres, producto: 'Cerveza Rubia', linea: 2 },
            }),
            observacion({
              id: 'a3',
              codigo: 'UBICACION_TOMADA_AL_SINCRONIZAR',
              detalle: { jornada_id: 'j1', ubicacion_id: 'x1' },
              nombres: { ...sinNombres, vendedor_de_jornada: 'Beto Vendedor' },
            }),
          ],
        }),
      ]),
    ])
    renderPantalla()

    const fila = (await screen.findAllByRole('row'))[1] as HTMLElement
    expect(within(fila).getByText('Autorizó Ana Supervisora (descuento, con el PIN de un supervisor); conserva el permiso')).toBeInTheDocument()
    expect(within(fila).getByText('Línea 2: Cerveza Rubia')).toBeInTheDocument()
    expect(within(fila).getByText('Tomada por la jornada de Beto Vendedor')).toBeInTheDocument()
  })

  it('pide los pendientes por defecto y cada filtro vuelve a pedir con su parámetro', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')

    expect(llamadas(apiFetchMock, 'GET', '/observaciones')[0]?.url.searchParams.get('estado')).toBe('PENDIENTE')

    await usuario.selectOptions(screen.getByLabelText('Estado'), 'RESUELTA')
    await usuario.selectOptions(screen.getByLabelText('Código'), 'STOCK_NEGATIVO')
    await usuario.selectOptions(screen.getByLabelText('Tipo de operación'), 'COBRANZA')
    await usuario.type(screen.getByLabelText('Desde'), '2026-11-01')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/observaciones').at(-1)?.url.searchParams
      expect(ultima?.get('estado')).toBe('RESUELTA')
      expect(ultima?.getAll('codigo')).toEqual(['STOCK_NEGATIVO'])
      expect(ultima?.getAll('tipo')).toEqual(['COBRANZA'])
      expect(ultima?.get('desde')).not.toBeNull()
    })
  })

  it('la jornada llega por la URL y se manda como filtro', async () => {
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla('GES', undefined, '/admin/revision?jornada=c0000000-0000-4000-8000-000000000001')

    await screen.findByText('Venta 0001-00000012')
    expect(llamadas(apiFetchMock, 'GET', '/observaciones')[0]?.url.searchParams.get('jornada_id')).toBe(
      'c0000000-0000-4000-8000-000000000001',
    )
  })

  it('sin pendientes dice «Sin avisos pendientes.»', async () => {
    montarApi(apiFetchMock, [reglaDeLista([])])
    renderPantalla()

    expect(await screen.findByText('Sin avisos pendientes.')).toBeInTheDocument()
  })

  it('«Resolver {N} avisos» cuenta lo elegido y la casilla de la operación elige todos sus avisos', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')

    expect(screen.getByRole('button', { name: /^resolver/i })).toBeDisabled()
    await usuario.click(screen.getAllByRole('checkbox', { name: /^Elegir aviso/ })[0] as HTMLElement)
    await usuario.click(screen.getAllByRole('checkbox', { name: /^Elegir aviso/ })[1] as HTMLElement)
    expect(screen.getByRole('button', { name: 'Resolver 2 avisos' })).toBeEnabled()

    await usuario.click(screen.getByRole('checkbox', { name: 'Elegir todos los avisos de Venta 0001-00000012' }))
    expect(screen.getByRole('button', { name: 'Resolver 3 avisos' })).toBeEnabled()
    await usuario.click(screen.getByRole('checkbox', { name: 'Elegir todos los avisos de Venta 0001-00000012' }))
    expect(screen.getByRole('button', { name: /^resolver/i })).toBeDisabled()
  })

  it('resuelve con comentario y confirmación: manda los ids y el comentario con su Operation-Id y recarga (SYN-08)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      reglaDeLista(),
      { metodo: 'POST', ruta: '/observaciones/resolucion', responder: () => ({ status: 200, cuerpo: RESOLUCION_OK }) },
    ])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')
    const cargasAntes = llamadas(apiFetchMock, 'GET', '/observaciones').length

    await usuario.click(screen.getAllByRole('checkbox', { name: /^Elegir aviso/ })[0] as HTMLElement)
    await usuario.click(screen.getAllByRole('checkbox', { name: /^Elegir aviso/ })[1] as HTMLElement)
    await usuario.click(screen.getByRole('button', { name: 'Resolver 2 avisos' }))

    const dialogo = await screen.findByRole('dialog', { name: 'Resolver 2 avisos' })
    expect(within(dialogo).getByText('¿Resolver 2 avisos con este comentario? No se puede deshacer.')).toBeInTheDocument()
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Se corrigió con un ajuste')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/observaciones/resolucion')).toHaveLength(1))
    const envio = llamadas(apiFetchMock, 'POST', '/observaciones/resolucion')[0]
    expect(JSON.parse(envio?.init.body as string)).toEqual({
      observaciones: [OBS_STOCK_1, OBS_STOCK_2],
      comentario: 'Se corrigió con un ajuste',
    })
    expect((envio?.init.headers as Record<string, string>)['Operation-Id']).toMatch(/^[0-9a-f-]{36}$/)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/observaciones').length).toBeGreaterThan(cargasAntes))
  })

  it('sin comentario no envía y avisa; con más de 500 caracteres tampoco (COMENTARIO_INVALIDO)', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')
    await usuario.click(screen.getByRole('checkbox', { name: 'Elegir todos los avisos de Venta 0001-00000012' }))
    await usuario.click(screen.getByRole('button', { name: 'Resolver 3 avisos' }))

    const dialogo = await screen.findByRole('dialog')
    await usuario.type(within(dialogo).getByLabelText('Comentario'), '   ')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))
    expect(await within(dialogo).findByText('Escribí un comentario de hasta 500 caracteres.')).toBeInTheDocument()

    await usuario.clear(within(dialogo).getByLabelText('Comentario'))
    await usuario.click(within(dialogo).getByLabelText('Comentario'))
    await usuario.paste('x'.repeat(501))
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))
    expect(within(dialogo).getByText('Escribí un comentario de hasta 500 caracteres.')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/observaciones/resolucion')).toHaveLength(0)
  })

  it('OBSERVACION_YA_RESUELTA muestra su texto y recarga la lista', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      reglaDeLista(),
      {
        metodo: 'POST',
        ruta: '/observaciones/resolucion',
        responder: () => ({ status: 409, cuerpo: { title: 'Ya resuelta.', codigo: 'OBSERVACION_YA_RESUELTA' } }),
      },
    ])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')
    const cargasAntes = llamadas(apiFetchMock, 'GET', '/observaciones').length
    await usuario.click(screen.getByRole('checkbox', { name: 'Elegir todos los avisos de Venta 0001-00000012' }))
    await usuario.click(screen.getByRole('button', { name: 'Resolver 3 avisos' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Revisado')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    expect(
      await within(dialogo).findByText('Alguno de los avisos ya lo resolvió otra persona. Actualizá la lista.'),
    ).toBeInTheDocument()
    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/observaciones').length).toBeGreaterThan(cargasAntes))
  })

  it('reintentar tras un fallo reenvía el mismo Operation-Id (INV-06)', async () => {
    const usuario = userEvent.setup()
    let intento = 0
    montarApi(apiFetchMock, [
      reglaDeLista(),
      {
        metodo: 'POST',
        ruta: '/observaciones/resolucion',
        responder: () => {
          intento += 1
          return intento === 1
            ? { status: 500, cuerpo: { title: 'Error del servidor.', codigo: 'ERROR_INTERNO' } }
            : { status: 200, cuerpo: RESOLUCION_OK }
        },
      },
    ])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')
    await usuario.click(screen.getByRole('checkbox', { name: 'Elegir todos los avisos de Venta 0001-00000012' }))
    await usuario.click(screen.getByRole('button', { name: 'Resolver 3 avisos' }))
    const dialogo = await screen.findByRole('dialog')
    await usuario.type(within(dialogo).getByLabelText('Comentario'), 'Revisado')
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/observaciones/resolucion')).toHaveLength(1))
    await usuario.click(within(dialogo).getByRole('button', { name: 'Resolver' }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/observaciones/resolucion')).toHaveLength(2))
    const [primero, segundo] = llamadas(apiFetchMock, 'POST', '/observaciones/resolucion')
    expect((segundo?.init.headers as Record<string, string>)['Operation-Id']).toBe(
      (primero?.init.headers as Record<string, string>)['Operation-Id'],
    )
  })

  it('un aviso resuelto muestra quién, cuándo y el comentario, y no se puede elegir', async () => {
    montarApi(apiFetchMock, [
      reglaDeLista([
        operacion({
          estado: 'RESUELTA',
          observaciones: [
            observacion({
              id: OBS_DESCUENTO,
              estado: 'RESUELTA',
              resuelto_por_id: 'u9',
              resuelto_por_nombre: 'Marta',
              resuelto_en: '2026-11-05T12:00:00Z',
              comentario: 'Se corrigió con un ajuste',
            }),
          ],
        }),
      ]),
    ])
    renderPantalla('GES', undefined, '/admin/revision')

    expect(
      await screen.findByText(/^Resuelta por Marta el \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}: Se corrigió con un ajuste$/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /^Elegir/ })).not.toBeInTheDocument()
  })

  it('«Ver» lleva a la operación solo si el usuario puede abrirla', async () => {
    montarApi(apiFetchMock, [reglaDeLista()])
    const { unmount } = renderPantalla('GES', ['REVISAR_OBSERVACIONES', 'VENDER'])
    const enlace = await screen.findByRole('link', { name: 'Ver' })
    expect(enlace).toHaveAttribute('href', `/admin/ventas/${VENTA_ID}`)
    unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla('GES', ['REVISAR_OBSERVACIONES'])
    await screen.findByText('Venta 0001-00000012')
    expect(screen.queryByRole('link', { name: 'Ver' })).not.toBeInTheDocument()
  })

  it('las pestañas llevan a «Rechazadas»', async () => {
    montarApi(apiFetchMock, [reglaDeLista()])
    renderPantalla()
    await screen.findByText('Venta 0001-00000012')

    expect(screen.getByRole('link', { name: 'Observaciones' })).toHaveAttribute('href', '/admin/revision')
    expect(screen.getByRole('link', { name: 'Rechazadas' })).toHaveAttribute('href', '/admin/revision/rechazadas')
  })
})
