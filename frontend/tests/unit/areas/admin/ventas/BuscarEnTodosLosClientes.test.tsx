/**
 * Change 20b, tarea 10.3 (D14; spec `clientes/cartera-de-clientes`, requisito "La cartera ordena lo
 * que se ofrece, no lo que se permite"; ADR-052, SYN-05, INV-17): en el selector de clientes para
 * vender y para cobrar, "Buscar en todos los clientes" pide todos aunque haya cartera asignada.
 */

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import { CobranzaFormScreen } from '../../../../../src/areas/admin/cobranzas/CobranzaFormScreen'
import { VentaFormScreen } from '../../../../../src/areas/admin/ventas/VentaFormScreen'
import { llamadas } from '../../../utils/enrutarApi'
import { queryClientConYo } from '../../../utils/permisosDePrueba'
import { montarApi as montarApiDeCobranzas } from '../cobranzas/cobranzasDePrueba'
import { montarApi as montarApiDeVentas } from './ventasDePrueba'

function pedidosDeOpciones() {
  return llamadas(apiFetchMock, 'GET', '/clientes/opciones')
}

describe('"Buscar en todos los clientes" (tarea 10.3, D14)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })
  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('al vender', () => {
    function montar() {
      montarApiDeVentas(apiFetchMock)
      return render(
        <QueryClientProvider client={queryClientConYo('VEN')}>
          <MemoryRouter initialEntries={['/admin/ventas/nueva']}>
            <Routes>
              <Route path="/admin/ventas/nueva" element={<VentaFormScreen />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      )
    }

    it('al principio pide solo lo que corresponde (sin alcance) y ofrece la casilla desmarcada', async () => {
      montar()

      const casilla = await screen.findByLabelText('Buscar en todos los clientes')
      expect(casilla).not.toBeChecked()
      await waitFor(() => expect(pedidosDeOpciones().length).toBeGreaterThan(0))
      expect(pedidosDeOpciones().every((p) => p.url.searchParams.get('alcance') === null)).toBe(true)
    })

    it('al marcarla vuelve a pedir con alcance=todos y conserva el consumidor final', async () => {
      const usuario = userEvent.setup()
      montar()

      await usuario.click(await screen.findByLabelText('Buscar en todos los clientes'))

      await waitFor(() => expect(pedidosDeOpciones().some((p) => p.url.searchParams.get('alcance') === 'todos')).toBe(true))
      const conAlcance = pedidosDeOpciones().find((p) => p.url.searchParams.get('alcance') === 'todos')!
      expect(conAlcance.url.searchParams.get('incluir_consumidor_final')).toBe('true')
    })

    it('al desmarcarla vuelve a pedir sin alcance', async () => {
      const usuario = userEvent.setup()
      montar()

      const casilla = await screen.findByLabelText('Buscar en todos los clientes')
      await usuario.click(casilla)
      await waitFor(() => expect(pedidosDeOpciones().some((p) => p.url.searchParams.get('alcance') === 'todos')).toBe(true))
      await usuario.click(casilla)

      await waitFor(() => expect(pedidosDeOpciones().at(-1)?.url.searchParams.get('alcance')).toBeNull())
    })

    it('muestra la ayuda de la cartera junto a la casilla', async () => {
      montar()

      await screen.findByLabelText('Buscar en todos los clientes')
      expect(screen.getByRole('button', { name: 'Ayuda: Vendedor del cliente' })).toBeInTheDocument()
    })
  })

  describe('al cobrar', () => {
    function montar() {
      montarApiDeCobranzas(apiFetchMock)
      return render(
        <QueryClientProvider client={queryClientConYo('VEN')}>
          <MemoryRouter initialEntries={['/admin/cobranzas/nuevo']}>
            <Routes>
              <Route path="/admin/cobranzas/nuevo" element={<CobranzaFormScreen />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      )
    }

    it('ofrece la casilla desmarcada y, al marcarla, pide con alcance=todos', async () => {
      const usuario = userEvent.setup()
      montar()

      const casilla = await screen.findByLabelText('Buscar en todos los clientes')
      expect(casilla).not.toBeChecked()
      expect(pedidosDeOpciones().every((p) => p.url.searchParams.get('alcance') === null)).toBe(true)
      await usuario.click(casilla)

      await waitFor(() => expect(pedidosDeOpciones().some((p) => p.url.searchParams.get('alcance') === 'todos')).toBe(true))
    })

    it('el consumidor final no se pide al cobrar, también con "todos"', async () => {
      const usuario = userEvent.setup()
      montar()

      await usuario.click(await screen.findByLabelText('Buscar en todos los clientes'))

      await waitFor(() => expect(pedidosDeOpciones().some((p) => p.url.searchParams.get('alcance') === 'todos')).toBe(true))
      const conAlcance = pedidosDeOpciones().find((p) => p.url.searchParams.get('alcance') === 'todos')!
      expect(conAlcance.url.searchParams.get('incluir_consumidor_final')).toBeNull()
    })
  })
})
