import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VersionScreen } from '../../../../../src/areas/admin/precios/VersionScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  LISTA_ID,
  PRECIO_MANUAL_CON_SENAL,
  VERSION_HISTORICA,
  VERSION_PROGRAMADA,
  VERSION_PROGRAMADA_ID,
  VERSION_VIGENTE_ID,
  montarApi,
  precio,
  reglasDeBorrador,
  version,
} from './preciosDePrueba'

function renderVersion(versionId: string, rol: 'ADM' | 'GES' = 'ADM', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[`/admin/precios/${LISTA_ID}/versiones/${versionId}`]}>
        <Routes>
          <Route path="/admin/precios/:listaId/versiones/:versionId" element={<VersionScreen />} />
          <Route path="/admin/precios/:listaId" element={<p>Detalle de la lista</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function respuestaDeVersion(v: unknown, precios: unknown[] = [precio(), PRECIO_MANUAL_CON_SENAL]) {
  return { version: v, precios, siguiente_cursor: null }
}

function montar(versionId: string, v: unknown, precios?: unknown[]) {
  montarApi(apiFetchMock, [
    {
      metodo: 'GET',
      ruta: `/precios/listas/${LISTA_ID}/versiones/${versionId}/precios`,
      responder: () => ({ status: 200, cuerpo: respuestaDeVersion(v, precios) }),
    },
    ...reglasDeBorrador().slice(1),
  ])
}

describe('VersionScreen: solo lectura (tarea 13.3; PRC-04, INV-11)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['vigente', VERSION_VIGENTE_ID, version(), 'Vigente'],
    ['histórica', VERSION_HISTORICA.id, VERSION_HISTORICA, 'Histórica'],
  ])('una versión %s muestra sus precios tal como se publicaron y ningún control de edición, ni a un Administrador', async (_n, id, v, estado) => {
    montar(id, v)
    renderVersion(id)

    expect(await screen.findByText(new RegExp(`versión ${(v as { numero: number }).numero}`, 'i'))).toBeInTheDocument()
    expect(screen.getByText(estado)).toBeInTheDocument()
    const tabla = within(screen.getByRole('table', { name: /precios de la versión/i }))
    const vino = tabla.getByText('Vino A').closest('tr') as HTMLElement
    expect(within(vino).getAllByRole('cell')[1]).toHaveTextContent('$ 9.500,00')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('muestra los autores y las vigencias', async () => {
    montar(VERSION_VIGENTE_ID, version())
    renderVersion(VERSION_VIGENTE_ID)

    expect(await screen.findByText(/publicada por pedro publicador/i)).toBeInTheDocument()
    expect(screen.getByText(/vigencia desde/i)).toBeInTheDocument()
  })

  it('con VER_COSTOS muestra el costo y la regla de cada precio; sin él, no', async () => {
    montar(VERSION_VIGENTE_ID, version())
    const { unmount } = renderVersion(VERSION_VIGENTE_ID, 'ADM')
    const conCostos = within(await screen.findByRole('table', { name: /precios de la versión/i }))
    expect(conCostos.getByRole('columnheader', { name: /costo de referencia/i })).toBeInTheDocument()
    unmount()

    montar(VERSION_VIGENTE_ID, version(), [
      precio({ costo_referencia: null, tipo_margen: null, valor_margen: null, precio_calculado: null }),
    ])
    renderVersion(VERSION_VIGENTE_ID, 'GES', ['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS'])
    const sinCostos = within(await screen.findByRole('table', { name: /precios de la versión/i }))
    expect(sinCostos.queryByRole('columnheader', { name: /costo de referencia/i })).not.toBeInTheDocument()
  })

  it('muestra el precio por presentación de cada línea (PRC-22), con productos de distintas presentaciones y uno sin presentaciones', async () => {
    montar(VERSION_VIGENTE_ID, version(), [
      precio(),
      PRECIO_MANUAL_CON_SENAL,
      precio({
        producto_id: 'd4d4d4d4-d4d4-44d4-84d4-d4d4d4d4d4d4',
        producto_nombre: 'Aceite D',
        unidades_referencia: 1,
        precio_final: '3000.00',
        presentaciones: [],
      }),
    ])
    renderVersion(VERSION_VIGENTE_ID)

    const tabla = within(await screen.findByRole('table', { name: /precios de la versión/i }))
    const vino = tabla.getByText('Vino A').closest('tr') as HTMLElement
    expect(within(vino).getByText(/botella \(1 u\.\).*1\.583,33/i)).toBeInTheDocument()
    expect(within(vino).getByText(/caja x6 \(6 u\.\).*9\.500,00/i)).toBeInTheDocument()
    const cerveza = tabla.getByText('Cerveza B').closest('tr') as HTMLElement
    expect(within(cerveza).getByText(/lata \(1 u\.\).*2\.583,33/i)).toBeInTheDocument()
    expect(within(cerveza).getByText(/caja x12 \(12 u\.\).*31\.000,00/i)).toBeInTheDocument()
    const aceite = tabla.getByText('Aceite D').closest('tr') as HTMLElement
    expect(within(aceite).queryByRole('list')).not.toBeInTheDocument()
    expect(within(aceite).getAllByRole('cell')[1]).toHaveTextContent('$ 3.000,00')
  })

  it('el precio por presentación se ve también sin VER_COSTOS', async () => {
    montar(VERSION_VIGENTE_ID, version(), [
      precio({ costo_referencia: null, tipo_margen: null, valor_margen: null, precio_calculado: null }),
    ])
    renderVersion(VERSION_VIGENTE_ID, 'GES', ['GESTIONAR_LISTAS', 'PUBLICAR_LISTAS'])

    expect(await screen.findByText(/botella \(1 u\.\).*1\.583,33/i)).toBeInTheDocument()
  })

  it('una versión anulada lo dice, con quién y cuándo, y no se puede anular de nuevo', async () => {
    const anulada = version({
      id: VERSION_PROGRAMADA_ID,
      numero: 5,
      estado: 'ANULADA',
      estado_derivado: null,
      anulado_por_id: 'c3c3c3c3-c3c3-43c3-83c3-c3c3c3c3c3c3',
      anulado_por_nombre: 'Ana Anuladora',
      anulado_en: '2026-10-06T12:00:00Z',
    })
    montar(VERSION_PROGRAMADA_ID, anulada)
    renderVersion(VERSION_PROGRAMADA_ID)

    expect(await screen.findByText(/anulada por ana anuladora/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /anular/i })).not.toBeInTheDocument()
  })

  it('un borrador no se edita acá: lleva a la pantalla del borrador', async () => {
    const borrador = version({ id: VERSION_PROGRAMADA_ID, numero: 6, estado: 'BORRADOR', estado_derivado: null })
    montar(VERSION_PROGRAMADA_ID, borrador)
    renderVersion(VERSION_PROGRAMADA_ID)

    expect(await screen.findByRole('link', { name: /abrir el borrador/i })).toHaveAttribute(
      'href',
      `/admin/precios/${LISTA_ID}/borrador`,
    )
    expect(screen.queryByRole('table', { name: /precios de la versión/i })).not.toBeInTheDocument()
  })

  it('sin permisos de listas muestra la falta de permiso', async () => {
    montar(VERSION_VIGENTE_ID, version())
    renderVersion(VERSION_VIGENTE_ID, 'GES', ['GESTIONAR_CLIENTES'])

    expect(await screen.findByText(/no ten[eé]s permiso para ver las listas de precios/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})

describe('VersionScreen: anular (tarea 13.3; PRC-05, PRC-06, D6)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  const rutaAnular = `/precios/listas/${LISTA_ID}/versiones/${VERSION_PROGRAMADA_ID}/anular`

  it('una versión programada ofrece "Anular" con PUBLICAR_LISTAS; la vigente no', async () => {
    montar(VERSION_PROGRAMADA_ID, VERSION_PROGRAMADA)
    const { unmount } = renderVersion(VERSION_PROGRAMADA_ID)
    expect(await screen.findByRole('button', { name: /anular versión/i })).toBeInTheDocument()
    unmount()

    montar(VERSION_VIGENTE_ID, version())
    renderVersion(VERSION_VIGENTE_ID)
    await screen.findByText(/versión 3/i)
    expect(screen.queryByRole('button', { name: /anular/i })).not.toBeInTheDocument()
  })

  it('sin PUBLICAR_LISTAS no ofrece "Anular" ni en una programada', async () => {
    montar(VERSION_PROGRAMADA_ID, VERSION_PROGRAMADA)
    renderVersion(VERSION_PROGRAMADA_ID, 'GES')

    await screen.findByText(/versión 5/i)
    expect(screen.queryByRole('button', { name: /anular/i })).not.toBeInTheDocument()
  })

  it('anula con confirmación: un POST con Operation-Id y vuelve al detalle de la lista', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/versiones/${VERSION_PROGRAMADA_ID}/precios`,
        responder: () => ({ status: 200, cuerpo: respuestaDeVersion(VERSION_PROGRAMADA) }),
      },
      { metodo: 'POST', ruta: rutaAnular, responder: () => ({ status: 200, cuerpo: { ...VERSION_PROGRAMADA, estado: 'ANULADA' } }) },
    ])
    const usuario = userEvent.setup()
    renderVersion(VERSION_PROGRAMADA_ID)

    await usuario.click(await screen.findByRole('button', { name: /anular versión/i }))
    const dialogo = within(screen.getByRole('dialog'))
    expect(dialogo.getByText(/sus precios no se borran/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', rutaAnular)).toHaveLength(0)
    await usuario.click(dialogo.getByRole('button', { name: /confirmar anulación/i }))

    expect(await screen.findByText(/detalle de la lista/i)).toBeInTheDocument()
    const envios = llamadas(apiFetchMock, 'POST', rutaAnular)
    expect(envios).toHaveLength(1)
    expect(new Headers(envios[0]?.init.headers).get('Operation-Id')).toBeTruthy()
  })

  it('VERSION_YA_VIGENTE se explica en el diálogo y la versión no se anula', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/precios/listas/${LISTA_ID}/versiones/${VERSION_PROGRAMADA_ID}/precios`,
        responder: () => ({ status: 200, cuerpo: respuestaDeVersion(VERSION_PROGRAMADA) }),
      },
      {
        metodo: 'POST',
        ruta: rutaAnular,
        responder: () => ({ status: 409, cuerpo: { title: 'La versión ya comenzó a regir.', codigo: 'VERSION_YA_VIGENTE' } }),
      },
    ])
    const usuario = userEvent.setup()
    renderVersion(VERSION_PROGRAMADA_ID)

    await usuario.click(await screen.findByRole('button', { name: /anular versión/i }))
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: /confirmar anulación/i }))

    expect(await within(screen.getByRole('dialog')).findByText('La versión ya comenzó a regir.')).toBeInTheDocument()
    expect(screen.queryByText(/detalle de la lista/i)).not.toBeInTheDocument()
    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', rutaAnular)).toHaveLength(1))
  })

  it('sin conexión no envía la anulación y avisa', async () => {
    montar(VERSION_PROGRAMADA_ID, VERSION_PROGRAMADA)
    vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
    const usuario = userEvent.setup()
    renderVersion(VERSION_PROGRAMADA_ID)

    await usuario.click(await screen.findByRole('button', { name: /anular versión/i }))
    await usuario.click(within(screen.getByRole('dialog')).getByRole('button', { name: /confirmar anulación/i }))

    expect(await within(screen.getByRole('dialog')).findByText(/se necesita conexión/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', rutaAnular)).toHaveLength(0)
    vi.restoreAllMocks()
  })
})
