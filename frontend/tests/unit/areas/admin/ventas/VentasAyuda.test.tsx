import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { VentaDetalleScreen } from '../../../../../src/areas/admin/ventas/VentaDetalleScreen'
import { VentaFormScreen } from '../../../../../src/areas/admin/ventas/VentaFormScreen'
import { queryClientConYo, type RolDePrueba } from '../../../utils/permisosDePrueba'
import { CLIENTE_ID, CONSUMIDOR_FINAL_ID, VENTA_ID, VINO_ID, montarApi, ventaDetalle } from './ventasDePrueba'

/**
 * Los "(?)" de las pantallas de venta (change 18a, tarea 13.1; spec `ayuda-contextual`, requisito
 * "Las pantallas de venta explican sus reglas"; `design.md` D22, textos aprobados el 2026-10-17).
 */

function pantalla(ruta: string, rol: RolDePrueba) {
  return render(
    <QueryClientProvider client={queryClientConYo(rol)}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/ventas/nueva" element={<VentaFormScreen />} />
          <Route path="/admin/ventas/:ventaId" element={<VentaDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

type Usuario = ReturnType<typeof userEvent.setup>

async function ventaConVinoA(usuario: Usuario, clienteId = CLIENTE_ID, nombre = 'Kiosco La Esquina') {
  await screen.findByRole('option', { name: nombre })
  await usuario.selectOptions(screen.getByLabelText(/^cliente$/i), clienteId)
  await screen.findByTestId('saldo-actual')
  await usuario.type(screen.getByLabelText(/buscar producto/i), 'vino')
  const resultado = await screen.findByTestId(`resultado-${VINO_ID}`)
  await usuario.click(within(resultado).getByRole('button', { name: /agregar vino a/i }))
  await screen.findByTestId(`item-${VINO_ID}`)
}

describe('ayuda contextual de ventas (tarea 13.1)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock)
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('el alta ofrece "(?)" en cajas y unidades, precio, stock, cobranza, medios y número', async () => {
    const usuario = userEvent.setup()
    pantalla('/admin/ventas/nueva', 'VEN')
    await ventaConVinoA(usuario)

    for (const nombre of ['Cajas y unidades', 'Precio', 'Stock', 'Cobranza en el acto', 'Medios de pago', 'Número de venta']) {
      expect(screen.getAllByRole('button', { name: `Ayuda: ${nombre}` }).length).toBeGreaterThan(0)
    }
  })

  it('el "(?)" de cajas y unidades explica el cobro en proporción con el ejemplo de $31.250', async () => {
    const usuario = userEvent.setup()
    pantalla('/admin/ventas/nueva', 'VEN')
    await ventaConVinoA(usuario)

    await usuario.click(screen.getAllByRole('button', { name: 'Ayuda: Cajas y unidades' })[0] as HTMLElement)

    expect(screen.getByText(/se cobra en proporción al precio de la caja/i)).toBeInTheDocument()
    expect(screen.getByText(/2 cajas \+ 3 botellas de Vino A/)).toBeInTheDocument()
  })

  it('el "(?)" del número explica de dónde sale y que no se repite', async () => {
    const usuario = userEvent.setup()
    pantalla('/admin/ventas/nueva', 'VEN')
    await ventaConVinoA(usuario)

    await usuario.click(screen.getByRole('button', { name: 'Ayuda: Número de venta' }))

    expect(screen.getByText(/las letras son de este dispositivo/i)).toBeInTheDocument()
    expect(screen.getByText(/V03-000142 es la venta 142 del teléfono V03/)).toBeInTheDocument()
  })

  // Escenario: "Otra lista o versión"
  it('el "(?)" de la lista anterior aparece para quien puede elegirla (PRC-21)', async () => {
    const usuario = userEvent.setup()
    pantalla('/admin/ventas/nueva', 'ADM')
    await ventaConVinoA(usuario)

    await usuario.click(await screen.findByRole('button', { name: 'Ayuda: Lista o versión anterior' }))

    expect(screen.getByText(/pide un motivo y queda registrado quién lo hizo/i)).toBeInTheDocument()
  })

  it('sin permiso para elegir otra lista no hay "(?)" de lista anterior', async () => {
    const usuario = userEvent.setup()
    pantalla('/admin/ventas/nueva', 'VEN')
    await ventaConVinoA(usuario)

    expect(screen.queryByRole('button', { name: 'Ayuda: Lista o versión anterior' })).not.toBeInTheDocument()
  })

  it('con el consumidor final aparece su "(?)"; con un cliente común no', async () => {
    const usuario = userEvent.setup()
    const primero = pantalla('/admin/ventas/nueva', 'VEN')
    await ventaConVinoA(usuario)
    expect(screen.queryByRole('button', { name: 'Ayuda: Consumidor final' })).not.toBeInTheDocument()
    primero.unmount()

    pantalla('/admin/ventas/nueva', 'VEN')
    await ventaConVinoA(usuario, CONSUMIDOR_FINAL_ID, 'Consumidor final')
    await usuario.click(screen.getByRole('button', { name: 'Ayuda: Consumidor final' }))

    expect(screen.getByText(/el pago tiene que ser igual al total/i)).toBeInTheDocument()
  })

  // Escenario: "Observaciones de una venta"
  it('el detalle ofrece "(?)" en el costo (con VER_COSTOS) y en las observaciones, con "Ver más"', async () => {
    const usuario = userEvent.setup()
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/ventas/${VENTA_ID}`,
        responder: () => ({
          status: 200,
          cuerpo: ventaDetalle({ observaciones: [{ codigo: 'JORNADA_LIBERADA', estado: 'PENDIENTE', detalle: null }] }),
        }),
      },
    ])
    pantalla(`/admin/ventas/${VENTA_ID}`, 'ADM')

    await usuario.click((await screen.findAllByRole('button', { name: 'Ayuda: Costo' }))[0] as HTMLElement)
    expect(screen.getByText(/al costo promedio del momento de la venta/i)).toBeInTheDocument()

    await usuario.click(await screen.findByRole('button', { name: 'Ayuda: Avisos de una venta' }))
    expect(screen.getByText(/la venta se tomó igual porque la mercadería ya se entregó/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver más' })).toHaveAttribute('href', '/admin/ayuda/ventas-observaciones')
  })

  it('sin VER_COSTOS el detalle no ofrece el "(?)" del costo', async () => {
    montarApi(apiFetchMock, [
      { metodo: 'GET', ruta: `/ventas/${VENTA_ID}`, responder: () => ({ status: 200, cuerpo: ventaDetalle() }) },
    ])
    pantalla(`/admin/ventas/${VENTA_ID}`, 'VEN')

    await screen.findByTestId('total-de-la-venta')
    expect(screen.queryByRole('button', { name: 'Ayuda: Costo' })).not.toBeInTheDocument()
  })
})
