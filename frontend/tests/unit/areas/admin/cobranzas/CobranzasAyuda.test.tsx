import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CobranzaDetalleScreen } from '../../../../../src/areas/admin/cobranzas/CobranzaDetalleScreen'
import { CobranzaFormScreen } from '../../../../../src/areas/admin/cobranzas/CobranzaFormScreen'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { CLIENTE_ID, COBRANZA_ID, cobranzaDetalle, montarApi } from './cobranzasDePrueba'

/**
 * Los "(?)" de las pantallas de cobranzas (change 17, tarea 15.1; spec `ayuda-contextual`,
 * requisito "Las pantallas de cobranzas explican sus reglas"; `design.md` D20, variante 5b).
 */

function render_(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('GES')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/cobranzas/nuevo" element={<CobranzaFormScreen />} />
          <Route path="/admin/cobranzas/:cobranzaId" element={<CobranzaDetalleScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ayuda contextual de cobranzas', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    montarApi(apiFetchMock, [
      {
        metodo: 'GET',
        ruta: `/cobranzas/${COBRANZA_ID}`,
        responder: () => ({
          status: 200,
          cuerpo: cobranzaDetalle({
            observaciones: [{ codigo: 'PERMISO_REVOCADO', estado: 'PENDIENTE', detalle: { motivo: 'PERMISO_QUITADO' } }],
          }),
        }),
      },
    ])
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('el alta ofrece "(?)" en medios de pago, en el saldo resultante y en jornada', async () => {
    const usuario = userEvent.setup()
    render_(`/admin/cobranzas/nuevo?cliente=${CLIENTE_ID}`)

    expect(await screen.findByRole('button', { name: 'Ayuda: Medios de pago' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ayuda: Jornada' })).toBeInTheDocument()
    await usuario.click(await screen.findByRole('button', { name: 'Ayuda: Saldo después de la cobranza' }))

    expect(screen.getByText(/debe \$150\.000 y paga \$160\.000/)).toBeInTheDocument()
    expect(screen.getByText(/baja lo que debe en total/i)).toBeInTheDocument()
  })

  it('el "(?)" de medios explica el reparto con el ejemplo de $50.000', async () => {
    const usuario = userEvent.setup()
    render_('/admin/cobranzas/nuevo')

    await usuario.click(await screen.findByRole('button', { name: 'Ayuda: Medios de pago' }))

    expect(screen.getByText(/podés repartir el total entre varios medios/i)).toBeInTheDocument()
    expect(screen.getByText(/\$30\.000 en efectivo y \$20\.000 por transferencia/)).toBeInTheDocument()
  })

  it('el detalle ofrece "(?)" en jornada, junto a "Anular cobranza" y en las observaciones', async () => {
    const usuario = userEvent.setup()
    render_(`/admin/cobranzas/${COBRANZA_ID}`)

    expect(await screen.findByRole('button', { name: 'Ayuda: Jornada' })).toBeInTheDocument()
    await usuario.click(screen.getByRole('button', { name: 'Ayuda: Anular una cobranza' }))
    expect(screen.getByText(/el cliente vuelve a deber lo mismo que antes/i)).toBeInTheDocument()
  })

  // Escenario: "Observaciones de una cobranza sin señal"
  it('el "(?)" de las observaciones queda corto y lleva a "Ver más" (tema cobranzas-observaciones)', async () => {
    const usuario = userEvent.setup()
    render_(`/admin/cobranzas/${COBRANZA_ID}`)

    await usuario.click(await screen.findByRole('button', { name: 'Ayuda: Avisos de una cobranza sin señal' }))

    expect(screen.getByText(/porque la plata ya se cobró/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver más' })).toHaveAttribute('href', '/admin/ayuda/cobranzas-observaciones')
  })
})
