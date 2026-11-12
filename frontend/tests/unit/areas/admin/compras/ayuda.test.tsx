/**
 * Change 16b, tarea 5.2: ayuda contextual en compras (spec `ayuda-contextual`, requisito "Las
 * pantallas de compras y costos explican sus reglas"; CST-02, CST-06, CST-11, CMP-04; ADR-051).
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CompraFormScreen } from '../../../../../src/areas/admin/compras/CompraFormScreen'
import { CompraResultado } from '../../../../../src/areas/admin/compras/CompraResultado'
import type { FormularioDeCompra } from '../../../../../src/domain/compras/formularioCompra'
import { enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { CAJA_X12_ID, CERVEZA_B_ID, COMPRA_ID, PROVEEDOR_ID, UBICACION_ID, montarApi, reglaFiscal } from './comprasDePrueba'

function montarFormulario() {
  return render(
    <QueryClientProvider client={queryClientConYo('GES')}>
      <MemoryRouter initialEntries={['/admin/compras/nueva']}>
        <Routes>
          <Route path="/admin/compras/nueva" element={<CompraFormScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function ayuda(titulo: string) {
  return screen.getByRole('button', { name: `Ayuda: ${titulo}` })
}

beforeEach(() => {
  apiFetchMock.mockReset()
})
afterEach(() => {
  vi.clearAllMocks()
})

describe('ayuda en el formulario de compra', () => {
  it('un responsable inscripto ve el "(?)" de "Valor" con el ejemplo de $1.239,67 y no el de "Valor pagado"', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    montarFormulario()
    await screen.findByLabelText(/^valor$/i)

    await usuario.click(ayuda('Valor'))

    expect(screen.getByText(/\$18\.000 \/ 1,21 \/ 12 = unos \$1\.239,67 por botella/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Ayuda: Valor pagado' })).not.toBeInTheDocument()
  })

  it('un monotributista ve el "(?)" de "Valor pagado" con el ejemplo de $1.815', async () => {
    montarApi(apiFetchMock, [reglaFiscal('MONOTRIBUTO')])
    const usuario = userEvent.setup()
    montarFormulario()
    await screen.findByLabelText(/^valor pagado$/i)

    await usuario.click(ayuda('Valor pagado'))

    expect(screen.getByText(/\$21\.780 \/ 12 = \$1\.815 por botella/)).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Ayuda: Valor' })).not.toBeInTheDocument()
  })

  it('"Bonificación", "Costo base" y "Total de factura" tienen su "(?)"', async () => {
    montarApi(apiFetchMock)
    const usuario = userEvent.setup()
    montarFormulario()
    await screen.findByLabelText(/^valor$/i)

    await usuario.click(ayuda('Bonificación'))
    expect(screen.getByText(/\$16\.200, o sea \$1\.350 por botella/)).toBeVisible()

    await usuario.click(ayuda('Costo base'))
    expect(screen.getByText(/\$18\.000 sin IVA → \$1\.500 por botella/)).toBeVisible()

    await usuario.click(ayuda('Total de factura'))
    expect(screen.getByText(/Este total es lo que le debés al proveedor/)).toBeVisible()
  })
})

const FORMULARIO: FormularioDeCompra = {
  proveedorId: PROVEEDOR_ID,
  fecha: '2026-05-10',
  ubicacionId: UBICACION_ID,
  condicion: 'CREDITO',
  numeroComprobante: '',
  observacion: '',
  lineas: [
    { productoId: CERVEZA_B_ID, presentacionId: CAJA_X12_ID, cantidad: '1', valor: '18000.00', incluyeIva: true, bonificacionPorcentaje: '10' },
  ],
  medios: [],
}

describe('ayuda en el resultado de la compra', () => {
  function montarResultado(diferencias: unknown[]) {
    enrutar(apiFetchMock, [])
    return render(
      <QueryClientProvider client={queryClientConYo('GES')}>
        <MemoryRouter>
          <CompraResultado
            resultado={
              { compra_id: COMPRA_ID, total_neto: '14876.03', total_factura: '18000.00', pago_id: null, diferencias_de_costo: diferencias } as never
            }
            computaCreditoFiscal
            formulario={FORMULARIO}
            nombresDeProductos={{ [CERVEZA_B_ID]: 'Cerveza B' }}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('junto a "Registrar como costo informado" explica el promedio de $1.050', async () => {
    const usuario = userEvent.setup()
    montarResultado([
      { linea: 0, producto_id: CERVEZA_B_ID, costo_base_compra: '1350.000000', costo_base_vigente: '1200.000000' },
    ])

    await usuario.click(ayuda('Costo promedio y costo informado'))

    expect(screen.getByText(/el promedio queda en \$1\.050/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Registrar como costo informado' })).toBeInTheDocument()
  })

  it('sin diferencias de costo no hay "(?)" (no hay nada que registrar)', () => {
    montarResultado([])

    expect(screen.queryByRole('button', { name: /^ayuda:/i })).not.toBeInTheDocument()
  })
})
