import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { AjustesPorMotivoReporte } from '../../../../../src/areas/admin/reportes/AjustesPorMotivoReporte'
import { enrutar, llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { reporteDeAjustes } from './otrosReportesDePrueba'

/**
 * Change 26, tarea 12.3 (spec `reportes/ajustes-por-motivo`, «La pestaña…», su escenario; D10, D12; cita STK-03,
 * RUT-06): una fila por motivo con su detalle por producto, «Diferencias de rendición», la nota de anulados y los
 * valores solo con `VER_COSTOS`.
 */
function montar(rol: RolDePrueba, reporte: unknown) {
  enrutar(apiFetchMock, [{ ruta: '/reportes/ajustes', responder: () => ({ status: 200, cuerpo: reporte }) }])
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <AjustesPorMotivoReporte />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AjustesPorMotivoReporte con VER_COSTOS (STK-03, RUT-06)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('una fila por motivo con ajustes, entradas, salidas y el valor de cada sentido', async () => {
    montar('GES', reporteDeAjustes(true))

    const tabla = await screen.findByRole('table', { name: 'Ajustes por motivo' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Motivo',
      'Ajustes',
      'Entradas',
      'Salidas',
      'Valor de las entradas',
      'Valor de las salidas',
      'Sin costo',
    ])
    const rotura = within(tabla).getByRole('row', { name: /Rotura/ })
    const celdas = within(rotura).getAllByRole('cell')
    expect(celdas[1]).toHaveTextContent('2')
    expect(celdas[3]).toHaveTextContent('9')
    expect(celdas[5]).toHaveTextContent('4.500,00')
  })

  it('la fila «Diferencias de rendición» va aparte, con las mismas columnas y sin cantidad de ajustes', async () => {
    montar('GES', reporteDeAjustes(true))

    const tabla = await screen.findByRole('table', { name: 'Ajustes por motivo' })
    const celdas = within(within(tabla).getByRole('row', { name: /Diferencias de rendición/ })).getAllByRole('cell')
    expect(celdas[1]?.textContent).toBe('')
    expect(celdas[2]).toHaveTextContent('1')
    expect(celdas[3]).toHaveTextContent('2')
    expect(celdas[4]).toHaveTextContent('100,00')
    expect(celdas[5]).toHaveTextContent('250,00')
  })

  it('el motivo se despliega con el detalle por producto (D10)', async () => {
    const usuario = userEvent.setup()
    montar('GES', reporteDeAjustes(true))

    const tabla = await screen.findByRole('table', { name: 'Ajustes por motivo' })
    expect(screen.queryByRole('table', { name: 'Rotura' })).not.toBeInTheDocument()
    await usuario.click(within(tabla).getByRole('button', { name: 'Rotura' }))

    expect(within(tabla).getByRole('button', { name: 'Rotura' })).toHaveAttribute('aria-expanded', 'true')
    const detalle = screen.getByRole('table', { name: 'Rotura' })
    expect(within(detalle).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Código',
      'Producto',
      'Entradas',
      'Salidas',
      'Valor de las entradas',
      'Valor de las salidas',
      'Sin costo',
    ])
    expect(within(detalle).getByRole('row', { name: /VIN-001/ })).toHaveTextContent('4.500,00')
    await usuario.click(within(tabla).getByRole('button', { name: 'Rotura' }))
    expect(screen.queryByRole('table', { name: 'Rotura' })).not.toBeInTheDocument()
  })

  it('muestra la nota de ajustes anulados con la cantidad y la ayuda del reporte', async () => {
    montar('GES', reporteDeAjustes(true))

    expect(await screen.findByText('Ajustes anulados: 1. No entran en los totales.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Ajustes por motivo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Período' })).toBeInTheDocument()
  })

  it('sin ajustes anulados no hay nota', async () => {
    montar('GES', reporteDeAjustes(true, { ajustes_anulados: 0 }))

    await screen.findByRole('table', { name: 'Ajustes por motivo' })
    expect(screen.queryByText(/Ajustes anulados/)).not.toBeInTheDocument()
  })

  it('el «Sin costo» de un motivo muestra las unidades que no tenían costo', async () => {
    const reporte = reporteDeAjustes(true)
    reporte.motivos[0] = { ...reporte.motivos[0], unidades_sin_costo: 4 } as (typeof reporte.motivos)[number]
    montar('GES', reporte)

    const tabla = await screen.findByRole('table', { name: 'Ajustes por motivo' })
    expect(within(within(tabla).getByRole('row', { name: /Rotura/ })).getAllByRole('cell')[6]).toHaveTextContent('4')
  })
})

describe('AjustesPorMotivoReporte sin VER_COSTOS y vacío', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('sin VER_COSTOS no hay columnas de valor ni de «Sin costo», pero sí las unidades', async () => {
    montar('SUP', reporteDeAjustes(false))

    const tabla = await screen.findByRole('table', { name: 'Ajustes por motivo' })
    expect(within(tabla).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Motivo',
      'Ajustes',
      'Entradas',
      'Salidas',
    ])
    expect(within(within(tabla).getByRole('row', { name: /Rotura/ })).getAllByRole('cell')[3]).toHaveTextContent('9')
    expect(screen.queryByText('4.500,00')).not.toBeInTheDocument()
  })

  it('un período sin ajustes ni diferencias muestra «Sin ajustes en el período.»', async () => {
    montar(
      'GES',
      reporteDeAjustes(true, {
        motivos: [],
        ajustes_anulados: 0,
        diferencias_de_rendicion: {
          entradas: 0,
          salidas: 0,
          valor_de_entradas: '0.00',
          valor_de_salidas: '0.00',
          unidades_sin_costo: 0,
          productos: [],
        },
      }),
    )

    expect(await screen.findByText('Sin ajustes en el período.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Ajustes por motivo' })).not.toBeInTheDocument()
  })

  it('manda el período elegido al servidor', async () => {
    const usuario = userEvent.setup()
    montar('GES', reporteDeAjustes(true))
    await screen.findByRole('table', { name: 'Ajustes por motivo' })
    expect(llamadas(apiFetchMock, 'GET', '/reportes/ajustes')[0]?.url.search).toBe('')

    await usuario.clear(screen.getByLabelText('Hasta'))
    await usuario.type(screen.getByLabelText('Hasta'), '2026-11-03')

    await waitFor(() => {
      const busquedas = llamadas(apiFetchMock, 'GET', '/reportes/ajustes').map((l) => l.url.search)
      expect(busquedas).toContain('?desde=2026-11-01&hasta=2026-11-03')
    })
  })
})
