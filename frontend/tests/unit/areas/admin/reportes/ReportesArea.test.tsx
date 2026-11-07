import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ReportesArea } from '../../../../../src/areas/admin/reportes/ReportesArea'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { reporteDeVentas } from './reporteDePrueba'

/**
 * Change 26, tarea 10.1 (spec `reportes/area-de-reportes`, «La sección «Reportes» de `/admin»; D8 = B, D11; cita
 * 01 §19, ADR-027, SEG-06): las seis pestañas, la de saldos de proveedores solo con la regla compuesta, y sin
 * `VER_REPORTES` ninguna pantalla pide datos.
 */
function montar(rol: RolDePrueba, ruta = '/admin/reportes') {
  apiFetchMock.mockImplementation(() =>
    Promise.resolve({ ok: true, status: 200, json: async () => reporteDeVentas(rol === 'CON') }),
  )
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/reportes/*" element={<ReportesArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const pestanas = () =>
  within(screen.getByRole('navigation', { name: 'Pestañas de reportes' }))
    .getAllByRole('link')
    .map((enlace) => enlace.textContent)

describe('ReportesArea: pestañas por permiso (D8 = B, D11)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('Consulta/Dirección ve las seis pestañas, con «Saldos de proveedores»', async () => {
    montar('CON')

    expect(await screen.findByRole('heading', { name: 'Reportes' })).toBeInTheDocument()
    expect(pestanas()).toEqual([
      'Ventas',
      'Rendiciones',
      'Saldos de clientes',
      'Saldos de proveedores',
      'Observaciones por vendedor',
      'Ajustes por motivo',
    ])
  })

  it('el Supervisor ve cinco: sin «Saldos de proveedores» (SEG-06)', async () => {
    montar('SUP')

    expect(await screen.findByRole('heading', { name: 'Reportes' })).toBeInTheDocument()
    expect(pestanas()).toEqual([
      'Ventas',
      'Rendiciones',
      'Saldos de clientes',
      'Observaciones por vendedor',
      'Ajustes por motivo',
    ])
  })

  it('Gestión (con GESTIONAR_PROVEEDORES) también ve «Saldos de proveedores»', async () => {
    montar('GES')

    await screen.findByRole('heading', { name: 'Reportes' })
    expect(pestanas()).toContain('Saldos de proveedores')
  })

  it('«Ventas» es la pestaña de entrada y pide el reporte del mes en curso', async () => {
    montar('CON')

    expect(await screen.findByRole('table', { name: 'Por día' })).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledWith('/reportes/ventas')
  })
})

describe('ReportesArea: entrada por URL sin la regla (SEG-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('el Supervisor que entra a /saldos-proveedores no ve esa pestaña y vuelve a «Ventas»', async () => {
    montar('SUP', '/admin/reportes/saldos-proveedores')

    expect(await screen.findByRole('table', { name: 'Por día' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Saldos de proveedores' })).not.toBeInTheDocument()
  })

  it('el Vendedor, sin VER_REPORTES, no ve pestañas ni pide ningún dato', async () => {
    montar('VEN')

    expect(await screen.findByRole('heading', { name: 'Reportes' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Pestañas de reportes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
