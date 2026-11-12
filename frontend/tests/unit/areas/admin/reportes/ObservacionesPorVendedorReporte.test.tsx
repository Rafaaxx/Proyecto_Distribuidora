import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { ObservacionesPorVendedorReporte } from '../../../../../src/areas/admin/reportes/ObservacionesPorVendedorReporte'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { reporteDeObservaciones } from './otrosReportesDePrueba'

/**
 * Change 26, tarea 12.2 (spec `reportes/observaciones-por-vendedor`, «La pestaña…», su escenario; D9, D12; cita
 * SYN-07, SYN-06, ADR-069): una fila por vendedor y «Ver en Revisión» solo con `REVISAR_OBSERVACIONES`.
 */
function montar(rol: RolDePrueba, reporte: unknown = reporteDeObservaciones()) {
  enrutar(apiFetchMock, [{ ruta: '/reportes/observaciones', responder: () => ({ status: 200, cuerpo: reporte }) }])
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <ObservacionesPorVendedorReporte />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ObservacionesPorVendedorReporte (SYN-07, SYN-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('una fila por vendedor con ventas sin conexión, avisos, rechazadas y excesos, cada uno con sus pendientes', async () => {
    montar('SUP')

    const tabla = await screen.findByRole('table', { name: 'Observaciones por vendedor' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Vendedor',
      'Ventas sin conexión',
      'Avisos',
      'Rechazadas',
      'Excesos de crédito detectados',
      '',
    ])
    expect(within(tabla).getAllByRole('row')).toHaveLength(3)
    const uno = within(tabla).getByRole('row', { name: /Vendedor Uno/ })
    const celdas = within(uno).getAllByRole('cell')
    expect(celdas[1]).toHaveTextContent('3')
    expect(celdas[2]).toHaveTextContent('3')
    expect(celdas[2]).toHaveTextContent('Pendientes: 2')
    expect(celdas[3]).toHaveTextContent('1')
    expect(celdas[3]).toHaveTextContent('Pendientes: 1')
    expect(celdas[4]).toHaveTextContent('Pendientes: 1')
    const dos = within(within(tabla).getByRole('row', { name: /Vendedor Dos/ })).getAllByRole('cell')
    expect(dos[1]).toHaveTextContent('1')
    expect(dos[2]).toHaveTextContent('Pendientes: 0')
  })

  it('«Ver en Revisión» solo con REVISAR_OBSERVACIONES, a la bandeja filtrada por ese vendedor', async () => {
    montar('SUP')

    const tabla = await screen.findByRole('table', { name: 'Observaciones por vendedor' })
    const enlaces = within(tabla).getAllByRole('link', { name: 'Ver en Revisión' })
    expect(enlaces).toHaveLength(2)
    expect(enlaces[0]).toHaveAttribute('href', '/admin/revision?usuario=v1')
    expect(enlaces[1]).toHaveAttribute('href', '/admin/revision?usuario=v2')
  })

  it('Consulta/Dirección, sin REVISAR_OBSERVACIONES, ve las cifras pero no el enlace', async () => {
    montar('CON')

    await screen.findByRole('table', { name: 'Observaciones por vendedor' })
    expect(screen.queryByRole('link', { name: 'Ver en Revisión' })).not.toBeInTheDocument()
  })

  it('sin operaciones sin conexión en el período muestra el texto aprobado', async () => {
    montar('SUP', reporteDeObservaciones({ vendedores: [] }))

    expect(await screen.findByText('Sin operaciones sin conexión en el período.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Observaciones por vendedor' })).not.toBeInTheDocument()
  })

  it('abre con el período del servidor, lo manda al cambiarlo y ofrece sus dos ayudas', async () => {
    const usuario = userEvent.setup()
    montar('SUP')

    expect(await screen.findByText('Período: 01/11/2026 al 06/11/2026')).toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'GET', '/reportes/observaciones')[0]?.url.search).toBe('')
    expect(screen.getByRole('button', { name: 'Ayuda: Observaciones por vendedor' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Período' })).toBeInTheDocument()

    await usuario.clear(screen.getByLabelText('Desde'))
    await usuario.type(screen.getByLabelText('Desde'), '2026-10-01')

    await waitFor(() => {
      const busquedas = llamadas(apiFetchMock, 'GET', '/reportes/observaciones').map((l) => l.url.search)
      expect(busquedas).toContain('?desde=2026-10-01&hasta=2026-11-06')
    })
  })

  it('un período demasiado largo muestra el texto aprobado', async () => {
    enrutar(apiFetchMock, [
      {
        ruta: '/reportes/observaciones',
        responder: () => ({ status: 422, cuerpo: { title: 'x', codigo: 'PERIODO_DEMASIADO_LARGO' } }),
      },
    ])
    render(
      <QueryClientProvider client={queryClientConYo('SUP')}>
        <MemoryRouter>
          <ObservacionesPorVendedorReporte />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('El período no puede superar los 366 días.')).toBeInTheDocument()
  })
})
