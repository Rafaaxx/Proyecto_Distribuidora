import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ProveedoresListScreen } from '../../../../../src/areas/admin/proveedores/ProveedoresListScreen'
import type { RolDePrueba } from '../../../utils/permisosDePrueba'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

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

const SIN_PERMISO_DE_PROVEEDORES = 'No tenés permiso para gestionar proveedores.'

/** Monta la pantalla con `['yo']` ya sembrado (auxiliar compartido de la
 * tarea 6.7). Roles de `01-dominio.md` §19: GES tiene
 * `GESTIONAR_PROVEEDORES`, VEN no tiene ninguno de administración. */
function renderPantalla(rol: RolDePrueba = 'GES') {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={['/admin/proveedores']}>
        <ProveedoresListScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Tarea 11.3: listado con búsqueda y filtro por actividad. Tarea 8.4 del
 * change 06b: la visibilidad sale de `['yo']` (`GESTIONAR_PROVEEDORES`) y el
 * 403 del servidor queda como red de seguridad -- escenarios "Usuario sin
 * permiso" y "El servidor rechaza aunque la interfaz creía tener el permiso"
 * de la spec `administracion-de-proveedores`.
 *
 * Línea base de la suite: 2 casos, todos verdes antes de la tarea 8.4. */
describe('ProveedoresListScreen (tareas 11.3 y 8.4, B2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lista los proveedores de la primera página', async () => {
    apiFetchMock.mockResolvedValue(respuesta(200, { items: [PROVEEDOR_1], cursor_siguiente: null }))

    renderPantalla('GES')

    expect(await screen.findByText('Bodega Andina')).toBeInTheDocument()
    expect(screen.getByText('30-71234567-1')).toBeInTheDocument()
  })

  it('sin el permiso en la consulta de sesión no pide proveedores y no muestra la tabla (B2, escenario "Usuario sin permiso")', async () => {
    renderPantalla('VEN')

    expect(await screen.findByText(SIN_PERMISO_DE_PROVEEDORES)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it('si el servidor rechaza aunque la interfaz creía tener el permiso, muestra la falta de permiso sin tabla y sin error genérico (red de seguridad, SEG-06)', async () => {
    apiFetchMock.mockResolvedValue(
      respuesta(403, { title: 'Falta el permiso requerido.', codigo: 'PERMISO_REQUERIDO' }),
    )

    renderPantalla('GES')

    expect(await screen.findByText(SIN_PERMISO_DE_PROVEEDORES)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/no se pudieron obtener los proveedores/i)).not.toBeInTheDocument()
  })
})
