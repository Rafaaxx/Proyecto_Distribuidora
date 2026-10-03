import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ComprasListScreen } from '../../../../../src/areas/admin/compras/ComprasListScreen'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { COMPRA_ID, PROVEEDOR_ID } from './comprasDePrueba'

function fila(id: string, estado: string, condicion = 'CREDITO') {
  return {
    id,
    fecha: '2026-05-10',
    proveedor_id: PROVEEDOR_ID,
    proveedor_nombre: 'Bodega Sur',
    condicion,
    total_neto: '14876.03',
    total_factura: '18000.00',
    estado,
    numero_comprobante: 'A-0001',
  }
}

function renderLista(rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={['/admin/compras']}>
        <Routes>
          <Route path="/admin/compras" element={<ComprasListScreen />} />
          <Route path="/admin/compras/nueva" element={<p>Pantalla nueva compra</p>} />
          <Route path="/admin/compras/:compraId" element={<p>Detalle de compra</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ComprasListScreen (tarea 12.3 / 12.1 permisos)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: '/compras',
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: { items: [fila('22222222-2222-4222-8222-222222222222', 'ANULADA')], cursor_siguiente: null } }
            : { status: 200, cuerpo: { items: [fila(COMPRA_ID, 'CONFIRMADA')], cursor_siguiente: 'c1' } },
      },
      { metodo: 'GET', ruta: '/proveedores/opciones', responder: () => ({ status: 200, cuerpo: { items: [{ id: PROVEEDOR_ID, nombre: 'Bodega Sur' }], cursor_siguiente: null } }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra fecha, proveedor, condición, total de factura y estado', async () => {
    renderLista()

    const tabla = await screen.findByRole('table')
    const celdas = within(tabla)
    expect(celdas.getByText('10/05/2026')).toBeInTheDocument()
    expect(celdas.getByText('Bodega Sur')).toBeInTheDocument()
    expect(celdas.getByText('A crédito')).toBeInTheDocument()
    expect(celdas.getByText('18.000,00')).toBeInTheDocument()
    expect(celdas.getByText('Confirmada')).toBeInTheDocument()
  })

  it('pagina por cursor: "Cargar más" trae la página siguiente', async () => {
    const usuario = userEvent.setup()
    renderLista()
    await screen.findByText('Confirmada')

    await usuario.click(screen.getByRole('button', { name: /cargar m[aá]s/i }))

    expect(await screen.findByText('Anulada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /cargar m[aá]s/i })).not.toBeInTheDocument()
  })

  it('los filtros de proveedor, estado y fechas viajan al servidor', async () => {
    const usuario = userEvent.setup()
    renderLista()
    await screen.findByText('Confirmada')
    await screen.findByRole('option', { name: 'Bodega Sur' })

    await usuario.selectOptions(screen.getByLabelText(/^proveedor$/i), PROVEEDOR_ID)
    await usuario.selectOptions(screen.getByLabelText(/^estado$/i), 'ANULADA')
    await usuario.type(screen.getByLabelText(/^desde$/i), '2026-05-01')
    await usuario.type(screen.getByLabelText(/^hasta$/i), '2026-05-31')

    await waitFor(() => {
      const ultima = llamadas(apiFetchMock, 'GET', '/compras').at(-1)
      expect(ultima?.url.searchParams.get('proveedor_id')).toBe(PROVEEDOR_ID)
      expect(ultima?.url.searchParams.get('estado')).toBe('ANULADA')
      expect(ultima?.url.searchParams.get('desde')).toBe('2026-05-01')
      expect(ultima?.url.searchParams.get('hasta')).toBe('2026-05-31')
    })
  })

  it('con REGISTRAR_COMPRA ofrece "Nueva compra"', async () => {
    renderLista('GES')

    expect(await screen.findByRole('link', { name: /nueva compra/i })).toBeInTheDocument()
  })

  it('un usuario con solo ANULAR_COMPRA ve el listado pero no "Nueva compra"', async () => {
    renderLista('GES', ['ANULAR_COMPRA'])

    expect(await screen.findByText('Confirmada')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /nueva compra/i })).not.toBeInTheDocument()
  })

  it('un usuario sin permisos de compra ve el aviso y no se pide el listado', async () => {
    renderLista('VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las compras/i)).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/compras')).toHaveLength(0)
  })

  it('un 403 del servidor se muestra como falta de permiso', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/compras', responder: () => ({ status: 403, cuerpo: { title: 'Falta permiso', codigo: 'PERMISO_REQUERIDO' } }) },
    ])
    renderLista()

    expect(await screen.findByText(/no ten[eé]s permiso para ver las compras/i)).toBeInTheDocument()
  })

  it('sin compras muestra el estado vacío', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'GET', ruta: '/compras', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
    ])
    renderLista()

    expect(await screen.findByText(/todav[ií]a no hay compras/i)).toBeInTheDocument()
  })
})
