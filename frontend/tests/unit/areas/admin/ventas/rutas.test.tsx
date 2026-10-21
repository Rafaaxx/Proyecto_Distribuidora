import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import VentasArea from '../../../../../src/areas/admin/ventas/VentasArea'
import { SECCIONES, seccionesPermitidas } from '../../../../../src/features/identidad/secciones'
import { PERMISOS_POR_ROL, queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { VENTA_ID, montarApi } from './ventasDePrueba'

function renderEn(ruta: string, rol: RolDePrueba = 'SUP', permisos?: string[]) {
  const cliente = permisos ? queryClientConYo(rol, { permisos } as never) : queryClientConYo(rol)
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/ventas/*" element={<VentasArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('rutas de ventas en /admin (change 18a, tarea 12.2)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: '/ventas', responder: () => ({ status: 200, cuerpo: { items: [], cursor_siguiente: null } }) },
      {
        metodo: 'GET',
        ruta: `/ventas/${VENTA_ID}`,
        responder: () => ({ status: 404, cuerpo: { title: 'No existe', codigo: 'RECURSO_NO_ENCONTRADO' } }),
      },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['/admin/ventas', /todav[ií]a no hay ventas/i],
    ['/admin/ventas/nueva', /confirmar venta/i],
    [`/admin/ventas/${VENTA_ID}`, /no se encontr[oó] la venta/i],
  ])('%s se resuelve a su pantalla (nueva se declara antes que :ventaId)', async (ruta, texto) => {
    renderEn(ruta)

    expect(await screen.findAllByText(texto)).not.toHaveLength(0)
  })

  // Escenario: "Sin permiso"
  it('un usuario de Consulta no ve el listado, el detalle ni "Nueva venta": ve el aviso de falta de permiso (SEG-06, ADR-027)', async () => {
    const usuario = renderEn('/admin/ventas', 'CON')
    expect(await screen.findByText(/no ten[eé]s permiso para ver las ventas/i)).toBeInTheDocument()
    usuario.unmount()

    const detalle = renderEn(`/admin/ventas/${VENTA_ID}`, 'CON')
    expect(await screen.findByText(/no ten[eé]s permiso para ver las ventas/i)).toBeInTheDocument()
    detalle.unmount()

    renderEn('/admin/ventas/nueva', 'CON')
    expect(await screen.findByText(/no ten[eé]s permiso para vender/i)).toBeInTheDocument()
  })

  it('con solo ANULAR_VENTA se ve el listado pero "Nueva venta" muestra la falta de permiso', async () => {
    renderEn('/admin/ventas/nueva', 'GES')

    expect(await screen.findByText(/no ten[eé]s permiso para vender/i)).toBeInTheDocument()
  })
})

describe('entrada de menú "Ventas" por permiso (D19, D21)', () => {
  const ve = (rol: RolDePrueba) =>
    seccionesPermitidas((permiso) => PERMISOS_POR_ROL[rol].includes(permiso)).some((s) => s.etiqueta === 'Ventas')
  const seccionesCon = (permiso: string) => seccionesPermitidas((p) => p === permiso).map((s) => s.etiqueta)

  it('está declarada y la ve quien tiene VENDER o ANULAR_VENTA', () => {
    expect(SECCIONES.some((s) => s.ruta === '/admin/ventas')).toBe(true)
    for (const rol of ['ADM', 'GES', 'SUP', 'VEN', 'CON'] as const) {
      const tiene = PERMISOS_POR_ROL[rol].some((p) => p === 'VENDER' || p === 'ANULAR_VENTA')
      expect([rol, ve(rol)]).toEqual([rol, tiene])
    }
  })

  it('el Vendedor y Administración la ven; Consulta no', () => {
    expect(ve('VEN')).toBe(true)
    expect(ve('GES')).toBe(true)
    expect(ve('CON')).toBe(false)
  })

  it('con solo VENDER o solo ANULAR_VENTA también la ve; con otro permiso no', () => {
    expect(seccionesCon('VENDER')).toContain('Ventas')
    expect(seccionesCon('ANULAR_VENTA')).toContain('Ventas')
    expect(seccionesCon('GESTIONAR_CLIENTES')).not.toContain('Ventas')
  })

  it('queda a continuación de Clientes y antes de Cobranzas', () => {
    const etiquetas = SECCIONES.map((s) => s.etiqueta)

    expect(etiquetas.indexOf('Ventas')).toBe(etiquetas.indexOf('Clientes') + 1)
    expect(etiquetas.indexOf('Cobranzas')).toBe(etiquetas.indexOf('Ventas') + 1)
  })
})
