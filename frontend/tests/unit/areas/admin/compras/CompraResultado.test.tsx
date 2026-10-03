import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CompraResultado } from '../../../../../src/areas/admin/compras/CompraResultado'
import type { FormularioDeCompra } from '../../../../../src/domain/compras/formularioCompra'
import { llamadas, enrutar } from '../../../utils/enrutarApi'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { CAJA_X12_ID, CERVEZA_B_ID, COMPRA_ID, PROVEEDOR_ID, UBICACION_ID } from './comprasDePrueba'

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

const NOMBRES = { [CERVEZA_B_ID]: 'Cerveza B' }

function resultado(diferencias: unknown[]) {
  return {
    compra_id: COMPRA_ID,
    total_neto: '14876.03',
    total_factura: '18000.00',
    pago_id: null,
    diferencias_de_costo: diferencias,
  }
}

const DIFERENCIA = {
  linea: 0,
  producto_id: CERVEZA_B_ID,
  costo_base_compra: '1350.000000',
  costo_base_vigente: '1200.000000',
}

function renderResultado(rol: RolDePrueba, diferencias: unknown[]) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter>
        <CompraResultado
          resultado={resultado(diferencias) as never}
          formulario={FORMULARIO}
          nombresDeProductos={NOMBRES}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CompraResultado (tarea 12.2, CMP-04, D7)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    enrutar(apiFetchMock, [
      { metodo: 'POST', ruta: '/costos', responder: () => ({ status: 201, cuerpo: { costos: [{ id: 'x', costo_base: '1350.000000' }] } }) },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('muestra la compra registrada con sus totales', () => {
    renderResultado('GES', [])

    expect(screen.getByRole('heading', { name: /compra registrada/i })).toBeInTheDocument()
    expect(screen.getByTestId('resultado-total-factura')).toHaveTextContent('18.000,00')
    expect(screen.getByRole('link', { name: /ver compra/i })).toHaveAttribute('href', `/admin/compras/${COMPRA_ID}`)
  })

  it('con EDITAR_COSTOS ofrece registrar el costo informado y envía COSTO_INFORMAR con la vigencia de la compra', async () => {
    const usuario = userEvent.setup()
    renderResultado('GES', [DIFERENCIA])

    expect(screen.getByText(/cerveza b/i)).toBeInTheDocument()
    expect(screen.getByText(/1\.350,000000/)).toBeInTheDocument()
    expect(screen.getByText(/1\.200,000000/)).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: /registrar como costo informado/i }))

    await waitFor(() => expect(llamadas(apiFetchMock, 'POST', '/costos')).toHaveLength(1))
    const llamada = llamadas(apiFetchMock, 'POST', '/costos')[0]
    expect(new Headers(llamada?.init.headers).get('Operation-Id')).toBeTruthy()
    expect(JSON.parse(String(llamada?.init.body))).toEqual({
      proveedor_id: PROVEEDOR_ID,
      costos: [
        {
          producto_id: CERVEZA_B_ID,
          presentacion_id: CAJA_X12_ID,
          valor: '18000.00',
          incluye_iva: true,
          bonificacion: '0.100000',
          vigencia_desde: '2026-05-10',
        },
      ],
    })
    expect(await screen.findByText(/costo informado registrado/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /registrar como costo informado/i })).not.toBeInTheDocument()
  })

  it('sin hacer nada no se envía ningún costo', () => {
    renderResultado('GES', [DIFERENCIA])

    expect(llamadas(apiFetchMock, 'POST', '/costos')).toHaveLength(0)
  })

  it('sin EDITAR_COSTOS no ofrece la acción (pero informa la diferencia no es necesaria)', () => {
    renderResultado('VEN', [DIFERENCIA])

    expect(screen.queryByRole('button', { name: /registrar como costo informado/i })).not.toBeInTheDocument()
    expect(llamadas(apiFetchMock, 'POST', '/costos')).toHaveLength(0)
  })

  it('un costo sin vigente previo se ofrece igual y dice que no había costo vigente', () => {
    renderResultado('GES', [{ ...DIFERENCIA, costo_base_vigente: null }])

    expect(screen.getByText(/sin costo vigente/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /registrar como costo informado/i })).toBeInTheDocument()
  })

  it('si el servidor rechaza el costo, muestra el error y deja reintentar', async () => {
    enrutar(apiFetchMock, [
      { metodo: 'POST', ruta: '/costos', responder: () => ({ status: 422, cuerpo: { title: 'Costo inválido.', codigo: 'COSTO_INVALIDO' } }) },
    ])
    const usuario = userEvent.setup()
    renderResultado('GES', [DIFERENCIA])

    await usuario.click(screen.getByRole('button', { name: /registrar como costo informado/i }))

    expect(await screen.findByText('Costo inválido.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /registrar como costo informado/i })).toBeEnabled()
  })
})
