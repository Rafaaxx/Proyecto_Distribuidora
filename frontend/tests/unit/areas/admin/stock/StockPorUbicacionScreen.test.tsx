import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { StockPorUbicacionScreen } from '../../../../../src/areas/admin/stock/StockPorUbicacionScreen'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const UBICACION = '11111111-1111-4111-8111-111111111111'
const PRODUCTO_A = '22222222-2222-4222-8222-222222222222'
const PRODUCTO_B = '33333333-3333-4333-8333-333333333333'

const CON_COSTO = {
  producto_id: PRODUCTO_A,
  producto_codigo: 'COD-1',
  producto_nombre: 'Vino A',
  cantidad_base: 31,
  unidades_referencia: 6,
  costo_promedio: '1050.000000',
}
const SIN_REFERENCIA = {
  producto_id: PRODUCTO_B,
  producto_codigo: 'COD-2',
  producto_nombre: 'Cerveza B',
  cantidad_base: 7,
  unidades_referencia: null,
  costo_promedio: null,
}

function renderStock(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[`/admin/stock/ubicaciones/${UBICACION}/stock`]}>
        <Routes>
          <Route path="/admin/stock/ubicaciones/:ubicacionId/stock" element={<StockPorUbicacionScreen />} />
          <Route path="/admin/stock/ubicaciones/:ubicacionId/kardex/:productoId" element={<p>Pantalla de kardex</p>} />
          <Route path="/admin/stock/ubicaciones/:ubicacionId/stock-inicial" element={<p>Pantalla de stock inicial</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('StockPorUbicacionScreen (tarea 8.3, CAT-08, D3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un Administrador ve cajas + unidades y el costo promedio formateado, "Sin costo" si es nulo', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: () => ({ status: 200, cuerpo: { items: [CON_COSTO, SIN_REFERENCIA], cursor_siguiente: null } }),
      },
    ])
    renderStock('ADM')

    const fila = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    expect(within(fila).getByText('5 cajas + 1 un.')).toBeInTheDocument()
    expect(within(fila).getByText('$ 1.050,000000')).toBeInTheDocument()
    const otra = screen.getByText('Cerveza B').closest('tr') as HTMLElement
    expect(within(otra).getByText('7 un.')).toBeInTheDocument()
    expect(within(otra).getByText('Sin costo')).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Costo promedio' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cargar stock inicial' })).toBeInTheDocument()
  })

  it('un Vendedor ve las cantidades y ninguna columna de costo, ni aunque la API la mandara', async () => {
    const sinCosto: Record<string, unknown> = { ...CON_COSTO }
    delete sinCosto.costo_promedio
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: () => ({ status: 200, cuerpo: { items: [sinCosto], cursor_siguiente: null } }),
      },
    ])
    renderStock('VEN')

    const fila = (await screen.findByText('Vino A')).closest('tr') as HTMLElement
    expect(within(fila).getByText('5 cajas + 1 un.')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Costo promedio' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Sin costo/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Cargar stock inicial' })).not.toBeInTheDocument()
  })

  it('un Vendedor nunca muestra un costo aunque el cuerpo lo trajera', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: () => ({ status: 200, cuerpo: { items: [CON_COSTO], cursor_siguiente: null } }),
      },
    ])
    renderStock('VEN')

    await screen.findByText('Vino A')
    expect(screen.queryByText('$ 1.050,000000')).not.toBeInTheDocument()
  })

  it('cada fila lleva al kardex del producto en esa ubicación', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: () => ({ status: 200, cuerpo: { items: [CON_COSTO], cursor_siguiente: null } }),
      },
    ])
    const usuario = userEvent.setup()
    renderStock('ADM')

    await usuario.click(await screen.findByRole('link', { name: 'Ver kardex' }))

    expect(await screen.findByText('Pantalla de kardex')).toBeInTheDocument()
  })

  it('"Cargar más" sigue con el cursor', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: { items: [SIN_REFERENCIA], cursor_siguiente: null } }
            : { status: 200, cuerpo: { items: [CON_COSTO], cursor_siguiente: 'c1' } },
      },
    ])
    const usuario = userEvent.setup()
    renderStock('ADM')

    await usuario.click(await screen.findByRole('button', { name: 'Cargar más' }))

    expect(await screen.findByText('Cerveza B')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', `/stock/ubicaciones/${UBICACION}/saldos`)).toHaveLength(2)
  })

  it('sin stock lo dice', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }),
      },
    ])
    renderStock('ADM')

    expect(await screen.findByText('No hay stock en esta ubicación.')).toBeInTheDocument()
  })

  it('una ubicación ajena o inexistente (404) lo avisa', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: `/stock/ubicaciones/${UBICACION}/saldos`,
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
    ])
    renderStock('ADM')

    expect(await screen.findByRole('alert')).toHaveTextContent('La ubicación pedida no existe.')
  })

  it('sin TRANSFERIR_STOCK no se monta ni se pide nada', async () => {
    renderStock('CON')

    expect(await screen.findByText('No tenés permiso para ver el stock.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
