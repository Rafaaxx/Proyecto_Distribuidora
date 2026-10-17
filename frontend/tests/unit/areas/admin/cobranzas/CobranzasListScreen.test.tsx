import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CobranzasListScreen } from '../../../../../src/areas/admin/cobranzas/CobranzasListScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import {
  COBRANZA_DE_VENTA_ID,
  COBRANZA_ID,
  CLIENTE_ID,
  JORNADA_ID,
  cobranzaResumen,
  montarApi,
} from './cobranzasDePrueba'

function renderPantalla(rol: 'GES' | 'VEN' | 'CON' = 'GES', permisos?: string[], ruta = '/admin/cobranzas') {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/cobranzas" element={<CobranzasListScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const pagina = (items: unknown[], cursor: string | null = null) => ({ items, cursor_siguiente: cursor })

describe('CobranzasListScreen (tarea 14.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sin permisos de cobranza muestra la falta de permiso y no pide nada', async () => {
    montarApi(apiFetchMock)
    renderPantalla('CON')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las cobranzas/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/cobranzas')).toHaveLength(0)
  })

  it('lista cliente, importe formateado, estado y origen, y enlaza al detalle', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/cobranzas',
        responder: () => ({
          status: 200,
          cuerpo: pagina([
            cobranzaResumen(),
            cobranzaResumen({ cobranza_id: COBRANZA_DE_VENTA_ID, estado: 'ANULADA', origen: 'VENTA', importe: '1250.50' }),
          ]),
        }),
      },
    ])
    renderPantalla()

    const fila = (await screen.findAllByRole('row'))[1] as HTMLElement
    expect(within(fila).getByText('Kiosco La Esquina')).toBeInTheDocument()
    expect(within(fila).getByText('50.000,00')).toBeInTheDocument()
    expect(within(fila).getByText('Confirmada')).toBeInTheDocument()
    expect(within(fila).getByText('Cobranza independiente')).toBeInTheDocument()
    expect(within(fila).getByRole('link', { name: /ver detalle/i })).toHaveAttribute('href', `/admin/cobranzas/${COBRANZA_ID}`)
    const segunda = (await screen.findAllByRole('row'))[2] as HTMLElement
    expect(within(segunda).getByText('1.250,50')).toBeInTheDocument()
    expect(within(segunda).getByText('Anulada')).toBeInTheDocument()
  })

  it('sin cobranzas dice que todavía no hay', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 200, cuerpo: pagina([]) }) }])
    renderPantalla()

    expect(await screen.findByText(/todav[ií]a no hay cobranzas/i)).toBeInTheDocument()
  })

  it('"Registrar cobranza" solo con REGISTRAR_COBRANZA; con solo ANULAR_COBRANZA ve el listado sin el botón', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 200, cuerpo: pagina([]) }) }])
    const primera = renderPantalla('GES', ['REGISTRAR_COBRANZA'])
    expect(await screen.findByRole('link', { name: /registrar cobranza/i })).toHaveAttribute('href', '/admin/cobranzas/nuevo')
    primera.unmount()

    renderPantalla('GES', ['ANULAR_COBRANZA'])
    expect(await screen.findByText(/todav[ií]a no hay cobranzas/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /registrar cobranza/i })).not.toBeInTheDocument()
  })

  it('los filtros viajan como parámetros: cliente, estado y fechas', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 200, cuerpo: pagina([]) }) }])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText(/todav[ií]a no hay cobranzas/i)
    await screen.findByRole('option', { name: 'Kiosco La Esquina' })

    await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), CLIENTE_ID)
    await usuario.selectOptions(screen.getByLabelText(/^estado$/i), 'ANULADA')
    await usuario.type(screen.getByLabelText(/^desde$/i), '2026-10-01')
    await usuario.type(screen.getByLabelText(/^hasta$/i), '2026-10-05')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/cobranzas').at(-1)
      expect(ultima?.url.searchParams.get('cliente_id')).toBe(CLIENTE_ID)
      expect(ultima?.url.searchParams.get('estado')).toBe('ANULADA')
      expect(ultima?.url.searchParams.get('desde')).toBe('2026-10-01')
      expect(ultima?.url.searchParams.get('hasta')).toBe('2026-10-05')
    })
  })

  it('la jornada y el usuario llegan por la URL como filtros y se pueden quitar', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 200, cuerpo: pagina([]) }) }])
    const usuario = userEvent.setup()
    renderPantalla('GES', undefined, `/admin/cobranzas?jornada=${JORNADA_ID}`)

    await screen.findByText(/todav[ií]a no hay cobranzas/i)
    expect(llamadas(apiFetchMock, 'GET', '/cobranzas')[0]?.url.searchParams.get('jornada_id')).toBe(JORNADA_ID)
    expect(screen.getByText(/filtrando por una jornada/i)).toBeInTheDocument()

    await usuario.click(screen.getByRole('button', { name: /quitar filtro de jornada/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'GET', '/cobranzas').at(-1)?.url.searchParams.has('jornada_id')).toBe(false))
    expect(screen.queryByText(/filtrando por una jornada/i)).not.toBeInTheDocument()
  })

  it('"Cargar más" pide la página siguiente con el cursor y suma las filas', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/cobranzas',
        responder: (url) =>
          url.searchParams.get('cursor') === 'PAG2'
            ? { status: 200, cuerpo: pagina([cobranzaResumen({ cobranza_id: COBRANZA_DE_VENTA_ID, cliente_nombre: 'Almacén Don Pedro' })]) }
            : { status: 200, cuerpo: pagina([cobranzaResumen()], 'PAG2') },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await screen.findByRole('cell', { name: 'Kiosco La Esquina' })
    await usuario.click(screen.getByRole('button', { name: /cargar m[aá]s/i }))

    expect(await screen.findByRole('cell', { name: 'Almacén Don Pedro' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Kiosco La Esquina' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cargar m[aá]s/i })).not.toBeInTheDocument()
  })

  it('un 403 del servidor muestra la falta de permiso y otro error, un aviso', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 403, cuerpo: { title: 'Sin permiso' } }) }])
    const primera = renderPantalla()
    expect(await screen.findByText(/no ten[eé]s permiso para ver las cobranzas/i)).toBeInTheDocument()
    primera.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/cobranzas', responder: () => ({ status: 500, cuerpo: { title: 'Falló' } }) }])
    renderPantalla()
    expect(await screen.findByText(/no se pudieron obtener las cobranzas/i)).toBeInTheDocument()
  })
})
