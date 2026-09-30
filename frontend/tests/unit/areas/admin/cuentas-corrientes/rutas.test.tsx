import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }))
vi.mock('../../../../../src/lib/api/httpClient', () => ({ apiFetch: apiFetchMock }))

import ClientesArea from '../../../../../src/areas/admin/clientes/ClientesArea'
import ProveedoresArea from '../../../../../src/areas/admin/proveedores/ProveedoresArea'
import { queryClientConYo } from '../../../utils/permisosDePrueba'

const ID = '11111111-1111-4111-8111-111111111111'

function respuesta(status: number, cuerpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => cuerpo }
}

function renderEn(ruta: string) {
  return render(
    <QueryClientProvider client={queryClientConYo('ADM')}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route path="/admin/clientes/*" element={<ClientesArea />} />
          <Route path="/admin/proveedores/*" element={<ProveedoresArea />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Change 08, tareas 7.3 y 7.4: las rutas de la cuenta corriente cuelgan de
 * las áreas de clientes y de proveedores, sin sección nueva en el menú (D13). */
describe('rutas de la cuenta corriente en /admin (change 08)', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    apiFetchMock.mockResolvedValue(
      respuesta(200, {
        saldo_anterior: '0.00',
        saldo_actual: '150000.00',
        zona_horaria: 'America/Argentina/Mendoza',
        items: [],
        cursor_siguiente: null,
      }),
    )
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['clientes', 'Nos debe $ 150.000,00'],
    ['proveedores', 'Le debemos $ 150.000,00'],
  ])('/admin/%s/:id/cuenta-corriente muestra el estado de cuenta', async (coleccion, saldo) => {
    renderEn(`/admin/${coleccion}/${ID}/cuenta-corriente`)

    expect(await screen.findByText(saldo)).toBeInTheDocument()
    expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining(`/${coleccion}/${ID}/cuenta-corriente`))
  })

  it.each(['clientes', 'proveedores'])('/admin/%s/:id/cuenta-corriente/saldo-inicial muestra el formulario', async (coleccion) => {
    renderEn(`/admin/${coleccion}/${ID}/cuenta-corriente/saldo-inicial`)

    expect(await screen.findByLabelText('Importe')).toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalled()
  })
})
