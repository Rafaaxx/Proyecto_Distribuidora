/**
 * Change 16, tarea 15.1: el área de descuentos se decide con los permisos de la sesión (spec
 * `descuentos/administracion-de-descuentos`, requisito "El área de descuentos se decide con los
 * permisos de la sesión"; ADR-027, SEG-06; `01` §19). `usePermisos()` es la única fuente; ocultar
 * es una comodidad y el servidor valida igual.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AdminLayout } from '../../../../../src/areas/admin/AdminLayout'
import DescuentosArea from '../../../../../src/areas/admin/descuentos/DescuentosArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'

const AVISO_SIN_PERMISO = /no tenés permiso para ver los descuentos/i

function clienteConPermisos(rol: RolDePrueba, permisos?: string[]) {
  return permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
}

function montarMenu(cliente: ReturnType<typeof queryClientConYo>) {
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={['/admin/catalogo']}>
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route path="catalogo" element={<p>Pantalla de catálogo</p>} />
            <Route path="descuentos/*" element={<DescuentosArea />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function montarArea(cliente: ReturnType<typeof queryClientConYo>, ruta: string) {
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/descuentos/*" element={<DescuentosArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function llamadasA(prefijo: string): unknown[] {
  return apiFetchMock.mock.calls.filter(([ruta]) => String(ruta).startsWith(prefijo))
}

beforeEach(() => {
  apiFetchMock.mockReset()
  enrutar(apiFetchMock, [
    { metodo: 'GET', ruta: '/descuentos/reglas', responder: () => ({ status: 200, cuerpo: { items: [], siguiente_cursor: null } }) },
    { metodo: 'GET', ruta: '/identidad/roles', responder: () => ({ status: 200, cuerpo: [] }) },
  ])
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('menú de /admin: sección "Descuentos" (15.1)', () => {
  it('está declarada en /admin/descuentos y se ofrece con GESTIONAR_DESCUENTOS', () => {
    expect(SECCIONES.find((s) => s.ruta === '/admin/descuentos')?.etiqueta).toBe('Descuentos')
    expect(seccionesPermitidas((p) => p === 'GESTIONAR_DESCUENTOS').map((s) => s.etiqueta)).toContain('Descuentos')
    expect(seccionesPermitidas((p) => p === 'ADMIN_USUARIOS').map((s) => s.etiqueta)).not.toContain('Descuentos')
  })

  it('Escenario Administrador: ve "Descuentos" en el menú', async () => {
    montarMenu(clienteConPermisos('ADM'))

    expect(await screen.findByRole('link', { name: 'Descuentos' })).toBeInTheDocument()
  })

  it.each([
    ['GES', 'Administración'],
    ['SUP', 'Supervisor comercial'],
    ['VEN', 'Vendedor/Repartidor'],
    ['CON', 'Consulta/Dirección'],
  ] as const)('Escenario usuario sin permisos de descuentos: %s (%s) no ve "Descuentos"', async (rol) => {
    montarMenu(clienteConPermisos(rol))

    await screen.findByRole('navigation', { name: /navegación de administración/i })
    expect(screen.queryByRole('link', { name: 'Descuentos' })).not.toBeInTheDocument()
  })

  it('Escenario rol a medida: con solo GESTIONAR_DESCUENTOS ve "Descuentos"', async () => {
    montarMenu(clienteConPermisos('GES', ['GESTIONAR_DESCUENTOS']))

    expect(await screen.findByRole('link', { name: 'Descuentos' })).toBeInTheDocument()
  })
})

describe('área de descuentos: Reglas y Topes por rol (15.1)', () => {
  it('Escenario Administrador: /admin/descuentos ofrece "Reglas" y "Topes por rol"', async () => {
    montarArea(clienteConPermisos('ADM'), '/admin/descuentos')

    const navegacion = await screen.findByRole('navigation', { name: /descuentos/i })
    expect(navegacion).toHaveTextContent('Reglas')
    expect(screen.getByRole('link', { name: 'Reglas' })).toHaveAttribute('href', '/admin/descuentos')
    expect(screen.getByRole('link', { name: 'Topes por rol' })).toHaveAttribute('href', '/admin/descuentos/topes')
  })

  it('Escenario rol a medida con solo las reglas: ve "Reglas" y no "Topes por rol"', async () => {
    montarArea(clienteConPermisos('GES', ['GESTIONAR_DESCUENTOS']), '/admin/descuentos')

    expect(await screen.findByRole('link', { name: 'Reglas' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Topes por rol' })).not.toBeInTheDocument()
  })

  it('Escenario sin permisos de descuentos: la ruta directa avisa la falta de permiso y no pide datos', async () => {
    montarArea(clienteConPermisos('GES'), '/admin/descuentos')

    expect(await screen.findByText(AVISO_SIN_PERMISO)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Reglas' })).not.toBeInTheDocument()
    expect(llamadasA('/descuentos')).toHaveLength(0)
    expect(llamadasA('/identidad')).toHaveLength(0)
  })

  it('/admin/descuentos/topes sin ADMIN_USUARIOS avisa la falta de permiso y no pide los roles', async () => {
    montarArea(clienteConPermisos('GES', ['GESTIONAR_DESCUENTOS']), '/admin/descuentos/topes')

    expect(await screen.findByText(/no tenés permiso para definir los topes/i)).toBeInTheDocument()
    expect(llamadasA('/identidad')).toHaveLength(0)
  })

  it('un usuario con ADMIN_USUARIOS pero sin GESTIONAR_DESCUENTOS no ve las reglas (D18: la lectura exige GESTIONAR_DESCUENTOS)', async () => {
    montarArea(clienteConPermisos('GES', ['ADMIN_USUARIOS']), '/admin/descuentos')

    expect(await screen.findByText(AVISO_SIN_PERMISO)).toBeInTheDocument()
    expect(llamadasA('/descuentos')).toHaveLength(0)
  })
})
