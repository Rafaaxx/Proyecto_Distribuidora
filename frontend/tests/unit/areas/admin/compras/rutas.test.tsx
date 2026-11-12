import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ComprasArea from '../../../../../src/areas/admin/compras/ComprasArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { COMPRA_ID, montarApi } from './comprasDePrueba'

function renderEn(ruta: string, rol: RolDePrueba = 'GES', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/compras/*" element={<ComprasArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('rutas de compras en /admin (change 11)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/compras', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      { metodo: 'GET', ruta: `/compras/${COMPRA_ID}`, responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['/admin/compras', /todav[ií]a no hay compras/i],
    ['/admin/compras/nueva', /confirmar compra/i],
    [`/admin/compras/${COMPRA_ID}`, /no se encontr[oó] la compra/i],
  ])('%s se resuelve a su pantalla', async (ruta, texto) => {
    renderEn(ruta)

    expect(await screen.findByText(texto)).toBeInTheDocument()
  })

  it('con solo ANULAR_COMPRA, /admin/compras/nueva muestra la falta de permiso', async () => {
    renderEn('/admin/compras/nueva', 'GES', ['ANULAR_COMPRA'])

    expect(await screen.findByText(/no ten[eé]s permiso para registrar compras/i)).toBeInTheDocument()
  })

  it('sin permisos de compra, /admin/compras muestra la falta de permiso', async () => {
    renderEn('/admin/compras', 'VEN')

    expect(await screen.findByText(/no ten[eé]s permiso para ver las compras/i)).toBeInTheDocument()
  })
})

describe('entrada de menú "Compras" por rol', () => {
  const ve = (rol: RolDePrueba) =>
    seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Compras')

  it('está declarada y la ven Administrador y Administración, no Supervisor, Vendedor ni Consulta', () => {
    expect(SECCIONES.some((s) => s.ruta === '/admin/compras')).toBe(true)
    expect((['ADM', 'GES', 'SUP', 'VEN', 'CON'] as const).map(ve)).toEqual([true, true, false, false, false])
  })
})
