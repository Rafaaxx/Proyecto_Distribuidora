import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { UbicacionesListScreen } from '../../../../../src/areas/admin/stock/UbicacionesListScreen'
import { enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const DEPOSITO = {
  id: '11111111-1111-4111-8111-111111111111',
  nombre: 'Depósito central',
  tipo: 'DEPOSITO',
  requiere_toma: false,
  activo: true,
  actualizado_en: '2026-03-10T15:00:00Z',
}
const CAMION = {
  id: '22222222-2222-4222-8222-222222222222',
  nombre: 'Camión 1',
  tipo: 'VEHICULO',
  requiere_toma: true,
  activo: false,
  actualizado_en: '2026-03-10T15:00:00Z',
}

function renderLista(rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/stock']}>
        <Routes>
          <Route path="/admin/stock" element={<UbicacionesListScreen />} />
          <Route path="/admin/stock/ubicaciones/nueva" element={<p>Pantalla de alta</p>} />
          <Route path="/admin/stock/ubicaciones/:ubicacionId" element={<p>Pantalla de edición</p>} />
          <Route path="/admin/stock/ubicaciones/:ubicacionId/stock" element={<p>Pantalla de stock</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('UbicacionesListScreen (tarea 8.2, D2, D3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/ubicaciones',
        responder: () => ({ status: 200, cuerpo: { items: [DEPOSITO, CAMION], cursor_siguiente: null } }),
      },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('un Administrador ve las ubicaciones con tipo y estado y todas las acciones', async () => {
    renderLista('ADM')

    expect(await screen.findByText('Depósito central')).toBeInTheDocument()
    const fila = screen.getByText('Camión 1').closest('tr') as HTMLElement
    expect(within(fila).getByText('Vehículo')).toBeInTheDocument()
    expect(within(fila).getByText('Inactiva')).toBeInTheDocument()
    expect(within(fila).getByText('Sí')).toBeInTheDocument() // requiere toma
    expect(screen.getByRole('link', { name: 'Nueva ubicación' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Editar' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Ver stock' })).toHaveLength(2)
  })

  it('un Vendedor ve las ubicaciones y el stock, pero no puede crear ni editar', async () => {
    renderLista('VEN')

    expect(await screen.findByText('Depósito central')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Ver stock' })).toHaveLength(2)
    expect(screen.queryByRole('link', { name: 'Nueva ubicación' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Editar' })).not.toBeInTheDocument()
  })

  it('sin TRANSFERIR_STOCK no se monta nada ni se pide ninguna ubicación', async () => {
    renderLista('CON')

    expect(await screen.findByText('No tenés permiso para ver el stock.')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('el filtro de estado vuelve a pedir el listado con activo', async () => {
    const usuario = userEvent.setup()
    renderLista('ADM')
    await screen.findByText('Depósito central')

    await usuario.selectOptions(screen.getByLabelText('Estado'), 'true')

    await waitFor(() => {
      const ultimas = apiFetchMock.mock.calls.map((c) => String(c[0]))
      expect(ultimas.some((r) => r.includes('activo=true'))).toBe(true)
    })
  })

  it('"Cargar más" trae la página siguiente con el cursor', async () => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      {
        ruta: '/stock/ubicaciones',
        responder: (url) =>
          url.searchParams.get('cursor') === 'c1'
            ? { status: 200, cuerpo: { items: [CAMION], cursor_siguiente: null } }
            : { status: 200, cuerpo: { items: [DEPOSITO], cursor_siguiente: 'c1' } },
      },
    ])
    const usuario = userEvent.setup()
    renderLista('ADM')

    await usuario.click(await screen.findByRole('button', { name: 'Cargar más' }))

    expect(await screen.findByText('Camión 1')).toBeInTheDocument()
    expect(screen.getByText('Depósito central')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
  })

  it('sin ubicaciones lo dice', async () => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { ruta: '/stock/ubicaciones', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
    ])
    renderLista('ADM')
    expect(await screen.findByText('Todavía no hay ubicaciones.')).toBeInTheDocument()
  })

  it('un error del servidor muestra un aviso', async () => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { ruta: '/stock/ubicaciones', responder: () => ({ status: 500, cuerpo: { title: 'Falla', codigo: 'X' } }) },
    ])
    renderLista('ADM')
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron obtener las ubicaciones.')
  })
})
