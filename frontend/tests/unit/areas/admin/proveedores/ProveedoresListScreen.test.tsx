import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ProveedoresListScreen } from '../../../../../src/areas/admin/proveedores/ProveedoresListScreen'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

const PROVEEDOR_1 = {
  id: '11111111-1111-4111-8111-111111111111',
  nombre: 'Bodega Andina',
  cuit: '30-71234567-1',
  contacto: null,
  telefono: null,
  email: null,
  activo: true,
  creado_en: '2026-01-01T00:00:00Z',
  actualizado_en: '2026-01-01T00:00:00Z',
}

function renderPantalla() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/proveedores']}>
        <ProveedoresListScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Tarea 11.3: listado con búsqueda, filtro por actividad; mensaje de "sin
 * permiso" ante `PERMISO_REQUERIDO` (spec `administracion-de-proveedores`,
 * escenario "Usuario sin permiso"). */
describe('ProveedoresListScreen (tarea 11.3)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los proveedores de la primera página', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { items: [PROVEEDOR_1], cursor_siguiente: null }))

    renderPantalla()

    expect(await screen.findByText('Bodega Andina')).toBeInTheDocument()
    expect(screen.getByText('30-71234567-1')).toBeInTheDocument()
  })

  it('ante PERMISO_REQUERIDO muestra el mensaje de falta de permiso y no la tabla', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
    )

    renderPantalla()

    expect(await screen.findByText(/no ten[eé]s permiso/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
