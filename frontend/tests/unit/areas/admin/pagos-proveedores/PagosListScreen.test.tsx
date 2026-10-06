import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { PagosListScreen } from '../../../../../src/areas/admin/pagos-proveedores/PagosListScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { COMPRA_DEL_PAGO_ID, PAGO_DE_COMPRA_ID, PAGO_ID, PROVEEDOR_ID, montarApi, pagoResumen } from './pagosDePrueba'

function renderPantalla() {
  return render(
    <QueryClientProvider client={queryClientConYo('GES')}>
      <MemoryRouter initialEntries={['/admin/pagos-proveedores']}>
        <Routes>
          <Route path="/admin/pagos-proveedores" element={<PagosListScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const PAGO_NORTE = pagoResumen({
  pago_id: 'aaaaaaaa-0000-4000-8000-000000000001',
  proveedor_nombre: 'Bodega Norte',
  importe: '80000.00',
})

describe('PagosListScreen (tarea 9.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra fecha, proveedor, importe, origen y estado de cada pago, con enlace a su detalle', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/pagos-proveedores',
        responder: () => ({
          status: 200,
          cuerpo: {
            items: [
              pagoResumen(),
              pagoResumen({ pago_id: PAGO_DE_COMPRA_ID, origen: 'COMPRA', compra_id: COMPRA_DEL_PAGO_ID, importe: '152460.00', estado: 'ANULADA' }),
            ],
            cursor_siguiente: null,
          },
        }),
      },
    ])
    renderPantalla()

    const tabla = await screen.findByRole('table')
    const filas = within(tabla).getAllByRole('row').slice(1)
    expect(filas).toHaveLength(2)
    expect(filas[0]).toHaveTextContent('05/10/2026')
    expect(filas[0]).toHaveTextContent('Bodega Sur')
    expect(filas[0]).toHaveTextContent('100.000,00')
    expect(filas[0]).toHaveTextContent('Pago independiente')
    expect(filas[0]).toHaveTextContent('Confirmado')
    expect(filas[1]).toHaveTextContent('152.460,00')
    expect(filas[1]).toHaveTextContent('Compra de contado')
    expect(filas[1]).toHaveTextContent('Anulado')
    expect(within(filas[0] as HTMLElement).getByRole('link', { name: /ver detalle/i })).toHaveAttribute('href', `/admin/pagos-proveedores/${PAGO_ID}`)
  })

  it('filtra por la fecha de hoy y muestra los dos pagos devueltos (escenario "Listado de la semana")', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/pagos-proveedores',
        responder: () => ({ status: 200, cuerpo: { items: [pagoResumen(), PAGO_NORTE], cursor_siguiente: null } }),
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table')

    await usuario.type(screen.getByLabelText(/^desde$/i), '2026-10-05')
    await usuario.type(screen.getByLabelText(/^hasta$/i), '2026-10-05')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/pagos-proveedores').at(-1)
      expect(ultima?.url.searchParams.get('desde')).toBe('2026-10-05')
      expect(ultima?.url.searchParams.get('hasta')).toBe('2026-10-05')
    })
    const filas = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(filas[0]).toHaveTextContent('100.000,00')
    expect(filas[1]).toHaveTextContent('80.000,00')
  })

  it('manda los filtros de proveedor, estado y origen', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/pagos-proveedores', responder: () => ({ status: 200, cuerpo: { items: [pagoResumen()], cursor_siguiente: null } }) },
    ])
    const usuario = userEvent.setup()
    renderPantalla()
    await screen.findByRole('table')
    await screen.findByRole('option', { name: 'Bodega Sur' })

    await usuario.selectOptions(screen.getByLabelText(/^proveedor$/i), PROVEEDOR_ID)
    await usuario.selectOptions(screen.getByLabelText(/^estado$/i), 'ANULADA')
    await usuario.selectOptions(screen.getByLabelText(/^origen$/i), 'COMPRA')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/pagos-proveedores').at(-1)
      expect(ultima?.url.searchParams.get('proveedor_id')).toBe(PROVEEDOR_ID)
      expect(ultima?.url.searchParams.get('estado')).toBe('ANULADA')
      expect(ultima?.url.searchParams.get('origen')).toBe('COMPRA')
    })
  })

  it('pagina por cursor: "Cargar más" pide la página siguiente y la agrega', async () => {
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/pagos-proveedores',
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: { items: [PAGO_NORTE], cursor_siguiente: null } }
            : { status: 200, cuerpo: { items: [pagoResumen()], cursor_siguiente: 'c1' } },
      },
    ])
    const usuario = userEvent.setup()
    renderPantalla()

    await usuario.click(await screen.findByRole('button', { name: /cargar m[aá]s/i }))

    await waitFor(() => expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3))
    expect(screen.queryByRole('button', { name: /cargar m[aá]s/i })).not.toBeInTheDocument()
  })

  it('un 403 del servidor se muestra como falta de permiso', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/pagos-proveedores', responder: () => ({ status: 403, cuerpo: { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' } }) },
    ])
    renderPantalla()

    expect(await screen.findByText(/no ten[eé]s permiso para ver los pagos a proveedores/i)).toBeInTheDocument()
  })

  it('otro error muestra que no se pudieron obtener los pagos', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/pagos-proveedores', responder: () => ({ status: 500, cuerpo: { title: 'Error', codigo: 'ERROR_INTERNO' } }) },
    ])
    renderPantalla()

    expect(await screen.findByText(/no se pudieron obtener los pagos/i)).toBeInTheDocument()
  })
})
