import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VentasListScreen } from '../../../../../src/areas/admin/ventas/VentasListScreen'
import { llamadas, type ReglaDeApi } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { CLIENTE_ID, JORNADA_ID, UBICACION_ID, VENTA_ID, montarApi, ventaResumen } from './ventasDePrueba'

function renderPantalla(rol: RolDePrueba = 'SUP', ruta = '/admin/ventas') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/ventas" element={<VentasListScreen />} />
          <Route path="/admin/ventas/nueva" element={<p>Nueva venta</p>} />
          <Route path="/admin/ventas/:ventaId" element={<p>Detalle de la venta</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function listado(respuesta: (url: URL) => { items: unknown[]; cursor_siguiente: string | null }): ReglaDeApi {
  return { metodo: 'GET', ruta: '/ventas', responder: (url) => ({ status: 200, cuerpo: respuesta(url) }) }
}

const ultimaConsulta = () => llamadas(apiFetchMock, 'GET', '/ventas').at(-1)?.url.searchParams

describe('VentasListScreen (tarea 12.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  // Escenario: "Listado con filtros"
  it('lista las ventas con número, cliente, total y estado, y cada fila lleva a su detalle', async () => {
    montarApi(apiFetchMock, [
      listado(() => ({
        items: [ventaResumen(), ventaResumen({ venta_id: 'otra', numero: 'V01-000041', total: '4300.00', estado: 'ANULADA' })],
        cursor_siguiente: null,
      })),
    ])
    renderPantalla()

    const filas = await screen.findAllByRole('row')
    expect(filas).toHaveLength(3)
    const primera = within(filas[1] as HTMLElement)
    expect(primera.getByText('V01-000042')).toBeInTheDocument()
    expect(primera.getByText('Kiosco La Esquina')).toBeInTheDocument()
    expect(primera.getByText('$ 31.250,00')).toBeInTheDocument()
    expect(primera.getByText('Confirmada')).toBeInTheDocument()
    expect(within(filas[2] as HTMLElement).getByText('Anulada')).toBeInTheDocument()
    expect(primera.getByRole('link', { name: /ver detalle/i })).toHaveAttribute('href', `/admin/ventas/${VENTA_ID}`)
  })

  it('sin ventas muestra el aviso', async () => {
    montarApi(apiFetchMock, [listado(() => ({ items: [], cursor_siguiente: null }))])
    renderPantalla()
    expect(await screen.findByText(/todav[ií]a no hay ventas/i)).toBeInTheDocument()
  })

  it('filtra por cliente, ubicación y fechas de negocio y lo pide al servidor', async () => {
    montarApi(apiFetchMock, [listado(() => ({ items: [ventaResumen()], cursor_siguiente: null }))])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('V01-000042')

    await screen.findByRole('option', { name: 'Kiosco La Esquina' })
    await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), CLIENTE_ID)
    await waitFor(() => expect(ultimaConsulta()?.get('cliente_id')).toBe(CLIENTE_ID))

    await screen.findByRole('option', { name: 'Depósito central' })
    await usuario.selectOptions(screen.getByLabelText(/^ubicaci[oó]n$/i), UBICACION_ID)
    await waitFor(() => expect(ultimaConsulta()?.get('ubicacion_id')).toBe(UBICACION_ID))

    await usuario.type(screen.getByLabelText(/^desde$/i), '2026-10-01')
    await usuario.type(screen.getByLabelText(/^hasta$/i), '2026-10-20')
    await waitFor(() => expect(ultimaConsulta()?.get('hasta')).toBe('2026-10-20'))
    expect(ultimaConsulta()?.get('desde')).toBe('2026-10-01')
    expect(ultimaConsulta()?.get('cliente_id')).toBe(CLIENTE_ID)
  })

  it('los filtros de usuario y jornada llegan por la URL y se pueden quitar', async () => {
    montarApi(apiFetchMock, [listado(() => ({ items: [ventaResumen()], cursor_siguiente: null }))])
    const usuario = userEvent.setup()
    renderPantalla('SUP', `/admin/ventas?jornada=${JORNADA_ID}&usuario=u-1`)
    await screen.findByText('V01-000042')
    expect(ultimaConsulta()?.get('jornada_id')).toBe(JORNADA_ID)
    expect(ultimaConsulta()?.get('usuario_id')).toBe('u-1')

    await usuario.click(screen.getByRole('button', { name: /quitar filtro de jornada/i }))
    await waitFor(() => expect(ultimaConsulta()?.has('jornada_id')).toBe(false))
    expect(ultimaConsulta()?.get('usuario_id')).toBe('u-1')
  })

  it('"Cargar más" pide la página siguiente con el cursor y la agrega sin repetir; al terminar desaparece', async () => {
    montarApi(apiFetchMock, [
      listado((url) =>
        url.searchParams.get('cursor') === 'c1'
          ? { items: [ventaResumen({ venta_id: 'v2', numero: 'V01-000043' })], cursor_siguiente: null }
          : { items: [ventaResumen()], cursor_siguiente: 'c1' },
      ),
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByText('V01-000042')

    await usuario.click(screen.getByRole('button', { name: /cargar m[aá]s/i }))
    await screen.findByText('V01-000043')
    expect(screen.getByText('V01-000042')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/ventas').at(-1)?.url.searchParams.get('cursor')).toBe('c1')
    expect(screen.queryByRole('button', { name: /cargar m[aá]s/i })).not.toBeInTheDocument()
  })

  it('"Nueva venta" solo se ofrece con VENDER', async () => {
    montarApi(apiFetchMock, [listado(() => ({ items: [], cursor_siguiente: null }))])
    const conVender = renderPantalla('SUP')
    expect(await screen.findByRole('link', { name: /nueva venta/i })).toHaveAttribute('href', '/admin/ventas/nueva')
    conVender.unmount()

    renderPantalla('GES')
    await screen.findByText(/todav[ií]a no hay ventas/i)
    expect(screen.queryByRole('link', { name: /nueva venta/i })).not.toBeInTheDocument()
  })

  it('un 403 o un error del listado se muestran sin romper la pantalla', async () => {
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/ventas', responder: () => ({ status: 403, cuerpo: { title: 'Sin permiso', codigo: 'PERMISO_REQUERIDO' } }) }])
    const primero = renderPantalla()
    expect(await screen.findByText(/no ten[eé]s permiso para ver las ventas/i)).toBeInTheDocument()
    primero.unmount()

    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [{ metodo: 'GET', ruta: '/ventas', responder: () => ({ status: 500, cuerpo: { title: 'Falla', codigo: 'ERROR' } }) }])
    renderPantalla()
    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudieron obtener las ventas/i)
  })

  it('sin VENDER ni ANULAR_VENTA muestra la falta de permiso y no pide nada', () => {
    montarApi(apiFetchMock)
    renderPantalla('CON')
    expect(screen.getByText(/no ten[eé]s permiso para ver las ventas/i)).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
